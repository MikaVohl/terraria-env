"""Budgeted, auditable development evaluation. No code execution or LLM judge."""
from collections import defaultdict
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics as stats
import time

from terraria_lite import SPEC
from terraria_lite.llm_protocol import Session, canonical, digest, validate_seed
from terraria_lite.llm_providers import OpenRouter, ProviderError

HARNESS = "terraria-llm-dev-v0.1"
DEFAULTS = {
    "provider": "random", "model": None, "reasoning_effort": "high",
    "seeds": [31000001], "replicates": 1, "random_seed": 12345,
    "max_steps": 3000, "max_calls": 256, "max_actions_per_call": 1,
    "max_output_tokens": 8192, "max_total_tokens_per_episode": 1_000_000,
    "max_context_bytes": 100_000, "max_wall_seconds": 1800,
    "request_timeout_seconds": 120, "history_turns": 8, "notes_max_chars": 2048,
    "max_cost_usd_total": 0.0, "input_usd_per_token_ceiling": None,
    "output_usd_per_token_ceiling": None, "pricing_source": None,
}


def config(raw):
    if not isinstance(raw, dict) or set(raw) - set(DEFAULTS):
        raise ValueError("Unknown configuration fields")
    c = {**DEFAULTS, **raw}
    if c["provider"] not in ("random", "noop", "openrouter"):
        raise ValueError("Unknown provider")
    for key, maximum in {"replicates": 10, "max_steps": 3000, "max_calls": 3000,
                         "max_actions_per_call": 16, "max_output_tokens": 128000,
                         "max_total_tokens_per_episode": 100_000_000,
                         "max_context_bytes": 1_000_000, "max_wall_seconds": 86400,
                         "request_timeout_seconds": 600, "history_turns": 64,
                         "notes_max_chars": 8192}.items():
        if type(c[key]) is not int or not 1 <= c[key] <= maximum:
            raise ValueError(f"Invalid positive integer budget: {key}")
    if type(c["random_seed"]) is not int or not 0 <= c["random_seed"] < 2**32:
        raise ValueError("Invalid random seed")
    if not isinstance(c["seeds"], list) or not 1 <= len(c["seeds"]) <= 128 or len(set(c["seeds"])) != len(c["seeds"]):
        raise ValueError("Provide 1..128 distinct world seeds; use replicates explicitly")
    for seed in c["seeds"]:
        validate_seed(seed)
    if type(c["max_cost_usd_total"]) not in (int, float) or not math.isfinite(c["max_cost_usd_total"]) or c["max_cost_usd_total"] < 0:
        raise ValueError("Invalid total dollar budget")
    if c["provider"] == "openrouter":
        if not isinstance(c["model"], str) or not re.fullmatch(r"[A-Za-z0-9_./:-]+", c["model"]):
            raise ValueError("An explicit OpenRouter model ID is required")
        if c["reasoning_effort"] not in ("low", "medium", "high", "xhigh", "max"):
            raise ValueError("Invalid reasoning effort")
        for key in ("input_usd_per_token_ceiling", "output_usd_per_token_ceiling"):
            if type(c[key]) not in (int, float) or not math.isfinite(c[key]) or c[key] <= 0:
                raise ValueError("Explicit positive pricing ceilings required for paid calls")
        if not isinstance(c["pricing_source"], str) or not c["pricing_source"] or c["max_cost_usd_total"] <= 0:
            raise ValueError("Paid runs require pricing provenance and a positive spend limit")
    return c


def response_schema(c):
    return {"type": "object", "properties": {
        "actions": {"type": "array", "minItems": 1, "maxItems": c["max_actions_per_call"],
                    "items": {"type": "integer", "minimum": 0, "maximum": SPEC.n_actions-1}},
        "memory": {"type": "string", "maxLength": c["notes_max_chars"]}},
        "required": ["actions", "memory"], "additionalProperties": False}


def parse_response(text, c):
    try:
        obj = json.loads(text)
        assert isinstance(obj, dict) and set(obj) == {"actions", "memory"}
        actions, memory = obj["actions"], obj["memory"]
        assert isinstance(actions, list) and 1 <= len(actions) <= c["max_actions_per_call"]
        assert all(type(a) is int and 0 <= a < SPEC.n_actions for a in actions)
        assert isinstance(memory, str) and len(memory) <= c["notes_max_chars"]
        return actions, memory, True
    except (ValueError, TypeError, AssertionError):
        # Atomic validation: never execute the valid prefix of a malformed batch.
        return [None], "", False


