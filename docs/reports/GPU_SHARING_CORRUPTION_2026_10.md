# Silent gradient corruption with two trainers per GPU (eg15, MI350X), October 2026

## Summary

- **Symptom.** Two `pot_e1024_max2` trainers on one eg15 GPU produce gradient-norm
  spikes (1e3 .. 9e18, and `inf`), first ones at 16-92M steps, and eventually die
  with a non-finite loss. Alone on a GPU the norm never exceeds 10.4 (ScaleFF's
  473M-step trace of the hidden-512 variant).
- **It is not our data or algorithm.** At every spike the minibatch inputs are finite,
  a float64 CPU recompute of the loss gives a norm of 0.17-0.30 (`spike_check.py`),
  the stored rollout log-probabilities match a recompute from the rollout parameters
  to 2e-6, log-ratios stay within ±0.85, and recomputing the *same* minibatch with
  the *same* parameters and the *same* compiled function right afterwards gives a
  normal norm (0.1-0.7). The trainer is single-stream; no data race in our code can
  produce this.
- **Where it happens.** The forward results of the spiking call (loss, approx-KL,
  clip fraction, per-row entropy) are bit-identical to the recompute, so the forward
  is correct; the raw gradients (copied before clipping, norm recomputed on the CPU in
  float64) are wrong, the critic gradients bit-identical. Every spike is a rank-1
  error from **one minibatch row and one logit: the action taken in that row**, i.e.
  a single garbage 32-bit value in d(loss)/d(log-prob) inside the backward of the
  compiled bf16 loss graph. Spike magnitudes are spread log-uniformly over
  1e2 .. 1e28, as random bit patterns are.
- **Trigger.** Needs `--bf16` **and** `--compile-all` (the whole minibatch loss as one
  Inductor graph under bf16 autocast) **and** another process on the GPU. Removing
  either flag removes the spikes (0 in 2 x 134M .. 2 x 268M steps with 4 trainers on
  the GPU, against 3-17 per trainer per ~200M steps for max2 with only 2).
  ROCm knobs that do not help: `HSA_ENABLE_SDMA=0`, `GPU_MAX_HW_QUEUES=1`, disjoint
  CU masks per process (`HSA_CU_MASK`).
