"""Export "targets" checkpoints and their training curve for viz/.

    uv run python tools/viz_export_policy.py <run-dir> viz/data

<run-dir> holds step-*.pt checkpoints and curve.json/summary.json from
tools/iterate_ppo.py (depth-2 "targets" architecture only). Writes:
  policy-<steps>.bin  float16 weights, in viz/wasm/policy.c's blob order
  policy-0.bin        the seeded untrained initialisation, for contrast
  run.json            checkpoint list, trimmed curve, training config
Float16 halves the download; the page widens to float32 on load. The parity
check below compares the wasm forward pass with PyTorch on the same rounded
weights.
"""
import json, shutil, subprocess, sys
from pathlib import Path

import numpy as np
import torch

from terraria_lite import SPEC
from terraria_lite.spatial_agent import build_agent

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["trunk.cells.0.weight", "trunk.cells.0.bias", "trunk.cells.2.weight", "trunk.cells.2.bias",
         "trunk.global_features.0.weight", "trunk.global_features.0.bias",
         "trunk.global_features.2.weight", "trunk.global_features.2.bias",
         "trunk.context.0.weight", "trunk.context.0.bias", "actor.weight", "actor.bias",
         "actor.target.0.weight", "actor.target.0.bias", "actor.target.2.weight", "actor.target.2.bias",
         "critic.weight", "critic.bias", "actor.coordinates"]


def blob(state) -> np.ndarray:
    if "trunk.global_features.4.weight" in state or "trunk.extra" in state:
        raise SystemExit("only depth-2 targets checkpoints without extra features are supported")
    return np.concatenate([state[k].float().numpy().ravel() for k in ORDER]).astype(np.float16)


def main(run: Path, out: Path):
    out.mkdir(parents=True, exist_ok=True)
    curve = json.loads((run / "curve.json").read_text())
    summary = json.loads((run / "summary.json").read_text())
    evals = {r["steps"]: r["evaluation"] for r in curve}
    checkpoints = []
    torch.manual_seed(summary["seed"])
    fresh = build_agent("targets", 128, 0, 2, 32)
    items = [(0, fresh.state_dict())] + sorted(
        (int(p.stem.split("-")[1]), torch.load(p, map_location="cpu", weights_only=False)["model"])
        for p in run.glob("step-*.pt"))
    for steps, state in items:
        hidden, cell_width = state["trunk.global_features.2.weight"].shape[0], state["trunk.cells.0.weight"].shape[0]
        b = blob(state)
        (out / f"policy-{steps}.bin").write_bytes(b.tobytes())
        e = evals.get(steps, {})
        checkpoints.append({"steps": steps, "file": f"policy-{steps}.bin", "hidden": int(hidden),
                            "cell_width": int(cell_width), "floats": int(b.size),
                            "mean_achievements": e.get("mean_achievements"), "death_rate": e.get("death_rate"),
                            "hits": e.get("hits"), "episodes": e.get("episodes")})
    keep = ("collection_seconds", "optimisation_seconds", "policy_entropy", "approx_kl", "clip_fraction",
            "explained_variance")
    run_json = {
        "source": str(run), "architecture": summary["architecture"], "parameters": summary.get("parameters"),
        "config": {k: summary[k] for k in ("gamma", "ent_coef", "lr", "envs", "steps", "seed", "sps")},
        "checkpoints": checkpoints,
        "curve": [{"steps": r["steps"], "elapsed": r["elapsed_seconds"],
                   **{k: r["profile"].get(k) for k in keep},
                   **{k: r["evaluation"][k] for k in ("mean_achievements", "p90_achievements", "max_achievements",
                                                      "death_rate", "mean_return", "mean_peak_depth")},
                   "hits": r["evaluation"]["hits"], "first": {k: v["median"] for k, v in
                                                            r["evaluation"]["first_achievement_steps"].items()}}
                  for r in curve],
    }
    (out / "run.json").write_text(json.dumps(run_json, separators=(",", ":")))
    print(f"{len(checkpoints)} checkpoints -> {out}")
    check(out / checkpoints[-1]["file"], items[-1][1])


def check(path: Path, state):
    """wasm forward (policy.c) vs PyTorch on the same float16-rounded weights."""
    agent = build_agent("targets", 128, 0, 2, 32)
    rounded = {k: (v.half().float() if v.is_floating_point() else v) for k, v in state.items()}
    agent.load_state_dict(rounded)
    from terraria_lite import TerrariaLite
    env, rows = TerrariaLite(), []
    raw = []
    for seed in range(4):
        obs, _ = env.reset(seed=seed)
        for t in range(40):
            rows.append(obs.copy()); raw.append((env._tile.copy(), env._light.copy(), env._status.copy()))
            obs, *_ = env.step(int(np.flatnonzero(env.action_mask())[(t * 7) % env.action_mask().sum()]))
    x = torch.tensor(np.stack(rows))
    with torch.no_grad():
        h = agent.trunk(x)
        logits, value = agent.actor(h).numpy(), agent.critic(h).squeeze(-1).numpy()
    obs_bytes = b"".join(t.tobytes() + l.tobytes() + b"\0" * (-(2 * SPEC.cells) % 4) + s.tobytes() for t, l, s in raw)
    tmp = ROOT / "viz/data/.parity_obs.bin"
    tmp.write_bytes(obs_bytes)
    try:
        node = shutil.which("node") or str(Path.home() / ".local/bin/node")
        res = subprocess.run([node, str(ROOT / "tools/viz_policy_check.mjs"), str(path), str(tmp), str(len(raw))],
                             capture_output=True, text=True, check=True).stdout
    finally:
        tmp.unlink()
    got = np.array(json.loads(res), dtype=np.float32).reshape(len(raw), SPEC.n_actions + 1)
    dl, dv = np.abs(got[:, :-1] - logits).max(), np.abs(got[:, -1] - value).max()
    print(f"policy parity on {len(raw)} observations: max |dlogit| {dl:.2e}, max |dvalue| {dv:.2e}")
    if dl > 1e-3 or dv > 1e-3:
        raise SystemExit("wasm policy disagrees with PyTorch")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "viz/data")
