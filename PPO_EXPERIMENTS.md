# PPO improvement experiment — 2026-08-20

## Objective and protocol

Improve achievement performance beyond the existing `ppo_terraria.pt` policy
without changing the game or evaluation reward. The study used **22.8 million
new PPO environment steps**, plus behavior cloning from 512 scripted-expert
worlds.

Every promoted checkpoint was evaluated on the same 256 unseen seeds,
`10001..10256`. Sampled-policy evaluation used torch seed 12345. Model selection
used mean extrinsic achievements; death rate and per-achievement hit rates were
secondary diagnostics. Training-only shaping never changes the environment's
reported return.

Reproduce an evaluation with:

```sh
uv run python -m terraria_lite.ppo_eval CHECKPOINT --episodes 256
uv run python -m terraria_lite.ppo_eval CHECKPOINT --episodes 256 --greedy
```

## Correctness fix

The original autoreset logic treated a time-limit truncation as nonterminal for
GAE *and* added `gamma * V(final_obs)` to its reward. Since the next observation
was already from a reset world, this double-bootstrapped the transition and let
advantage leak between unrelated episodes.

The fix cuts GAE at both death and timeout boundaries, while adding the final
observation bootstrap only for a timeout. `ppo_selftest` contains a regression
check where a large reward in the reset episode must not affect the previous
episode.

## Results

All numbers below are sampled-policy results on the fixed 256-seed holdout.

| Variant | PPO steps | Mean ach. | Death | Max | Important result |
|---|---:|---:|---:|---:|---|
| Original `ppo_terraria.pt` | 600k | **4.617** | 58.2% | 10 | workbench 3.9% |
| Fixed vanilla, seed 11 | 600k | 5.074 | 11.3% | 7 | large seed variance |
| Fixed vanilla, seed 12 | 600k | 3.988 | 7.8% | 4 | |
| Fixed vanilla, seed 13 | 600k | 3.102 | 20.7% | 6 | |
| Progress 0.25 | 600k | 4.742 | 2.7% | 5 | stalls before stone |
| Progress 0.50, seed 21 | 600k | 7.195 | 12.1% | 14 | furnace 46.5% |
| Progress 0.50, seed 22 | 600k | 5.074 | 1.2% | 7 | |
| Progress 0.50, seed 23 | 600k | 9.199 | 15.2% | 14 | furnace 91.0% |
| Progress 1.00 | 600k | 4.926 | 0.8% | 5 | over-focuses workbench |
| Progress 0.50, entropy 0.02 | 1.2M | 6.598 | 9.4% | 12 | excess exploration hurts |
| Progress 0.50 annealed | 1.2M | 8.809 | 11.7% | 14 | best fair medium run |
| BC, 128 expert seeds | 0 | 6.645 | 71.1% | 18 | useful but brittle |
| BC-128 + vanilla PPO | 600k | 7.137 | 48.0% | 12 | safer, loses deep skill |
| BC-128 + progress PPO | 1.2M | 9.605 | 32.4% | 14 | strong, still brittle |
| BC, 512 expert seeds | 0 | 8.867 | 71.9% | **24** | one full clear; copper pick 12.5% |
| Recurrent vanilla | 600k | 4.984 | 0.0% | 5 | workbench 99.2%, no stone |
| Recurrent + progress | 600k | 4.223 | 30.9% | 6 | slower and worse |
| Recurrent + annealed progress | 600k | 3.590 | 0.4% | 6 | slower and worse |
| **From scratch, annealed progress** | **4M** | **10.746** | **2.3%** | 14 | best mean; recommended |
| BC-512 + vanilla PPO | 4M | 10.391 | 9.0% | **15** | copper pick 2.0%, reaches iron |
| BC-512 + annealed progress | 4M | 10.223 | 10.9% | 14 | no advantage over pure PPO |

The three 600k progress-0.5 replications average 7.156 achievements, compared
with 4.055 for the three corrected vanilla seeds. Variance remains large, but
the effect is much larger than that variance.

### Winning policy details

`ppo_long_scratch_s71.pt`, trained from scratch for four million steps with
`--progress-coef 0.5 --progress-anneal`, scored:

- 10.746 ± 2.180 achievements; median 10, p90 14.
- 2.3% deaths.
- Workbench crafted in 100% of worlds.
- Furnace crafted in 94.1% and placed in 93.4%.
- Copper collected in 41.8% and smelted in 31.6%.
- Torch crafted and placed in 25.0%.
- No copper pickaxe on this holdout; that remains the next wall.

The local ignored checkpoint is 4,892,547 bytes with SHA-256
`546428597b357abf0e732b9f8222edd28ee702f57fda153a773931ee0838816c`.

Greedy evaluation scored 7.320. Keep sampling for benchmark evaluation; argmax
throws away useful stochastic behavior. `rollout_best_ppo.tape` records a
14-achievement holdout run and can be watched with the pixel frontend.

Training command:

```sh
uv run python -m terraria_lite.ppo_agent \
  --steps 4000000 --seed 71 \
  --progress-coef 0.5 --progress-anneal \
  --save ppo_long_scratch_s71.pt
```

## Design conclusions

1. **Keep the timeout/GAE fix.** It is correctness, independent of score.
2. **Keep fixed-seed evaluation.** Trailing training summaries overstated the
   original checkpoint and conceal extreme seed variance.
3. **Promote capped progress shaping as an opt-in training mode.** Coefficient
   0.5, annealed to zero, more than doubled holdout score while leaving final
   evaluation purely extrinsic. It does encode the crafting graph, so benchmark
   reports must disclose it.
4. **Keep behavior cloning as a separate, explicitly privileged experiment.**
   More demonstrations produce rare full clears, but PPO fine-tuning trades
   that tail performance for a safer shallow policy. It is not the recommended
   default or a fair from-scratch comparison.
5. **Do not promote recurrent PPO yet.** At equal environment steps it is slower
   and worse. It reliably remembers enough to gather/craft a workbench, then
   collapses before stone. Memory alone does not solve hierarchical credit.
6. **The next wall is the copper pickaxe.** A better next experiment is a
   curriculum or auxiliary objective around repeated copper smelting, not a
   larger generic MLP or more entropy.
