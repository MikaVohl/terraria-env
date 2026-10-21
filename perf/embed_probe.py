"""Tile-embedding lookup instead of one-hot x Linear in the targets encoder.

The cell MLP's first layer sees [one-hot tile (24), light, 4 entity features].
Multiplying a one-hot by W is a column lookup, so the layer equals
W_tile[:, id] + light * w_light + W_ent @ ent + b: the same parameters, the
same function, a different floating-point summation order. This probe times
one PPO minibatch update (forward, backward, Adam) from compact rows both ways
and reports the output difference.

    HIP_VISIBLE_DEVICES=7 PYTHONPATH=python python perf/embed_probe.py
"""
import json, time

import numpy as np
import torch
from torch.nn import functional as F


def main():
    from terraria_lite import SPEC
    from terraria_lite.compact import Expander, RAW_BYTES, LIGHT_LUT
    from terraria_lite.ppo_agent import VecTerraria
    from terraria_lite.target_agent import TargetActorCritic
    dev = torch.device("cuda")
    torch.manual_seed(0)
    agent = TargetActorCritic(128).to(dev)
    expand = Expander(dev)
    lut = torch.as_tensor(LIGHT_LUT, device=dev)
    off = RAW_BYTES - 4 * SPEC.status_len
    vec = VecTerraria(2048, seed=901 * 10_000_000, workers=16, native_autoreset=True, compact=True)
    raw, mask = vec.reset()
    rows = [raw.copy()]
    rng = np.random.default_rng(0)
    for _ in range(15):
        act = np.array([rng.choice(np.flatnonzero(m)) for m in vec.mask])
        raw = vec.step(act)[0]; rows.append(raw.copy())
    raw_all = torch.as_tensor(np.concatenate(rows), device=dev)
    enc = agent.trunk

    def trunk_embed(r):
        n = r.shape[0]
        tile = r[:, :SPEC.cells].long()
        light = lut[r[:, SPEC.cells:2 * SPEC.cells].long()]
        status = r[:, off:].contiguous().view(torch.float32)
        ent = status[:, SPEC.status_entity0:].reshape(n, SPEC.cells, 4)
        first, rest = enc.cells[0], enc.cells[1:]
        w = first.weight                                   # (32, kinds + 5)
        h = (F.embedding(tile, w[:, :SPEC.tile_kinds].t()) + light.unsqueeze(-1) * w[:, SPEC.tile_kinds]
             + F.linear(ent, w[:, SPEC.tile_kinds + 1:], first.bias))
        cells = rest(h)
        g = enc.global_features(torch.cat((cells.flatten(1), status[:, :SPEC.status_entity0]), -1))
        ctx = enc.context(cells[:, enc.neighborhoods, :].reshape(n, SPEC.reach_count, 9 * 32))
        return torch.cat((g, ctx.flatten(1)), -1)

    def heads(h, m):
        logits = agent.actor(h).masked_fill(~m, float("-inf"))
        return torch.log_softmax(logits, -1), agent.critic(h).squeeze(-1)

    out = {}
    with torch.no_grad():
        m = torch.ones((raw_all.shape[0], SPEC.n_actions), dtype=torch.bool, device=dev)
        a, va = heads(enc(expand(raw_all)), m)
        b, vb = heads(trunk_embed(raw_all), m)
        out["max_abs_logp_diff"] = float((a - b).abs().max())
        out["max_abs_value_diff"] = float((va - vb).abs().max())
    opt = torch.optim.Adam(agent.parameters(), lr=3e-4, eps=1e-5)
    for M in (8192, 16384):
        idx = torch.randint(0, raw_all.shape[0], (M,), device=dev)
        r = raw_all[idx]; m = torch.ones((M, SPEC.n_actions), dtype=torch.bool, device=dev)
        for name, trunk in (("onehot", lambda x: enc(expand(x))), ("embedding", trunk_embed)):
            def stepfn():
                lp, v = heads(trunk(r), m)
                loss = -lp[:, 0].mean() + v.pow(2).mean()
                opt.zero_grad(); loss.backward(); opt.step()
            for _ in range(5): stepfn()
            torch.cuda.synchronize(); t = time.perf_counter()
            for _ in range(30): stepfn()
            torch.cuda.synchronize()
            out[f"{name}_update_ms_mb{M}"] = round(1e3 * (time.perf_counter() - t) / 30, 3)
    print(json.dumps(out))


if __name__ == "__main__":
    main()
