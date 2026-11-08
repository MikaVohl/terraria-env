"""Per-run spend ledger for a campaign directory (gateway incl. Unified route vs OpenRouter/Jev).

    python tools/campaign_ledger.py runs/<campaign> [--extra extra.json]   # prints the ledger JSON

Per run: reported USD (gateway header or list price, as each run's accounting recorded it) and uncertain
reservations (failed sent attempts; provably-unsent connection failures excluded, as in pilot_spend.py).
`--extra` adds out-of-run calls (price probes, smoke tests outside the campaign dir) as
[{"what": ..., "provider": "gateway"|"openrouter", "usd": ...}].
"""
import argparse
import json
from decimal import Decimal
from pathlib import Path

from pilot_spend import failures_unsent


def run_rows(d):
    m = json.loads((d / "manifest.json").read_text())
    r = json.loads((d / "result.json").read_text()) if (d / "result.json").exists() else {}
    rows = []
    if "protocol" in m:
        roles = r.get("roles") or {}
        for f in d.glob("accounting-*.json"):
            roles.setdefault(f.stem.split("-", 1)[1], {"accounting": json.loads(f.read_text()), "provider": None})
        for name, role in roles.items():
            a = role["accounting"]
            provider = role.get("provider") or ("openrouter" if "jev" in str(m["config"].get(f"{name}_model", "")) else "gateway")
            rows.append({"run": d.name, "role": name, "provider": provider, "reported": Decimal(a["reported_usd"]),
                         "uncertain": Decimal(a["uncertain_reserved_usd"])})
        return rows
    a = r.get("accounting") or (json.loads((d / "accounting.json").read_text()) if (d / "accounting.json").exists() else None)
    if a:
        uncertain = max(Decimal(0), Decimal(a["uncertain_reserved_usd"]) - failures_unsent(d) * Decimal(a["reservation_per_call_usd"]))
        rows.append({"run": d.name, "role": "single", "provider": "openrouter" if m.get("provider") == "openrouter" else "gateway",
                     "reported": Decimal(a["reported_usd"]), "uncertain": uncertain})
    return rows


def main():
    p = argparse.ArgumentParser()
    p.add_argument("campaign", type=Path)
    p.add_argument("--extra", type=Path)
    args = p.parse_args()
    rows = [row for mf in sorted(args.campaign.glob("*/manifest.json")) for row in run_rows(mf.parent)]
    if args.extra and args.extra.exists():
        rows += [{"run": e["what"], "role": "extra", "provider": e["provider"], "reported": Decimal(str(e["usd"])),
                  "uncertain": Decimal(0)} for e in json.loads(args.extra.read_text())]
    total = {k: {"reported": sum((r["reported"] for r in rows if r["provider"] == k), Decimal(0)),
                 "uncertain": sum((r["uncertain"] for r in rows if r["provider"] == k), Decimal(0))} for k in ("gateway", "openrouter")}
    out = {"rows": [{**r, "reported": f'{r["reported"]:.6f}', "uncertain": f'{r["uncertain"]:.6f}'} for r in rows],
           "totals": {k: {"reported": f'{v["reported"]:.6f}', "uncertain": f'{v["uncertain"]:.6f}',
                          "conservative": f'{v["reported"] + v["uncertain"]:.6f}'} for k, v in total.items()}}
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
