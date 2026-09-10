"""Controlled checked-sampling experiments; production code is not modified.
Run: .venv/bin/python experiments/perf-followup-20260910/study.py
Use --smoke before the full study. All timed children run sequentially.
"""
import argparse
import ast
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import asdict
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import random
import subprocess
import sys
import time

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
SOURCE = OUT / 'source'


def instrument_train(ppo, phase):
    """Wrap existing AST statements, without replacing training computations."""
    tree = ast.parse(inspect.getsource(ppo.train))
    fn = tree.body[0]
    loop = next(n for n in fn.body if isinstance(n, ast.For) and ast.unparse(n.target) == 'it')
    collect = next(n for n in loop.body if isinstance(n, ast.For) and ast.unparse(n.target) == 't')

    def wrap(label, nodes):
        return ast.With(items=[ast.withitem(context_expr=ast.Call(
            func=ast.Name(id='_study_phase', ctx=ast.Load()),
            args=[ast.Constant(label)], keywords=[]))], body=nodes)

    # Identify complete statement boundaries in the existing trainer.
    def starts(nodes, text):
        matches = [i for i, n in enumerate(nodes) if ast.unparse(n).startswith(text)]
        assert len(matches) == 1, (text, matches)
        return matches[0]

    body = collect.body
    policy = starts(body, 'with torch.no_grad():')
    saved = starts(body, 'act_b[t], logp_b[t], val_b[t] =')
    step = starts(body, 'obs, msk, r, term, trunc, final, finished =')
    collect.body = [wrap('rollout_buffer', body[:policy]),
                    wrap('policy', body[policy:saved]),
                    wrap('rollout_buffer', body[saved:step]),
                    wrap('step_and_action_retrieval', body[step:step+1]),
                    wrap('transfers_bootstrap_bookkeeping', body[step+1:])]
    ast.fix_missing_locations(tree)
    body = loop.body
    gae = starts(body, 'with torch.no_grad():')
    update = starts(body, 'idx = np.arange(cfg.batch)')
    end_update = starts(body, 'optimisation_seconds +=')
    report = starts(body, 'y = b_ret.cpu().numpy()')
    loop.body = body[:gae] + [wrap('gae_and_flatten', body[gae:update]),
                             wrap('ppo_updates', body[update:end_update])] + body[end_update:report] + [wrap('reporting', body[report:])]
    ast.fix_missing_locations(tree)
    generated = ast.unparse(tree)
    (OUT / 'instrumented_train.py').write_text(generated + '\n')
    namespace = dict(vars(ppo), _study_phase=phase)
    exec(compile(tree, str(OUT / 'instrumented_train.py'), 'exec'), namespace)
    return namespace['train']


