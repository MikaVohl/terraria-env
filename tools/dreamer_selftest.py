"""Tiny-scale checks of the Dreamer pieces (CPU, ~1 minute).

    TERRARIA_LITE_LIB=<v7 lib> PYTHONPATH=python python tools/dreamer_selftest.py

Checks: two-hot round trip; masked policy never samples illegal actions;
replay rows/sequences and episode boundaries; a short real training run
(collection + updates); world-model loss decreases on a fixed batch;
imagination respects masks (real mask at step 0, predicted afterwards);
checkpoint save/load reproduces the policy; holdout evaluation runs on the
validation worlds with ppo_eval's result keys.
"""
import tempfile
import time
from pathlib import Path

import numpy as np
import torch

from terraria_lite import SPEC
from terraria_lite.dreamer.agent import Config, Dreamer, load_dreamer, train
from terraria_lite.dreamer.evaluate import diagnose, evaluate
from terraria_lite.dreamer.nets import TwoHot, masked_policy, sample_logp
from terraria_lite.dreamer.replay import Replay

TINY = dict(deter=64, stoch=8, classes=8, units=64, layers=2, envs=16, sim_workers=4,
            capacity=16 * 400, batch=8, seq_len=16, train_ratio=4.0, prefill=20, horizon=5,
            device="cpu", seed=7, potential=3.0)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok:", msg, flush=True)