class Journal:
    def __init__(self, filename):
        self.file = Path(filename).open("x")
        self.previous = "0" * 64

    def append(self, event, **data):
        row = {"event": event, "previous_sha256": self.previous, "monotonic_ns": time.monotonic_ns(), **data}
        row["sha256"] = digest(row)
        self.file.write(canonical(row) + "\n")
        self.file.flush()
        self.previous = row["sha256"]

    def close(self):
        self.file.close()


def read_journal(filename):
    rows, previous = [], "0" * 64
    for line in Path(filename).read_text().splitlines():
        row = json.loads(line)
        assert row["previous_sha256"] == previous, "Journal chain mismatch"
        claimed = row.pop("sha256")
        assert digest(row) == claimed, "Journal content mismatch"
        row["sha256"] = claimed
        rows.append(row)
        previous = claimed
    return rows


def file_sha(filename):
    return hashlib.sha256(Path(filename).read_bytes()).hexdigest()


def provenance(environment_root):
    root = Path(environment_root).resolve()
    header = (root / "include/env.h").read_text()
    if int(re.search(r"#define ENV_VERSION (\d+)", header)[1]) != SPEC.version:
        raise ValueError("Environment source root differs from loaded library version")
    # The CLI loads this exact native library before importing the binding.
    lib = root / "python/terraria_lite/libterraria.dylib"
    if not lib.exists():
        lib = root / "python/terraria_lite/libterraria.so"
    sources = [p for folder in ("src", "include") for p in (root / folder).glob("*") if p.suffix in (".c", ".h")]
    return {"environment_root": str(root), "environment_version": SPEC.version,
            "native_library_sha256": file_sha(lib),
            "native_sources": {str(p.relative_to(root)): file_sha(p) for p in sorted(sources)},
            "harness_sources": {p.name: file_sha(p) for p in (Path(__file__), Path(__file__).with_name("llm_protocol.py"), Path(__file__).with_name("llm_providers.py"), Path(__file__).with_name("rules.py"), Path(__file__).with_name("__init__.py"))}}


def prompt(session, c):
    return ("Play this scaled-down Terraria environment to earn as many distinct achievements as possible within the primitive action budget. "
            "Public game rules are supplied below; they are not a strategy guide. "
            "Return ONLY a JSON object with actions (integer IDs) and memory (your own concise notes). "
            f"Submit 1..{c['max_actions_per_call']} primitive actions per call. Each costs a tick; the world advances between them. "
            "There is no observation or conditional control inside a submitted list. An action list is not a macro, pathfinder or recipe executor. "
            "A malformed response costs one noop. Known illegal actions remain attempts. No reset, undo, external tools or code execution. "
            "No time passes during inference. Memory is reset between episodes; only your own notes and the configured recent turns persist.\n"
            + canonical(session.knowledge()))


def score(records, planned):
    usable = [r for r in records if r["status"] != "infrastructure_error"]
    groups = defaultdict(list)
    for r in usable:
        groups[r["seed"]].append(r["score"])
    world_means = [stats.mean(v) for v in groups.values()]
    interval = None
    if len(world_means) > 1:
        rng = random.Random(12345)
        samples = sorted(stats.mean(rng.choices(world_means, k=len(world_means))) for _ in range(2000))
        interval = [samples[49], samples[1949]]
    rates = {name: sum(name in r["achievements"] for r in usable)/len(usable) if usable else None for name in SPEC.achievement_names}
    return {"planned_episodes": planned, "recorded_episodes": len(records), "scoreable_episodes": len(usable),
            "complete": len(records) == planned and len(usable) == planned,
            "mean_achievements": stats.mean(world_means) if world_means else None,
            "world_cluster_bootstrap_95": interval,
            "achievement_rates": rates,
            "crafter_style_coverage_secondary": math.expm1(stats.mean(math.log1p(100*r) for r in rates.values())) if usable else None,
            "death_rate": stats.mean(r["died"] for r in usable) if usable else None,
            "stop_reasons": {name: sum(r["status"] == name for r in records) for name in sorted({r["status"] for r in records})},
            "interpretation": "Development only; no best-of selection. Incomplete aggregate is not a valid leaderboard score. Bootstrap resamples world means, not repeated calls or correlated replicates."}


