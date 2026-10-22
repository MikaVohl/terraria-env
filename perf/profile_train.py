"""Where the wall time of a real tools/iterate_ppo.py run goes.

Runs iterate_ppo.main() unchanged (same argv as a production arm) with timing
wrappers around the trainer's phases, and prints one JSON line with seconds
per phase (totals and per PPO iteration, the first iteration excluded):

  act         policy forward + sampling in collection (actor.act)
  sim         VecTerraria.step (C batch step, autoreset, info dicts)
  potential   RecipePotential.step       novelty   CellNovelty.step
  expand      compact-obs expansion in collection (Expander on the collect device)
  absorb      _absorb_truncation          collect_rest  H2D, buffer writes, telemetry
  gae         compute_gae + next value    update        minibatch loop + actor sync
  checkpoint  torch.save                  evaluate      load_agent + evaluate

--sync synchronises the GPU at the end of every wrapped phase, so GPU work is
charged to the phase that launched it (the phases then cannot overlap, which
they only partly do anyway: actions are copied to the host every step).

    HIP_VISIBLE_DEVICES=0 TERRARIA_LITE_LIB=perf/v7/build-lw/libterraria.so PYTHONPATH=python \
      python perf/profile_train.py [--sync] -- --out /tmp/x --steps 8388608 --interval 4194304 <arm flags>
"""
import argparse
import collections
import functools
import json
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sync", action="store_true")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    a = p.parse_args()
    argv = a.rest[1:] if a.rest[:1] == ["--"] else a.rest
    sync = torch.cuda.synchronize if a.sync and torch.cuda.is_available() else (lambda: None)

    import iterate_ppo
    from terraria_lite import ppo_agent, compact
    T = collections.defaultdict(float)
    marks = []      # (time, T snapshot) at each PPO iteration end

    def timed(name, fn):
        @functools.wraps(fn)
        def wrapper(*args, **kw):
            t0 = time.perf_counter()
            out = fn(*args, **kw)
            sync()
            T[name] += time.perf_counter() - t0
            return out
        return wrapper

    def patch_method(cls, attr, name):
        setattr(cls, attr, timed(name, getattr(cls, attr)))

    patch_method(ppo_agent.VecTerraria, "step", "sim")
    try:
        from terraria_lite import gpusim
        patch_method(gpusim.GpuVec, "step", "sim")
    except Exception:
        pass
    from terraria_lite import potential, count_novelty
    patch_method(potential.RecipePotential, "step", "potential")
    patch_method(count_novelty.CellNovelty, "step", "novelty")
    ppo_agent._absorb_truncation = timed("absorb", ppo_agent._absorb_truncation)
    ppo_agent.compute_gae = timed("gae", ppo_agent.compute_gae)
    # actor.act in collection runs under inference_mode; the update uses
    # act/_score_bf16 with grad. Charge only the inference calls to "act".
    act = ppo_agent.ActorCritic.act

    def act_wrapper(self, x, action=None, mask=None):
        if action is not None:
            return act(self, x, action, mask)
        t0 = time.perf_counter()
        out = act(self, x, mask=mask)
        sync()
        T["act"] += time.perf_counter() - t0
        return out
    ppo_agent.ActorCritic.act = act_wrapper
    expand_call = compact.Expander.__call__
    _in_update = [False]   # set after compute_gae, cleared at the iteration end

    def expand_wrapper(self, raw):
        t0 = time.perf_counter()
        out = expand_call(self, raw)
        sync()
        T["expand_update" if _in_update[0] else "expand"] += time.perf_counter() - t0
        return out
    compact.Expander.__call__ = expand_wrapper
    torch.save = timed("checkpoint", torch.save)
    iterate_ppo.evaluate = timed("evaluate", iterate_ppo.evaluate)
    iterate_ppo.load_agent = timed("evaluate", iterate_ppo.load_agent)
    # train() reports collection/optimisation seconds to the callback; record
    # one mark per iteration through the iterate_ppo callback wrapper.
    train = ppo_agent.train

    def train_wrapper(cfg, checkpoint_callback=None):
        def cb(agent, steps, profile):
            sync()
            marks.append((time.perf_counter(), steps, dict(T), dict(profile)))
            _in_update[0] = False
            t0 = time.perf_counter()
            checkpoint_callback(agent, steps, profile)
            T["callback_total"] += time.perf_counter() - t0
        return train(cfg, checkpoint_callback=cb)
    iterate_ppo.train = train_wrapper
    # Expansions inside the update (minibatches) happen after compute_gae.
    gae = ppo_agent.compute_gae

    def gae_wrapper(*args, **kw):
        out = gae(*args, **kw)
        _in_update[0] = True
        return out
    ppo_agent.compute_gae = gae_wrapper

    sys.argv = ["iterate_ppo.py", *argv]
    t_start = time.perf_counter()
    iterate_ppo.main()
    wall = time.perf_counter() - t_start
    sync()

    (t1, s1, T1, P1), (tn, sn, Tn, Pn) = marks[0], marks[-1]
    iters = len(marks) - 1
    d = {k: Tn.get(k, 0.0) - T1.get(k, 0.0) for k in set(Tn) | set(T1)}
    coll = Pn["collection_seconds"] - P1["collection_seconds"]
    opt = Pn["optimisation_seconds"] - P1["optimisation_seconds"]
    collect_parts = ("act", "sim", "potential", "novelty", "expand", "absorb")
    per_iter = {k: d.get(k, 0.0) / iters for k in collect_parts}
    per_iter["collect_rest"] = coll / iters - sum(per_iter.values())
    per_iter["gae"] = d.get("gae", 0.0) / iters
    per_iter["update"] = opt / iters - per_iter["gae"]
    span = tn - t1
    per_iter["callback(ckpt+eval)"] = (d.get("callback_total", 0.0)) / iters
    per_iter["other"] = span / iters - coll / iters - opt / iters - per_iter["callback(ckpt+eval)"]
    out = {"argv": argv, "sync": a.sync, "iterations_timed": iters, "steps_per_iter": (sn - s1) // iters,
           "ms_per_iter": {k: round(1e3 * v, 2) for k, v in per_iter.items()},
           "steady_sps_incl_eval": round((sn - s1) / span),
           "steady_sps_excl_callback": round((sn - s1) / (span - d.get("callback_total", 0.0))),
           "totals_s": {"wall": round(wall, 1), "checkpoint": round(T["checkpoint"], 2),
                        "evaluate": round(T["evaluate"], 2), "evaluations": sum(1 for _ in Path(argv[argv.index('--out') + 1]).glob("step-*.pt")),
                        "first_iter_s": round(t1 - t_start, 1)}}
    print("PROFILE " + json.dumps(out), flush=True)


if __name__ == "__main__":
    main()
