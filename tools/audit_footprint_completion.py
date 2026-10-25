"""Reporting-only audit of saved footprint results; never evaluates a policy."""
import hashlib
import json
import statistics as st
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
STUDY = REPO / 'experiments/footprints-v45-complete-20261012.JabnGY'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def interval(values):
    mean = st.mean(values)
    delta = 2.7764451051977987 * st.stdev(values) / len(values) ** .5
    return {'per_seed': values, 'mean': mean, 'paired_t_95_interval': [mean-delta, mean+delta]}


def ratio(a, b):
    return a / b if b else None


def crafting_summary(d):
    h = d['gate_steps_before_first_furnace_stone_sufficient']
    n = sum(h)
    c = d['counters']
    return {
        'stone_sufficient_prefurnace_actions': n,
        'wood_missing_fraction': ratio(sum(x for i, x in enumerate(h) if not i & 1), n),
        'torch_missing_fraction': ratio(sum(x for i, x in enumerate(h) if not i & 4), n),
        'station_missing_fraction': ratio(sum(x for i, x in enumerate(h) if not i & 8), n),
        'wood_and_station_missing_fraction': ratio(sum(x for i, x in enumerate(h) if not i & 1 and not i & 8), n),
        'all_prerequisites_fraction': ratio(h[15], n),
        'opportunity_episodes': d['opportunity_episodes'],
        'bench_selected_when_owned_fraction': ratio(c.get('bench_selected_steps', 0), c.get('bench_owned_steps', 0)),
        'bench_has_space_when_owned_fraction': ratio(c.get('bench_owned_with_space_steps', 0), c.get('bench_owned_steps', 0)),
        'bench_exists_far_fraction': ratio(c.get('bench_exists_but_far_steps', 0), c['observed_actions']),
        'furnace_legal_actions': c.get('furnace_legal_steps', 0),
        'furnace_chosen_actions': c.get('furnace_chosen', 0),
        'mean_probability_when_legal': ratio(c.get('furnace_probability_sum', 0), c.get('furnace_legal_steps', 0)),
        'wood_acquired_per_episode': c.get('wood_acquired', 0) / d['episodes'],
        'wood_sinks_per_episode': {k: v/d['episodes'] for k, v in d['wood_consumed_by_action'].items()},
        'prefurnace_wood_sinks_per_episode': {k: v/d['episodes'] for k, v in d['wood_consumed_before_first_furnace'].items()},
        'bench_placements': c.get('bench_placements', 0),
        'bench_removals': c.get('bench_removals', 0),
    }


