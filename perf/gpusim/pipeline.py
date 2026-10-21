"""Pipeline benchmarks on one GPU (run with HIP_VISIBLE_DEVICES=7).

  python pipeline.py transfer             # H2D float32 one-hot obs vs compact obs
  python pipeline.py infer                # policy inference: eager / HIP graph / torch.compile
  python pipeline.py learn                # PPO minibatch update: eager / torch.compile
  python pipeline.py e2e --sim gpu|cpu --envs N --iters K [--store flat|compact] [--lib ...]

The e2e loop is a lean copy of ppo_agent.train's hot path (same TargetActorCritic,
same losses, Adam, GAE, clipping; no telemetry/extras). target_kl early stop is
disabled so every iteration runs all epochs (worst case for the learner).
"""
import argparse, ctypes as C, hashlib, json, os, sys, time
import numpy as np
import torch
from torch import nn

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "python"))   # this checkout's package
from terraria_lite import SPEC                                     # noqa: E402
from terraria_lite.target_agent import TargetActorCritic           # noqa: E402

dev = torch.device("cuda")
A, F = SPEC.n_actions, SPEC.obs_size


def sync():
    torch.cuda.synchronize()


def timeit(fn, reps=20, warm=5):
    for _ in range(warm):
        fn()
    sync(); t = time.perf_counter()
    for _ in range(reps):
        fn()
    sync()
    return (time.perf_counter() - t) / reps


# ------------------------------------------------------------- GPU simulator
class GpuVec:
    """Device-resident batch: verbatim core in HIP, lane-ordered pool resets.

    Seeds match VecTerraria: lanes 0..n-1 start with seeds s..s+n-1; the k-th
    finished lane (lane order within a step, steps in order) gets seed s+n+k.
    World k lives in pool slot k % pool_n, generated on device in batches."""

    def __init__(self, n, seed, lib, pool_n=65536, max_steps=0):
        self.L = C.CDLL(lib)
        for f in ("gs_init", "gs_reset", "gs_step", "gs_reset_from_pool", "gs_encode"):
            getattr(self.L, f).restype = C.c_int
        self.L.gs_encode.argtypes = [C.c_void_p, C.c_longlong, C.c_void_p, C.c_void_p]
        self.sb, self.ob = self.L.gs_state_bytes(), self.L.gs_obs_bytes()
        assert self.L.gs_flat_size() == F and self.L.gs_act_count() == A
        self.n, self.s0, self.pool_n = n, seed, pool_n
        self.max_steps = max_steps or SPEC.default_steps
        self.env = torch.empty(n * self.sb, dtype=torch.uint8, device=dev)
        self.pool = torch.empty(pool_n * self.sb, dtype=torch.uint8, device=dev)
        self.raw = torch.empty((n, self.ob), dtype=torch.uint8, device=dev)
        self.mask = torch.empty((n, A), dtype=torch.uint8, device=dev)
        self.rew = torch.empty(n, dtype=torch.float32, device=dev)
        self.ends = torch.zeros(n, dtype=torch.int32, device=dev)
        self.cursor = torch.zeros((), dtype=torch.int64, device=dev)   # worlds consumed
        self.generated = 0
        st = self.stream()
        self._chk(self.L.gs_init(C.c_void_p(self.env.data_ptr()), n, self.max_steps, st))
        self._chk(self.L.gs_init(C.c_void_p(self.pool.data_ptr()), pool_n, self.max_steps, st))
        seeds = torch.arange(seed, seed + n, dtype=torch.int64, device=dev)
        self._chk(self.L.gs_reset(C.c_void_p(self.env.data_ptr()), None, C.c_void_p(seeds.data_ptr()), n,
                                  C.c_void_p(self.raw.data_ptr()), C.c_void_p(self.mask.data_ptr()), st))
        self.reset_seconds = 0.0
        self._refill(pool_n)

    @staticmethod
    def stream():
        return C.c_void_p(torch.cuda.current_stream().cuda_stream)

    @staticmethod
    def _chk(e):
        if e:
            raise RuntimeError(f"HIP error {e}")

    def _refill(self, upto):
        """Generate worlds [generated, upto) into their pool slots (device worldgen)."""
        if upto <= self.generated:
            return
        t = time.perf_counter()
        k = torch.arange(self.generated, upto, dtype=torch.int64, device=dev)
        idx = (k % self.pool_n).to(torch.int32)
        seeds = self.s0 + self.n + k
        self._chk(self.L.gs_reset(C.c_void_p(self.pool.data_ptr()), C.c_void_p(idx.data_ptr()),
                                  C.c_void_p(seeds.data_ptr()), int(upto - self.generated), None, None, self.stream()))
        self.generated = upto
        sync()
        self.reset_seconds += time.perf_counter() - t

    def step(self, actions):
        st = self.stream()
        a = actions.to(torch.int32)
        self._chk(self.L.gs_step(C.c_void_p(self.env.data_ptr()), self.n, C.c_void_p(a.data_ptr()),
                                 C.c_void_p(self.raw.data_ptr()), C.c_void_p(self.mask.data_ptr()),
                                 C.c_void_p(self.rew.data_ptr()), C.c_void_p(self.ends.data_ptr()), st))
        done = self.ends != 0
        csum = torch.cumsum(done, 0)
        slot = self.cursor + csum - 1
        self._chk(self.L.gs_reset_from_pool(C.c_void_p(self.env.data_ptr()), self.n, C.c_void_p(self.ends.data_ptr()),
                                            C.c_void_p(slot.data_ptr()), C.c_void_p(self.pool.data_ptr()), self.pool_n,
                                            C.c_void_p(self.raw.data_ptr()), C.c_void_p(self.mask.data_ptr()), st))
        self.cursor += csum[-1]
        return self.rew, self.ends

    def maybe_refill(self):
        """One host sync per call; keep at least half a pool of unconsumed worlds."""
        c = int(self.cursor)
        if c > self.generated:
            raise RuntimeError("pool underrun: increase pool_n or refill more often")
        if self.generated - c < self.pool_n // 2:
            self._refill(c + self.pool_n)

    def encode(self, raw, out):
        self._chk(self.L.gs_encode(C.c_void_p(raw.data_ptr()), raw.shape[0], C.c_void_p(out.data_ptr()), self.stream()))
        return out


