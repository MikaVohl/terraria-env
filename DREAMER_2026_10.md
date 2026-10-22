# DreamerV3-style world-model agent for terraria-lite v7 (October 2026)

Branch `dreamer`. Status: **design** (results sections are filled in below as runs finish).

Question: does a model-based learner that trains its policy in imagination get past
the PPO v7 plateau (~25/32 at 512M steps), in particular the never-earned
stockpiling crafts (wood breastplate, iron chainmail, iron/gold pickaxe) and
"return to surface"? Game, extrinsic rewards, observations, masks and the
evaluation protocol are unchanged; PPO code paths are untouched (new files only).

## Design

Code: `python/terraria_lite/dreamer/` (`nets.py`, `replay.py`, `agent.py`,
`evaluate.py`) and `tools/train_dreamer.py`; Mac smoke test `tools/dreamer_selftest.py`.

### Data
- Collection: `VecTerraria(native_autoreset=True, compact=True)` from `ppo_agent`
  (one `tl_batch_step_autoreset` C call per step for all lanes), compact uint8 rows
  (2,152 B) expanded on the GPU by `compact.Expander` into exactly PPO's flat input.
- Replay (on the GPU): one ring per env lane. Row `t` = `(obs_t, mask_t,
  prev_action_t, reward_t, first_t, cont_t)`. At an episode end the lane writes
  two rows: the true terminal observation (`cont=0`, reward of the last action) and
  the reset observation (`first=1`, no previous action). Death and the 3,000-step
  deadline both get `cont=0`: the deadline is inherent and observed (status
  `time`), matching PPO's zero future value at the deadline. Sequences of length
  64 are sampled uniformly over each lane's ring; `first` resets the RSSM state
  inside a sequence; sequences start from a zero state.
- Optional training-only reward: the same potential shaping as the PPO
  baseline (`potential.RecipePotential`, `--potential C --potential-mode`) added to
  the stored reward, so the reward head learns shaped reward. Evaluation is
  always extrinsic. Disclosed per run in `protocol.json`.

### World model (RSSM)
- Encoder: flat obs (tile one-hot 99x24, light/15, status 488; status symlog) ->
  MLP (LayerNorm + SiLU) -> embedding.
- Deterministic GRU state (DreamerV3 LayerNorm GRU, update bias -1), stochastic
  latent 32 categoricals x 32 classes, 1% unimix, straight-through sampling.
- Heads on `feat = [h, z]`: decoder (tile categorical per cell, light
  categorical per cell (16 levels), status symlog MSE where inventory targets are
  `symlog(count)` instead of the encoded sqrt(count/999) so 9 vs 10 bars are well
  separated), reward (two-hot symlog, 255 bins), continue (Bernoulli), and an
  **action-mask head** (83 Bernoulli, terminal rows excluded).
- Loss: prediction + 0.5 dyn KL + 0.1 rep KL, free bits 1.0 (KL balancing).

### Actor-critic in imagination
- Starts: every posterior state of the replayed batch (B x 64), horizon 15,
  gamma 0.997, lambda 0.95. Imagined trajectories are rolled out without
  gradient (discrete actions use REINFORCE, as in DreamerV3), then actor and
  critic are trained on the stored features.
- Critic: two-hot symlog (255 bins), returns from a slow EMA critic (0.02/update),
  plus a regulariser toward the slow critic's prediction.
- Actor: REINFORCE with advantage `(R_lambda - V) / max(1, S)`, S = EMA(0.99) of
  the 95th-5th return percentile range; entropy 3e-4; 1% unimix over the legal set;
  steps weighted by the predicted continuation product.
- **Action mask in imagination: predicted.** Step 0 uses the real mask stored
  with the replayed state (exact). Later steps use the mask head
  (`p > 0.5`; if empty, `noop` is legal). Justification: illegal actions are forbidden
  in the real env, so the world model has never seen their consequences; a fixed
  start-state mask becomes wrong as soon as the imagined agent moves (mining
  targets, crafting after ingredients change), which would let imagination exploit
  unlearned transitions (e.g. "craft iron pickaxe" with 5 bars) or forbid newly legal
  crafts. Masks are a deterministic function of the state (inventory, stations in
  view, tiles in reach), so they are learnable from the latent, and the head also
  forces the latent to encode exact craft thresholds. Real acting always uses the
  real mask.

### Training loop
- N env lanes collect with the current actor (sampled, posterior filtered);
  updates are interleaved so that replayed steps / env steps = `train_ratio`
  (`--train-ratio`). bf16 autocast for the networks; losses, distributions and
  returns in float32. Adam (world model 1e-4, actor/critic 3e-5, eps 1e-8/1e-5,
  grad-norm clip 1000/100).

### Evaluation (comparable to PPO)
- `dreamer/evaluate.py` mirrors `ppo_eval.evaluate`: validation worlds
  23,000,001-23,000,128, cohorts of 64, `torch.manual_seed(54321)`, categorical
  sampling from the masked policy, `NativeBatch.step` flat observations, same result
  keys (mean achievements /32, per-achievement hits, death rate, peak depth, ...).
- Inventory diagnostic mirrors `tools/policy_diagnostics.py` (`diagnose`): peak
  inventories, legal-step counts, chosen actions.
- PPO comparison: `experiments/eg18/eg18-wall-v7-20261021/runs/wall_ctl-150{1,2,3}`
  (potential 3, 512M) at equal env steps and equal wall-clock.

## Plan on eg18 (GPU 6 only, <= 24 cores)
1. Throughput calibration of model size / batch / train ratio.
2. Short runs (10-20M env steps) at two train ratios: check learning and throughput.
3. One long run at the best setting for ~10-12 h with validation every few M steps.
4. Diagnostic on the best checkpoint.