- **Fix (branch `gpushare-fix`).** Under `bf16`, `compile_all` no longer compiles the
  minibatch loss as one graph; the policy modules inside it stay compiled
  (`--compile`) and the sampling graph stays compiled. Proven at 2 per GPU: see
  [Fix](#fix). Default and exact training are untouched (fingerprints below).
- **Second, independent sharing bug (minimal repro for upstream).** PyTorch's own
  bf16 column sum `x.sum(0)` (the eager bias gradient of `nn.Linear`) returns wrong
  values (up to 75 % of the largest output) in ~1-2 % of calls while other processes
  use the GPU, and is bit-exact alone: `tools/gpushare/colsum_repro.py`.
- **Not hipBLASLt.** All 41 GEMM calls of the max2 update (logged with
  `HIPBLASLT_LOG_MASK=32`, `tools/gpushare/trainer_gemms_max2.log`) replayed under
  sharing are bit-deterministic (`tools/gpushare/gemm_replay.py`).

## Environment

eg15 = cv350-rck-g03-c01-08, AMD Instinct MI350X (gfx950, 256 CUs, 8 XCDs), HIP
device 7 (PCI 0x98, amd-smi GPU 5). Kernel 6.8.0-136-generic, amdgpu 6.16.13, system
ROCm 7.2.4; firmware CP_MEC 41, RLC 43, SDMA 12, PSP SOS 00.45.00.2A, PM 04.86.16.03,
PLDM bundle 00.26.00.02. User space from the venv wheel: torch 2.13.0+rocm7.1
(git cf30153c4c131c8164ee7798e5022d810682e2cb) with its bundled HIP 7.1.52802,
hipBLASLt, rocBLAS and HSA runtime; Triton 3.7.1. eg18 (ROCm 7.2.2) could not be
compared: its amdgpu module was not loaded after its last reboot (no `/dev/kfd`).

## Method

`tools/gpushare/spike_probe.py` wraps `tools/iterate_ppo.py` (the explore_screen
`pot_e1024_max2` package, targets net, hidden 128; launcher
`tools/gpushare/trainer_pair.sh`). It logs every pre-clip gradient norm
(`gradnorms.npy`) and, when a norm exceeds 100 (alone the maximum is ~10):

1. copies the raw gradients before clipping and recomputes their norm on the CPU
   (float64) and again with `_foreach_norm` on the GPU;
2. re-runs the same minibatch with the same parameters through the trainer's own
   loss function (compiled, bf16) and through the eager float32 loss, and compares
   the forward outputs of the spiking call with the recompute;
3. recomputes the stored rollout log-probabilities from the rollout-time parameters;
4. dumps inputs, parameters, raw and recomputed gradients
   (`tools/gpushare/spike_check.py` re-evaluates a dump in float64 on the CPU,
   `tools/gpushare/spike_rows.py` locates the corrupted row and logit).

The trainer's own gradients are restored afterwards, so the traced run follows its
normal trajectory. `tools/gpushare/count_spikes.py` summarises `gradnorms.npy`.

## Results

All runs: eg15 HIP 7, seeds 1801/1802, 2048 env steps per update. "4 procs" = two
arms of two trainers each ran at the same time (heavier sharing than production).

| arm | flags vs max2 | trainers on GPU | steps per trainer | updates > 1e3 (per trainer) | max norm |
|---|---|---|---|---|---|
| max2 (run a) | - | 2 | 201M / 211M | 6 / 17 (+7 / 4 inf) | 8.9e18 |
| max2 (run b) | - | 2 | 178M / 180M | 9 / 3 (+3 / 5 inf) | 9.4e14 |
| max2 (run c) | - | 2 | 201M / 201M | 5 / 5 (+2 / 4 inf) | 5.4e16 |
| no bf16 | `--bf16` off | 4 | 134M x 2 | 0 / 0 | 5.4 |
| exact | compile, bf16, fused, compile-all off | 4 | 134M x 2 | 0 / 0 | 5.4 |
| eager bf16 | compile, compile-all off | 4 | 268M x 2 | 0 / 0 | 5.4 |
| max (= max2 without compile-all) | compile-all off | 4 | 268M x 2 | 0 / 0 | 5.4 |
| **fix** (this branch) | max2 flags | 2 | 268M x 2 | **0 / 0** (none > 100) | 5.4 |

Short screens (2 trainers, 67M steps each, so mostly before the spike-prone phase;
same-session max2 control: 1 / 0): `HSA_ENABLE_SDMA=0` 0 / 1, `GPU_MAX_HW_QUEUES=1`
1 / 1, `HSA_CU_MASK` 0:0-127 / 0:128-255 4 / 1, log-prob as a masked sum instead of
`Categorical.log_prob`'s gather (removes the zero-fill + `tl.atomic_add` scatter
kernel from the backward) 0 / 3 with the same single-row signature. None of these
removes the corruption.

### Anatomy of a spike

18 spikes of run c and 21 of run b, each analysed as above:

- forward outputs of the spiking call == recompute, bit for bit (18/18);
- raw-gradient norm on the CPU == the GPU norm (the norm kernel is fine), the
  gradients themselves are wrong; critic gradients unchanged;
- the error of the policy-head weight gradient is rank 1 (second singular value
  at most 4e-4 of the first) and aligned (cosine 0.99999) with exactly one minibatch row's
  features; the corrupted logit is the action taken in that row (20/21 with p(taken)
  0.7-1.0; in the remaining one the taken action is a target action and the error
  shows in the dominant "other" logit through the softmax backward);
- the error then propagates into every trunk parameter through that row.

