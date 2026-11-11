"""Export the fixed headroom study's durable evidence, without fresh evaluations."""
import argparse
import hashlib
import json
from pathlib import Path


def read(path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def compact_curve(rows):
    return [{'steps': r['steps'], 'checkpoint_seconds': r.get('checkpoint_elapsed_seconds', r['elapsed_seconds']),
             'available_seconds': r['elapsed_seconds'], 'profile': r['profile'],
             'evaluation': {k: v for k, v in r['evaluation'].items() if k != 'records'}} for r in rows]


def compact_diag(data):
    return None if data is None else {k: v for k, v in data.items() if k != 'records'}


def latest_before(rows, seconds, key):
    eligible = [r for r in rows if r[key] <= seconds]
    return max(eligible, key=lambda r: r['steps']) if eligible else None


def export(root, output):
    manifest = read(root / 'manifest.json')
    budget = read(root / 'budget.json')
    completion = read(root / 'complete.json', {})
    jobs = read(root / 'ownership.json', [])
    result = {'study': 'v10 generic PPO headroom 2026-11-11', 'remote_path': '/home/mvohl/Projects/RL-headroom-20261111',
              'immutable_snapshot': manifest, 'budget': budget, 'completion': completion,
              'hardware': read(root / 'hip_mapping.json'), 'supervision': read(root / 'supervision.json'),
              'final_gpu_processes': read(root / 'final_gpu_processes.json'),
              'model_runtime': {'model': 'amd-unified/gpt-6.1-sol', 'reasoning': 'high', 'fallback': False,
                                'evidence': 'parent observed session metadata and thinking_level_change'},
              'startup_failure': read(root / 'startup-failure/error.json', read(root / 'error.json')),
              'startup_attempts': read(root / 'startup-failure/ownership.json', []),
              'recovery_authorization': read(root / 'recovery_authorization.json'),
              'screen_supervisor_failure': read(root / 'error.json'),
              'promotion_authorization': read(root / 'promotion_authorization.json'),
              'original_screen_close': read(root / 'screen-close/complete.json'),
              'supervisor_source_versions': read(root / 'supervisor_sources.json'),
              'controls': {}, 'trials': [], 'comparisons': [],
              'limitations': ['Selection uses validation worlds, not reserved test worlds.',
                              'One screen seed and at most two selected seeds cannot establish a definitive ranking or robust CI.',
                              'Cached control timing used two trainers on HIP7; candidates use one trainer per GPU. Timings are not exact compute parity.',
                              'Asynchronous checkpoint-write time and score-availability time are distinguished; no interpolation or extrapolated 1B score.',
                              'Longer-credit changes are a package, not an isolated lambda or rollout effect.']}
    for seed in (3001, 3002):
        folder = root / 'controls' / str(seed)
        result['controls'][str(seed)] = {'curve': compact_curve(read(folder / 'curve.json', [])),
                                        'summary': read(folder / 'summary.json'), 'protocol': read(folder / 'protocol.json'),
                                        'diagnostics': compact_diag(read(folder / 'diag.json'))}
    for job in jobs:
        folder = root / 'runs' / job['name']
        rows = compact_curve(read(folder / 'curve.json', []))
        protocol = read(folder / 'protocol.json')
        diag = compact_diag(read(folder / 'diag.json'))
        trial = {'ownership': job, 'protocol': protocol, 'curve': rows, 'summary': read(folder / 'summary.json'),
                 'diagnostics': diag, 'last_evaluated_steps': rows[-1]['steps'] if rows else None,
                 'last_score': rows[-1]['evaluation']['weighted_score'] if rows else None,
                 'full_1B': bool(rows and rows[-1]['steps'] == 1073741824),
                 'artifact_sha256': {f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in folder.glob('*.json')}}
        result['trials'].append(trial)
        control = result['controls'][str(job['seed'])]['curve']
        matched_steps = []
        for row in rows:
            ctl = next((r for r in control if r['steps'] == row['steps']), None)
            if ctl:
                matched_steps.append({'steps': row['steps'], 'candidate_score': row['evaluation']['weighted_score'],
                                      'control_score': ctl['evaluation']['weighted_score'],
                                      'delta_pp': row['evaluation']['weighted_score'] - ctl['evaluation']['weighted_score'],
                                      'candidate_checkpoint_seconds': row['checkpoint_seconds'],
                                      'control_checkpoint_seconds': ctl['checkpoint_seconds'],
                                      'candidate_available_seconds': row['available_seconds'],
                                      'control_available_seconds': ctl['available_seconds']})
        matched_time = []
        limits = sorted(set([600, 1200, 1800, 2400, 3000, 3600] + [int(r['available_seconds']) + 1 for r in rows]))
        if rows:
            limits = [t for t in limits if t <= rows[-1]['available_seconds'] + 1]
        else:
            limits = []
        for limit in limits:
            for clock in ('checkpoint_seconds', 'available_seconds'):
                a, b = latest_before(rows, limit, clock), latest_before(control, limit, clock)
                matched_time.append({'seconds': limit, 'clock': clock,
                                     'candidate_steps': None if a is None else a['steps'],
                                     'control_steps': None if b is None else b['steps'],
                                     'candidate_score': None if a is None else a['evaluation']['weighted_score'],
                                     'control_score': None if b is None else b['evaluation']['weighted_score'],
                                     'delta_pp': None if a is None or b is None else a['evaluation']['weighted_score'] - b['evaluation']['weighted_score']})
        result['comparisons'].append({'trial': job['name'], 'paired_control_seed': job['seed'],
                                      'matched_steps': matched_steps, 'matched_time': matched_time})
        available_pairs = [r for r in matched_time if r['clock'] == 'available_seconds' and r['delta_pp'] is not None]
        result['comparisons'][-1]['last_observed_time_comparison'] = available_pairs[-1] if available_pairs else None
        result['comparisons'][-1]['observed_score_per_time_improvement'] = bool(available_pairs and available_pairs[-1]['delta_pp'] > 0)
    selection = read(root / 'selection.json')
    result['selection'] = selection
    result['logical_candidate_jobs'] = len(jobs)
    result['candidate_process_attempts'] = len(jobs) + len(result['startup_attempts'])
    result['reserved_test_worlds_used'] = 0
    result['fresh_control_jobs'] = 0
    screen_pairs = [{'trial': c['trial'], **r} for c in result['comparisons'] if c['trial'].startswith('A-')
                    for r in c['matched_steps'] if r['steps'] == 268435456]
    result['A_matched_256Mi'] = {'pairs': screen_pairs,
        'mean_paired_delta_pp': sum(r['delta_pp'] for r in screen_pairs) / len(screen_pairs) if screen_pairs else None,
        'interpretation': 'paired early-budget evidence only; no two-seed full1B claim or robust CI'}
    final_pairs = [c['matched_steps'][-1] for c in result['comparisons'] if c['matched_steps']]
    if not final_pairs:
        conclusion = 'Operational launch failure: no evaluated checkpoint; no learning or headroom conclusion.'
    elif selection and selection.get('winner'):
        chosen = [t for t in result['trials'] if t['ownership']['candidate'] == selection['winner']]
        final_rows = [(t['ownership']['name'], next(c for c in result['comparisons'] if c['trial'] == t['ownership']['name'])['matched_steps'][-1]) for t in chosen if t['curve']]
        conclusion = (f"Provisionally selected {selection['winner']}; last paired comparisons "
                      + ', '.join(f"{name} {row['delta_pp']:+.2f}pp at {row['steps']:,} steps" for name,row in final_rows)
                      + '. This is not a definitive ranking.')
    else:
        conclusion = 'Neither candidate promoted; bounded screen is negative/inconclusive, not a claim that generic long-horizon methods cannot work.'
    result['conclusion'] = conclusion
    lines = ['# v10 generic PPO headroom study, 2026-11-11', '', conclusion, '', '## Frozen protocol', '',
             f"- Engine `4ede178`; library SHA256 `{manifest['library_sha256']}`; immutable input manifest `{manifest['sha256']}`.",
             '- 93 actions, 40 weighted achievements, max145, 11×9 view, 10,000-step episodes; no engine/interface/observation/mask/evaluation-reward changes.',
             '- Cached generic controls3001/3002 reused with exact trainer/package hashes. No fresh control job, BC, task-specific shaping, curriculum, or reserved test-world evaluation.',
             '- Targets h128/depth2/cell32,487896 parameters; γ.9999, LR.0003 linearly annealed over1,073,741,824 steps, novelty.01, unimix.01,4epochs×16minibatches, batch131072/minibatch8192.',
             '- A: entropy.01 (baseline.03). B: λ.995,512envs×256rollout (baselineλ.99,1024×128); entropy.03. Every other baseline knob is unchanged.',
             '- GPU collect/train; CPU async validation128worlds23000001–23000128, sampler54321, every134,217,728steps; native-autoreset/compact/compile/bf16/fusedAdam/compile-all safe eager bf16 backward,4threads/12simworkers.',
             '- Actual worker runtime: amd-unified/gpt-6.1-sol/high, no fallback, as observed by parent session metadata.', '', '## Ownership and budget', '',
             f"- Common GPU-work window began `{budget['start']}`; immutable hard deadline `{budget['deadline']}`. Detached watchdog enforces only owned process groups, starting termination10s early.",
             '- HIP6 → PCI0000:e8:00.0 / amd-smiGPU6; HIP7 → PCI0000:98:00.0 / amd-smiGPU5. Trainers use CPUs300–323 and324–347 on NUMA1.',
             f"- Remote durable evidence: `{result['remote_path']}`. Commands, PID/PGID/start-ticks and logs are in the JSON/remote evidence."]
    if result['startup_failure']:
        lines += [f"- Startup supervision failure preserved: `{result['startup_failure']['error']}`. Initial process attempts terminated before any evaluated checkpoint; training steps are unknown, not assumed zero. Both attempts and shutdown times are retained in JSON."]
    if result['recovery_authorization']:
        lines += [f"- Recovery authorization: {result['recovery_authorization']['authorization']}; original deadline unchanged."]
    if result['screen_supervisor_failure']:
        lines += [f"- Screen supervisor exception preserved: `{result['screen_supervisor_failure']['error']}`. A duplicated `time` keyword in event logging invoked ownership-scoped shutdown after the screen decision was written. The final source fixes this collision; the running confirmation path did not invoke that screen event."]
    if result['promotion_authorization']:
        lines += [f"- Parent promotion amendment: {result['promotion_authorization']['authorization']}. A3001 remains screen-only; no weights-only reconstruction of its Adam/RNG/LR state was attempted.",
                  '- The original 1.2×fresh-confirmation completion guard was too conservative (A missed it by about12s despite ~67min remaining). It was not evidence of learning failure or hard budget impossibility. Parent approved only the planned A3002 confirmation; original selection/shutdown evidence remains archived.']
    closed = completion.get('gpu_closed', read(root / 'gpu_closed.json', {}))
    lines += [f"- Logical candidate jobs={len(jobs)}; actual process attempts={result['candidate_process_attempts']} including the two explicitly authorized initialization retries. No additional condition or seed."]
    if selection:
        lines += [f"- Screen decision: {selection.get('reason')}; winner={selection.get('winner')}; live-state continuation={selection.get('live_state_preserved', False)}, checkpoint restart={selection.get('checkpoint_restart', False)}."]
    for c in result['comparisons']:
        last = c['last_observed_time_comparison']
        if last:
            lines += [f"- {c['trial']} at the last jointly observed available-time comparison ({last['seconds']}s): {last['delta_pp']:+.2f}pp versus paired control. {'Observed score-per-time advantage' if last['delta_pp'] > 0 else 'No observed advantage at this snapshot'}; not a robust efficiency ranking."]
    lines += [f"- GPU shutdown: `{closed.get('time')}`; deadline respected={closed.get('deadline_respected')}; candidate occupied-job-hours upper bound={closed.get('gpu_job_hours_upper_bound')}; zero fresh controls/reserved test worlds.", '', '## Per-seed results', '',
              '| Trial | Status / stop reason | Last evaluated steps | Score % | Paired control % | Difference pp | Checkpoint / available seconds |',
              '|---|---|---:|---:|---:|---:|---:|']
    for trial, comparison in zip(result['trials'], result['comparisons']):
        j = trial['ownership']; row = comparison['matched_steps'][-1] if comparison['matched_steps'] else None
        lines.append(f"| {j['name']} | {j['status']}: {j.get('stop_reason', 'normal full-budget completion' if trial['full_1B'] else 'no full1B result')} | "
                     + (f"{row['steps']:,} | {row['candidate_score']:.2f} | {row['control_score']:.2f} | {row['delta_pp']:+.2f} | {row['candidate_checkpoint_seconds']:.1f} / {row['candidate_available_seconds']:.1f} |" if row else '— | — | — | — | — |'))
    lines += ['', 'Full1B means an observed1,073,741,824-step evaluation only. Partial/stopped runs are not extrapolated.']
    if result['promotion_authorization']:
        lines += ['', 'Only A3002 can have a full1B result; A3001 was stopped at the screen. There is no two-seed full1B mean/ranking. Compare both A seeds at256Mi, and A3002 against its paired cached control at later observed checkpoints.']
    if screen_pairs:
        lines += ['', 'A at matched256Mi: ' + ', '.join(f"{r['trial']} {r['candidate_score']:.2f}% vs {r['control_score']:.2f}% ({r['delta_pp']:+.2f}pp)" for r in screen_pairs)
                  + f"; mean paired difference {result['A_matched_256Mi']['mean_paired_delta_pp']:+.2f}pp. This is early-budget evidence, not a full1B average."]
    lines += ['', '## Matched-step and matched-time evidence', '',
              '| Trial | Steps | Candidate / control % | Difference pp | Checkpoint seconds candidate / control |', '|---|---:|---:|---:|---:|']
    for c in result['comparisons']:
        for r in c['matched_steps']:
            lines.append(f"| {c['trial']} | {r['steps']:,} | {r['candidate_score']:.2f} / {r['control_score']:.2f} | {r['delta_pp']:+.2f} | {r['candidate_checkpoint_seconds']:.1f} / {r['control_checkpoint_seconds']:.1f} |")
    lines += ['', '| Trial | Available-time limit s | Latest observed steps candidate / control | Score candidate / control % | Difference pp |', '|---|---:|---:|---:|---:|']
    for c in result['comparisons']:
        for r in c['matched_time']:
            if r['clock'] == 'available_seconds' and r['delta_pp'] is not None:
                lines.append(f"| {c['trial']} | {r['seconds']} | {r['candidate_steps']:,} / {r['control_steps']:,} | {r['candidate_score']:.2f} / {r['control_score']:.2f} | {r['delta_pp']:+.2f} |")
    lines += ['', 'JSON also includes checkpoint-write-time comparisons. Cached controls shared HIP7; wall-time comparisons include that limitation.', '', '## Behavior and stability', '']
    late = ('craft iron pickaxe', 'craft gold pickaxe', 'craft iron chainmail', 'return to surface', 'defeat Demon Eye', 'collect lens', 'hold 6 lenses', 'craft Suspicious Looking Eye', 'defeat the Eye of Cthulhu')
    for t in result['trials']:
        if not t['curve']:
            lines.append(f"- {t['ownership']['name']}: no evaluation, therefore no behavior/stability inference.")
            continue
        r=t['curve'][-1]; ev=r['evaluation']; p=r['profile']; diag=t['diagnostics']
        lines.append(f"- {t['ownership']['name']}: death={ev['death_rate']:.3f}, peak-depth={ev['mean_peak_depth']:.1f}, tail-after-last-achievement={ev['mean_steps_after_last_achievement']:.1f}; entropy={p['policy_entropy']:.3f}, KL={p['approx_kl']:.5f}, clip={p['clip_fraction']:.5f}, EV={p['explained_variance']:.5f}.")
        lines.append('  Late-achievement hits/128: ' + ', '.join(f"{k}={ev['hits'].get(k,0)}" for k in late) + '.')
        paired = next(c for c in result['controls'][str(t['ownership']['seed'])]['curve'] if c['steps'] == r['steps'])['evaluation']
        lines.append(f"  Matched-step control: death={paired['death_rate']:.3f}, peak-depth={paired['mean_peak_depth']:.1f}, tail-after-last-achievement={paired['mean_steps_after_last_achievement']:.1f}; "
                     + ', '.join(f"{k}={paired['hits'].get(k,0)}" for k in late) + '.')
        lines.append('  Mid-progression hits candidate/control: ' + ', '.join(
            f"{k}={ev['hits'].get(k,0)}/{paired['hits'].get(k,0)}" for k in
            ('craft anvil', 'craft metal sword', 'craft wood breastplate', 'smelt silver', 'smelt gold', 'survive a night')) + '.')
        if diag:
            actions=diag['actions']; total=sum(v['chosen'] for v in actions.values()); attack=sum(v['chosen'] for k,v in actions.items() if k.startswith('attack')); place=sum(v['chosen'] for k,v in actions.items() if k.startswith('place')); outcomes=diag.get('place_outcomes',{})
            lines.append(f"  CPU final/checkpoint diagnostic: night-deaths={diag.get('deaths_at_night')}, attack-share={attack/max(total,1):.3%}, place-share={place/max(total,1):.3%}, place-outcomes={outcomes}; diagnostic score={diag['score']['weighted_score']:.2f}%. All action counts/probabilities, inventory peaks and layer fractions are in JSON.")
            if t['full_1B']:
                ctl_diag = result['controls'][str(t['ownership']['seed'])]['diagnostics']
                lines.append(f"  Matched1B control night-deaths={ctl_diag['deaths_at_night']}; candidate death-rate change={ev['death_rate']-paired['death_rate']:+.3f}. Higher score is not a survival win; the late-frontier hit counts above distinguish mid-tier gains from new endgame progression.")
        else:
            lines.append('  CPU action diagnostic unavailable; no fabricated action/death-night results.')
    full_confirmation = next((t for t in result['trials'] if t['ownership']['name'] == 'A-3002' and t['full_1B']), None)
    if full_confirmation:
        ctl = result['controls']['3002']['summary']
        wall = full_confirmation['summary']['wall_seconds_including_validation']
        lines += ['', f"A3002 observed full1B completion: {wall:.1f}s versus cached control {ctl['wall_seconds_including_validation']:.1f}s. This small timing difference is not an isolated throughput claim; the score gain is evaluated at matched steps and the tables show matched-time evidence."]
    lines += ['', '## Limits', '', *['- '+s for s in result['limitations']], '',
              '- Prior width/memory/longer-budget studies were negative; no capacity or algorithm grid was launched. Release Gate1 remains open; no defaults/checkpoints promoted into the project.',
              '- No builds, lint, offline tests or formatters. Exercised checks were provenance/runtime protocol parity, actual process/GPU inspection, scheduled validation and bounded CPU diagnostics.', '',
              f"Compact evidence: `{output.name}.json`. Reproduction/supervision: `tools/headroom_study.py`; evidence exporter: `tools/headroom_report.py`.", '']
    output.with_suffix('.json').write_text(json.dumps(result, separators=(',', ':'), allow_nan=False)+'\n')
    output.with_suffix('.md').write_text('\n'.join(lines))


if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('root', type=Path); p.add_argument('--out', type=Path, required=True)
    args=p.parse_args(); export(args.root,args.out)
