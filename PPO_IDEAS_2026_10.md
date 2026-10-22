# DreamerV3-inspired PPO options on v7 (October 2026)

Branch `ppo-ideas`. Compact data: `PPO_IDEAS_2026_10.json` (final-score table, diagnostics, score curves,
stopped runs, fingerprints). Table tool: `tools/ppo_ideas_table.py`.

**Headline.** None of the three options moved the 25/32 wall. Unimix .01 matched the base arm: one full seed scored
25.44, against 25.28 for the same base seed, and the paired curves track within noise on three seeds. The two-hot
critic was worse on both seeds (22.77 and 24.38, against 25.28 and 25.36). Percentile return normalisation broke
learning in this shared-trunk PPO, both at entropy .03 and at the rescaled entropy .003. No run earned iron/gold
pickaxe, iron chainmail or wood breastplate. Iron-bar inventory peaks stayed at a median of 5. The user stopped the
study early; see "Stopped runs".

## What the options do (all off by default, training-only)

Implemented in `python/terraria_lite/dreamer_tricks.py`. Exposed as `ppo_agent.Config` fields
`return_norm`/`value_head`/`unimix`, as `iterate_ppo.py` flags `--return-norm percentile`, `--value-head twohot`
and `--unimix EPS`, and as `explore_screen.py` arms `idea_*`.

- **`--return-norm percentile`.** Once per iteration, the 5th and 95th percentiles of the batch's lambda-returns
  (`ret = adv + V`, including the training shaping) update separate zero-initialised EMAs. The decay is .99, with no
  debiasing, as in DreamerV3's retnorm. Advantages are divided by `max(1, P95_ema - P5_ema)`.
  - Interaction with the existing code: this **replaces** PPO's per-minibatch standardisation
    `(adv - mean) / (std + 1e-8)`. There is no centring and no std division. Clipping, the value loss and the
    entropy term are unchanged.
  - Telemetry: `curve.json` `profile.return_norm` holds the EMA percentiles, the scale and the normalised `|adv|` and
    std.