def main():
    torch.manual_seed(0)
    t0 = time.perf_counter()
    # two-hot
    th = TwoHot()
    target = torch.tensor([-3.0, 0.0, 0.25, 1.0, 7.5, 300.0])
    y = torch.sign(target) * torch.log1p(target.abs())
    hi = torch.bucketize(y, th.bins); w = (y - th.bins[hi - 1]) / (th.bins[hi] - th.bins[hi - 1])
    probs = torch.zeros(len(target), len(th.bins))
    probs[torch.arange(len(target)), hi - 1] = 1 - w; probs[torch.arange(len(target)), hi] = w
    check(torch.allclose(th.mean(probs.clamp_min(1e-30).log()), target, rtol=1e-3, atol=1e-4), "two-hot mean inverts the encoding")
    check(th.nll(torch.zeros(1, 255), torch.tensor([1.0])).item() > th.nll(probs[3:4].clamp_min(1e-30).log(), target[3:4]).item(),
          "two-hot nll prefers the matching distribution")

    # masked policy
    mask = torch.rand(4096, SPEC.n_actions) < 0.2
    mask[:, 0] = True
    logp = masked_policy(torch.randn(4096, SPEC.n_actions) * 5, mask, 0.01)
    a = sample_logp(logp)
    check(bool(mask.gather(1, a[:, None]).all()), "masked policy samples only legal actions")
    check(torch.allclose(logp.exp().sum(-1), torch.ones(4096), atol=1e-5), "masked policy is normalised over the legal set")

    # replay boundaries
    rp = Replay(2, 40, "cpu", seed=1)
    raw = torch.zeros(2, 2152, dtype=torch.uint8)
    lanes = torch.arange(2)
    for t in range(30):
        raw[:, 0] = t
        rp.add(lanes, raw, torch.ones(2, SPEC.n_actions, dtype=torch.bool), torch.full((2,), t), torch.zeros(2),
               torch.zeros(2), torch.full((2,), t == 0), torch.ones(2, dtype=torch.bool))
    s = rp.sample(64, 8)
    check(s["obs"].shape == (8, 64, 2152), "replay samples time-major sequences")
    check(bool((s["obs"][1:, :, 0].long() - s["obs"][:-1, :, 0].long() == 1).all()), "replay sequences are contiguous within a lane")
    check(bool((s["act"].long() == s["obs"][..., 0].long()).all()), "replay rows keep obs/action alignment")

    # short real training run (collection + updates)
    cfg = Config(total_steps=16 * 120, **TINY)
    holder = {}
    summary = train(cfg, callback=lambda ag, st, pr: holder.update(agent=ag), log_every=1e9, log=lambda s: None)
    agent: Dreamer = holder["agent"]
    check(summary["updates"] > 0 and summary["env_steps"] == 16 * 120,
          f"training loop ran {summary['updates']} updates over {summary['env_steps']} env steps")

    # world-model loss decreases on a fixed real batch (rebuild replay from a fresh collection)
    rp = Replay(cfg.envs, cfg.capacity, "cpu", seed=3)
    from terraria_lite.ppo_agent import VecTerraria
    envs = VecTerraria(cfg.envs, seed=99, workers=4, native_autoreset=True, compact=True)
    obs, msk = envs.reset()
    lanes = torch.arange(cfg.envs)
    one = torch.ones(cfg.envs, dtype=torch.bool)
    rp.add(lanes, torch.as_tensor(obs), torch.as_tensor(msk), torch.full((cfg.envs,), -1), torch.zeros(cfg.envs),
           torch.zeros(cfg.envs), one, one)
    rng = np.random.default_rng(0)
    for _ in range(60):
        act = np.array([rng.choice(np.flatnonzero(m)) for m in msk])
        obs, msk, r, te, tr, final, _ = envs.step(act)
        rp.add(lanes, torch.as_tensor(obs), torch.as_tensor(msk), torch.as_tensor(act), torch.as_tensor(r),
               torch.zeros(cfg.envs), ~one, torch.as_tensor(~(te | tr)))
    envs.close()
    batch = rp.sample(16, 16)
    fresh = Dreamer(Config(**{**TINY, "potential": 0.0, "model_lr": 1e-3}))
    losses = [float(fresh.update(batch)["model_loss"]) for _ in range(40)]
    check(losses[-1] < 0.7 * losses[0], f"world-model loss decreases on a fixed batch ({losses[0]:.1f} -> {losses[-1]:.1f})")
    m = fresh.update(batch)
    check(0.0 <= float(m["mask_false_legal"]) <= 1.0, f"mask false-legal rate reported ({float(m['mask_false_legal']):.3f})")

    # imagination respects masks
    with torch.no_grad():
        N = 256
        h = torch.randn(N, cfg.deter); z = torch.zeros(N, cfg.stoch * cfg.classes); z[:, ::cfg.classes] = 1
        mask0 = torch.zeros(N, SPEC.n_actions, dtype=torch.bool); mask0[:, 0] = True; mask0[:, 2] = True
        feats, masks, acts = fresh.imagine(h, z, mask0, 6)
    check(bool((masks[0] == mask0).all()), "imagination step 0 uses the real start mask")
    check(bool(acts[0].ge(0).all() and torch.isin(acts[0], torch.tensor([0, 2])).all()), "imagined first actions are legal under the real mask")
    legal = masks[:-1].gather(-1, acts[..., None])[..., 0]
    check(bool(legal.all()), "every imagined action is legal under the mask in force")
    with torch.no_grad():
        pred = fresh.wm.predicted_mask(feats[1:])
    check(bool((pred == masks[1:]).all()), "imagination after step 0 uses the predicted mask")

    # checkpoint round trip
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "ckpt.pt"
        agent.save(path, optimizers=True)
        loaded = load_dreamer(path, "cpu", training=True)
        from terraria_lite.compact import Expander
        x = Expander("cpu")(batch["obs"][0])
        st = agent.initial_state(x.shape[0])
        first = torch.ones(x.shape[0], dtype=torch.bool)
        torch.manual_seed(5); l1, _ = agent.policy_logp(x, batch["mask"][0], st, first)
        torch.manual_seed(5); l2, _ = loaded.policy_logp(x, batch["mask"][0], loaded.initial_state(x.shape[0]), first)
        check(torch.equal(l1, l2), "checkpoint save/load reproduces the policy exactly")

    # holdout evaluation (2 validation worlds, full 3,000-step episodes)
    result = evaluate(agent, [23_000_001, 23_000_002], num_envs=64, sample_seed=54321)
    from terraria_lite.ppo_eval import print_report
    print_report(result, "tiny dreamer", False)
    check(result["episodes"] == 2 and {"mean_achievements", "hits", "death_rate", "records"} <= set(result),
          "evaluation runs on validation worlds with ppo_eval's result keys")
    again = evaluate(agent, [23_000_001, 23_000_002], num_envs=64, sample_seed=54321)
    check(again["mean_achievements"] == result["mean_achievements"] and
          [r["steps"] for r in again["records"]] == [r["steps"] for r in result["records"]], "evaluation is reproducible")
    diag = diagnose(agent, [23_000_001])
    check(diag["episodes"] == 1 and "iron bar" in diag["inventory_peak"], "inventory diagnostic runs")
    print(f"all checks passed in {time.perf_counter() - t0:.0f}s")


if __name__ == "__main__":
    main()
