"""Correctness checks for memory agents (memory_agent.py) in the fast trainer.

    PYTHONPATH=python python tools/memory_checks.py [--device cuda] [--train]

1. Reset: a lane whose `done` is set continues exactly like a fresh state.
2. Replay: the update's sequence pass (fused RNN / batched attention from the
   rollout-start snapshot) reproduces the rollout's step-by-step outputs,
   across episode starts, for warm states and transformer windows shorter and
   longer than the rollout.
3. --train: a short real training run from a sharp random policy records
   first-minibatch approx KL ~ 0 every iteration (the update replays the
   rollout: ratio == 1 before any step),
   and the saved checkpoint round-trips through load_agent, evaluate and
   tools/policy_diagnostics.diagnose.
"""
import argparse
import sys
import tempfile
from pathlib import Path

import torch

from terraria_lite import SPEC
from terraria_lite.memory_agent import MemoryActorCritic

CASES = [("gru", 64, 0), ("lstm", 64, 0), ("transformer", 64, 8), ("transformer", 128, 40)]


def observations(steps, lanes, generator, device):
    """Plausible inputs: one-hot tiles, light in [0,1], small status values."""
    tiles = torch.randint(SPEC.tile_kinds, (steps, lanes, SPEC.cells), generator=generator)
    onehot = torch.nn.functional.one_hot(tiles, SPEC.tile_kinds).float().flatten(2)
    rest = torch.rand((steps, lanes, SPEC.obs_size - onehot.shape[-1]), generator=generator)
    return torch.cat((onehot, rest), -1).to(device)


def make_agent(memory, size, length, device):
    torch.manual_seed(0)
    agent = MemoryActorCritic(memory, size, length).to(device).eval()
    with torch.no_grad():
        for p in agent.core.parameters():      # open the zero-initialised residual branches too
            p.add_(0.05 * torch.randn_like(p))
    return agent


def rollout(agent, x, done, state):
    outs = []
    for t in range(len(x)):
        h, state = agent.core_step(x[t], state, done[t])
        outs.append(h)
    return torch.stack(outs), state


@torch.no_grad()
def check_reset(memory, size, length, device):
    agent = make_agent(memory, size, length, device)
    g = torch.Generator().manual_seed(1)
    lanes, warm, steps = 4, 37, 20
    x = observations(warm + steps, lanes, g, device)
    done = torch.zeros(warm + steps, lanes, device=device)
    done[warm, 1] = 1.0          # lane 1 starts a new episode at step `warm`
    out, _ = rollout(agent, x, done, agent.initial_state(lanes, device))
    fresh, _ = rollout(agent, x[warm:], torch.zeros(steps, lanes, device=device), agent.initial_state(lanes, device))
    err = (out[warm:, 1] - fresh[:, 1]).abs().max().item()
    differs = (out[warm:, 0] - fresh[:, 0]).abs().max().item()   # lane 0 kept its memory
    assert err < 1e-5, f"{memory}: reset lane deviates from a fresh state by {err}"
    assert differs > 1e-4, f"{memory}: memory has no effect ({differs})"
    return err


@torch.no_grad()
def check_replay(memory, size, length, device):
    agent = make_agent(memory, size, length, device)
    g = torch.Generator().manual_seed(2)
    lanes, warm, steps = 6, 50, 32
    x = observations(warm + steps, lanes, g, device)
    done = (torch.rand((warm + steps, lanes), generator=g) < 0.06).float().to(device)
    done[warm, 0] = 1.0                        # an episode start on the rollout's first step
    done[warm + 5, :] = 1.0                    # all lanes at once
    _, state = rollout(agent, x[:warm], done[:warm], agent.initial_state(lanes, device))
    snapshot = agent.snapshot(state)
    stepped, _ = rollout(agent, x[warm:], done[warm:], state)
    lanes_idx = torch.tensor([4, 0, 2, 5, 1, 3], device=device)          # a shuffled minibatch of lanes
    replay = agent.sequence(x[warm:][:, lanes_idx].reshape(steps * lanes, -1), agent.select(snapshot, lanes_idx),
                            done[warm:][:, lanes_idx]).reshape(steps, lanes, -1)
    err = (replay - stepped[:, lanes_idx]).abs().max().item()
    assert err < 2e-5, f"{memory}: sequence replay deviates from the rollout by {err}"
    return err


def check_training(device):
    from terraria_lite.ppo_agent import Config, train
    from terraria_lite.ppo_eval import evaluate, load_agent
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from policy_diagnostics import diagnose
    results = {}
    for memory, size, length in [("gru", 64, 0), ("lstm", 64, 0), ("transformer", 64, 16)]:
        kls = []
        with tempfile.TemporaryDirectory() as tmp:
            path, init = str(Path(tmp) / "m.pt"), str(Path(tmp) / "init.pt")
            # Start from a sharp policy with open memory branches, so a replay
            # mismatch shows in the KL (a near-uniform initial policy hides it).
            sharp = make_agent(memory, size, length, "cpu")
            with torch.no_grad():
                for p in sharp.actor.parameters():
                    p.mul_(100.0)
            torch.save({"model": sharp.state_dict(), "environment_version": SPEC.version,
                        "obs_size": SPEC.obs_size, "n_actions": SPEC.n_actions}, init)
            cfg = Config(init=init, total_steps=16 * 64 * 3, num_envs=16, rollout=64, minibatches=4, epochs=2,
                         architecture="targets", potential_coef=3.0, memory=memory, memory_size=size,
                         memory_len=length, device=device, collect_device=device, quiet=True, save=path,
                         native_autoreset=True, compact_obs=True, sim_workers=2, gamma=.999, gae_lambda=.99,
                         ent_coef=.03)
            summary = train(cfg, checkpoint_callback=lambda a, s, p: kls.append(p["first_minibatch_kl"]))
            agent = load_agent(path, "cpu")
            assert type(agent) is MemoryActorCritic and agent.memory == memory
            ev = evaluate(agent, [23000001, 23000002], num_envs=2, sample_seed=54321, max_steps=200)
            dg = diagnose(agent, [23000001, 23000002], max_steps=200)
        assert max(abs(k) for k in kls) < 1e-6, f"{memory}: first-minibatch KL {kls}"
        results[memory] = {"first_minibatch_kl": kls, "params": summary["parameters"],
                           "eval_episodes": ev["episodes"], "diag_episodes": dg["episodes"]}
        print(memory, results[memory], flush=True)
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--device", default="cpu")
    p.add_argument("--train", action="store_true")
    a = p.parse_args()
    for case in CASES:
        print("reset ", case, f"{check_reset(*case, a.device):.2e}", flush=True)
        print("replay", case, f"{check_replay(*case, a.device):.2e}", flush=True)
    if a.train:
        check_training(a.device)
    print("memory checks passed")


if __name__ == "__main__":
    main()
