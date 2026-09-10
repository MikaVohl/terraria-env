"""Fresh unshaped 100M PPO run using measured, semantics-preserving speedups.
Run with .venv/bin/python; --smoke exercises a separate 262,144-step run first.
Production modules and earlier experiment outputs are never modified.
"""
import argparse
import ast
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
SOURCE = OUT / 'source'
BATCH = 32768
REQUESTED = 100_000_000
ACTUAL = ((REQUESTED + BATCH - 1) // BATCH) * BATCH
THRESHOLDS = [1_000_000, 4_000_000, 8_000_000, 16_000_000, 24_000_000,
              32_000_000, 48_000_000, 64_000_000, 80_000_000, ACTUAL]


def setup():
    if (OUT / 'manifest.json').exists():
        manifest = json.loads((OUT / 'manifest.json').read_text())
        for rel, expected in manifest['source_sha256'].items():
            assert hashlib.sha256((SOURCE / rel).read_bytes()).hexdigest() == expected, rel
        assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == manifest['runner_sha256']
        for name, expected in manifest['library_sha256'].items():
            assert hashlib.sha256((OUT / name).read_bytes()).hexdigest() == expected, name
        return
    hashes = {}
    files = [*ROOT.glob('src/*.[ch]'), *ROOT.glob('include/*.h'),
             *ROOT.glob('python/terraria_lite/*.py'), *ROOT.glob('tools/*.py'),
             ROOT / 'tools/perf_probe.c', ROOT / 'pyproject.toml', ROOT / 'uv.lock']
    for src in files:
        rel = src.relative_to(ROOT)
        dest = SOURCE / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes()
        dest.write_bytes(data)
        hashes[str(rel)] = hashlib.sha256(data).hexdigest()
    build = ['cc', '-std=c11', '-O2', '-g', '-fPIC', '-Iinclude', '-Isrc']
    subprocess.run(build + ['-Dlight_recompute=light_reference', '-c', 'src/light.c',
                           '-o', str(OUT / 'light-ref.o')], cwd=SOURCE, check=True)
    for lib in ['reference', 'cached']:
        subprocess.run(build + ['-shared'] + (['-DPROBE_CACHE'] if lib == 'cached' else []) +
                       ['src/sim.c', 'src/worldgen.c', 'src/obs.c', 'src/capi.c',
                        'tools/perf_probe.c', str(OUT / 'light-ref.o'),
                        '-o', str(OUT / (lib + '.dylib'))], cwd=SOURCE, check=True)
    manifest = {
        'requested_steps': REQUESTED, 'actual_steps': ACTUAL,
        'rounding': 'Round upward to finish a PPO batch and meet the requested budget.',
        'initialization': 'fresh; no checkpoint loading', 'seed': 101,
        'envs': 256, 'rollout': 128, 'batch': BATCH, 'minibatch': 8192,
        'native_workers': 8, 'torch_cpu_threads': 2, 'device': 'mps',
        'lighting': 'experimental exact cache; serial environment registration',
        'sampling': 'existing CheckedSamplingPolicy, CPU multinomial on GPU probabilities',
        'reward': 'unchanged +1 achievements / -1 death; no progression shaping',
        'learning_rate': '.0003 linearly annealed over the complete run',
        'checkpoint_thresholds': THRESHOLDS,
        'validation_worlds': [1000001, 1000128], 'evaluation_sample_seed': 54321,
        'evaluation': 'CPU/reference lighting, batch 64; separate processes after training',
        'test_set': 'unused',
        'checkpoint_contract': 'inference weights only, not exact optimizer/RNG/environment resume state',
        'platform': platform.platform(), 'python': sys.version,
        'source_sha256': hashes,
        'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'library_sha256': {name: hashlib.sha256((OUT / name).read_bytes()).hexdigest()
                           for name in ['reference.dylib', 'cached.dylib']},
    }
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


