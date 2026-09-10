"""Aggregate the longer fixed-PPO-batch device and inference-batch sweep."""
from collections import defaultdict
import json
from pathlib import Path
from statistics import median

ROOT=Path(__file__).resolve().parent
rows=[json.loads(s) for s in (ROOT/'batching.jsonl').read_text().splitlines()]
assert len(rows)==27,len(rows)
groups=defaultdict(list)
for r in rows:
    cfg=r['config']
    assert cfg['num_envs']*cfg['rollout']==32768
    assert cfg['minibatches']==4
    assert r['measured_steps']==917504
    groups[r['workload'],cfg['num_envs'],cfg['device'],r['workers']].append(r)
summary=[]
for (workload,n,device,w),rs in sorted(groups.items()):
    speeds=[r['measured_sps'] for r in rs]
    hashes=sorted({r['final_model_sha256'] for r in rs})
    row={'workload':workload,'envs':n,'rollout':32768//n,'device':device,'workers':w,
         'repeats':len(rs),'median_sps':median(speeds),'min_sps':min(speeds),
         'max_sps':max(speeds),'final_model_hashes':hashes}
    summary.append(row)
    print(f'{workload:6} envs={n} rollout={32768//n} {device} workers={w}: '
          f'{median(speeds):,.0f}/s [{min(speeds):,.0f}, {max(speeds):,.0f}], hashes={len(hashes)}')
a=groups['mature',256,'mps',4]
b=groups['mature',256,'mps',8]
assert {r['final_model_sha256'] for r in a}=={r['final_model_sha256'] for r in b}
by_rep={r['repeat']:r for r in a}
worker_ratios=[r['measured_sps']/by_rep[r['repeat']]['measured_sps'] for r in b]
report={'runs':len(rows),'groups':summary,'paired_eight_vs_four_worker_speedups':worker_ratios,
        'median_eight_vs_four_worker_speedup':median(worker_ratios),
        'total_child_wall_seconds':sum(r['wall_seconds'] for r in rows),
        'caveat':'Changing num_envs and rollout changes trajectories and GAE boundaries even with fixed total batch. Device changes also produce different numerical/RNG trajectories. This is a throughput comparison, not a sample-efficiency or learning-quality claim.'}
(ROOT/'batching-summary.json').write_text(json.dumps(report,indent=2)+'\n')
print('8/4 workers, paired speedups:',worker_ratios)