def child(a):
    import ctypes
    import numpy as np
    import torch
    from terraria_lite import SPEC, _lib
    import terraria_lite.ppo_agent as ppo
    from perf_probe import Batch

    torch.set_num_threads(2)
    assert torch.backends.mps.is_available()
    _lib.probe_workers.argtypes = [ctypes.c_int]
    _lib.probe_workers(a.workers)
    # Execute the exact existing checked sampler, not a second implementation.
    tree = ast.parse((SOURCE / 'tools/scaling_study.py').read_text())
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == 'CheckedSamplingPolicy')
    namespace = {'ppo': ppo, 'torch': torch}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<existing checked sampler>', 'exec'), namespace)
    checked = namespace['CheckedSamplingPolicy']
    ppo.ActorCritic = checked
    ppo.VecTerraria = Batch
    totals = defaultdict(float)
    counts = defaultdict(int)
    enabled = False

    @contextmanager
    def phase(name):
        if not enabled:
            yield
            return
        torch.mps.synchronize()
        start = time.perf_counter()
        try:
            yield
        finally:
            torch.mps.synchronize()
            totals[name] += time.perf_counter() - start
            counts[name] += 1

    # In profiling only, split the policy at statement boundaries and time the
    # native C call separately inside Batch.step. Nested measurements are marked
    # inclusive and must not be added to their parents.
    if a.profile:
        act_tree = ast.parse(ast.unparse(next(n for n in node.body if isinstance(n, ast.FunctionDef) and n.name == 'act')))
        act = act_tree.body[0]
        sample = next(n for n in act.body if isinstance(n, ast.If) and ast.unparse(n.test) == 'action is None')
        def policy_wrap(name, body):
            return ast.With(items=[ast.withitem(context_expr=ast.Call(func=ast.Name(id='_study_phase', ctx=ast.Load()), args=[ast.Constant(name)], keywords=[]))], body=body)
        at = act.body.index(sample)
        sample.body = [policy_wrap('policy_sampling_inclusive', sample.body)]
        act.body = [policy_wrap('policy_forward_distribution', act.body[:at]), sample,
                    policy_wrap('policy_logprob_entropy_value', act.body[at+1:])]
        ast.fix_missing_locations(act_tree)
        ns = dict(checked.act.__globals__, _study_phase=phase)
        exec(compile(act_tree, '<profiled checked sampler>', 'exec'), ns)
        # Detailed policy timers only during rollout (updates have supplied actions).
        profiled_act = ns['act']
        def act_wrapper(self, x, action=None, mask=None):
            if action is not None:
                return checked.act(self, x, action, mask)
            return profiled_act(self, x, action, mask)
        class ProfilePolicy(checked):
            act = act_wrapper
        ppo.ActorCritic = ProfilePolicy
        native = _lib.probe_batch
        native.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
        native.restype = None
        class NativeTimer:
            def __call__(self, *args):
                with phase('native_step_inclusive'):
                    return native(*args)
        _lib.probe_batch = NativeTimer()

    cfg = ppo.Config(total_steps=a.steps, num_envs=256, rollout=128,
                     device='mps', seed=101, quiet=True, save='',
                     init=str(OUT/'mature.pt') if a.workload == 'mature' else '',
                     anneal_lr=False, lr=0.00015, progress_coef=0.)
    trainer = instrument_train(ppo, phase) if a.profile else ppo.train
    warmup_steps = 4 * cfg.batch
    measured_start = None
    measured_end = None
    final_hash = None
    def callback(agent, steps, timing):
        nonlocal enabled, measured_start, measured_end, final_hash
        if steps == warmup_steps:
            torch.mps.synchronize()
            measured_start = time.perf_counter()
            enabled = True
        if steps == a.steps:
            torch.mps.synchronize()
            measured_end = time.perf_counter()
            enabled = False
            h = hashlib.sha256()
            for key, value in agent.state_dict().items():
                value = value.detach().cpu()
                assert bool(torch.isfinite(value).all()), key
                h.update(key.encode()); h.update(value.numpy().tobytes())
            final_hash = h.hexdigest()
    torch.mps.synchronize()
    start = time.perf_counter()
    result = trainer(cfg, checkpoint_callback=callback)
    torch.mps.synchronize()
    wall = time.perf_counter() - start
    measured = measured_end - measured_start
    assert measured > 0
    row = {'workload': a.workload, 'workers': a.workers, 'library': a.library,
           'profile': a.profile, 'steps': a.steps, 'warmup_steps': warmup_steps,
           'measured_steps': a.steps-warmup_steps, 'measured_seconds': measured,
           'measured_sps': (a.steps-warmup_steps)/measured,
           'wall_seconds': wall, 'final_model_sha256': final_hash,
           'phases_seconds': dict(totals), 'phase_calls': dict(counts),
           'config': asdict(cfg), 'training': result}
    print(json.dumps(row), flush=True)