# ----------------------------------------------------------------- benches
def bench_transfer():
    rows = []
    for n in (4096, 8192, 16384):
        flat = np.random.rand(n, F).astype(np.float32)
        pinned = torch.from_numpy(flat).pin_memory()
        comp_tiles = np.random.randint(0, 24, (n, SPEC.cells), dtype=np.uint8)
        comp_light = np.random.randint(0, 16, (n, SPEC.cells), dtype=np.uint8)
        comp_status = np.random.rand(n, SPEC.status_len).astype(np.float32)
        packed = np.concatenate([comp_tiles, comp_light, comp_status.view(np.uint8)], 1)
        packed_pin = torch.from_numpy(packed).pin_memory()
        lut = (torch.arange(16, dtype=torch.float64) / 15).float().to(dev)
        eye = torch.eye(SPEC.tile_kinds, device=dev)

        def expand(p):
            t = p[:, :SPEC.cells].long(); l = p[:, SPEC.cells:2 * SPEC.cells].long()
            s = p[:, 2 * SPEC.cells:].contiguous().view(torch.float32)
            return torch.cat([eye[t].reshape(n, -1), lut[l], s], 1)

        r = {"envs": n, "flat_MB": round(flat.nbytes / 2**20, 1), "compact_MB": round(packed.nbytes / 2**20, 2)}
        r["flat_pageable_ms"] = 1e3 * timeit(lambda: torch.as_tensor(flat).to(dev))      # ppo_agent path
        r["flat_pinned_ms"] = 1e3 * timeit(lambda: pinned.to(dev, non_blocking=True))
        r["compact_pageable_ms"] = 1e3 * timeit(lambda: torch.as_tensor(packed).to(dev))
        r["compact_pinned_ms"] = 1e3 * timeit(lambda: packed_pin.to(dev, non_blocking=True))
        dp = packed_pin.to(dev)
        r["gpu_expand_ms"] = 1e3 * timeit(lambda: expand(dp))
        r = {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}
        print(json.dumps(r), flush=True); rows.append(r)
    return rows


