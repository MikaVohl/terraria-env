"""Fit USD/token prices of a Unified-route model from the gateway's X-Token-Usage-Cost on two probes (the
2026-11-08 method in terrariabench/unified.py): one long prompt with a tiny answer, one tiny prompt with a long answer.
Both calls are journaled in the TerraBot ledger with a conservative reservation first.

    python tools/terrabot/probe_price.py gpt-6-astra [--reasoning low]
"""
import argparse
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))
from terrariabench import gateway, unified  # noqa: E402
from agent import ledger_spent, ledger_write  # noqa: E402

RESERVE = 0.30  # per probe call: covers up to $60/M input on 2.1k tokens and $300/M output on 700 tokens


def probe(model, reasoning, prompt, max_tokens, key, label):
    if ledger_spent() + RESERVE > 10.0:
        raise SystemExit("ledger cap")
    cid = f"probe-{model}-{label}-{int(time.time())}"
    ledger_write({"kind": "reserve", "call": cid, "run": "price-probe", "model": model, "usd": RESERVE})
    body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_completion_tokens": max_tokens,
            "reasoning_effort": reasoning}
    try:
        header, data = unified._post("/chat/completions", body, key, 300)
    except Exception:
        ledger_write({"kind": "settle", "call": cid, "run": "price-probe", "model": model, "usd": RESERVE,
                      "source": "reservation_kept_after_error"})
        raise
    usage = data.get("usage") or {}
    cost = float(header if header is not None else usage.get("total_cost") or RESERVE)
    ledger_write({"kind": "settle", "call": cid, "run": "price-probe", "model": model, "usd": cost,
                  "source": "gateway_header" if header is not None else "usage_total_cost",
                  "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens")})
    return {"cost": cost, "prompt": usage.get("prompt_tokens"), "completion": usage.get("completion_tokens"),
            "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "model_version": data.get("model")}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("model")
    p.add_argument("--reasoning", default="low")
    a = p.parse_args()
    key = gateway.load_key()
    long_prompt = "Reply with the single word OK.\n" + ("The quick brown fox jumps over the lazy dog. " * 210)
    r1 = probe(a.model, a.reasoning, long_prompt, 16, key, "long-in")
    r2 = probe(a.model, a.reasoning, "Write about 450 words on caves.", 900, key, "long-out")
    # Solve cost = pin * prompt + pout * completion for the two probes.
    (c1, p1, o1), (c2, p2, o2) = (r1["cost"], r1["prompt"], r1["completion"]), (r2["cost"], r2["prompt"], r2["completion"])
    det = p1 * o2 - p2 * o1
    pin = (c1 * o2 - c2 * o1) / det
    pout = (p1 * c2 - p2 * c1) / det
    print(json.dumps({"model": a.model, "probes": [r1, r2], "usd_per_m_input": round(pin * 1e6, 4),
                      "usd_per_m_output": round(pout * 1e6, 4)}))


if __name__ == "__main__":
    main()
