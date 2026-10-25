"""Reporting-only audit of existing PPO artifacts; never imports/runs a learner.

Recomputes seed-unit statistics, validates frozen provenance and checkpoint
metadata, and summarizes already-recorded diagnostic trajectories. No rollouts,
API calls, source repairs, test evaluation or policy selection.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics as st
import subprocess


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def close(a, b):
    assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-10), (a, b)


def critical(probability):
    # Independently integrate the t(df=4) density with Simpson's rule rather
    # than reusing the frozen report's analytic CDF implementation.
    def cdf(t):
        n = 4096
        h = t / n
        f = lambda x: .375 * (1 + x*x/4) ** -2.5
        return .5 + h/3 * (f(0) + f(t) + sum(
            (4 if i % 2 else 2) * f(i*h) for i in range(1, n)))
    low, high = 0., 10.
    for _ in range(60):
        mid = (low + high)/2
        if cdf(mid) < probability:
            low = mid
        else:
            high = mid
    return (low + high)/2


def sums(records, key):
    c = Counter()
    for record in records:
        c.update(record.get(key, {}))
    return dict(c)


def craft_summary(d):
    gates = d['gate_steps_before_first_furnace_stone_sufficient']
    total = sum(gates)
    counter = d['counters']
    owned = counter.get('bench_owned_steps', 0)
    return {
        'opportunity_episodes': d['opportunity_episodes'],
        'pre_furnace_stone_sufficient_actions': total,
        'pre_furnace_joint_legal_actions': gates[15],
        'missing_wood_and_bench_given_stone': sum(
            n for i, n in enumerate(gates) if not i & 1 and not i & 8) / total,
        'wood_acquired_per_world': counter.get('wood_acquired', 0)/d['episodes'],
        'bench_selected_fraction_when_owned': counter.get('bench_selected_steps', 0)/owned if owned else None,
        'bench_space_fraction_when_owned': counter.get('bench_owned_with_space_steps', 0)/owned if owned else None,
        'counters': counter,
        'gate_steps_before_first_furnace': d['gate_steps_before_first_furnace'],
        'wood_consumed_before_first_furnace': d['wood_consumed_before_first_furnace'],
    }


def audit(study, amendment):
    # Only the original supervisor's pure source-manifest checker is called.
    spec = importlib.util.spec_from_file_location('frozen_report', study/'supervisor.py')
    frozen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(frozen)
    protocol = read(study/'study-protocol.json')
    frozen.verify_sources(study, protocol)
    result_path = study/'results.json'
    result = read(result_path)
    repo = Path(protocol['repository'])
    assert sha(result_path) == sha(repo/'docs/reports/V7_REWARD_STUDY_2026_10_17.json')
    assert result['protocol'] == protocol and result['complete']
    assert result['reserved_tests_consumed'] is False
    assert protocol['main_transitions'] == result['main_transitions'] == 419430400
    assert protocol['calibration_transitions_excluded'] == 81920
    assert protocol['reserved_test_seeds'] == [19000001, 19000128]
    assert not list(study.rglob('*.claim.json'))
    assert not [p for p in (study/'runs').rglob('*')
                if p.is_file() and p.suffix in ('.json','.jsonl')
                and ('test' in p.name or 'selection' in p.name)]
    rows = {(r['cell'], r['seed']): r for r in result['runs']}
    assert len(rows) == len(result['runs']) == 25
    assert sum(r['summary']['steps'] for r in rows.values()) == 419430400
    checkpoint_hashes = [digest for r in rows.values() for file, digest in r['artifact_sha256'].items() if file.endswith('.pt')]
    assert len(checkpoint_hashes) == len(set(checkpoint_hashes)) == 100
    expected_names = {f'{cell}-{seed}' for cell, seed in protocol['jobs']}
    assert {d.name for d in (study/'runs').iterdir()} == expected_names
    all_runs = {}
    # Reading serialized tensor metadata is not inference or evaluation.
    import torch
    for cell, seed in protocol['jobs']:
        name = f'{cell}-{seed}'
        directory = study/'runs'/name
        row = rows[cell, seed]
        config = read(directory/'protocol.json')
        cfg = config['config']
        summary, curve, crafting = (read(directory/f) for f in
                                   ('summary.json', 'curve.json', 'crafting.json'))
        version = protocol['cells'][cell]['version']
        variant = study/'variants'/version
        assert summary == row['summary'] and curve == row['curve'] and crafting == row['crafting']
        assert summary['steps'] == config['actual_steps'] == cfg['total_steps'] == 16777216
        assert cfg['seed'] == seed and cfg['gamma'] == protocol['cells'][cell]['gamma']
        assert cfg['achievement_reward'] == protocol['cells'][cell]['reward']
        assert config['reward'] == protocol['reward_schemes'][cfg['achievement_reward']]
        for k, v in {'num_envs':64, 'rollout':128, 'epochs':4, 'minibatches':4,
                     'lr':.0003, 'anneal_lr':True, 'gae_lambda':.99,
                     'ent_coef':.03, 'architecture':'targets', 'device':'cpu',
                     'init':'', 'progress_coef':0., 'curiosity_coef':0.,
                     'bootstrap_time_limit':False}.items():
            assert cfg[k] == v, (name, k)
        assert config['torch_threads'] == 4 and config['sampler_seed'] == 54321
        assert config['environment_version'] == int(version[1:])
        assert not config['demonstrations'] and not config['prerequisite_shaping']
        assert config['training_novelty'] is None
        assert config['validation_seeds'] == protocol['validation_seeds']
        assert config['reserved_test_seeds'] == protocol['reserved_test_seeds']
        assert config['driver_sha256'] == sha(variant/'tools/iterate_ppo.py')
        for file, digest in config['implementation_sha256'].items():
            assert sha(directory/'implementation'/file) == digest
            assert sha(variant/'python/terraria_lite'/file) == digest
        assert len(curve) == 4
        assert [p['steps'] for p in curve] == protocol['checkpoint_steps']
        assert len(list(directory.glob('step-*.pt'))) == 4
        for file, digest in row['artifact_sha256'].items():
            assert sha(directory/file) == digest
        for point in curve:
            checkpoint = torch.load(directory/f"step-{point['steps']}.pt", weights_only=True, map_location='cpu')
            assert checkpoint['environment_version'] == int(version[1:])
            assert checkpoint['architecture'] == 'targets'
            assert checkpoint['training_objective'] == config['training_objective']
            e = point['evaluation']
            records = e['records']
            assert len(records) == e['episodes'] == 128
            assert sorted(r['seed'] for r in records) == list(range(17000001,17000129))
            for key, record_key in [('mean_achievements','achievements'), ('death_rate','died'),
                                    ('mean_return','episode_return'), ('mean_length','steps')]:
                close(e[key], st.mean(r[record_key] for r in records))
            hits = Counter()
            for r in records:
                assert 0 < r['steps'] <= 3000
                assert r['died'] == (r['health'] <= 0)
                assert r['achievements'] == r['achievement_mask'].bit_count()
                close(r['episode_return'], r['achievements']-r['died'])
                hits.update(r['first_achievement_steps'].keys())
            assert dict(hits) == e['hits']
        assert crafting['diagnostic_source_sha256'] == sha(variant/'tools/crafting_diagnostics.py')
        assert crafting['probe_sha256'] == protocol['probe_sha256'][version]
        assert crafting['checkpoint_sha256'] == sha(directory/'step-16777216.pt')
        assert crafting['sample_seed'] == 54321 and crafting['seed_range'] == protocol['validation_seeds']
        assert crafting['policy_mode'] == 'categorical sampled'
        assert crafting['episodes'] == len(crafting['records']) == 128
        final = {r['seed']: r for r in curve[-1]['evaluation']['records']}
        for r in crafting['records']:
            assert r['info'] == {k: final[r['seed']][k] for k in r['info']}
            assert sum(r['gate_steps']) == r['counters']['observed_actions'] == r['info']['steps']
        for key in ['gate_steps', 'gate_steps_after_stone_sufficient',
                    'gate_steps_before_first_furnace', 'gate_steps_before_first_furnace_stone_sufficient']:
            assert crafting[key] == [sum(r[key][i] for r in crafting['records']) for i in range(16)]
        for key in ['counters','wood_consumed_by_action','wood_consumed_before_first_furnace']:
            assert crafting[key] == sums(crafting['records'], key)
        close(crafting['mean_achievements'], curve[-1]['evaluation']['mean_achievements'])
        assert crafting['opportunity_episodes'] == sum(r['first_furnace_opportunity'] >= 0 for r in crafting['records'])
        log = (study/'logs'/f'{name}.log').read_text()
        assert log.count('Completed '+name+':') == 1
        all_runs[name] = {'artifact_sha256':row['artifact_sha256'], 'crafting':craft_summary(crafting)}
    # Independent contrast algebra and numerical t critical values.
    criticals = {key: critical(p) for key, p in [('descriptive_95',.975),('four_contrast_familywise_95',.99375)]}
    close(criticals['descriptive_95'], 2.7764451051977987)
    for metric, get in {
        'score': lambda e:e['mean_achievements'], 'death_rate':lambda e:e['death_rate'],
        'furnace_rate':lambda e:e['hits'].get('craft furnace',0)/128,
        'anvil_rate':lambda e:e['hits'].get('craft anvil',0)/128}.items():
        contrast_values = {name:[] for name in protocol['comparisons']}
        for seed in protocol['training_seeds']:
            a,b,c,d,e = [get(rows[cell,seed]['curve'][-1]['evaluation']) for cell in protocol['cells']]
            for name, value in zip(protocol['comparisons'], [b-a,(c+e-b-d)/2,(d+e-b-c)/2,e-d-c+b]):
                contrast_values[name].append(value)
        for name, values in contrast_values.items():
            for interval_name, recorded in result['paired_contrasts'][metric][name].items():
                assert recorded['per_seed'] == values
                mean = st.mean(values)
                half = criticals[interval_name]*st.stdev(values)/math.sqrt(5)
                close(recorded['mean'],mean)
                for got, expected in zip(recorded['interval'],[mean-half,mean+half]):
                    close(got,expected)
    aggregates = {}
    for cell in protocol['cells']:
        group = [rows[cell,s] for s in protocol['training_seeds']]
        ds = [g['crafting'] for g in group]
        combined = {'episodes':640, 'counters':sums(ds,'counters'),
                    'opportunity_episodes':sum(d['opportunity_episodes'] for d in ds),
                    'wood_consumed_before_first_furnace':sums(ds,'wood_consumed_before_first_furnace')}
        for key in ['gate_steps_before_first_furnace','gate_steps_before_first_furnace_stone_sufficient']:
            combined[key] = [sum(d[key][i] for d in ds) for i in range(16)]
        aggregates[cell] = {
            'curve_means':[st.mean(g['curve'][i]['evaluation']['mean_achievements'] for g in group) for i in range(4)],
            'crafting':craft_summary(combined),
            'collection_seconds':sum(g['summary']['collection_seconds'] for g in group),
            'optimisation_seconds':sum(g['summary']['optimisation_seconds'] for g in group),
        }
    pointer = read(study/'parallel-amendment.json')
    am, start, launch, last, done, prior = [read(amendment/f) for f in
        ['amendment.json','started.json','launch.json','last-trial-launch.json','completed.json','status-before.json']]
    assert pointer['amendment_root'] == str(amendment)
    assert sha(amendment/'coordinator.py') == am['coordinator_sha256'] == start['coordinator_sha256'] == launch['coordinator_sha256'] == '40920da39caa6f6dbf99766100b0be93251b2085e6b08d39a7ddb8601286e09c'
    assert am['original_protocol_sha256'] == start['original_protocol_sha256'] == sha(study/'study-protocol.json') == '5f3d6fc9114d4aff1670754897884a1aadde226afadd9594a48473a3f162cdd1'
    assert am['original_supervisor_sha256'] == sha(study/'supervisor.py') == protocol['supervisor_sha256']
    assert read(study/'started.json')['protocol_sha256'] == sha(study/'study-protocol.json')
    assert prior['active'] == am['adopted_workers']
    assert am['adopted_workers'] == {'v4-equal-g999-805':25123, 'v7-equal-g999-805':25143, 'v7-equal-g1-805':25148}
    original_log = (study/'runner.log').read_text().splitlines()
    dispatches = [line.split() for line in original_log if line.startswith('Started ')]
    assert len(dispatches) == 24 and {line[1] for line in dispatches} == expected_names-{'v7-difficulty-g999-805'}
    for name, pid in am['adopted_workers'].items():
        assert sum(line == ['Started', name, str(pid)] for line in dispatches) == 1
        identity = am['adopted_worker_identities'][str(pid)]
        assert str(study/'runs'/name) in identity['command'] and identity['start'].startswith('Sat Oct 17 17:55:')
    assert prior['pending'] == [['v7-difficulty-g999',805]]
    assert len(prior['completed']) == 21
    assert set(prior['completed']) | set(am['adopted_workers']) | {last['name']} == expected_names
    assert last['name'] == 'v7-difficulty-g999-805' and last['pid'] == pointer['last_trial_pid'] == 27801
    assert last['command'] == frozen.command(study,'v7-difficulty-g999',805)
    assert done['all25_main_runs_complete']
    assert (amendment/'runner.log').read_text().count('last trial started once') == 1
    assert not any('Started v7-difficulty-g999-805 ' in line for line in (study/'runner.log').read_text().splitlines())
    for root in [study, amendment]:
        status = read(root/'status.json')
        assert status['stage'] == 'complete' and not status['active'] and not status['pending']
        assert set(status['completed']) == expected_names
    ps = subprocess.check_output(['ps','-axo','pid=,command='], text=True)
    tracked_pids = {99218,27793,27801,*am['adopted_workers'].values()}
    for line in ps.splitlines():
        pid, command = line.strip().split(maxsplit=1)
        assert int(pid) not in tracked_pids, line
        if '/bin/zsh -lc ' not in command:
            assert not (str(study) in command and any('/'+s+' ' in command for s in ['iterate_ppo.py','crafting_diagnostics.py','supervisor.py'])), line
            assert str(amendment/'coordinator.py')+' ' not in command, line
    overlap = set(am['adopted_workers']) | {last['name']}
    timings = {name:rows[name.rsplit('-',1)[0], int(name.rsplit('-',1)[1])]['summary']['wall_seconds_including_validation'] for name in expected_names}
    return {
        'audit_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'scope':'Existing-artifact audit only; no policy inference, training, replay, test evaluation or selection.',
        'study':str(study), 'results_sha256':sha(result_path),
        'protocol_sha256':sha(study/'study-protocol.json'), 'source_and_probe_hashes_verified':True,
        'main_runs':25,'checkpoints_and_curve_points':100,'main_transitions':419430400,
        'preflight_transitions_excluded':81920, 'validation_trajectory_records_checked':12800,
        'final_crafting_records_exactly_match_validation':3200,
        'reserved_tests_consumed':False,'test_claims':[],
        'statistical_unit':'Five paired training seeds; rates/curves/crafting telemetry are descriptive.',
        'independent_t_df4_criticals':criticals, 'paired_contrasts':result['paired_contrasts'],
        'aggregates':aggregates, 'runs':all_runs,
        'amendment':{'root':str(amendment),'coordinator_sha256':sha(amendment/'coordinator.py'),
                     'records_sha256':{f:sha(amendment/f) for f in ['launch.json','started.json','amendment.json','last-trial-launch.json','completed.json','status-before.json','runner.log']},
                     'adopted_worker_identities':am['adopted_worker_identities'],
                     'last_trial_launch':last, 'all_tracked_processes_absent':True,
                     'completion_utc':dt.datetime.fromtimestamp(done['completed_utc'],dt.timezone.utc).isoformat(),
                     'timing_caveat':'Final four trials overlap under amended contention; no intrinsic throughput contrast.',
                     'wall_seconds_including_validation_amended_overlap':{n:timings[n] for n in sorted(overlap)},
                     'wall_seconds_including_validation_original_three_way':{n:timings[n] for n in sorted(expected_names-overlap)}}
    }


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--study', type=Path, required=True)
    p.add_argument('--amendment', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = audit(args.study.resolve(), args.amendment.resolve())
    with args.out.open('x') as f:
        json.dump(result,f,indent=2,allow_nan=False)
        f.write('\n')
    print(json.dumps({k:result[k] for k in ['main_runs','checkpoints_and_curve_points','main_transitions','reserved_tests_consumed']}))
