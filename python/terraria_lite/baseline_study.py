"""Auditable unshaped PPO learning curves. Run with python -m terraria_lite.baseline_study."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import time

import torch

from terraria_lite.ppo_agent import Config, train
from terraria_lite.ppo_eval import evaluate, load_agent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--steps', type=int, default=4_000_000)
    p.add_argument('--seeds', type=int, nargs='+', default=[101, 202, 303])
    p.add_argument('--episodes', type=int, default=128)
    p.add_argument('--threads', type=int, default=6)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    torch.set_num_threads(a.threads)
    root = Path(__file__).resolve().parents[2]
    sources = sorted([*root.glob('src/*.c'), *root.glob('src/*.h'),
                      *root.glob('include/*.h'), *root.glob('python/terraria_lite/*.py')])
    source_dir = a.out / 'source'
    for path in sources:
        dest = source_dir / path.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.read_bytes())
    manifest = {
        'platform': platform.platform(), 'torch': str(torch.__version__),
        'threads': a.threads, 'training_seeds': a.seeds,
        'validation_seeds': [1_000_001, 1_000_001 + a.episodes - 1],
        'evaluation_sample_seed': 54321, 'evaluation_batch': 64,
        'test_policy': 'Final test seeds reserved; this run uses validation only.',
        'git_head': subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip(),
        'sources': {str(x.relative_to(root)): hashlib.sha256(x.read_bytes()).hexdigest() for x in sources},
    }
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    with (a.out / 'results.jsonl').open('w', buffering=1) as results:
        for seed in a.seeds:
            cfg = Config(total_steps=a.steps, seed=seed, quiet=True, save='',
                         progress_coef=0.0, init='')
            (a.out / f'config-{seed}.json').write_text(json.dumps(asdict(cfg), indent=2))
            thresholds = sorted(set(min(x, a.steps // cfg.batch * cfg.batch)
                                    for x in [250_000, 1_000_000, 2_000_000, a.steps]))
            saved = []
            def checkpoint(agent, steps, timing):
                if thresholds and steps >= thresholds[0]:
                    thresholds.pop(0)
                    path = a.out / f'seed-{seed}-step-{steps}.pt'
                    torch.save(agent.state_dict(), path)
                    saved.append((path, steps, timing.copy()))
                    print(json.dumps({'event':'checkpoint', 'seed':seed, 'steps':steps, **timing}), flush=True)
            summary = train(cfg, checkpoint_callback=checkpoint)
            (a.out / f'training-{seed}.json').write_text(json.dumps(summary, indent=2))
            # Evaluate only after training: evaluation RNG cannot affect the learning trajectory.
            for path, steps, timing in saved:
                start = time.perf_counter()
                report = evaluate(load_agent(path),
                                  list(range(1_000_001, 1_000_001+a.episodes)),
                                  sample_seed=54321, num_envs=64)
                row = {'seed':seed, 'steps':steps, 'checkpoint':path.name,
                       **timing, 'evaluation_seconds':time.perf_counter()-start, **report}
                results.write(json.dumps(row)+'\n')
                print(json.dumps({k:v for k,v in row.items() if k not in ('records','hits')}), flush=True)


if __name__ == '__main__':
    main()
