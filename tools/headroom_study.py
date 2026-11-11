"""Detached, ownership-scoped supervisor for the fixed 2026-11-11 PPO study.

Run prepare, then run once on eg18. No learner modifications or checkpoint
restarts: both initial learners remain live until the bounded screen decision.
"""
import argparse
import ctypes
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import shutil

BASE = Path('/home/mvohl/Projects/RL-heldaim')
ROOT = Path('/home/mvohl/Projects/RL-headroom-20261111')
PYTHON = '/home/mvohl/Projects/RL/.venv/bin/python'
LIB_HASH = 'f6413078a1684d54b65e5f70f028e59a5ee1e95670d093a03fdee68d1e30e971'
FULL = 1073741824
SCREEN = 268435456
INTERVAL = 134217728


def stamp(t=None):
    return dt.datetime.fromtimestamp(time.time() if t is None else t, dt.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    temp.replace(path)


def load(path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def event(kind, **fields):
    row = {'time': stamp(), 'kind': kind}
    row.update(fields)
    with (ROOT / 'events.jsonl').open('a') as f:
        f.write(json.dumps(row, allow_nan=False) + '\n')


def ticks(pid):
    try:
        return Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    except (FileNotFoundError, ProcessLookupError):
        return None


def owned(job):
    if ticks(job['pid']) != job['start_ticks']:
        return False
    try:
        return str(ROOT).encode() in Path(f"/proc/{job['pid']}/cmdline").read_bytes()
    except FileNotFoundError:
        return False


def group_exists(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def stop(job, reason):
    if not owned(job):
        return
    event('stop_requested', trial=job['name'], pid=job['pid'], reason=reason)
    os.killpg(job['pgid'], signal.SIGCONT)
    os.killpg(job['pgid'], signal.SIGTERM)
    limit = min(time.time() + 5, load(ROOT / 'budget.json')['deadline_epoch'] - 1)
    while time.time() < limit and group_exists(job['pgid']):
        time.sleep(.2)
    if group_exists(job['pgid']):
        os.killpg(job['pgid'], signal.SIGKILL)
    event('stop_signals_completed', trial=job['name'], reason=reason)


def prepare():
    ROOT.mkdir(exist_ok=False)
    (ROOT / 'tools').mkdir()
    package = ROOT / 'python/terraria_lite'
    package.mkdir(parents=True)
    controls = ROOT / 'controls'
    controls.mkdir()
    records = []
    for seed in (3001, 3002):
        src = BASE / f'experiments/eg18-v10heldtight-20261111/v10ht_gen_1B-{seed}/runs/v10_gen_g9999-{seed}'
        proto = load(src / 'protocol.json')
        assert proto['environment_version'] == 10 and proto['episode_steps'] == 10000
        assert proto['validation_seeds'] == [23000001, 23000128]
        assert proto['sampler_seed'] == 54321 and proto['parameters'] == 487896
        assert proto['implementation_sha256']['libterraria.so'] == LIB_HASH
        dst = controls / str(seed)
        dst.mkdir()
        for name in ('protocol', 'curve', 'summary', 'diag'):
            shutil.copy2(src / f'{name}.json', dst / f'{name}.json')
        records.append({'seed': seed, 'source': str(src), 'files': {p.name: digest(p) for p in dst.iterdir()},
                        'checkpoints': {p.name: digest(p) for p in src.glob('step-*.pt')}})
        if seed == 3001:
            for name, expected in proto['implementation_sha256'].items():
                source = src / 'implementation' / name
                assert digest(source) == expected, name
                if source.suffix == '.py':
                    shutil.copy2(source, package / name)
    library = BASE / 'perf/v7/build-v10/libterraria.so'
    assert digest(library) == LIB_HASH
    (ROOT / 'inputs').mkdir()
    shutil.copy2(library, ROOT / 'inputs/libterraria.so')
    for name in ('iterate_ppo.py', 'policy_diagnostics.py'):
        shutil.copy2(BASE / 'tools' / name, ROOT / 'tools' / name)
    assert digest(ROOT / 'tools/iterate_ppo.py') == load(controls / '3001/protocol.json')['driver_sha256']
    for seed in (3001, 3002):
        control = load(controls / str(seed) / 'protocol.json')
        for source in package.glob('*.py'):
            assert digest(source) == control['implementation_sha256'][source.name], (seed, source.name)
    shutil.copy2(Path(__file__), ROOT / 'headroom_study.py')
    manifest = {str(p.relative_to(ROOT)): digest(p) for folder in ('python', 'inputs', 'tools', 'controls')
                for p in sorted((ROOT / folder).rglob('*')) if p.is_file()}
    manifest['headroom_study.py'] = digest(ROOT / 'headroom_study.py')
    immutable = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    save(ROOT / 'manifest.json', {'sha256': immutable, 'files': manifest, 'library_sha256': LIB_HASH,
                                 'controls': records, 'created': stamp(), 'engine_commit': '4ede178',
                                 'source_policy': 'cached control implementation, exact per-file hashes',
                                 'model_runtime': 'not exposed to worker; parent reports task override amd-unified/gpt-6.1-sol:high'})
    print(json.dumps({'study': str(ROOT), 'immutable_sha256': immutable, 'control_parity': 'exact'}))


def preflight():
    hip = ctypes.CDLL('libamdhip64.so')
    count = ctypes.c_int()
    assert hip.hipGetDeviceCount(ctypes.byref(count)) == 0 and count.value == 2
    mapping = []
    for index, permitted in enumerate((6, 7)):
        bus = ctypes.create_string_buffer(64)
        assert hip.hipDeviceGetPCIBusId(bus, len(bus), index) == 0
        assert hip.hipSetDevice(index) == 0 and hip.hipFree(None) == 0
        mapping.append({'hip': permitted, 'visible_index': index, 'pci_bus': bus.value.decode()})
    save(ROOT / 'hip_mapping.json', {'time': stamp(), 'HIP_VISIBLE_DEVICES': os.environ['HIP_VISIBLE_DEVICES'], 'devices': mapping})
    print(json.dumps(mapping), flush=True)


def watchdog():
    budget = load(ROOT / 'budget.json')
    assert isinstance(load(ROOT / 'ownership.json'), list)
    save(ROOT / 'watchdog_ready.json', {'pid': os.getpid(), 'time': stamp(), 'deadline': budget['deadline']})
    while time.time() < budget['deadline_epoch'] - 10:
        if (ROOT / 'gpu_closed.json').exists():
            return
        time.sleep(min(1, max(.05, budget['deadline_epoch'] - 10 - time.time())))
    event('watchdog_deadline_enforcement', deadline=budget['deadline'])
    for job in load(ROOT / 'ownership.json', []):
        stop(job, 'common 90-minute GPU deadline')
    save(ROOT / 'watchdog_fired.json', {'time': stamp(), 'deadline': budget['deadline']})


def environment(hip):
    env = os.environ.copy()
    env.update(HIP_VISIBLE_DEVICES=str(hip), PYTHONPATH=str(ROOT / 'python'),
               TERRARIA_LITE_LIB=str(ROOT / 'inputs/libterraria.so'), PYTHONUNBUFFERED='1',
               OMP_NUM_THREADS='4', MKL_NUM_THREADS='4',
               TORCHINDUCTOR_CACHE_DIR=str(ROOT / f'cache-hip{hip}'))
    return env


def argv(candidate, seed, out):
    args = [PYTHON, str(ROOT / 'tools/iterate_ppo.py'), '--out', str(out),
            '--steps', str(FULL), '--seed', str(seed), '--interval', str(INTERVAL),
            '--threads', '4', '--architecture', 'targets', '--hidden', '0', '--depth', '2',
            '--cell-width', '32', '--epochs', '4', '--minibatches', '16', '--gamma', '.9999',
            '--lr', '.0003', '--achievement-reward', 'equal', '--novelty', '.01', '--unimix', '.01',
            '--potential', '0', '--episode-steps', '0', '--device', 'cuda', '--collect-device', 'cuda',
            '--evaluation-device', 'cpu', '--async-evaluation', '--sim-workers', '12',
            '--validation-episodes', '128', '--validation-seed-start', '23000001',
            '--test-seed-start', '25000001', '--native-autoreset', '--compact-obs',
            '--compile', '--bf16', '--fused-adam', '--compile-all', '--entropy', '.01' if candidate == 'A' else '.03',
            '--gae-lambda', '.99' if candidate == 'A' else '.995',
            '--envs', '1024' if candidate == 'A' else '512', '--rollout', '128' if candidate == 'A' else '256']
    return args


def launch(candidate, seed, hip, cpus, jobs):
    assert len(jobs) < 3 and time.time() < load(ROOT / 'budget.json')['deadline_epoch'] - 60
    name = f'{candidate}-{seed}'
    assert not any(j['name'] == name for j in jobs)
    out = ROOT / 'runs' / name
    assert not out.exists()
    command = ['taskset', '-c', cpus, *argv(candidate, seed, out)]
    with (ROOT / f'{name}.log').open('x') as log:
        p = subprocess.Popen(command, cwd=ROOT, env=environment(hip), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    job = {'name': name, 'candidate': candidate, 'seed': seed, 'hip': hip, 'cpus': cpus,
           'pid': p.pid, 'pgid': p.pid, 'start_ticks': ticks(p.pid), 'command': command,
           'start_epoch': time.time(), 'start': stamp(), 'status': 'running'}
    jobs.append(job)
    save(ROOT / 'ownership.json', jobs)
    event('candidate_started', **job)
    return p


def curves(job):
    return load(ROOT / 'runs' / job['name'] / 'curve.json', [])


def parity(job):
    proto = load(ROOT / 'runs' / job['name'] / 'protocol.json')
    if not proto:
        return False
    baseline = load(ROOT / 'controls' / str(job['seed']) / 'protocol.json')
    changes = {'ent_coef'} if job['candidate'] == 'A' else {'gae_lambda', 'num_envs', 'rollout'}
    for key, val in baseline['config'].items():
        if key not in changes:
            assert proto['config'][key] == val, (job['name'], key)
    for key in ('implementation_sha256', 'driver_sha256', 'parameters', 'reward', 'validation_seeds',
                'sampler_seed', 'episode_steps', 'training_objective', 'async_evaluation', 'torch_threads', 'torch'):
        assert proto[key] == baseline[key], (job['name'], key)
    return True


def diagnostics(jobs):
    processes = []
    for i, job in enumerate(jobs):
        rows = curves(job)
        if not rows:
            continue
        step = rows[-1]['steps']
        out = ROOT / 'runs' / job['name']
        cmd = ['taskset', '-c', '348-371' if i % 2 == 0 else '372-383', PYTHON,
               str(ROOT / 'tools/policy_diagnostics.py'), str(out / f'step-{step}.pt'), '--out', str(out / 'diag.json'),
               '--episodes', '128', '--seed-start', '23000001']
        env = environment('')
        env['HIP_VISIBLE_DEVICES'] = ''
        with (ROOT / f"{job['name']}-diag.log").open('w') as log:
            p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        processes.append((p, job['name']))
    limit = time.time() + 900
    for p, name in processes:
        try:
            code = p.wait(timeout=max(.1, limit - time.time()))
            event('cpu_diagnostic_finished', trial=name, returncode=code)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            event('cpu_diagnostic_censored', trial=name, reason='15-minute shared CPU diagnostic limit')


def persist_status(jobs):
    save(ROOT / 'ownership.json', jobs)
    save(ROOT / 'status.json', {'time': stamp(), 'jobs': jobs, 'last_evaluations': {j['name']: [
        {'steps': r['steps'], 'score': r['evaluation']['weighted_score'], 'seconds': r['checkpoint_elapsed_seconds']}
        for r in curves(j)] for j in jobs}})


def recover():
    # One parent-authorized initialization retry per logical A/B trial, not a
    # checkpoint restart. Preserve the failed process attempts and budget clock.
    previous = load(ROOT / 'ownership.json')
    assert previous and all(not group_exists(j['pgid']) for j in previous)
    assert not list((ROOT / 'runs').glob('*/step-*.pt'))
    archived = ROOT / 'startup-failure'
    archived.mkdir(exist_ok=False)
    persist_status(previous)  # Exercise the corrected nonempty status/write path.
    for name in ('ownership.json', 'status.json', 'run.lock', 'watchdog.log', 'supervision.json',
                 'preflight.log', 'hip_mapping.json', 'launch.json', 'events.jsonl', 'error.json',
                 'gpu_closed.json', 'complete.json', 'A-3001.log', 'B-3001.log', 'runs'):
        path = ROOT / name
        if path.exists():
            path.rename(archived / name)
    save(ROOT / 'recovery_authorization.json', {'time': stamp(),
         'authorization': 'Main explicitly authorized one operational retry each for logical A3001/B3001; max3 counts logical trial identities, failed process attempts retained; original deadline unchanged',
         'initial_attempt_training_steps': 'unknown; no checkpoint is not proof of zero steps',
         'supervisor_revision_sha256': digest(Path(__file__))})
    run()


def run():
    lock = ROOT / 'run.lock'
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, str(os.getpid()).encode()); os.close(fd)
    budget = load(ROOT / 'budget.json')
    if budget is None:
        start = time.time()
        budget = {'start_epoch': start, 'start': stamp(start), 'deadline_epoch': start + 5400,
                  'deadline': stamp(start + 5400), 'max_gpu_hours': 3, 'clock_scope': 'before first HIP runtime preflight'}
        save(ROOT / 'budget.json', budget)
    assert time.time() < budget['deadline_epoch'] - 60
    save(ROOT / 'ownership.json', [])
    with (ROOT / 'watchdog.log').open('x') as log:
        wd = subprocess.Popen([sys.executable, str(Path(__file__)), 'watchdog'], stdout=log,
                              stderr=subprocess.STDOUT, start_new_session=True)
    save(ROOT / 'supervision.json', {'pid': os.getpid(), 'pgid': os.getpgrp(), 'watchdog_pid': wd.pid,
                                    'watchdog_pgid': wd.pid, 'budget': budget})
    persist_status([])
    ready_limit = time.time() + 5
    while not (ROOT / 'watchdog_ready.json').exists() and time.time() < ready_limit:
        assert wd.poll() is None, 'watchdog exited before readiness'
        time.sleep(.05)
    assert load(ROOT / 'watchdog_ready.json')['pid'] == wd.pid
    event('pre_gpu_supervision_ready', watchdog_pid=wd.pid, deadline=budget['deadline'])
    jobs, processes = [], []
    try:
        with (ROOT / 'preflight.log').open('x') as log:
            check = subprocess.run([PYTHON, str(Path(__file__)), 'preflight'],
                                   env=environment('6,7'), stdout=log, stderr=subprocess.STDOUT, timeout=45)
        assert check.returncode == 0, 'HIP mapping preflight failed'
        (ROOT / 'runs').mkdir()
        processes.append(launch('A', 3001, 6, '300-323', jobs))
        processes.append(launch('B', 3001, 7, '324-347', jobs))
        save(ROOT / 'launch.json', {'time': stamp(), 'jobs': jobs, 'mapping': load(ROOT / 'hip_mapping.json'),
                                   'budget': budget, 'immutable_sha256': load(ROOT / 'manifest.json')['sha256']})
        while time.time() < budget['deadline_epoch'] - 30:
            for job, p in zip(jobs, processes):
                if p.poll() is not None and job['status'] == 'running':
                    job.update(status='finished' if p.returncode == 0 else 'failed', returncode=p.returncode,
                               end_epoch=time.time(), end=stamp())
                    event('candidate_exited', trial=job['name'], returncode=p.returncode)
                if job['status'] == 'running':
                    parity(job)
            if not (ROOT / 'selection.json').exists():
                rows = [[r for r in curves(j) if r['steps'] == SCREEN] for j in jobs[:2]]
                if all(rows):
                    baseline = next(r for r in load(ROOT / 'controls/3001/curve.json') if r['steps'] == SCREEN)
                    scores = [r[0]['evaluation']['weighted_score'] for r in rows]
                    stable = [all(math.isfinite(float(r[0]['profile'][k])) for k in ('policy_entropy', 'approx_kl', 'explained_variance'))
                              and r[0]['profile']['approx_kl'] < .1 and r[0]['profile']['explained_variance'] > .9 for r in rows]
                    # Full completion of a fresh confirmation is not a prerequisite:
                    # matched-screen confirmation remains useful if later censored.
                    feasible = [budget['deadline_epoch'] - time.time() >
                                1.1 * (FULL / SCREEN - 1) * r[0]['checkpoint_elapsed_seconds'] + 60 for r in rows]
                    promising = [s >= baseline['evaluation']['weighted_score'] - 2 and ok and f
                                 for s, ok, f in zip(scores, stable, feasible)]
                    eligible = [i for i, yes in enumerate(promising) if yes]
                    winner = max(eligible, key=lambda i: scores[i]) if eligible else None
                    decision = {'time': stamp(), 'screen_steps': SCREEN, 'scores': dict(zip(('A', 'B'), scores)),
                                'baseline_score': baseline['evaluation']['weighted_score'], 'stable': stable,
                                'live_continuation_budget_feasible': feasible, 'winner': None if winner is None else jobs[winner]['candidate'],
                                'reason': 'provisional score/stability/live-continuation feasibility screen; not a ranking' if winner is not None else
                                          'neither within 2pp of paired control with stable telemetry and live-continuation budget',
                                'live_state_preserved': winner is not None, 'checkpoint_restart': False}
                    save(ROOT / 'selection.json', decision)
                    event('screen_decision', **decision)
                    for i in range(2):
                        if i != winner:
                            stop(jobs[i], 'not promoted at bounded screen')
                            jobs[i].update(status='screen_stopped', end_epoch=time.time(), end=stamp(), stop_reason=decision['reason'])
                    if winner is not None:
                        loser = 1 - winner
                        processes.append(launch(jobs[winner]['candidate'], 3002, jobs[loser]['hip'], jobs[loser]['cpus'], jobs))
                    else:
                        break
                elif any(p.poll() is not None and not rows[i] for i, p in enumerate(processes[:2])):
                    save(ROOT / 'selection.json', {'winner': None, 'time': stamp(), 'reason': 'candidate exited before common screen; no promotion'})
                    break
            persist_status(jobs)
            if all(p.poll() is not None for p in processes):
                break
            time.sleep(2)
    except BaseException as exc:
        event('supervisor_error', error=repr(exc))
        save(ROOT / 'error.json', {'time': stamp(), 'error': repr(exc)})
    finally:
        for job, p in zip(jobs, processes):
            if p.poll() is None:
                stop(job, 'common budget or supervisor shutdown')
                job.update(status='budget_censored' if time.time() >= budget['deadline_epoch'] - 30 else 'stopped',
                           end_epoch=time.time(), end=stamp(), stop_reason='common budget or supervisor shutdown')
            elif 'end_epoch' not in job:
                job.update(status='finished' if p.returncode == 0 else 'failed', returncode=p.returncode,
                           end_epoch=time.time(), end=stamp())
            p.wait(timeout=10)
        save(ROOT / 'ownership.json', jobs)
        save(ROOT / 'gpu_closed.json', {'time': stamp(), 'epoch': time.time(), 'deadline': budget['deadline'],
                                       'deadline_respected': time.time() <= budget['deadline_epoch'],
                                       'owned_groups_remaining': [j['pgid'] for j in jobs if group_exists(j['pgid'])],
                                       'gpu_job_hours_upper_bound': (sum(j['end_epoch'] - j['start_epoch'] for j in jobs)
                                           + sum(j['end_epoch'] - j['start_epoch'] for j in load(ROOT / 'startup-failure/ownership.json', []))) / 3600,
                                       'reserved_test_worlds_used': 0, 'fresh_control_jobs': 0})
    diagnostics(jobs)
    save(ROOT / 'complete.json', {'time': stamp(), 'jobs': jobs, 'selection': load(ROOT / 'selection.json'),
                                  'gpu_closed': load(ROOT / 'gpu_closed.json')})
    print(json.dumps(load(ROOT / 'complete.json')), flush=True)


def confirm():
    # Parent amendment: the two screening learners were already stopped. Never
    # reconstruct their optimizer/RNG state; only the planned third identity runs.
    jobs = load(ROOT / 'ownership.json')
    assert len(jobs) == 2 and {j['name'] for j in jobs} == {'A-3001', 'B-3001'}
    assert all(not group_exists(j['pgid']) for j in jobs)
    assert load(ROOT / 'promotion_authorization.json')['candidate'] == 'A'
    budget = load(ROOT / 'budget.json')
    assert time.time() < budget['deadline_epoch'] - 60
    fd = os.open(ROOT / 'confirmation.lock', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.write(fd, str(os.getpid()).encode()); os.close(fd)
    archived = ROOT / 'screen-close'
    archived.mkdir(exist_ok=False)
    for name in ('complete.json', 'gpu_closed.json', 'watchdog.log', 'watchdog_ready.json',
                 'supervision.json', 'selection.json', 'status.json'):
        source = ROOT / name
        if source.exists():
            source.rename(archived / name)
    original = load(archived / 'selection.json')
    selection = dict(original, winner='A', live_state_preserved=False,
                     reason='Parent promotion amendment: positive A screen; collect planned A3002 confirmation within original deadline, no A3001 restart',
                     amendment_time=stamp(), original_screen_decision=original)
    save(ROOT / 'selection.json', selection)
    persist_status(jobs)
    with (ROOT / 'watchdog.log').open('x') as log:
        wd = subprocess.Popen([sys.executable, str(Path(__file__)), 'watchdog'], stdout=log,
                              stderr=subprocess.STDOUT, start_new_session=True)
    save(ROOT / 'supervision.json', {'pid': os.getpid(), 'pgid': os.getpgrp(), 'watchdog_pid': wd.pid,
                                    'watchdog_pgid': wd.pid, 'budget': budget, 'phase': 'authorized A3002 confirmation'})
    limit = time.time() + 5
    while not (ROOT / 'watchdog_ready.json').exists() and time.time() < limit:
        assert wd.poll() is None
        time.sleep(.05)
    assert load(ROOT / 'watchdog_ready.json')['pid'] == wd.pid
    event('confirmation_pre_gpu_supervision_ready', watchdog_pid=wd.pid, deadline=budget['deadline'])
    p = launch('A', 3002, 6, '300-323', jobs)
    job = jobs[-1]
    try:
        while p.poll() is None and time.time() < budget['deadline_epoch'] - 10:
            parity(job)
            persist_status(jobs)
            time.sleep(2)
    except BaseException as exc:
        event('confirmation_supervisor_error', error=repr(exc))
        save(ROOT / 'confirmation_error.json', {'time': stamp(), 'error': repr(exc)})
    finally:
        if p.poll() is None:
            stop(job, 'common deadline or confirmation supervisor shutdown')
            job.update(status='budget_censored', stop_reason='common deadline or confirmation supervisor shutdown')
        else:
            job.update(status='finished' if p.returncode == 0 else 'failed', returncode=p.returncode)
        p.wait(timeout=10)
        job.update(end_epoch=time.time(), end=stamp())
        persist_status(jobs)
        save(ROOT / 'gpu_closed.json', {'time': stamp(), 'epoch': time.time(), 'deadline': budget['deadline'],
             'deadline_respected': time.time() <= budget['deadline_epoch'],
             'owned_groups_remaining': [j['pgid'] for j in jobs if group_exists(j['pgid'])],
             'gpu_job_hours_upper_bound': (sum(j['end_epoch'] - j['start_epoch'] for j in jobs)
                 + sum(j['end_epoch'] - j['start_epoch'] for j in load(ROOT / 'startup-failure/ownership.json', []))) / 3600,
             'reserved_test_worlds_used': 0, 'fresh_control_jobs': 0})
    diagnostics([job])
    save(ROOT / 'complete.json', {'time': stamp(), 'jobs': jobs, 'selection': selection,
                                  'gpu_closed': load(ROOT / 'gpu_closed.json')})
    print(json.dumps(load(ROOT / 'complete.json')), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'run', 'recover', 'confirm', 'preflight', 'watchdog'))
    globals()[parser.parse_args().mode]()