So one value of d(loss)/d(newlogp[r]) — computed in the backward of the compiled
graph from the saved ratio and the normalised advantage of row r — is garbage. The
float32 compiled loss has the same kernel structure for this step (zero-fill,
scatter of d(log-prob), softmax backward), and never spikes; the bf16 graph differs in its buffers (bf16 logits, an
in-place bf16 softmax backward), which is consistent with a stale or misdirected
read whose damage depends on what the memory held before, rather than with an
arithmetic bug. We could not pin it to one kernel without root access (no way to
disable CWSR or change cache policy per process).

### Speed

Two trainers per GPU, 67M steps (wall seconds, mean of the two): max2 194 s,
max (compile-all off) 261 s, eager bf16 279 s, this branch 233 s (+20 %; 566 s vs 475 s for max2 at 167M steps).

## Fix

`python/terraria_lite/ppo_agent.py`: `ppo_loss` is compiled as one graph only when
`compile_all and not bf16`. With `--bf16 --compile --compile-all` the loss runs
eagerly around the compiled policy modules (the configuration with 0 spikes in
2 x 268M steps above) while the sampling graph stays compiled.
Evidence: two traced trainers on HIP 7, max2 flags, seeds 1801/1802, 268M steps each (131,072 updates each): 0 norms > 100, maximum 5.07 / 5.38, none non-finite (`~/gsb/fix1` on eg15). The same command on main spiked 3-17 times per trainer by ~200M steps.

Default and exact paths never reach this branch; `perf/bench_trainer.py` (v7
build-lw2) fingerprints on this branch: default `a18970ad67930ebb`, `--set native_autoreset=1 compact_obs=1 potential_mode=frontier novelty_coef=.01` `9b00de160bd6436b` (both unchanged).

Operational advice until upstream is fixed: on shared GPUs use either this branch,
or max2 without `--compile-all`, or without `--bf16`. Runs that have already
spiked silently trained on corrupted updates (clipped to norm 0.5, so the damage per
spike is bounded, but the direction is garbage); treat 2-per-GPU max2 results from
eg15 as suspect.

## Upstream material

1. `tools/gpushare/colsum_repro.py`: pure PyTorch, bf16 `x.sum(0)` of [811008, 32];
   alone 0 of 1.9M sums differ (float32 0 of 2.0M); next to two `stress.py` processes (bf16 GEMMs + compiled policy forward/backward) 6144 of 322,362 sums differ (worst 10 % of the largest output); inside `stress.py` at 3 processes 1-2 % of bf16 column sums of every vectorised shape were wrong (up to 75 %). The neighbour matters: three copies of the repro alone, or a plain bf16 matmul loop as neighbour, gave 0 wrong sums. The kernel is ATen's
   `reduce_kernel` with a cross-block global reduction (`ReduceConfig.ctas_per_output
   > 1`, vectorised output); on ROCm its staging stores use `cmtdStore`
   (relaxed agent-scope atomic stores + `s_waitcnt vmcnt(0)`) instead of
   `__threadfence()`, and the last block reads after an agent-scope acquire fence
   (`aten/src/ATen/native/cuda/Reduce.cuh`, `KernelUtils.cuh`). Wrong lanes come in
   stride-4 patterns within the vector outputs. float32 sums of the same shapes and
   bf16 sums with N=43 (no output vectorisation) are unaffected.
2. The trainer-level corruption: `tools/gpushare/trainer_pair.sh` + `spike_probe.py`
   reproduce it within ~30-90M steps per trainer; the anatomy above is the report.
   `tools/gpushare/stress.py` (synthetic policy/PPO-loss replica, GEMMs, Adam,
   reductions with rotating input sets so stale reads are detectable) did not
   reproduce the single-value corruption in 15 minutes x 3 processes (one process
   showed large run-to-run differences in one bf16 weight gradient, not
   investigated further). `tools/gpushare/atomic_repro.py` (zero-fill followed by
   relaxed atomics, the Inductor scatter pattern) gave 0 errors in 3.9M iterations
   under sharing.

Report to: ROCm (amdgpu/firmware on MI350X, multi-process) with PyTorch-ROCm in copy;
the colsum repro is the self-contained one.