def setup():
    if (OUT/'manifest.json').exists():
        return
    sources = [*ROOT.glob('src/*.[ch]'), *ROOT.glob('include/*.h'),
               *ROOT.glob('python/terraria_lite/*.py'), *ROOT.glob('tools/*.py'),
               ROOT/'tools/perf_probe.c']
    hashes = {}
    for src in sources:
        rel = src.relative_to(ROOT)
        dest = SOURCE/rel; dest.parent.mkdir(parents=True, exist_ok=True)
        data = src.read_bytes(); dest.write_bytes(data)
        hashes[str(rel)] = hashlib.sha256(data).hexdigest()
    checkpoint = ROOT/'experiments/scaling-checked-20260909/32000000/step-31981568.pt'
    data = checkpoint.read_bytes(); (OUT/'mature.pt').write_bytes(data)
    build = ['cc', '-std=c11', '-O2', '-g', '-fPIC', '-Iinclude', '-Isrc']
    subprocess.run(build+['-Dlight_recompute=light_reference', '-c', 'src/light.c', '-o', str(OUT/'light-ref.o')], cwd=SOURCE, check=True)
    for lib in ['reference', 'cached']:
        subprocess.run(build+['-shared']+(['-DPROBE_CACHE'] if lib=='cached' else [])+
                       ['src/sim.c','src/worldgen.c','src/obs.c','src/capi.c','tools/perf_probe.c',str(OUT/'light-ref.o'),'-o',str(OUT/(lib+'.dylib'))], cwd=SOURCE, check=True)
    manifest = {'platform': platform.platform(), 'source_sha256': hashes,
                'mature_checkpoint': str(checkpoint.relative_to(ROOT)),
                'mature_checkpoint_sha256': hashlib.sha256(data).hexdigest(),
                'design': 'Sequential randomized complete blocks; 256 envs, rollout 128, fixed LR .00015, seed 101. 4 warmup updates, 12 measured updates. Mature starts from final 32M weights with fresh Adam and fresh environments: not resumed learning. Profiled timings serialize MPS and are diagnostic only.',
                'python': sys.version}
    (OUT/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')


def run(a):
    setup()
    env = {**os.environ, 'PYTHONPATH': str(SOURCE/'python')+os.pathsep+str(SOURCE/'tools'), 'PYTHONUNBUFFERED':'1'}
    if a.smoke:
        jobs = [('mature','cached',4,False,0), ('mature','cached',4,True,0)]
        steps = 196608
        dest = OUT/'smoke.jsonl'
    else:
        steps = 524288
        jobs = []
        rng = random.Random(20260910)
        for repeat in range(3):
            block = [('mature',lib,w,False,repeat) for lib in ['reference','cached'] for w in [1,2,4,6,8]]
            rng.shuffle(block); jobs.extend(block)
        for repeat in range(2):
            block = [('fresh',lib,w,False,repeat) for lib in ['reference','cached'] for w in [1,4,8]]
            rng.shuffle(block); jobs.extend(block)
        jobs += [('mature','cached',4,True,r) for r in range(3)]
        jobs += [('fresh','cached',4,True,0)]
        dest = OUT/'results.jsonl'
    with dest.open('x') as output:
        for index,(workload,lib,workers,profile,repeat) in enumerate(jobs):
            args = [sys.executable,str(Path(__file__).resolve()),'--child','--workload',workload,'--library',lib,'--workers',str(workers),'--steps',str(steps)]
            if profile: args.append('--profile')
            child_env = dict(env,TERRARIA_LITE_LIB=str(OUT/(lib+'.dylib')))
            result = subprocess.run(args, env=child_env, cwd=SOURCE, text=True, capture_output=True, timeout=240)
            (OUT/f'{dest.stem}-{index:02d}.log').write_text(result.stdout+result.stderr)
            if result.returncode:
                raise RuntimeError(f'child {index} failed: {result.stderr}')
            row = json.loads(result.stdout.splitlines()[-1])
            row['repeat'] = repeat; row['index'] = index
            output.write(json.dumps(row)+'\n'); output.flush()
            print(json.dumps({k:row[k] for k in ['index','workload','library','workers','profile','repeat','measured_sps','final_model_sha256']}), flush=True)
    print('STUDY COMPLETE', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--child',action='store_true'); p.add_argument('--smoke',action='store_true')
    p.add_argument('--profile',action='store_true'); p.add_argument('--workers',type=int,default=4)
    p.add_argument('--steps',type=int,default=524288)
    p.add_argument('--workload',choices=['fresh','mature'],default='mature')
    p.add_argument('--library',choices=['reference','cached'],default='cached')
    a=p.parse_args()
    child(a) if a.child else run(a)