def run(raw_config, environment_root, out, *, allow_api=False, key=None, credential_source=None, provider=None):
    c = config(raw_config)
    if c["provider"] == "openrouter" and not allow_api:
        raise ValueError("Paid/network execution requires explicit --allow-api")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = provenance(environment_root)
    manifest = {"harness": HARNESS, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "config": c, "provenance": sources, "credential_source": credential_source,
                "track": "symbolic-primitive" if c["max_actions_per_call"] == 1 else "symbolic-open-loop",
                "external_knowledge": "Public rules and recipes; pretrained-model priors allowed, unlike scratch RL",
                "private_holdout": False, "automatic_retries": False,
                "cost_guard": "Pre-request conservative UTF8-byte token reservation + declared price ceilings. Provider-reported costs retained. Not a substitute for a provider account billing limit; unknown charges stop the run.",
                "planned_episodes": len(c["seeds"])*c["replicates"]}
    (out / "manifest.json").write_text(canonical(manifest) + "\n")
    adapter = provider or (OpenRouter(c, key=key) if c["provider"] == "openrouter" else None)
    records, total_cost, total_reported_cost = [], 0.0, 0.0
    abort = False
    for seed in c["seeds"]:
        for replicate in range(c["replicates"]):
            if abort:
                break
            directory = out / f"world-{seed}-rep-{replicate}"
            directory.mkdir()
            (directory / "claim.json").write_text(canonical({"seed": seed, "replicate": replicate, "manifest_sha256": file_sha(out / "manifest.json")}) + "\n")
            journal = Journal(directory / "events.jsonl")
            session = Session(seed, c["max_steps"], environment_root)
            rng = random.Random(c["random_seed"] + seed + replicate*1_000_003)
            history, memory, actions, first = [], "", [], {}
            calls = tokens = 0
            episode_cost = 0.0
            begin, status = time.monotonic(), "running"
            error_type = error_message = None
            system = prompt(session, c)
            journal.append("initial", seed=seed, max_steps=c["max_steps"], observation_sha256=digest(session.packet()))
            try:
                while not session.ended:
                    remaining = c["max_wall_seconds"] - (time.monotonic()-begin)
                    if remaining <= 0:
                        status = "wall_budget"; break
                    if calls >= c["max_calls"]:
                        status = "call_budget"; break
                    user = canonical({"observation": session.packet(), "memory": memory,
                                      "remaining_primitive_actions": c["max_steps"]-session.info["steps"]})
                    messages = [{"role": "system", "content": system}, *history[-2*c["history_turns"]:], {"role": "user", "content": user}]
                    if len(canonical(messages).encode()) > c["max_context_bytes"]:
                        status = "context_budget"; break
                    reserve_cost = 0.0
                    if adapter:
                        payload = adapter.payload(messages, response_schema(c))
                        # Conservative local upper-bound heuristic; verify actual usage afterwards.
                        input_bound = len(canonical(payload).encode()) + 4096
                        token_reserve = input_bound + c["max_output_tokens"]
                        reserve_cost = input_bound*c["input_usd_per_token_ceiling"] + c["max_output_tokens"]*c["output_usd_per_token_ceiling"]
                        if total_cost + reserve_cost > c["max_cost_usd_total"]:
                            status = "cost_budget"; break
                        if tokens + token_reserve > c["max_total_tokens_per_episode"]:
                            status = "token_budget"; break
                        calls += 1
                        journal.append("request_started", call=calls, payload=payload,
                                       reserved_cost_usd=reserve_cost, input_token_bound=input_bound)
                        request_begin = time.monotonic()
                        reply = adapter.call(payload, min(c["request_timeout_seconds"], remaining))
                        reply["latency_seconds"] = time.monotonic() - request_begin
                        usage = reply["usage"]
                        cost = usage.get("cost")
                        if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
                            raise ProviderError("Invalid provider cost field")
                        estimate = usage["prompt_tokens"]*c["input_usd_per_token_ceiling"] + usage["completion_tokens"]*c["output_usd_per_token_ceiling"]
                        charged = max(estimate, cost or 0.0)
                        episode_cost += charged
                        total_cost += charged
                        if cost is not None:
                            total_reported_cost += cost
                        tokens += usage["total_tokens"]
                        journal.append("response_received", call=calls, response=reply, accounted_cost_usd=charged)
                        if usage["prompt_tokens"] > input_bound or usage["completion_tokens"] > c["max_output_tokens"] or charged > reserve_cost + 1e-9:
                            raise ProviderError("Provider exceeded reserved token/cost bound; stop")
                    else:
                        calls += 1
                        choice = 0 if c["provider"] == "noop" else rng.choice(session.packet()["legal_actions"])
                        reply = {"text": canonical({"actions": [choice], "memory": ""}),
                                 "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0},
                                 "model": c["provider"], "finish_reason": "stop"}
                        journal.append("offline_response", call=calls, response=reply)
                    chosen, new_memory, valid = parse_response(reply["text"], c)
                    if reply.get("finish_reason") not in ("stop", "tool_calls"):
                        chosen, new_memory, valid = [None], "", False
                    if valid:
                        memory = new_memory
                    for action in chosen:
                        if session.ended:
                            break
                        result = session.act({"action": action})
                        actions.append(result["executed_action"])
                        for achievement in result["achievements"]:
                            first.setdefault(achievement, result["steps"])
                        journal.append("step", action=action, executed_action=result["executed_action"],
                                       reward=result["reward"], observation_sha256=digest(session.packet()))
                    history += [{"role": "user", "content": user}, {"role": "assistant", "content": reply["text"]}]
                    history = history[-2*c["history_turns"]:]
                if session.ended:
                    status = "death" if session.terminated else "action_budget"
            except Exception as error:
                # Do not log arbitrary exception strings: they can contain remote secrets.
                status, error_type, abort = "infrastructure_error", type(error).__name__, True
                error_message = str(error) if isinstance(error, ProviderError) else None
                if adapter:
                    total_cost += reserve_cost  # retain conservative uncertainty reservation
                journal.append("infrastructure_error", error_type=error_type, error_message=error_message, charge_may_be_unknown=bool(adapter))
            finally:
                packet = session.packet()
                record = {"seed": seed, "replicate": replicate, "status": status, "error_type": error_type, "error_message": error_message,
                          "score": packet["score"], "achievements": packet["achievements"], "died": session.terminated,
                          "steps": session.info["steps"], "calls": calls, "tokens": tokens,
                          "first_achievement_steps": first, "native_info": session.info,
                          "invalid_requests": session.invalid_requests, "illegal_attempts": session.illegal_attempts,
                          "accounted_cost_usd": episode_cost, "elapsed_seconds": time.monotonic()-begin,
                          "final_observation_sha256": digest(packet)}
                journal.append("final", record=record)
                journal.close()
                session.close()
                if actions:
                    with (directory / "actions.tape").open("x") as f:
                        f.write(f"# terraria-lite tape\nenvironment {SPEC.version}\nseed {seed}\nmax_steps {c['max_steps']}\nlabel {HARNESS} {c['provider']}\nactions {len(actions)}\n")
                        f.writelines(f"{a}\n" for a in actions)
                record["journal_sha256"] = file_sha(directory / "events.jsonl")
                (directory / "result.json").write_text(canonical(record) + "\n")
                records.append(record)
                print(f"world={seed} rep={replicate} status={status} score={record['score']}/32 steps={record['steps']} calls={calls} accounted=${total_cost:.4f}", flush=True)
                summary = {**score(records, manifest["planned_episodes"]), "episodes": records,
                           "accounted_cost_usd_total": total_cost, "provider_reported_cost_usd_total": total_reported_cost,
                           "charge_uncertain": abort and bool(adapter)}
                (out / "summary.json").write_text(canonical(summary) + "\n")
    return summary