def main():
    p = read(STUDY/'study-protocol.json')
    plan = read(STUDY/'completion-plan.json')
    report = read(REPO/'docs/reports/FOOTPRINT_LEARNING_2026_10.json')
    old = Path(plan['original_study'])
    assert read(STUDY/'status.json')['stage'] == 'complete'
    assert sha(STUDY/'runner.py') == p['supervisor_sha256']
    assert sha(old/'runner.py') == plan['original_supervisor_sha256']
    assert sha(old/'study-protocol.json') == plan['original_protocol_sha256']
    assert sha(REPO/'docs/reports/FOOTPRINT_LEARNING_PARTIAL_2026_10.json') == plan['original_partial_report_sha256']
    op = read(old/'study-protocol.json')
    for key in op:
        if key not in ('study', 'supervisor_sha256'):
            assert p[key] == op[key], key
    source_count = {}
    for v, manifest in p['implementation_sha256'].items():
        assert manifest == op['implementation_sha256'][v]
        for rel, expected in manifest.items():
            assert sha(STUDY/'variants'/v/rel) == sha(old/'variants'/v/rel) == expected, (v, rel)
        source_count[v] = len(manifest)
    copied = {}
    for name, artifact in plan['reused_artifacts'].items():
        for rel, expected in artifact['artifact_sha256'].items():
            assert sha(STUDY/name/rel) == sha(Path(artifact['original'])/rel) == expected, (name, rel)
        copied[name] = len(artifact['artifact_sha256'])
    assert len(plan['completed_main_runs_reused']) == 15
    assert len(plan['interrupted_runs_restarted_from_scratch']) == 3
    assert len(plan['previously_unstarted_runs']) == 12
    expected_names = {f'main/{v}/{m}-{seed}' for v in ('v4','v5') for m in p['methods'] for seed in p['training_seeds']}
    assert set(plan['completed_main_runs_reused'] + plan['interrupted_runs_restarted_from_scratch'] + plan['previously_unstarted_runs']) == expected_names
    assert {str(x.parent.relative_to(STUDY)) for x in STUDY.glob('main/*/*/summary.json')} == expected_names
    evals, diagnostics, artifacts, runrows = {}, {}, {}, []
    for name in sorted(expected_names):
        d = STUDY/name
        v = name.split('/')[1]
        method, seed = name.split('/')[2].rsplit('-', 1)
        rp, summary, curve, diagnostic = (read(d/f) for f in ('protocol.json','summary.json','curve.json','crafting.json'))
        cfg = rp['config']
        assert summary['steps'] == rp['actual_steps'] == p['steps_per_run']
        assert [x['steps'] for x in curve] == [4194304,8388608,12582912,16777216]
        assert rp['environment_version'] == int(v[1:]) and cfg['seed'] == int(seed)
        assert rp['validation_seeds'] == p['validation_seeds'] and rp['reserved_test_seeds'] == p['reserved_test_seeds']
        assert rp['sampler_seed'] == p['sampler_seed'] and rp['torch_threads'] == 6
        assert not cfg.get('init') and not cfg['bootstrap_time_limit'] and cfg['progress_coef'] == cfg.get('curiosity_coef', 0) == 0
        assert not rp['demonstrations'] and not rp['prerequisite_shaping'] and rp['training_novelty'] is None
        for k, value in {'total_steps':16777216,'num_envs':64,'rollout':128,'epochs':4,'minibatches':4,'lr':.0003,'anneal_lr':True,'gamma':.999,'device':'cpu'}.items():
            assert cfg[k] == value, (name,k)
        assert cfg['architecture'] == p['methods'][method]['architecture']
        assert cfg['gae_lambda'] == p['methods'][method]['gae_lambda'] and cfg['ent_coef'] == p['methods'][method]['entropy']
        for rel, expected in rp['implementation_sha256'].items():
            assert sha(d/'implementation'/rel) == sha(Path(rp['package'])/rel) == expected
        for checkpoint in curve:
            assert sorted(x['seed'] for x in checkpoint['evaluation']['records']) == list(range(10000001,10000129))
        e = curve[-1]['evaluation']
        evals[name] = e
        assert diagnostic['checkpoint_sha256'] == sha(d/'step-16777216.pt')
        assert diagnostic['probe_sha256'] == sha(STUDY/f'probe-{v}.dylib')
        assert diagnostic['diagnostic_source_sha256'] == sha(STUDY/'variants'/v/'tools/crafting_diagnostics.py')
        assert diagnostic['environment_version'] == int(v[1:]) and diagnostic['seed_range'] == p['validation_seeds'] and diagnostic['sample_seed'] == p['sampler_seed']
        assert diagnostic['episodes'] == 128 and len(diagnostic['records']) == 128
        assert diagnostic['mean_achievements'] == e['mean_achievements']
        assert sorted(x['seed'] for x in diagnostic['records']) == list(range(10000001,10000129))
        for key in ('gate_steps','gate_steps_after_stone_sufficient','gate_steps_before_first_furnace','gate_steps_before_first_furnace_stone_sufficient'):
            assert diagnostic[key] == [sum(x[key][i] for x in diagnostic['records']) for i in range(16)]
        assert diagnostic['opportunity_episodes'] == sum(x['first_furnace_opportunity'] >= 0 for x in diagnostic['records'])
        diagnostics[name] = crafting_summary(diagnostic)
        artifacts[name] = {f.name:sha(f) for f in [d/'summary.json',d/'protocol.json',d/'curve.json',d/'crafting.json',*sorted(d.glob('step-*.pt'))]}
        runrows.append({'name':name,'score':e['mean_achievements'],'death':e['death_rate'],'furnace':e['hits'].get('craft furnace',0),'anvil':e['hits'].get('craft anvil',0)})
    assert sum(read(STUDY/name/'summary.json')['steps'] for name in expected_names) == report['main_transitions'] == 503316480
    comparisons = {}
    for m in p['methods']:
        pairs = [(evals[f'main/v4/{m}-{s}'],evals[f'main/v5/{m}-{s}']) for s in p['training_seeds']]
        comparisons[m] = {metric:interval([get(b)-get(a) for a,b in pairs]) for metric,get in {
            'score':lambda e:e['mean_achievements'],'death':lambda e:e['death_rate'],
            'furnace_rate':lambda e:e['hits'].get('craft furnace',0)/128,
            'anvil_rate':lambda e:e['hits'].get('craft anvil',0)/128}.items()}
        for metric in ('score','death'):
            assert comparisons[m][metric]['mean'] == report['paired_comparisons'][m][f'v5_minus_v4_{metric}']['mean']
        score_bounds = comparisons[m]['score']['paired_t_95_interval']
        death_bounds = comparisons[m]['death']['paired_t_95_interval']
        supported = score_bounds[0] >= -1 and death_bounds[1] <= .05
        negative = score_bounds[1] < -1 or death_bounds[0] > .05
        comparisons[m]['noninferiority_classification'] = 'supported' if supported else ('negative' if negative else 'inconclusive')
        assert supported == report['paired_comparisons'][m]['learning_noninferiority_supported']
    ranking = []
    for m in p['methods']:
        es = [evals[f'main/{v}/{m}-{s}'] for v in ('v4','v5') for s in p['training_seeds']]
        ranking.append({'method':m,'mean':st.mean(e['mean_achievements'] for e in es),'death_rate':st.mean(e['death_rate'] for e in es)})
    ranking.sort(key=lambda x:(-x['mean'],x['death_rate'],x['method']))
    m = ranking[0]['method']
    seedranking = []
    for s in p['training_seeds']:
        es = [evals[f'main/{v}/{m}-{s}'] for v in ('v4','v5')]
        seedranking.append({'seed':s,'mean':st.mean(e['mean_achievements'] for e in es),'death_rate':st.mean(e['death_rate'] for e in es)})
    seedranking.sort(key=lambda x:(-x['mean'],x['death_rate'],x['seed']))
    selection = read(STUDY/'selected/selection.json')
    assert selection['criterion'] == p['selection'] and selection['method_ranking'] == ranking and selection['paired_seed_ranking'] == seedranking
    assert selection['method'] == m and selection['seed'] == seedranking[0]['seed']
    selected = {}
    for v in ('v4','v5'):
        d = STUDY/'selected'/v
        claim, test, replay = (read(d/f) for f in ('test.claim.json','test.json','replay-verification.json'))
        assert sha(d/'model.pt') == sha(Path(selection['checkpoints'][v]['source'])) == selection['checkpoints'][v]['sha256'] == claim['checkpoint_sha256']
        assert claim['seeds'] == p['reserved_test_seeds'] and claim['environment_version'] == int(v[1:]) and claim['sampler_seed'] == 54321
        assert test['episodes'] == len(test['records']) == 128 and sorted(x['seed'] for x in test['records']) == list(range(11000001,11000129))
        assert st.mean(x['achievements'] for x in test['records']) == test['mean_achievements']
        assert st.mean(x['died'] for x in test['records']) == test['death_rate']
        assert replay['python_sdl_final_state_exact'] and replay['policy_provenance']['sampled_tape_exactly_reproduced']
        assert replay['policy_provenance']['checkpoint_sha256'] == sha(d/'model.pt') and replay['tape_sha256'] == sha(d/'seed9.tape')
        assert replay['state']['environment_version'] == int(v[1:])
        # Filesystem order corroborates the frozen supervisor's explicit order;
        # timestamps alone are not an independent proof of exclusive execution.
        assert (STUDY/'selected/selection.json').stat().st_mtime_ns <= (d/'test.claim.json').stat().st_mtime_ns <= (d/'test.json').stat().st_mtime_ns
        for w in ('v4','v5'):
            assert (STUDY/'selected'/w/'model.pt').stat().st_mtime_ns <= (d/'test.claim.json').stat().st_mtime_ns
        selected[v] = {'artifacts':{f.name:sha(f) for f in d.iterdir() if f.is_file()},'score':test['mean_achievements'],'death':test['death_rate'],'furnace':test['hits'].get('craft furnace',0),'anvil':test['hits'].get('craft anvil',0),'replay':replay}
    groups = {}
    for v in ('v4','v5'):
        for m in p['methods']:
            ds = [read(STUDY/f'main/{v}/{m}-{s}/crafting.json') for s in p['training_seeds']]
            agg = {'episodes':640,'opportunity_episodes':sum(d['opportunity_episodes'] for d in ds),'gate_steps_before_first_furnace_stone_sufficient':[sum(d['gate_steps_before_first_furnace_stone_sufficient'][i] for d in ds) for i in range(16)]}
            for key in ('counters','wood_consumed_by_action','wood_consumed_before_first_furnace'):
                cnt = Counter()
                for d in ds:cnt.update(d[key])
                agg[key] = dict(cnt)
            groups[f'{v}/{m}'] = crafting_summary(agg)
    result = {'passed':True,'audit_date':'2026-10-12','report_sha256':sha(REPO/'docs/reports/FOOTPRINT_LEARNING_2026_10.json'),'protocol_sha256':sha(STUDY/'study-protocol.json'),'supervisor_sha256':sha(STUDY/'runner.py'),'original_supervisor_sha256':plan['original_supervisor_sha256'],'frozen_source_counts':source_count,'reused_artifact_file_counts':copied,'main_runs':30,'retained_main_runs':15,'new_main_runs':15,'main_transitions':503316480,'additional_main_transitions':251658240,'discarded_partial_checkpoint_transitions':12582912,'paired_comparisons':comparisons,'runs':runrows,'run_artifact_sha256':artifacts,'crafting_per_policy':diagnostics,'crafting_action_weighted_groups':groups,'selection_recomputed':selection,'selected_tests_and_replays':selected,'reserved_tests_evaluated_by_audit':False,'note':'Only saved artifacts read; no neural evaluations or training. Gate fractions overlap and are action-weighted descriptive associations, not causal interventions or extra independent seeds.'}
    (REPO/'docs/reports/FOOTPRINT_LEARNING_2026_10.audit.json').write_text(json.dumps(result,indent=2)+'\n')
    lines = ['# Final-policy crafting diagnostics — 2026-10-12', '',
        'Reporting-only analysis of all 30 saved final-policy validation rollouts. No new neural evaluations. Full joint 16-code histograms, wood sinks and event records remain in each run’s `crafting.json`; per-policy derived metrics and hashes are in [the audit](FOOTPRINT_LEARNING_2026_10.audit.json).', '',
        'Missing fractions condition on pre-first-furnace actions with at least 20 stone. Wood means at least 4, torches at least 3, station means a nearby workbench. These are overlapping action-weighted descriptions, not independent seeds or causal attribution. Bench selection conditions on inventory ownership, not on placement-space availability. Acquired wood includes recoveries; sinks count actual consumed units, not unique resource supply.', '',
        '| Policy | Score /32 | Opportunity worlds /128 | Furnace worlds /128 | Missing wood / station / both | Bench selected while owned | Wood acquired / platform sink per world |',
        '| --- | ---: | ---: | ---: | --- | ---: | --- |']
    for row in runrows:
        d = diagnostics[row['name']]
        def percent(x):
            return 'n/a' if x is None else f'{x:.1%}'
        missing = ' / '.join(percent(d[k]) for k in ('wood_missing_fraction','station_missing_fraction','wood_and_station_missing_fraction'))
        lines.append(f"| {row['name'].removeprefix('main/')} | {row['score']:.3f} | {d['opportunity_episodes']} | {row['furnace']} | {missing} | {percent(d['bench_selected_when_owned_fraction'])} | {d['wood_acquired_per_episode']:.1f} / {d['wood_sinks_per_episode'].get('craft platforms',0):.1f} |")
    lines += ['', 'Interpretation: the v5 targets/memory packages reach zero furnace opportunities across all five seeds each. They acquire roughly 16 wood/world, spend roughly 10 on platforms and 2.5–2.7 on torches, and almost never craft benches. On v4, the same packages acquire more wood and craft more benches, but still almost never coordinate all four furnace prerequisites. The successful v5 MLP seeds demonstrate that the enlarged-object game supports workshop progression; the two late MLP seeds remain near 11/32 with no furnaces. Missing furnace opportunity is not the same as inability to learn the furnace action.', '',
        'Bench space is available during more than 98% of owned-bench actions in every aggregate package/version group. This weakens a simple “cannot place the larger bench anywhere” explanation, but does not exclude harder placement during rare strategically useful moments. V5 MLP has more opportunities without more aggregate bench-selection frequency. Inventory friction, wood retention/reacquisition, station positioning and sparse long-term credit remain candidate intervention targets—not proven individual causes.', '',
        'These observations do not isolate object size, world generation, interaction reach, architecture, entropy or trace settings. No resource supply, recipe, mask, reward or controller was changed. See [the study report](FOOTPRINT_LEARNING_2026_10.md) for the five-independent-seed comparisons.']
    (REPO/'docs/reports/FOOTPRINT_CRAFTING_2026_10.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({k:result[k] for k in ['passed','frozen_source_counts','main_runs','main_transitions','paired_comparisons','crafting_action_weighted_groups']},indent=2))


if __name__ == '__main__':
    main()
