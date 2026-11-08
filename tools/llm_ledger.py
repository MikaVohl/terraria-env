"""Spend ledger for an LLM campaign directory: <dir>/runs/*/ (eval_llm.py outputs).

Per run: provider, model, cap (max_cost_usd_total), accounted (conservative, includes failed-request
reservations and the reservation of an infrastructure error) and provider-reported cost, read from the
hash-chained journals so running runs are included. `committed` counts the full cap of runs that are
still running, so committed <= budget guarantees the hard limit.
Usage: python tools/llm_ledger.py <campaign dir> [--budget-gateway 11 --budget-openrouter 0.5]
"""
import argparse
import json
from pathlib import Path


def run_spend(run):
    manifest = json.loads((run / "manifest.json").read_text())
    c = manifest["config"]
    accounted = reported = 0.0
    calls = 0
    finished = (run / "summary.json").exists() and json.loads((run / "summary.json").read_text())["recorded_episodes"] == manifest["planned_episodes"]
    for journal in run.glob("world-*/events.jsonl"):
        for line in journal.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue  # partially written last line of a running journal
            if row["event"] == "response_received":
                calls += 1
                accounted += row["accounted_cost_usd"]
                reported += row["response"]["usage"].get("cost") or 0.0
            elif row["event"] == "request_failed":
                accounted += row["charged_reservation_usd"]
    if finished:
        summary = json.loads((run / "summary.json").read_text())
        accounted = max(accounted, summary["accounted_cost_usd_total"])
    route = "openrouter" if c["provider"].startswith("openrouter") else "gateway" if c["provider"] in ("anthropic_gateway", "openai_gateway") else "offline"
    return {"run": run.name, "route": route, "model": c.get("model"), "label": c.get("label"), "finished": finished,
            "cap_usd": c["max_cost_usd_total"], "calls": calls, "accounted_usd": round(accounted, 6),
            "reported_usd": round(reported, 6), "committed_usd": round(accounted if finished else max(accounted, c["max_cost_usd_total"]), 6)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("--budget-gateway", type=float, default=11.0)
    parser.add_argument("--budget-openrouter", type=float, default=0.5)
    args = parser.parse_args()
    rows = [run_spend(r) for r in sorted((args.campaign / "runs").iterdir()) if (r / "manifest.json").exists()]
    totals = {}
    for route, budget in (("gateway", args.budget_gateway), ("openrouter", args.budget_openrouter)):
        sel = [r for r in rows if r["route"] == route]
        totals[route] = {"budget_usd": budget, "accounted_usd": round(sum(r["accounted_usd"] for r in sel), 6),
                         "reported_usd": round(sum(r["reported_usd"] for r in sel), 6),
                         "committed_usd": round(sum(r["committed_usd"] for r in sel), 6)}
        totals[route]["available_usd"] = round(budget - totals[route]["committed_usd"], 6)
    ledger = {"runs": rows, "totals": totals}
    (args.campaign / "ledger.json").write_text(json.dumps(ledger, indent=1) + "\n")
    print(json.dumps(totals, indent=1))


if __name__ == "__main__":
    main()
