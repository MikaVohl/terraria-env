"""Frozen, bounded Luna harness comparison. Preparation never reads credentials."""
import argparse
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from urllib.request import urlopen

ARMS = {
    "full16": {"observation_format": "full", "history_turns": 8, "max_actions_per_call": 16, "batch_interrupt": "never"},
    "compact16": {"observation_format": "compact", "history_turns": 2, "max_actions_per_call": 16, "batch_interrupt": "never"},
    "compact4": {"observation_format": "compact", "history_turns": 2, "max_actions_per_call": 4, "batch_interrupt": "never"},
    "compact16_interrupt": {"observation_format": "compact", "history_turns": 2, "max_actions_per_call": 16, "batch_interrupt": "illegal"},
}
SEEDS = [32000001, 32000002]


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value, exclusive=False):
    with Path(path).open("x" if exclusive else "w") as f:
        json.dump(value, f, indent=2); f.write("\n")


def load_harness(root, environment):
    os.environ["TERRARIA_LITE_LIB"] = str(environment / "python/terraria_lite/libterraria.dylib")
    sys.path.insert(0, str(root / "implementation"))
    from terraria_lite import llm_bench
    return llm_bench


def prepare(root, environment):
    repo = Path(__file__).resolve().parents[1]
    assert root.is_dir() and not any(root.iterdir()), "Use a fresh empty study root"
    package = root / "implementation/terraria_lite"
    package.mkdir(parents=True)
    for source in (repo / "python/terraria_lite").glob("*.py"):
        shutil.copy2(source, package / source.name)
    shutil.copy2(__file__, root / "supervisor.py")
    shutil.copy2(repo / "tools/eval_llm.py", root / "eval_llm.py")
    harness = load_harness(root, environment)
    with urlopen("https://openrouter.ai/api/v1/models", timeout=30) as response:
        model = next(x for x in json.load(response)["data"] if x["id"] == "openai/gpt-6-luna")
    assert {"reasoning", "structured_outputs"} <= set(model["supported_parameters"])
    # Context cap plus schema/framing remains far below the272K token tier.
    assert float(model["pricing"]["prompt"]) <= .000000125
    assert float(model["pricing"]["completion"]) <= .0000005
    assert float(model["pricing"].get("input_cache_write", 0)) <= .000000125
    write(root / "public-model-metadata.json", {"queried_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "model": model}, True)
    base = {"provider": "openrouter", "model": "openai/gpt-6-luna", "reasoning_effort": "high",
            "replicates": 1, "max_steps": 3000, "max_calls": 1000,
            "max_output_tokens": 8192, "max_context_bytes": 100000,
            "max_total_tokens_per_episode": 20000000, "max_wall_seconds": 7200,
            "request_timeout_seconds": 120, "max_cost_usd_total": .35,
            "input_usd_per_token_ceiling": .000000125, "output_usd_per_token_ceiling": .0000005,
            "pricing_source": "OpenRouter live catalog,2026-10-17; short-context prompt/cache-write ceiling$0.125/M, output$0.50/M.100KB context plus framing/schema cannot reach272K-token surcharge tier; actual reported cost is also checked."}
    configs, jobs = {}, []
    names = list(ARMS)
    (root / "configs").mkdir()
    for i, seed in enumerate(SEEDS):
        for arm in names[i:] + names[:i]:
            name = f"{arm}-{seed}"
            c = harness.config({**base, **ARMS[arm], "seeds": [seed]})
            write(root / "configs" / (name + ".json"), c, True)
            configs[name] = c; jobs.append({"name": name, "arm": arm, "seed": seed})
    frozen = [root / "supervisor.py", root / "eval_llm.py", root / "public-model-metadata.json",
              *package.glob("*.py"), *(root / "configs").glob("*.json")]
    protocol = {"created_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "environment_root": str(environment),
                "model": "openai/gpt-6-luna", "arms": ARMS, "seeds": SEEDS, "jobs": jobs, "workers": 2,
                "user_new_spend_authority_usd": 3.0, "per_attempt_accounted_guard_usd": .35,
                "sum_attempt_guards_usd": round(sum(c["max_cost_usd_total"] for c in configs.values()), 8),
                "unallocated_safety_margin_usd": .2, "allowance_reallocation": False,
                "source_sha256": {str(p.relative_to(root)): sha(p) for p in sorted(frozen)},
                "provenance": harness.provenance(environment),
                "comparison": "Four scaffold packages x two matched public worlds, one attempt each. Equal independent conservative dollar caps,3000-action ceilings; budget-censored scores are not full-budget mastery. Compact-v-full bundles history with duplicate-field removal. No best-of or confirmatory significance claim.",
                "failure_rule": "No retries/replacements. Unknown-charge or infrastructure failure stops new dispatch; already active independent capped attempt finishes. No budget recycling."}
    assert protocol["sum_attempt_guards_usd"] == 2.8
    write(root / "study-protocol.json", protocol, True)
    print(json.dumps({"study": str(root), "jobs": jobs, "total_guard_usd": 2.8, "api_calls": 0}, indent=2))


def verify_sources(root, protocol, harness):
    for name, digest in protocol["source_sha256"].items():
        assert sha(root / name) == digest, f"Frozen source/config changed: {name}"
    assert harness.provenance(Path(protocol["environment_root"])) == protocol["provenance"]


def metrics(root, job, harness, environment):
    out = root / "runs" / job["name"]
    summary = read(out / "summary.json")
    assert summary["complete"] and not summary["charge_uncertain"]
    record = summary["episodes"][0]
    directory = out / f"world-{job['seed']}-rep-0"
    rows = harness.read_journal(directory / "events.jsonl")
    responses = [r for r in rows if r["event"] == "response_received"]
    requests = [r for r in rows if r["event"] == "request_started"]
    assert len(responses) == len(requests) == record["calls"]
    assert all(r["response"]["model"] == "openai/gpt-6-luna" for r in responses)
    assert all(r["payload"]["reasoning"] == {"effort": "high", "exclude": True} for r in requests)
    assert summary["accounted_cost_usd_total"] <= .35 + 1e-9
    session = harness.Session(job["seed"], 3000, environment)
    milestones = {}
    try:
        for row in rows:
            if row["event"] == "step":
                result = session.act({"action": row["action"]})
                if result["steps"] in (128,512,1024,2048,3000): milestones[str(result["steps"])] = result["score"]
        assert session.info == record["native_info"]
    finally:
        session.close()
    for step in (128,512,1024,2048,3000):
        if str(step) not in milestones:
            milestones[str(step)] = record["score"] if record["died"] else None
    prompt_tokens = sum(r["response"]["usage"]["prompt_tokens"] for r in responses)
    output_tokens = sum(r["response"]["usage"]["completion_tokens"] for r in responses)
    return {**job, **record, "provider_reported_cost_usd": summary["provider_reported_cost_usd_total"],
            "accounted_cost_with_uncertainty_usd": summary["accounted_cost_usd_total"],
            "prompt_tokens": prompt_tokens, "completion_tokens": output_tokens,
            "mean_call_seconds": sum(r["response"]["latency_seconds"] for r in responses)/len(responses) if responses else None,
            "illegal_fraction": record["illegal_attempts"]/record["steps"] if record["steps"] else None,
            "score_at_action_budget": milestones,
            "milestone_rule": "Replay-derived. Death carries terminal score forward; still-alive budget truncation is null beyond observed actions, never silently imputed.",
            "artifact_sha256": {str(p.relative_to(out)): sha(p) for p in [out / "manifest.json",out / "summary.json",directory / "events.jsonl",directory / "result.json",directory / "claim.json",directory / "actions.tape"] if p.exists()}}


def report(root, protocol, harness):
    import statistics as stats
    environment = Path(protocol["environment_root"])
    rows = [metrics(root, job, harness, environment) for job in protocol["jobs"]]
    arms = {}
    for arm in ARMS:
        records = [r for r in rows if r["arm"] == arm]
        arms[arm] = {"mean_score": stats.mean(r["score"] for r in records),
                     "scores": [r["score"] for r in records], "mean_steps": stats.mean(r["steps"] for r in records),
                     "deaths": sum(r["died"] for r in records),
                     "bench_worlds": sum("craft workbench" in r["achievements"] for r in records),
                     "furnace_worlds": sum("craft furnace" in r["achievements"] for r in records),
                     "anvil_worlds": sum("craft anvil" in r["achievements"] for r in records),
                     "actual_cost_usd": sum(r["provider_reported_cost_usd"] for r in records),
                     "stops": [r["status"] for r in records]}
    paired = {arm: {str(seed): next(r["score"] for r in rows if r["arm"] == arm and r["seed"] == seed)-next(r["score"] for r in rows if r["arm"] == "compact16" and r["seed"] == seed) for seed in SEEDS} for arm in ARMS if arm != "compact16"}
    result = {"protocol_sha256": sha(root / "study-protocol.json"), "records": rows, "arms": arms,
              "paired_score_minus_compact16": paired,
              "actual_cost_usd": sum(r["provider_reported_cost_usd"] for r in rows),
              "accounted_cost_usd": sum(r["accounted_cost_with_uncertainty_usd"] for r in rows),
              "interpretation": "Exploratory two-world paired scaffold study. No selection, confidence claims, checkpoint/world pooling, or equal-prior PPO ranking. Equal independent dollar guards, not necessarily equal action counts. All attempts retained."}
    assert result["accounted_cost_usd"] <= 2.8 + 1e-8
    write(root / "results.json", result, True)
    lines = ["# Luna harness comparison — October17,2026", "", result["interpretation"], "",
             "| Arm | Scores /32 | Mean | Mean actions | Deaths /2 | Bench/furnace/anvil worlds /2 | Actual cost | Stops |",
             "|---|---|---:|---:|---:|---|---:|---|"]
    for arm, a in arms.items():
        lines.append(f"|{arm}|{a['scores']}|{a['mean_score']:.3f}|{a['mean_steps']:.0f}|{a['deaths']}|{a['bench_worlds']}/{a['furnace_worlds']}/{a['anvil_worlds']}|${a['actual_cost_usd']:.4f}|{', '.join(a['stops'])}|")
    lines += ["",f"Actual reported cost${result['actual_cost_usd']:.6f}; conservative accounted${result['accounted_cost_usd']:.6f} of$2.80. User authority$3; no allowance recycling.","", "Paired differences, exact action milestones, first achievements, token/latency/illegal-attempt data and artifact hashes are in results.json. A null action milestone is censored, not zero. Native sources and defaults unchanged. Frozen Python replay passed for each run; independent SDL audit is a completion-reporting step."]
    (root / "results.md").write_text("\n".join(lines)+"\n")
    return result


def run(root, allow_api):
    assert allow_api, "Explicit --allow-api required"
    protocol = read(root / "study-protocol.json")
    environment = Path(protocol["environment_root"])
    harness = load_harness(root, environment)
    verify_sources(root, protocol, harness)
    write(root / "started.json", {"pid": os.getpid(), "started_utc": time.time(), "protocol_sha256": sha(root / "study-protocol.json")}, True)
    from terraria_lite.llm_providers import hermes_key
    key, credential_source = hermes_key("mika@omarchy")
    print("Authorized Hermes credential in memory only; value suppressed", flush=True)
    pending, active, completed = list(protocol["jobs"]), {}, []
    failure = None
    def status(stage):
        write(root / "status.json", {"stage": stage, "pid": os.getpid(), "updated_utc": time.time(),
                                     "active": list(active.values()), "completed": completed, "pending": pending, "failure": failure})
    def trial(job):
        cfg = read(root / "configs" / (job["name"] + ".json"))
        out = root / "runs" / job["name"]
        summary = harness.run(cfg, environment, out, allow_api=True, key=key, credential_source=credential_source)
        if not summary["complete"] or summary["charge_uncertain"]:
            raise RuntimeError("Incomplete or charge-uncertain attempt; no retry")
        harness.verify(out, environment)
    status("starting")
    with ThreadPoolExecutor(max_workers=2) as pool:
        while pending or active:
            while pending and len(active) < 2 and not failure:
                verify_sources(root, protocol, harness)
                job = pending.pop(0)
                active[pool.submit(trial, job)] = job
                print("Started", job["name"], flush=True)
            status("failed_draining" if failure else "running")
            if not active: break
            done, _ = wait(active, timeout=10, return_when=FIRST_COMPLETED)
            for future in done:
                job = active.pop(future)
                try:
                    future.result(); completed.append(job)
                    print("Completed", job["name"], flush=True)
                except Exception as error:
                    failure = {"job": job["name"], "error_type": type(error).__name__, "message": "Artifacts preserved; no retry or replacement. Inspect sanitized episode error."}
        if failure:
            status("failed"); raise SystemExit("Study incomplete; inspect artifacts, never silently retry")
    verify_sources(root, protocol, harness)
    status("reporting")
    report(root, protocol, harness)
    status("complete")
    print("Complete; no additional paid calls", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--environment-root", type=Path)
    parser.add_argument("--mode", choices=("prepare", "run"), required=True)
    parser.add_argument("--allow-api", action="store_true")
    args = parser.parse_args()
    if args.mode == "prepare":
        assert not args.allow_api and args.environment_root
        prepare(args.study.resolve(), args.environment_root.resolve())
    else:
        run(args.study.resolve(), args.allow_api)