- **`--value-head twohot`.** The critic becomes a same-class linear head (targets' `GlobalCritic`) with 255 outputs,
  zero-initialised.
  - The bins are spaced evenly over symlog space [-20, 20].
  - Value = `symexp(sum softmax * bins)`, so GAE, bootstrap and evaluation still see a scalar value.
  - The loss is the cross-entropy against the two-hot encoding of `symlog(lambda-return)`, weighted by `vf_coef`
    (.5).
  - There is no value clipping (`clip_vloss` does not apply to the categorical loss).
  - Checkpoints record `value_head`; `ppo_eval.load_agent` installs the head, so evaluation and
    `policy_diagnostics.py` load these checkpoints.
- **`--unimix EPS`.** The policy becomes `(1-eps) softmax(masked logits) + eps * uniform(legal actions)`. It is
  computed in log space with `logaddexp`, so illegal actions keep exactly zero probability and get finite (zero)
  gradients. It is used for sampling, stored log-probs, ratios and entropy (`ActorCritic.act`, `_score_bf16` and the
  twohot scorer).
  - The frozen evaluation protocol samples from the plain masked logits, so evaluation never mixes.
- **Compatibility.** All three work with `--compile`, `--bf16`, `--fused-adam`, `--compact-obs` and
  `--native-autoreset`. Each combination was run with all four performance options on eg18; the score-time critic
  logits stay inside bf16 autocast and are cast to float32 for the loss.
  - Refused: twohot with SIL, and any of the three options with the recurrent agents.

## Default training is unchanged

All fingerprints use `perf/bench_trainer.py --envs 1024 --iters 6` on eg18 GPU 5 with the v7 `build-lw` library.
The library was rebuilt in my clone; its disassembly is identical to the live one. Each SHA covers the final
parameters and the episode telemetry, and main matched the branch on all four paths:

| path | main | ppo-ideas |
|---|---|---|
| default (exact) | a18970ad67930ebb | a18970ad67930ebb |
| + native-autoreset, compact-obs, frontier, novelty .01 | 9b00de160bd6436b | 9b00de160bd6436b |
| same + bf16 | 4ef99ff7b106da73 | 4ef99ff7b106da73 |
| same + bf16 + fused Adam | b02f2226b3a5124e | b02f2226b3a5124e |

`--compile` cannot be bit-compared: main against itself gives different SHAs from run to run (5f037c8e…/87496cc9…
with all options; ca16b713…/f9678ae5… with compile alone). On Mac CPU (targets, 64 envs, 3 iterations, frontier +
novelty, seed 1501, with and without native-autoreset + compact-obs), main and the branch both gave
`679164a7f96f0920`.

Mac smoke tests:
- each flag alone and all three together, with and without bf16, through `train()`;
- `iterate_ppo.py` with all three flags, followed by `policy_diagnostics.py` on the resulting twohot checkpoint.

Numerical unit checks:
- two-hot rows sum to 1, and the round-trip is exact inside the range;
- unimix leaves zero mass on illegal actions, and its gradients are finite.

## Setup

Every arm is `wall_frontier_nov01` (the `pot_e1024_max` path with frontier potential 3 and novelty .01) plus the
option.
- Budget: 512M steps, evaluated every 64M on validation worlds 23,000,001–23,000,128 (sampler seed 54321). Score =
  validation mean achievements at the last evaluation.
- Hardware: eg18 GPU 5 only, 2 runs at a time, pinned to CPUs 120–143. About 45 min per run.
- Diagnostics: `tools/policy_diagnostics.py` on the final checkpoint, same 128 validation worlds. Wall columns give
  the validation worlds (out of 128) that earned each achievement.
- Controls: the parent's runs. Their diagnostics were re-run here from their checkpoints.

## Results: final 512M policies

| run | score | anvil | metal sword | iron pick | gold pick | chainmail | breastplate | surface | iron bar peak med/max | gold bar peak med/max | wood peak med/max |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **unimix .01** 1501 | **25.438** | 80 | 20 | 0 | 0 | 0 | 0 | 0 | 5/10 | 2/7 | 15/26 |
| twohot 1501 | 22.766 | 20 | 4 | 0 | 0 | 0 | 0 | 0 | 2/13 | 0/4 | 13/22 |
| twohot 1502 | 24.383 | 35 | 8 | 0 | 0 | 0 | 0 | 0 | 4/14 | 1/5 | 14/26 |
| base: frontier_nov01 1501 | 25.281 | 73 | 26 | 0 | 0 | 0 | 0 | 0 | 5/11 | 2/6 | 14/25 |
| base: frontier_nov01 1502 | 25.359 | 73 | 17 | 0 | 0 | 0 | 0 | 0 | 5/10 | 1/7 | 15/26 |
| base: frontier_nov01 1503 | 24.945 | 63 | 15 | 0 | 0 | 0 | 0 | 1 | 5/11 | 2/9 | 15/26 |
| base: frontier_nov01 1504 | 25.359 | 76 | 19 | 0 | 0 | 0 | 0 | 0 | 5/8 | 1/8 | 15/26 |
| wall_ctl 1501 | 25.055 | 65 | 10 | 0 | 0 | 0 | 0 | 1 | 5/12 | 2/7 | 15/26 |
| wall_ctl 1502 | 25.070 | 59 | 14 | 0 | 0 | 0 | 0 | 0 | 5/11 | 1/7 | 13/15 |
| wall_ctl 1503 | 24.938 | 46 | 6 | 0 | 0 | 0 | 0 | 0 | 5/13 | 2/6 | 13/19 |
| wall_ctl 1504 | 24.688 | 55 | 11 | 0 | 0 | 0 | 0 | 0 | 5/9 | 1/8 | 13/17 |

Base means: frontier_nov01 is 25.24 over 4 seeds (25.32 on 1501/1502); wall_ctl is 24.94 over 4 seeds.

## Stopped runs (no final checkpoint; score at last evaluation)

| run | last eval | score | for comparison: base same seed, same step |
|---|---|---|---|
| return-norm, entropy .03, 1501 | 134M | 10.27 (no workbench) | 23.44 |
| return-norm, entropy .003, 1501 | 335M | 17.17 (furnace 0/128) | 24.80 |
| all three, entropy .003, 1501 | 201M | 16.25 (furnace 0/128) | 24.25 |
| unimix .01, 1502 | 335M | 24.62 | 25.05 |
| unimix .01, 1504 | 67M | 22.07 | 19.95 |

Paired unimix curves against the base, at the same steps:
- seed 1501, from 64M to 512M: 20.50/21.51, 23.53/23.44, 24.03/24.25, 24.57/24.54, 25.09/24.80, 25.13/24.86,
  25.27/25.36, 25.44/25.28;
- seed 1502, from 64M to 320M: 20.89/21.81, 23.65/23.73, 24.35/24.23, 24.77/24.83, 24.62/25.05.

Both pairs cross repeatedly. The difference never exceeds the ±0.2 spread between seeds of the same arm.

Twohot curves lag the base early and stay behind:
- seed 1501 reached 128/128 furnace worlds only near 512M (108 at the end); at 128M the base already scores 23.4;
- seed 1502 caught up faster but still ended about 1 point below its base.

## Notes per option

- **Return norm.** With frontier shaping, `P95 - P5` of the returns settles at 4–7. The normalised advantages
  therefore have a std of .03–.09, against about 1 after standardisation.
  - At entropy .03 the entropy bonus dominates. The policy never got past about 10/32 and never crafted a workbench.
  - The original D arm (all three at entropy .03) was therefore not run.
  - Rescaling entropy by the same factor (.003; DreamerV3 itself uses 3e-4) still left learning stuck near 17/32,
    with no furnace in 335M steps.
  - Likely cause [INFERENCE]: the value loss and global gradient clipping. The targets model shares its trunk
    between actor and critic, and PPO clips the global gradient norm at .5. With advantages scaled down 10–30x, the
    value loss dominates the shared trunk's gradient and the clip budget. DreamerV3 separates the actor and critic
    networks and optimisers, so this normalisation does not transfer to shared-trunk PPO without also rescaling
    `vf_coef`.
- **Two-hot critic.** Consistently worse on 2 of 2 seeds, by 2.5 and 1.0 points, and slower early. Untested
  explanations [INFERENCE]:
  - the categorical cross-entropy gradient competes with the policy in the shared trunk;
  - only about 22 of the 255 bins span the return range [0, 30].

  The gamma .9995 twohot variant was not tried, because twohot alone already hurt.
- **Unimix .01.** Neutral on the evidence: 1 full seed at +0.16, 1 partial seed slightly behind at 320M, and 1 seed
  stopped at 64M. Anvil worlds were higher on 1501 (80 against 73), but metal sword worlds were not (20 against 26).
  Inventory peaks are unchanged.

## Conclusion

No option made any of the four never-legal crafts legal. Iron-bar peaks stay at a median of 5 and a max of 8–14 in
every arm, and no arm earned return to surface more than once. Seed counts:

| arm | seeds |
|---|---|
| unimix | 1 full + 2 partial |
| twohot | 2 full |
| return norm | 2 partial (entropy .03 and .003, 1 seed each) |
| all three | 1 partial |

The base arm has 4 seeds. Unimix is the only option not shown harmful. Its effect is within seed noise; resolving
a gain of about 0.1 would take at least 4 paired seeds. Main's parallel results point the same way: potential 10/30
did not raise the stockpile either. The wall is not a matter of advantage scale, value representation or residual
exploration noise. It looks like a problem of long-horizon credit and memory: finding and hoarding ore with an 11x9
view.