def make_agent():
    torch.manual_seed(0)
    return TargetActorCritic(128).to(dev)


def bench_infer():
    for n in (4096, 8192, 16384, 65536):
        agent = make_agent(); agent.eval()
        x = torch.rand(n, F, device=dev); m = torch.rand(n, A, device=dev) > 0.3; m[:, 0] = True

        def eager():
            with torch.inference_mode():
                return agent.act(x, mask=m)

        def fwd(x, m):
            h = agent.trunk(x); logits = agent.actor(h).masked_fill(~m, float("-inf"))
            g = -torch.log(-torch.log(torch.rand_like(logits).clamp_(1e-20, 1.)))
            a = (logits + g).argmax(-1)
            return a, torch.log_softmax(logits, -1).gather(1, a[:, None]).squeeze(1), agent.critic(h).squeeze(-1)

        sx, sm = x.clone(), m.clone()
        s = torch.cuda.Stream(); s.wait_stream(torch.cuda.current_stream())
        with torch.no_grad(), torch.cuda.stream(s):
            for _ in range(3):
                fwd(sx, sm)
        torch.cuda.current_stream().wait_stream(s)
        g = torch.cuda.CUDAGraph()
        with torch.no_grad(), torch.cuda.graph(g):
            out = fwd(sx, sm)
        r = {"envs": n, "eager_act_ms": 1e3 * timeit(eager), "graph_act_ms": 1e3 * timeit(g.replay)}
        try:
            cf = torch.compile(fwd, mode="max-autotune-no-cudagraphs")
            with torch.no_grad():
                r["compile_act_ms"] = 1e3 * timeit(lambda: cf(x, m), warm=3)
        except Exception as e:  # report, do not hide
            r["compile_error"] = str(e)[:200]
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)


def ppo_minibatch(agent, opt, x, act, oldlogp, adv, ret, val, msk, clip=0.2, ent=0.03, vf=0.5):
    _, newlogp, entropy, newval = agent.act(x, act, mask=msk)
    logratio = newlogp - oldlogp; ratio = logratio.exp()
    with torch.no_grad():
        approx_kl = ((ratio - 1) - logratio).mean()
    a = (adv - adv.mean()) / (adv.std() + 1e-8)
    pg = torch.max(-a * ratio, -a * torch.clamp(ratio, 1 - clip, 1 + clip)).mean()
    vu = (newval - ret) ** 2
    vc = (val + torch.clamp(newval - val, -clip, clip) - ret) ** 2
    loss = pg - ent * entropy.mean() + vf * 0.5 * torch.max(vu, vc).mean()
    opt.zero_grad(set_to_none=True)
    loss.backward()
    nn.utils.clip_grad_norm_(agent.parameters(), 0.5)
    opt.step()
    return approx_kl


def bench_learn():
    for M in (8192, 32768, 65536):
        agent = make_agent(); opt = torch.optim.Adam(agent.parameters(), lr=3e-4, eps=1e-5)
        x = torch.rand(M, F, device=dev); msk = torch.rand(M, A, device=dev) > 0.3; msk[:, 0] = True
        act = torch.zeros(M, dtype=torch.long, device=dev)
        z = lambda: torch.randn(M, device=dev)  # noqa: E731
        args = (x, act, z() - 4, z(), z(), z(), msk)
        r = {"minibatch": M, "eager_ms": 1e3 * timeit(lambda: ppo_minibatch(agent, opt, *args), reps=10)}
        try:
            agent2 = make_agent(); opt2 = torch.optim.Adam(agent2.parameters(), lr=3e-4, eps=1e-5)
            step = torch.compile(lambda *a: ppo_minibatch(agent2, opt2, *a))
            r["compile_ms"] = 1e3 * timeit(lambda: step(*args), reps=10, warm=3)
        except Exception as e:
            r["compile_error"] = str(e)[:300]
        def bf16():
            with torch.autocast("cuda", dtype=torch.bfloat16):
                return ppo_minibatch(agent, opt, *args)
        r["eager_bf16_autocast_ms"] = 1e3 * timeit(bf16, reps=10)
        r["samples_per_s_eager"] = M / (r["eager_ms"] / 1e3)
        print(json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)


