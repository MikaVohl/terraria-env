"""Standalone check for silent wrong results when several processes share one GPU.

Pure PyTorch (no project imports). Every op is built for --variants input sets
and computed once per set as a reference, then recomputed in a loop on a
randomly chosen set; each repeat is compared with that set's reference, so a
read of stale memory (another set's result) shows up as a mismatch. Counted
per op:
  nonfinite  -- any NaN/inf in an output
  corrupt    -- max |out - ref| / max |ref| > --tol (default 1e-2, far above
                bf16 rounding and split-K reordering)
  nondet     -- not bit-identical to the reference (informational)

Ops reproduce the PPO learner's work: the GEMMs of the 'targets' policy at the
minibatch size (forward, grad-input and grad-weight), bias-gradient column sums,
the policy forward/backward with a toy loss and with the trainer's PPO loss
(policy_*, ppo_*; bf16 autocast or float32, eager or torch.compile), a fused
and a foreach Adam step, and (--zoo) other eager reductions. Run one copy alone
and several copies on the same GPU at once:

  HIP_VISIBLE_DEVICES=7 python stress.py --seconds 300 --tag alone
  for i in 1 2 3; do HIP_VISIBLE_DEVICES=7 python stress.py --seconds 300 --tag p$i & done; wait

Prints one JSON line per report interval and a final summary.
"""
import argparse
import json
import os
import random
import socket
import time

import torch
from torch import nn
from torch.nn import functional as F

# 'targets' policy dimensions (TargetActorCritic, hidden 128) at minibatch 8192.
CELLS, KINDS, STATUS0, REACH, ACTIONS = 99, 24, 92, 20, 83
OBS = CELLS * KINDS + CELLS + STATUS0 + CELLS * 4      # 2963
MB = 8192


class Policy(nn.Module):
    """Same layers and data flow as terraria_lite.target_agent.TargetActorCritic."""

    def __init__(self, hidden=128):
        super().__init__()
        self.cells = nn.Sequential(nn.Linear(KINDS + 5, 32), nn.ReLU(), nn.Linear(32, 32), nn.ReLU())
        self.glob = nn.Sequential(nn.Linear(CELLS * 32 + STATUS0, hidden), nn.Tanh(),
                                  nn.Linear(hidden, hidden), nn.Tanh())
        self.context = nn.Sequential(nn.Linear(9 * 32, 64), nn.ReLU())
        self.register_buffer("hoods", torch.randint(0, CELLS, (REACH, 9)))
        self.other = nn.Linear(hidden, ACTIONS - 2 * REACH)
        self.target = nn.Sequential(nn.Linear(hidden + 64, 64), nn.Tanh(), nn.Linear(64, 2))
        self.critic = nn.Linear(hidden, 1)

    def forward(self, x):
        n = x.shape[0]
        end = CELLS * KINDS
        status = x[:, end + CELLS:]
        tiles = x[:, :end].reshape(n, CELLS, KINDS)
        light = x[:, end:end + CELLS].unsqueeze(-1)
        ent = status[:, STATUS0:].reshape(n, CELLS, 4)
        c = self.cells(torch.cat((tiles, light, ent), -1))
        g = self.glob(torch.cat((c.flatten(1), status[:, :STATUS0]), -1))
        ctx = self.context(c[:, self.hoods, :].reshape(n, REACH, 9 * 32))
        z = torch.cat((g[:, None, :].expand(n, REACH, g.shape[1]), ctx), -1)
        scores = self.target(z)
        logits = torch.cat((self.other(g), scores[:, :, 0], scores[:, :, 1]), -1)
        return logits, self.critic(g).squeeze(-1)


def ppo_like_loss(model, x, action, bf16):
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=bf16):
        logits, value = model(x)
    logp = logits.float().log_softmax(-1)
    ratio = (logp.gather(-1, action[:, None]).squeeze(-1) - logp.detach().gather(-1, action[:, None]).squeeze(-1) * 0.9).exp()
    entropy = -(logp.exp() * logp).sum(-1)
    return -(ratio.mean()) + 0.5 * value.float().pow(2).mean() - 0.01 * entropy.mean()


