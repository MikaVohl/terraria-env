"""Spend tally for a campaign directory: gateway vs OpenRouter, reported + uncertain.

Reads result.json (finished) or accounting.json (in progress) of single-model runs, and the per-role
accounting of planner/executor runs. Connection failures that provably never reached the provider are
excluded from the uncertain amount. Prints JSON: {"gateway": ..., "openrouter": ...}.
"""
import json
import sys
from decimal import Decimal
from pathlib import Path


def failures_unsent(d):
    try:
        rows = [json.loads(l) for l in open(d / "provider-failures.jsonl")]
    except OSError:
        return 0
    return sum(1 for f in rows if f.get("sent") is False or ("URLError" in f.get("error", "") and f.get("sent", True)))


def tally(root):
    total = {"gateway": Decimal(0), "openrouter": Decimal(0)}
    for manifest in Path(root).glob("*/manifest.json"):
        d = manifest.parent
        m = json.loads(manifest.read_text())
        result = d / "result.json"
        r = json.loads(result.read_text()) if result.exists() else {}
        if "roles" in r or "protocol" in m:  # planner/executor run
            roles = r.get("roles") or {}
            for f in d.glob("accounting-*.json"):  # live per-role snapshots
                roles.setdefault(f.stem.split("-", 1)[1], {"accounting": json.loads(f.read_text()), "provider": None})
            for name, role in roles.items():
                a = role["accounting"]
                provider = role.get("provider") or ("openrouter" if "jev" in str(m.get("config", {}).get(f"{name}_model", "")) else "gateway")
                total[provider] += Decimal(a["reported_usd"]) + Decimal(a["uncertain_reserved_usd"])
            continue
        a = r.get("accounting") or (json.loads((d / "accounting.json").read_text()) if (d / "accounting.json").exists() else None)
        if not a:
            continue
        uncertain = max(Decimal(0), Decimal(a["uncertain_reserved_usd"]) - failures_unsent(d) * Decimal(a["reservation_per_call_usd"]))
        provider = "openrouter" if m.get("provider") == "openrouter" else "gateway"
        total[provider] += Decimal(a["reported_usd"]) + uncertain
    return total


if __name__ == "__main__":
    print(json.dumps({k: str(v.quantize(Decimal("0.0001"))) for k, v in tally(sys.argv[1]).items()}))