# --------------------------------------------------------------------- e2e
def e2e(a):
    torch.manual_seed(a.seed); np.random.seed(a.seed)
    N, T = a.envs, a.rollout
    seed0 = a.seed * 10_000_000
    agent = TargetActorCritic(128).to(dev)
    opt = torch.optim.Adam(agent.parameters(), lr=3e-4, eps=1e-5)
    if a.compile:
        agent.trunk = torch.compile(agent.trunk, dynamic=False)
        agent.actor = torch.compile(agent.actor, dynamic=False)
    compact = a.store == "compact"
    if a.sim == "gpu":
        sim = GpuVec(N, seed0, a.lib, pool_n=a.pool)
        raw_dim = sim.ob
    else:
        from terraria_lite.ppo_agent import VecTerraria
        sim = VecTerraria(N, seed=seed0, workers=a.workers)
        o0, m0 = sim.reset()
        assert not compact, "cpu backend stores the binding's float32 obs"
    if compact:
        obs_b = torch.empty((T, N, raw_dim), dtype=torch.uint8, device=dev)
    else:
        obs_b = torch.empty((T, N, F), device=dev)
    act_b = torch.zeros((T, N), dtype=torch.long, device=dev)
    logp_b, rew_b, done_b, val_b = (torch.zeros((T, N), device=dev) for _ in range(4))
    msk_b = torch.zeros((T, N, A), dtype=torch.bool, device=dev)
    nxt = torch.empty((N, F), device=dev)
    if a.sim == "gpu":
        sim.encode(sim.raw, nxt); next_mask = sim.mask.bool()
    else:
        nxt.copy_(torch.as_tensor(o0)); next_mask = torch.as_tensor(m0, device=dev)
    next_done = torch.zeros(N, device=dev)
    mb = a.minibatch; nmb = N * T // mb
    t_collect = t_learn = 0.0; steps = 0; episodes = 0; ret_sum = 0.0
    digest = hashlib.sha256()
    log = []
    br = {"sim_s": 0.0, "h2d_s": 0.0}
    for it in range(a.iters):
        sync(); t0 = time.perf_counter()
        for t in range(T):
            if compact:
                obs_b[t] = sim.raw
            else:
                obs_b[t] = nxt
            done_b[t] = next_done; msk_b[t] = next_mask
            with torch.inference_mode():
                act, logp, _, v = agent.act(nxt, mask=next_mask)
            act_b[t], logp_b[t], val_b[t] = act, logp, v
            if a.sim == "gpu":
                if a.breakdown:
                    sync(); tb0 = time.perf_counter()
                r, ends = sim.step(act)
                rew_b[t] = r
                sim.encode(sim.raw, nxt); next_mask = sim.mask.bool()
                next_done = (ends != 0).float()
                if t % a.refill_every == a.refill_every - 1:
                    sim.maybe_refill()
                if a.breakdown:
                    sync(); br["sim_s"] += time.perf_counter() - tb0
            else:
                acts = act.cpu().numpy()                     # waits for inference
                tb0 = time.perf_counter()
                o, m, r, term, trunc, final, fin = sim.step(acts)
                tb1 = time.perf_counter()
                rew_b[t] = torch.as_tensor(r, device=dev)
                nxt.copy_(torch.as_tensor(o)); next_mask = torch.as_tensor(m, device=dev)
                next_done = torch.as_tensor((term | trunc).astype(np.float32), device=dev)
                if a.breakdown:
                    sync()
                br["sim_s"] += tb1 - tb0; br["h2d_s"] += time.perf_counter() - tb1
            steps += N
        sync(); t1 = time.perf_counter(); t_collect += t1 - t0
        if it == 0 and a.digest:
            for x in (act_b, rew_b, done_b):
                digest.update(x.cpu().numpy().tobytes())
        episodes += int(done_b[1:].sum()) + int(next_done.sum())
        ret_sum += float(rew_b.sum())
        with torch.no_grad():
            next_value = agent.value(nxt)
            adv = torch.zeros_like(rew_b); last = torch.zeros_like(next_value)
            for t in reversed(range(T)):
                nonterm = 1.0 - (next_done if t == T - 1 else done_b[t + 1])
                nv = next_value if t == T - 1 else val_b[t + 1]
                delta = rew_b[t] + a.gamma * nv * nonterm - val_b[t]
                last = delta + a.gamma * a.lam * nonterm * last
                adv[t] = last
            ret = adv + val_b
        b_obs = obs_b.reshape(N * T, -1); b_act = act_b.reshape(-1); b_logp = logp_b.reshape(-1)
        b_adv = adv.reshape(-1); b_ret = ret.reshape(-1); b_val = val_b.reshape(-1); b_msk = msk_b.reshape(N * T, A)
        xbuf = torch.empty((mb, F), device=dev) if compact else None
        for _ in range(a.epochs):
            perm = torch.randperm(N * T, device=dev)
            for s in range(nmb):
                idx = perm[s * mb:(s + 1) * mb]
                x = sim.encode(b_obs[idx], xbuf) if compact else b_obs[idx]
                ppo_minibatch(agent, opt, x, b_act[idx], b_logp[idx], b_adv[idx], b_ret[idx], b_val[idx], b_msk[idx])
        sync(); t_learn += time.perf_counter() - t1
        log.append({"it": it, "collect_s": round(t1 - t0, 3), "learn_s": round(time.perf_counter() - t1, 3)})
    skip = 1 if a.iters > 2 else 0   # first iteration includes warm-up / allocator growth
    c = sum(l["collect_s"] for l in log[skip:]); l_ = sum(l["learn_s"] for l in log[skip:])
    st = (a.iters - skip) * N * T
    out = {"sim": a.sim, "lib": os.path.basename(a.lib) if a.sim == "gpu" else "repo libterraria.so",
           "envs": N, "rollout": T, "store": a.store, "iters_timed": a.iters - skip, "minibatch": mb, "epochs": a.epochs,
           "collect_steps_per_s": round(st / c), "learn_s_per_iter": round(l_ / (a.iters - skip), 3),
           "collect_s_per_iter": round(c / (a.iters - skip), 3), "e2e_steps_per_s": round(st / (c + l_)),
           "collect_share": round(c / (c + l_), 3), "episodes": episodes, "reward_sum": round(ret_sum, 1),
           "peak_mem_GB": round(torch.cuda.max_memory_allocated() / 2**30, 1),
           "first_rollout_sha256": digest.hexdigest()[:16] if a.digest else None}
    if a.sim == "gpu":
        out["pool_refill_s_total"] = round(sim.reset_seconds, 3)
    out["breakdown_per_step_ms"] = {k: round(1e3 * v / (a.iters * T), 3) for k, v in br.items()}
    out["compiled"] = a.compile
    print(json.dumps(out), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd")
    p.add_argument("--sim", default="gpu")
    p.add_argument("--lib", default=os.path.join(HERE, "libgpusim.so"))
    p.add_argument("--envs", type=int, default=4096)
    p.add_argument("--rollout", type=int, default=128)
    p.add_argument("--iters", type=int, default=4)
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--minibatch", type=int, default=32768)
    p.add_argument("--store", default="flat")
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--pool", type=int, default=65536)
    p.add_argument("--refill-every", type=int, default=8)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--gamma", type=float, default=0.999)
    p.add_argument("--lam", type=float, default=0.99)
    p.add_argument("--digest", action="store_true")
    p.add_argument("--breakdown", action="store_true", help="sync around the simulator to time it (perturbs overlap)")
    p.add_argument("--compile", action="store_true", help="torch.compile the encoder and actor")
    p.add_argument("--threads", type=int, default=8)
    a = p.parse_args()
    torch.set_num_threads(a.threads)
    {"transfer": lambda: bench_transfer(), "infer": lambda: bench_infer(), "learn": lambda: bench_learn(),
     "e2e": lambda: e2e(a)}[a.cmd]()
