"""Summarize complete records; no training or simulator work is performed."""
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean, median

ROOT = Path(__file__).resolve().parent
rows = [json.loads(line) for line in (ROOT/'results.jsonl').read_text().splitlines()]
expected = 46
assert len(rows) == expected, (len(rows), expected)
groups = defaultdict(list)
for row in rows:
    assert row['measured_steps'] == 393216
    assert row['config']['progress_coef'] == 0
    groups[row['workload'],row['library'],row['workers'],row['profile']].append(row)
summary = []
for (workload,lib,workers,profile), group in sorted(groups.items()):
    speeds = [r['measured_sps'] for r in group]
    summary.append({'workload':workload,'library':lib,'workers':workers,'profile':profile,
                    'repeats':len(group),'median_sps':median(speeds),'min_sps':min(speeds),
                    'max_sps':max(speeds),'mean_seconds':mean(r['measured_seconds'] for r in group)})
    print(f'{workload:6} {lib:9} workers={workers} profile={profile}: '
          f'{median(speeds):,.0f}/s [{min(speeds):,.0f}, {max(speeds):,.0f}]')

# Repetitions share a seed: these are repeat timing measurements, not independent
# learning-seed experiments. Compare paired repeats for lighting effects.
lighting = []
for workload in ['mature','fresh']:
    for workers in [1,2,4,6,8]:
        ref = groups.get((workload,'reference',workers,False),[])
        cached = groups.get((workload,'cached',workers,False),[])
        if not ref or not cached:
            continue
        lookup = {r['repeat']:r for r in ref}
        ratios = [r['measured_sps']/lookup[r['repeat']]['measured_sps'] for r in cached]
        lighting.append({'workload':workload,'workers':workers,'paired_cache_speedups':ratios,
                         'median_cache_speedup':median(ratios)})

hashes = {}
for workload in ['mature','fresh']:
    hashes[workload] = sorted({r['final_model_sha256'] for r in rows if r['workload']==workload})
    print(workload,'distinct final model hashes:',len(hashes[workload]))

phases = {}
top = ['rollout_buffer','policy','step_and_action_retrieval',
       'transfers_bootstrap_bookkeeping','gae_and_flatten','ppo_updates','reporting']
for workload in ['mature','fresh']:
    profiled = groups[workload,'cached',4,True]
    wall = mean(r['measured_seconds'] for r in profiled)
    times = {k:mean(r['phases_seconds'][k] for r in profiled) for k in profiled[0]['phases_seconds']}
    baseline = groups[workload,'cached',4,False]
    normal = mean(r['measured_seconds'] for r in baseline)
    phases[workload] = {'mean_measured_seconds':wall,'unprofiled_mean_seconds':normal,
                        'instrumentation_wall_ratio':wall/normal,'seconds':times,
                        'fraction_of_profiled_wall':{k:v/wall for k,v in times.items()},
                        'top_level_coverage':sum(times[k] for k in top)/wall,
                        'top_level_labels':top,
                        'nested_labels':['native_step_inclusive','policy_forward_distribution',
                                         'policy_sampling_inclusive','policy_logprob_entropy_value']}
    print(workload,'profiling wall ratio:',round(wall/normal,3))
    for k in top:
        print(' ',k,round(100*times[k]/wall,1),'%')

report = {'runs':len(rows),'groups':summary,'lighting':lighting,'final_model_hashes':hashes,
          'phases':phases,'total_child_wall_seconds':sum(r['wall_seconds'] for r in rows)}
(ROOT/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
