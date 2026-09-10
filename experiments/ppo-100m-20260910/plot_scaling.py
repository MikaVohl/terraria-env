"""Plot measured validation curves, not a fitted scaling law.
Run: uv run --no-project --with matplotlib python experiments/ppo-100m-20260910/plot_scaling.py
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import StrMethodFormatter

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent.parent
summary = json.loads((OUT / 'summary.json').read_text())
# The verified summary enumerates every achievement, including zero-hit entries.
ceiling = len(summary['curve'][-1]['hits'])
assert ceiling == 24
runs = [
    ('16M schedule', ROOT / 'experiments/scaling-checked-20260909/16000000', '#8092A7'),
    ('32M schedule', ROOT / 'experiments/scaling-checked-20260909/32000000', '#D88829'),
    ('100M schedule', OUT / 'training', '#2563EB'),
]
curves = []
for label, directory, color in runs:
    config = json.loads((directory / 'config.json').read_text())
    batch = config['num_envs'] * config['rollout']
    assert batch == 32768
    points = []
    for path in directory.glob('step-*.eval.json'):
        steps = int(path.name.split('-')[1].split('.')[0])
        result = json.loads(path.read_text())
        assert steps % batch == 0
        assert result['episodes'] == 128
        assert 0 <= result['mean_achievements'] <= ceiling
        points.append((steps // batch, result['mean_achievements']))
    points.sort()
    assert points
    curves.append((label, color, points))
    print(label, points)
assert [len(c[2]) for c in curves] == [4, 6, 10]
assert curves[-1][2][-1][0] == 3052

plt.rcParams.update({
    'font.family': 'DejaVu Sans',
    'font.size': 11,
    'axes.titlesize': 21,
    'axes.labelsize': 12,
    'axes.edgecolor': '#D0D7E2',
    'text.color': '#17243A',
    'axes.labelcolor': '#334155',
    'xtick.color': '#526176',
    'ytick.color': '#526176',
    'svg.fonttype': 'none',
})
fig, ax = plt.subplots(figsize=(12, 7), facecolor='white')
fig.subplots_adjust(left=.085, right=.96, bottom=.19, top=.83)
ax.set_facecolor('#FAFBFD')
ax.set_title('PPO scaling: achievements vs. training iterations', loc='left', pad=42, fontweight='bold')
ax.text(0, 1.065, 'Mean achievements on the same 128 validation worlds',
        transform=ax.transAxes, fontsize=12, color='#526176')
ax.set_axisbelow(True)
ax.grid(axis='y', color='#E2E8F0', linewidth=.8)
ax.grid(axis='x', color='#EEF2F7', linewidth=.6)
for spine in ['top', 'right']:
    ax.spines[spine].set_visible(False)

ax.axhline(ceiling, color='#526176', linewidth=1.5, linestyle=(0, (6, 4)), zorder=1)
ax.text(3180, ceiling + .45, 'Total achievable: 24', ha='right', va='bottom',
        fontsize=11, color='#334155', fontweight='bold')
for label, color, points in curves:
    xs, ys = zip(*points)
    main = label.startswith('100M')
    ax.plot(xs, ys, color=color, label=label, linewidth=2.7 if main else 2,
            marker='o', markersize=5.5 if main else 4.5,
            markeredgecolor='white', markeredgewidth=.8, zorder=4 if main else 3)
    offset = (12, -16) if label.startswith('16M') else (12, 16) if label.startswith('32M') else (-8, 15)
    ax.annotate(f'{ys[-1]:.2f}', (xs[-1], ys[-1]), xytext=offset,
                textcoords='offset points', color=color, fontweight='bold',
                ha='right' if main else 'left', fontsize=11)

ax.set_xlim(0, 3220)
ax.set_ylim(0, 26)
ax.set_xticks([0, 500, 1000, 1500, 2000, 2500, 3000])
ax.xaxis.set_major_formatter(StrMethodFormatter('{x:,.0f}'))
ax.set_yticks([0, 4, 8, 12, 16, 20, 24])
ax.set_xlabel('Training iterations  (1 iteration = 32,768 environment transitions)', labelpad=13)
ax.set_ylabel('Mean achievements', labelpad=12)
ax.legend(loc='upper left', bbox_to_anchor=(.015, .855), frameon=True,
          facecolor='white', edgecolor='#E2E8F0', framealpha=1, fontsize=10)
fig.text(.085, .072, 'One training seed per schedule; each run uses its own learning-rate annealing horizon.',
         fontsize=10, color='#64748B')
fig.text(.085, .044, 'Markers are evaluated checkpoints. Lines connect observations; no scaling-law fit or extrapolation.',
         fontsize=10, color='#64748B')
for extension in ['png', 'svg']:
    path = OUT / f'scaling_law.{extension}'
    fig.savefig(path, dpi=200, facecolor='white')
    if extension == 'svg':
        lines = path.read_text().splitlines()
        path.write_text('\n'.join(line.rstrip() for line in lines) + '\n')
    print(path)
plt.close(fig)