def verify(directory, environment_root):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    if provenance(environment_root) != manifest["provenance"]:
        raise ValueError("Environment or harness hash changed; use the original frozen implementation")
    count = 0
    for episode in sorted(directory.glob("world-*-rep-*")):
        rows = read_journal(episode / "events.jsonl")
        initial, final = rows[0], rows[-1]
        assert initial["event"] == "initial" and final["event"] == "final"
        session = Session(initial["seed"], initial["max_steps"], environment_root)
        try:
            assert digest(session.packet()) == initial["observation_sha256"]
            for row in rows:
                if row["event"] == "step":
                    result = session.act({"action": row["action"]})
                    assert result["executed_action"] == row["executed_action"]
                    assert result["reward"] == row["reward"]
                    assert digest(session.packet()) == row["observation_sha256"]
            assert session.info == final["record"]["native_info"]
            assert digest(session.packet()) == final["record"]["final_observation_sha256"]
            saved = json.loads((episode / "result.json").read_text())
            assert saved["journal_sha256"] == file_sha(episode / "events.jsonl")
            assert {k:v for k,v in saved.items() if k != "journal_sha256"} == final["record"]
            claim = json.loads((episode / "claim.json").read_text())
            assert claim["manifest_sha256"] == file_sha(directory / "manifest.json")
            assert claim["seed"] == initial["seed"]
            executed = [r["executed_action"] for r in rows if r["event"] == "step"]
            if executed:
                tape = (episode / "actions.tape").read_text().splitlines()
                marker = tape.index(f"actions {len(executed)}")
                assert list(map(int, tape[marker+1:])) == executed
                assert f"environment {SPEC.version}" in tape and f"seed {initial['seed']}" in tape
                assert f"max_steps {initial['max_steps']}" in tape
        finally:
            session.close()
        count += 1
    return {"verified_episodes": count, "checks": "hash chain, each native transition/reward/observation and final state", "api_calls": 0}