def train(destination, steps):
    import ctypes
    import torch
    from terraria_lite import _lib
    import terraria_lite.ppo_agent as ppo
    from perf_probe import Batch

    torch.set_num_threads(2)
    assert torch.backends.mps.is_available(), 'MPS is required; no silent fallback'
    # Reuse the exact checked sampler already exercised in long runs and studies.
    tree = ast.parse((SOURCE / 'tools/scaling_study.py').read_text())
    node = next(n for n in ast.walk(tree)
                if isinstance(n, ast.ClassDef) and n.name == 'CheckedSamplingPolicy')
    namespace = {'ppo': ppo, 'torch': torch}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<checked sampler>', 'exec'), namespace)
    ppo.ActorCritic = namespace['CheckedSamplingPolicy']
    _lib.probe_workers.argtypes = [ctypes.c_int]
    _lib.probe_workers.restype = None
    _lib.probe_workers(8)
    ppo.VecTerraria = Batch
    cfg = ppo.Config(total_steps=steps, num_envs=256, rollout=128, device='mps',
                     seed=101, quiet=True, save='', init='', progress_coef=0.)
    (destination / 'config.json').write_text(json.dumps(asdict(cfg), indent=2) + '\n')
    (destination / 'runtime.json').write_text(json.dumps({'torch': torch.__version__,
        'mps_available': torch.backends.mps.is_available(), 'cpu_threads': torch.get_num_threads()}, indent=2) + '\n')
    targets = sorted({min(t, steps) for t in THRESHOLDS})
    torch.mps.synchronize()
    start = time.perf_counter()
    last = start
    events = []
    def checkpoint(agent, count, timing):
        nonlocal last
        now = time.perf_counter()
        if targets and count >= targets[0]:
            threshold = targets.pop(0)
            torch.mps.synchronize()
            state = {k: v.detach().cpu() for k, v in agent.state_dict().items()}
            assert all(bool(torch.isfinite(v).all()) for v in state.values()), 'nonfinite checkpoint'
            path = destination / f'step-{count}.pt'
            assert not path.exists(), path
            temp = path.with_suffix('.tmp')
            torch.save(state, temp)
            temp.replace(path)
            event = {'event': 'checkpoint', 'threshold': threshold, 'steps': count,
                     'wall_seconds': time.perf_counter() - start, 'file': path.name,
                     'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
            events.append(event)
            (destination / 'checkpoints.json').write_text(json.dumps(events, indent=2) + '\n')
            print(json.dumps(event), flush=True)
        if now - last >= 60:
            torch.mps.synchronize()
            elapsed = time.perf_counter() - start
            print(json.dumps({'event': 'progress', 'steps': count,
                              'target': steps, 'wall_seconds': elapsed,
                              'synchronized_sps': count / elapsed}), flush=True)
            last = time.perf_counter()
    summary = ppo.train(cfg, checkpoint_callback=checkpoint)
    torch.mps.synchronize()
    summary['synchronized_wall_seconds'] = time.perf_counter() - start
    summary['synchronized_sps'] = summary['steps'] / summary['synchronized_wall_seconds']
    assert summary['steps'] == steps and not targets
    (destination / 'training.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({'event': 'training_complete', **summary}), flush=True)


def evaluate(checkpoint):
    import torch
    from terraria_lite.ppo_eval import evaluate as evaluate_agent, load_agent
    torch.set_num_threads(2)
    result = evaluate_agent(load_agent(checkpoint), list(range(1000001, 1000129)),
                            sample_seed=54321, num_envs=64)
    assert sorted(r['seed'] for r in result['records']) == list(range(1000001, 1000129))
    checkpoint.with_suffix('.eval.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'event': 'evaluation', 'checkpoint': checkpoint.name,
                     **{k: v for k, v in result.items() if k != 'records'}}), flush=True)


def logged_child(args, log, library):
    env = {**os.environ, 'TERRARIA_LITE_LIB': str(OUT / library),
           'PYTHONPATH': str(SOURCE / 'python') + os.pathsep + str(SOURCE / 'tools'),
           'PYTHONUNBUFFERED': '1'}
    with log.open('x') as output:
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *args],
                                   cwd=SOURCE, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            output.write(line); output.flush()
            print(line, end='', flush=True)
        code = process.wait()
    if code:
        raise RuntimeError(f'child exited {code}; see {log}')


def main(a):
    setup()
    dest = OUT / ('smoke' if a.smoke else 'training')
    dest.mkdir(exist_ok=False)
    steps = 262144 if a.smoke else ACTUAL
    print(json.dumps({'event': 'start', 'requested': 262144 if a.smoke else REQUESTED,
                      'actual': steps, 'directory': str(dest)}), flush=True)
    logged_child(['--child', 'train', '--destination', str(dest), '--steps', str(steps)],
                 dest / 'train.log', 'cached.dylib')
    checkpoints = sorted(dest.glob('step-*.pt'), key=lambda p: int(p.stem.split('-')[1]))
    for path in checkpoints:
        logged_child(['--child', 'eval', '--checkpoint', str(path)],
                     path.with_suffix('.eval.log'), 'reference.dylib')
    (dest / 'COMPLETE').write_text('Training and all validation checkpoint evaluations completed.\n')
    print('RUN COMPLETE', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--child', choices=['train', 'eval'])
    p.add_argument('--destination', type=Path)
    p.add_argument('--steps', type=int)
    p.add_argument('--checkpoint', type=Path)
    a = p.parse_args()
    if a.child == 'train':
        train(a.destination, a.steps)
    elif a.child == 'eval':
        evaluate(a.checkpoint)
    else:
        main(a)