def ppo_loss(model, x, action, mask, old_logp, adv, ret, old_value, bf16, clip=0.2):
    """terraria_lite.ppo_agent._ppo_loss with _score_bf16 (clip_vloss, entropy .03, vf .5)."""
    with torch.autocast("cuda", dtype=torch.bfloat16, enabled=bf16):
        logits, value = model(x)
    logits = logits.float().masked_fill(~mask, float("-inf"))
    dist = torch.distributions.Categorical(logits=logits, validate_args=False)
    newlogp, entropy, newval = dist.log_prob(action), dist.entropy(), value.float()
    logratio = newlogp - old_logp
    ratio = logratio.exp()
    adv = (adv - adv.mean()) / (adv.std() + 1e-8)
    pg = torch.max(-adv * ratio, -adv * torch.clamp(ratio, 1 - clip, 1 + clip)).mean()
    v_unclipped = (newval - ret) ** 2
    v_clipped = (old_value + torch.clamp(newval - old_value, -clip, clip) - ret) ** 2
    v_loss = 0.5 * torch.max(v_unclipped, v_clipped).mean()
    return pg - 0.03 * entropy.mean() + 0.5 * v_loss


def make_ops(args, dev, seed=1234):
    g = torch.Generator().manual_seed(seed)
    ops = {}

    def rnd(*shape, scale=1.0):
        return (torch.randn(*shape, generator=g) * scale).to(dev)

    # Raw GEMMs, the learner's shapes: forward, grad-input, grad-weight.
    shapes = [(MB, CELLS * 32 + STATUS0, 128), (MB, OBS, 128), (MB, 128, 128), (MB * REACH, 288, 64),
              (MB * CELLS, 29, 32), (MB * REACH, 192, 64)]
    for dtype_name in args.gemm_dtypes:
        dt = {"bf16": torch.bfloat16, "fp32": torch.float32}[dtype_name]
        for (m, k, n) in shapes:
            x, w, dy = rnd(m, k).to(dt), rnd(n, k, scale=k ** -0.5).to(dt), rnd(m, n).to(dt)

            def gemm(x=x, w=w, dy=dy):
                return [F.linear(x, w), dy @ w, dy.t() @ x]
            ops[f"gemm_{dtype_name}_{m}x{k}x{n}"] = gemm

    # Column sums (the bias gradient of a Linear layer: grad_out.sum(0)).
    for dtype_name in args.reduce_dtypes:
        dt = {"bf16": torch.bfloat16, "fp32": torch.float32}[dtype_name]
        for (m, n) in [(MB * CELLS, 32), (MB * REACH, 64), (MB * REACH, 2), (MB, 128), (MB, 43)]:
            dy = rnd(m, n, scale=1e-4).to(dt)

            def colsum(dy=dy):
                return [dy.sum(0)]
            ops[f"colsum_{dtype_name}_{m}x{n}"] = colsum

    # Other reduction kernels the trainer runs eagerly (full, row, Welford, norms).
    if args.zoo:
        for dtype_name, dt in (("fp32", torch.float32), ("bf16", torch.bfloat16)):
            big, rows, vec = rnd(1 << 23).to(dt), rnd(MB, 3260).to(dt), rnd(MB * 16).to(dt)
            tall = rnd(MB * 16, 128).to(dt)
            ops[f"zoo_{dtype_name}_fullsum"] = lambda big=big: [big.sum(), big.float().sum()]
            ops[f"zoo_{dtype_name}_rowsum"] = lambda rows=rows: [rows.sum(1)]
            ops[f"zoo_{dtype_name}_mean_std"] = lambda vec=vec: [vec.mean(), vec.std(), vec.var(0)]
            ops[f"zoo_{dtype_name}_amax"] = lambda big=big: [big.amax(), big.abs().max()]
            ops[f"zoo_{dtype_name}_norm"] = lambda big=big: [torch.linalg.vector_norm(big)]
            ops[f"zoo_{dtype_name}_colsum_tall"] = lambda tall=tall: [tall.sum(0), tall.mean(0)]
            ps = [rnd(*s).to(dt) for s in ((128, 3260), (128,), (128, 128), (64, 288), (32, 29), (43, 128))]
            ops[f"zoo_{dtype_name}_foreach_norm"] = lambda ps=ps: list(torch._foreach_norm(ps))

    torch.manual_seed(99)
    base = Policy().to(dev)
    x = (torch.rand(MB, OBS, generator=g) < 0.05).float().to(dev)
    action = torch.randint(0, ACTIONS, (MB,), generator=g).to(dev)

    for mode in args.models:                      # e.g. bf16-eager, bf16-compile, fp32-eager
        prec, how = mode.split("-")
        model = Policy().to(dev)
        model.load_state_dict(base.state_dict())
        params = list(model.parameters())
        lossf = ppo_like_loss
        if how == "compile":
            lossf = torch.compile(ppo_like_loss, dynamic=False)

        def step(model=model, params=params, lossf=lossf, bf16=prec == "bf16"):
            for p in params:
                p.grad = None
            loss = lossf(model, x, action, bf16)
            loss.backward()
            return [loss.detach()] + [p.grad for p in params]
        ops[f"policy_{mode}"] = step

        # The trainer's full PPO minibatch loss (one compiled graph with compile_all).
        mask = torch.rand(MB, ACTIONS, generator=g).to(dev) < 0.5
        mask[torch.arange(MB, device=dev), action] = True
        with torch.no_grad():
            logits, val = base(x)
            old_logp = torch.distributions.Categorical(
                logits=logits.masked_fill(~mask, float("-inf"))).log_prob(action)
            old_logp = old_logp + 0.1 * torch.randn(MB, generator=g).to(dev)
        adv, ret = torch.randn(MB, generator=g).to(dev), val + torch.randn(MB, generator=g).to(dev)
        pfn = torch.compile(ppo_loss, dynamic=False) if how == "compile" else ppo_loss

        def ppo_step(model=model, params=params, pfn=pfn, bf16=prec == "bf16", mask=mask, old_logp=old_logp,
                     adv=adv, ret=ret, val=val):
            for p in params:
                p.grad = None
            loss = pfn(model, x, action, mask, old_logp, adv, ret, val, bf16)
            loss.backward()
            return [loss.detach()] + [p.grad for p in params]
        ops[f"ppo_{mode}"] = ppo_step

    if args.adam:
        p0 = [p.detach().clone() for p in base.parameters()]
        g0 = [torch.randn_like(p) for p in p0]
        m0 = [torch.randn_like(p).abs() * 1e-3 for p in p0]
        v0 = [torch.rand_like(p) * 1e-4 for p in p0]
        for fused in (True, False):
            ps = [nn.Parameter(p.clone()) for p in p0]
            opt = torch.optim.Adam(ps, lr=3e-4, eps=1e-5, fused=fused, foreach=None if fused else True)
            for p, gg, m, v in zip(ps, g0, m0, v0):
                p.grad = gg.clone()
                opt.state[p] = {"step": torch.tensor(10.0, device=dev) if fused else torch.tensor(10.0),
                                "exp_avg": m.clone(), "exp_avg_sq": v.clone()}

            def adam(opt=opt, ps=ps):
                with torch.no_grad():
                    for p, a, m, v in zip(ps, p0, m0, v0):
                        p.copy_(a)
                        st = opt.state[p]
                        st["exp_avg"].copy_(m)
                        st["exp_avg_sq"].copy_(v)
                        st["step"].fill_(10.0)
                opt.step()
                return [p.detach() for p in ps]
            ops[f"adam_{'fused' if fused else 'foreach'}"] = adam
    return ops


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=300)
    ap.add_argument("--tag", default="run")
    ap.add_argument("--tol", type=float, default=1e-2)
    ap.add_argument("--gemm-dtypes", default="bf16,fp32")
    ap.add_argument("--reduce-dtypes", default="bf16,fp32")
    ap.add_argument("--models", default="bf16-eager,bf16-compile,fp32-eager")
    ap.add_argument("--no-adam", dest="adam", action="store_false")
    ap.add_argument("--zoo", action="store_true", help="also other eager reduction kernels")
    ap.add_argument("--only", default="", help="comma list of op-name substrings to keep")
    ap.add_argument("--blas", default="", help="cublaslt|cublas (hipBLASLt|hipBLAS/rocBLAS)")
    ap.add_argument("--report", type=float, default=30)
    ap.add_argument("--dump", default="", help="directory for the first bad outputs")
    ap.add_argument("--variants", type=int, default=3,
                    help="input sets per op, picked at random each repeat, so a read of stale memory "
                         "(another set's result) is a mismatch; 1 = repeat identical work")
    args = ap.parse_args()
    args.gemm_dtypes = [d for d in args.gemm_dtypes.split(",") if d]
    args.reduce_dtypes = [d for d in args.reduce_dtypes.split(",") if d]
    args.models = [m for m in args.models.split(",") if m]
    if args.blas:
        torch.backends.cuda.preferred_blas_library(args.blas)
    torch.backends.cuda.matmul.allow_tf32 = False
    dev = torch.device("cuda")
    sets = [make_ops(args, dev, seed=1234 + v) for v in range(args.variants)]
    if args.only:
        keep = args.only.split(",")
        sets = [{k: f for k, f in ops.items() if any(s in k for s in keep)} for ops in sets]
    ops = sets[0]
    refs, scale = {}, {}
    for name in ops:
        for v, variant in enumerate(sets):
            variant[name]()                       # warm-up / compile / autotune
            torch.cuda.synchronize()
            refs[name, v] = [t.detach().clone() for t in variant[name]()]
            torch.cuda.synchronize()
            assert all(bool(torch.isfinite(t).all()) for t in refs[name, v]), name
            scale[name, v] = [t.float().abs().max().clamp_min(1e-30) for t in refs[name, v]]
    pick = random.Random(os.getpid())
    stats = {n: dict(runs=0, nonfinite=0, corrupt=0, nondet=0, worst=0.0) for n in ops}
    dumped = 0
    head = dict(tag=args.tag, host=socket.gethostname(), pid=os.getpid(),
                hip=os.environ.get("HIP_VISIBLE_DEVICES"), blas=str(torch.backends.cuda.preferred_blas_library()),
                torch=torch.__version__, ops=list(ops))
    print(json.dumps(dict(start=head)), flush=True)
    t0 = last = time.time()
    while time.time() - t0 < args.seconds:
        for name in ops:
            v = pick.randrange(len(sets))
            outs = sets[v][name]()
            errs = torch.stack([((o.float() - r.float()).abs().max() / s) for o, r, s in
                                zip(outs, refs[name, v], scale[name, v])])
            fin = torch.stack([torch.isfinite(o).all() for o in outs])
            errs, fin = errs.cpu(), fin.cpu()        # one sync per op
            st = stats[name]
            st["runs"] += 1
            bad_fin = not bool(fin.all())
            emax = float(errs.nan_to_num(float("inf")).max())
            st["nonfinite"] += bad_fin
            st["corrupt"] += (emax > args.tol) and not bad_fin
            st["nondet"] += emax > 0
            st["worst"] = max(st["worst"], emax)
            if (bad_fin or emax > args.tol):
                i = int(errs.nan_to_num(float("inf")).argmax())
                print(json.dumps(dict(bad=name, run=st["runs"], output=i, relerr=emax, nonfinite=bad_fin,
                                      t=round(time.time() - t0, 1))), flush=True)
                if args.dump and dumped < 5:
                    os.makedirs(args.dump, exist_ok=True)
                    torch.save(dict(out=outs[i].cpu(), ref=refs[name, v][i].cpu(), name=name, output=i, variant=v),
                               f"{args.dump}/{args.tag}-{name}-{st['runs']}.pt")
                    dumped += 1
        if time.time() - last > args.report:
            last = time.time()
            print(json.dumps(dict(t=round(last - t0), tag=args.tag,
                                  bad={n: s for n, s in stats.items() if s["nonfinite"] or s["corrupt"]},
                                  runs=sum(s["runs"] for s in stats.values()))), flush=True)
    print(json.dumps(dict(final=head, seconds=round(time.time() - t0), stats=stats)), flush=True)


if __name__ == "__main__":
    main()
