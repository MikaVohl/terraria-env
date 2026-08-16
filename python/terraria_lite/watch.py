"""Record one rollout of a trained policy and watch it in the pixel frontend.

The two halves never share a process. This script plays an episode and writes
a *tape* -- the seed plus the action taken on every tick -- and `terraria-px
--watch` replays it.

That split is deliberate. The engine is deterministic (selftest pins
byte-identical state after 1500 identical actions), so replaying a tape
reproduces the episode exactly rather than approximating it. In exchange:

  - torch never has to live in the same process as SDL,
  - `libterraria` stays free of an SDL dependency the trainer would pay for,
  - the frontend's interpolation, camera easing and frame pacing are reused
    as-is instead of being re-implemented on the Python side,
  - and a tape is a small text file, so a good run can be kept and re-watched.

    uv run python -m terraria_lite.watch --policy ppo_terraria.pt --play
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import torch

from terraria_lite import SPEC, TerrariaLite


def _load(path: Path):
    """Return (act_fn, kind). Distinguishes PPO from DQN by state-dict keys.

    PPO saves an ActorCritic (trunk/actor/critic); the DQN saves a plain
    Sequential. Sniffing the checkpoint beats a --kind flag the user would
    have to remember and could get wrong.
    """
    sd = torch.load(path, map_location="cpu")
    keys = set(sd)

    if any(k.startswith("actor.") for k in keys):
        from terraria_lite.ppo_agent import ActorCritic
        net = ActorCritic(SPEC.obs_size, SPEC.n_actions)
        net.load_state_dict(sd)
        net.eval()

        def ppo(obs, mask, greedy):
            with torch.no_grad():
                logits = net.actor(net.trunk(torch.as_tensor(obs).unsqueeze(0)))
                logits = logits.masked_fill(~torch.as_tensor(mask).unsqueeze(0),
                                            float("-inf"))
                if greedy:
                    return int(logits.argmax())
                return int(torch.distributions.Categorical(logits=logits).sample())

        return ppo, "ppo"

    # DQN: infer the hidden width from the checkpoint rather than assuming it.
    import torch.nn as nn
    hidden = sd["0.weight"].shape[0]
    net = nn.Sequential(
        nn.Linear(SPEC.obs_size, hidden), nn.ReLU(),
        nn.Linear(hidden, hidden), nn.ReLU(),
        nn.Linear(hidden, SPEC.n_actions),
    )
    net.load_state_dict(sd)
    net.eval()

    def dqn(obs, mask, greedy):
        with torch.no_grad():
            q = net(torch.as_tensor(obs))
            q = q.masked_fill(~torch.as_tensor(mask), float("-inf"))
            if greedy:
                return int(q.argmax())
            # Match the trained behaviour: eps-greedy at the annealed floor.
            if np.random.random() < 0.05:
                return int(np.random.choice(np.flatnonzero(mask)))
            return int(q.argmax())

    return dqn, "dqn"


def rollout(act_fn, seed: int, greedy: bool, max_steps: int | None = None):
    env = TerrariaLite(max_steps=max_steps)
    obs, _ = env.reset(seed=seed)
    actions: list[int] = []
    while True:
        a = act_fn(obs, env.action_mask(), greedy)
        actions.append(a)
        obs, _, term, trunc, info = env.step(a)
        if term or trunc:
            break
    env.close()
    return actions, info, term


def write_tape(path: Path, seed: int, max_steps: int, label: str,
               actions: list[int]) -> None:
    with path.open("w") as f:
        f.write("# terraria-lite tape v1\n")
        f.write(f"seed {seed}\n")
        f.write(f"max_steps {max_steps}\n")
        f.write(f"label {label}\n")
        f.write(f"actions {len(actions)}\n")
        f.write("".join(f"{a}\n" for a in actions))


def _viewer() -> Path | None:
    """Absolute path to terraria-px, or None if it is not built.

    Absolute on purpose. `Path("./terraria-px")` stringifies to
    "terraria-px" -- pathlib drops the leading "./" -- and subprocess resolves
    a bare name against PATH, not the working directory. So the obvious
    spelling finds the binary with exists() and then fails to launch it.

    The repo root is derived from this file rather than assumed to be the cwd,
    so recording a tape from somewhere else still finds the viewer.
    """
    root = Path(__file__).resolve().parents[2]   # <repo>/python/terraria_lite
    for c in (root / "terraria-px", Path.cwd() / "terraria-px"):
        if c.is_file() and os.access(c, os.X_OK):
            return c
    found = shutil.which("terraria-px")
    return Path(found) if found else None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        description="Record a policy rollout and watch it in terraria-px.")
    p.add_argument("--policy", type=Path, default=Path("ppo_terraria.pt"),
                   help="checkpoint; PPO or DQN is detected from its keys")
    p.add_argument("--seed", type=int, default=1, help="world seed to play")
    p.add_argument("--out", type=Path, default=Path("rollout.tape"))
    p.add_argument("--greedy", action="store_true",
                   help="argmax instead of sampling. Cleaner to watch, but it "
                        "is not the policy the reported metrics came from")
    p.add_argument("--best-of", type=int, default=1, metavar="N",
                   help="play N consecutive seeds and tape the best one")
    p.add_argument("--play", action="store_true",
                   help="launch terraria-px on the tape when done")
    p.add_argument("--tick-ms", type=int, default=80, metavar="MS",
                   help="playback speed passed to terraria-px, 10..1000")
    a = p.parse_args(argv)

    if not a.policy.exists():
        print(f"no checkpoint at {a.policy}. Train one first:\n"
              f"  uv run python -m terraria_lite.ppo_agent --steps 600000",
              file=sys.stderr)
        return 2

    # Mirrors terraria-px's own bounds. Checking here means a typo costs a
    # message rather than a full --best-of sweep followed by a rejection.
    if not 10 <= a.tick_ms <= 1000:
        print(f"--tick-ms must be between 10 and 1000 (got {a.tick_ms})",
              file=sys.stderr)
        return 2

    act_fn, kind = _load(a.policy)
    print(f"{a.policy.name}: {kind}, {'greedy' if a.greedy else 'sampled'}")

    best = None
    for k in range(a.best_of):
        seed = a.seed + k
        actions, info, died = rollout(act_fn, seed, a.greedy)
        print(f"  seed {seed:<4} {info['achievements']:2d} achievements  "
              f"{info['steps']:5d} steps  return {info['episode_return']:+.2f}"
              f"{'  (died)' if died else ''}")
        # Ties break toward the longer episode. Several seeds routinely reach
        # the same achievement count and one of them died at 45 steps; that is
        # a miserable thing to sit and watch.
        key = (info["achievements"], info["steps"])
        if best is None or key > (best[1]["achievements"], best[1]["steps"]):
            best = (seed, info, actions)

    seed, info, actions = best
    label = (f"{a.policy.stem} {kind} seed {seed} "
             f"{info['achievements']}/{SPEC.n_achievements} ach")
    write_tape(a.out, seed, SPEC.default_steps, label, actions)
    print(f"wrote {a.out} -- {len(actions)} actions, seed {seed}")

    if not a.play:
        print(f"watch it with:  ./terraria-px --watch {a.out}")
        return 0

    exe = _viewer()
    if exe is None:
        print("terraria-px is not built. Run `make terraria-px` (needs SDL2).",
              file=sys.stderr)
        return 1
    return subprocess.call([str(exe), "--watch", str(a.out.resolve()),
                            "--tick-ms", str(a.tick_ms)])


if __name__ == "__main__":
    raise SystemExit(main())
