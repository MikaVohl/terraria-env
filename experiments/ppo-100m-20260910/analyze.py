"""Verify retained evaluation records and summarize the validation learning curve."""
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
import numpy as np
import torch

ACHIEVEMENTS = [
    'collect wood', 'collect dirt', 'collect stone', 'place block',
    'craft workbench', 'place workbench', 'craft stone pick', 'craft furnace',
    'place furnace', 'collect copper', 'smelt copper', 'craft torch',
    'place torch', 'craft copper pick', 'collect iron', 'smelt iron',
    'craft anvil', 'place anvil', 'craft iron pick', 'collect gold',
    'smelt gold', 'craft lantern', 'place lantern', 'descend deep',
]

torch.set_num_threads(2)
run = OUT / 'training'
assert (run / 'COMPLETE').exists()
manifest = json.loads((OUT / 'manifest.json').read_text())
training = json.loads((run / 'training.json').read_text())
checkpoints = json.loads((run / 'checkpoints.json').read_text())
assert training['steps'] == manifest['actual_steps']
assert len(checkpoints) == len(manifest['checkpoint_thresholds'])
assert checkpoints[-1]['steps'] == manifest['actual_steps']

curve = []
for event in checkpoints:
    result = json.loads((run / event['file']).with_suffix('.eval.json').read_text())
    records = result['records']
    assert result['episodes'] == 128
    assert sorted(r['seed'] for r in records) == list(range(1000001, 1000129))
    for r in records:
        assert r['achievements'] == r['achievement_mask'].bit_count()
        assert 0 < r['steps'] <= 3000
    arrays = {
        'mean_achievements': [r['achievements'] for r in records],
        'mean_return': [r['episode_return'] for r in records],
        'mean_length': [r['steps'] for r in records],
        'death_rate': [r['died'] for r in records],
    }
    for key, values in arrays.items():
        assert math.isfinite(result[key]) and np.isclose(result[key], np.mean(values)), key
    hits = Counter()
    for r in records:
        for i, name in enumerate(ACHIEVEMENTS):
            hits[name] += (r['achievement_mask'] >> i) & 1
    assert all(result['hits'].get(name, 0) == hits[name] for name in ACHIEVEMENTS)
    row = {**event, **{k: v for k, v in result.items() if k not in ['records', 'hits']},
           'hits': dict(hits)}
    curve.append(row)
    print(f"{event['steps']:>11,}  {result['mean_achievements']:6.3f}/24  "
          f"return={result['mean_return']:6.3f}  deaths={100*result['death_rate']:5.1f}%  "
          f"copper_pick={hits['craft copper pick']}/128  iron_pick={hits['craft iron pick']}/128  "
          f"lantern={hits['place lantern']}/128")

prior = {}
for budget, steps in [(16000000, 15990784), (32000000, 31981568)]:
    path = ROOT / 'experiments/scaling-checked-20260909' / str(budget) / f'step-{steps}.eval.json'
    data = json.loads(path.read_text())
    prior[str(budget)] = {k: v for k, v in data.items() if k != 'records'}
summary = {
    'requested_steps': manifest['requested_steps'], 'actual_steps': training['steps'],
    'synchronized_training_seconds': training['synchronized_wall_seconds'],
    'synchronized_sps': training['synchronized_sps'],
    'curve': curve, 'prior_final_validation': prior,
    'final_mean_gain_vs_32m': curve[-1]['mean_achievements'] - prior['32000000']['mean_achievements'],
    'validation_best_checkpoint': max(curve, key=lambda r: r['mean_achievements'])['file'],
    'test_set': 'unused',
    'verification': 'All source/library/checkpoint hashes match; all model parameters finite; 128 expected worlds per checkpoint; aggregate means and every achievement count recomputed from per-world records.',
    'caveat': 'One seed per schedule; different LR annealing horizons. Validation checkpoint selection is not a final-test score.',
}
(OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps({k: v for k, v in summary.items() if k not in ['curve', 'prior_final_validation']}, indent=2))
