"""Cross-check saved evidence; does not certify official benchmark eligibility."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .live import pixel_actions
from .scoring import read_journal, score


def audit(root):
    if not __debug__:
        raise RuntimeError("Run the evidence audit without Python -O; checks must be enabled")
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text())
    result = json.loads((root / "result.json").read_text())
    responses = sorted(root.glob("response-*.json"))
    receipts = [json.loads(line) for line in (root / "inputs.jsonl").read_text().splitlines()]
    expected, invalid, cost, tokens = [], 0, Decimal(0), 0
    for index, path in enumerate(responses):
        response = json.loads(path.read_text())
        assert response["model"] == manifest["model"]["id"], "model identity mismatch"
        cost += Decimal(str(response["usage"]["cost"]))
        tokens += response["usage"]["prompt_tokens"] + response["usage"]["completion_tokens"]
        request = json.loads((root / f"request-{index:03d}.json").read_text())
        frame = root / "frames" / f"{index:05d}.png"
        assert hashlib.sha256(frame.read_bytes()).hexdigest() == request["frame_sha256"], "frame hash mismatch"
        try:
            content = json.loads(response["choices"][0]["message"]["content"])
            if (not isinstance(content, dict) or set(content) != {"notes", "actions"}
                    or not isinstance(content["notes"], str) or len(content["notes"]) > 2000):
                raise ValueError("invalid response shape")
            expected.extend(pixel_actions(content["actions"], manifest.get("coordinate_system", "pixels")))
        except (ValueError, KeyError, IndexError, TypeError):
            invalid += 1
            expected.append({"ms": 100})
    assert len(responses) == result["calls"], "call count mismatch"
    assert expected == [receipt["action"] for receipt in receipts], "response/input mismatch"
    assert all(r["actor"] == "agent" and r["ended_unix"] >= r["started_unix"] for r in receipts)
    assert len(receipts) == result["primitive_actions"], "action count mismatch"
    assert invalid == result["invalid_outputs"], "invalid count mismatch"
    assert cost == Decimal(result["accounting"]["reported_usd"]), "cost reconciliation mismatch"
    assert tokens == result["accounting"]["tokens"], "token count mismatch"
    for name, digest in manifest["source_hashes"].items():
        source = root / "source/terrariabench" / name
        assert hashlib.sha256(source.read_bytes()).hexdigest() == digest, "source hash mismatch"
    journals = sorted((root / "telemetry").glob("*.jsonl"))
    assert len(journals) == 1, "expected exactly one world session"
    progress = score(read_journal(journals[0]))
    # Explanatory eligibility wording can evolve; factual measurements must match.
    measured = {k: v for k, v in progress.items() if k != "ineligibility_reason"}
    recorded = {k: v for k, v in result["observed_progress"].items() if k != "ineligibility_reason"}
    assert measured == recorded, "journal/result mismatch"
    summary = {"checks_passed": True, "calls": len(responses), "input_commands": len(receipts),
               "frames_verified": len(responses), "reported_usd": str(cost),
               "source_files_verified": len(manifest["source_hashes"]), "milestones": list(progress["first_unlocks"]),
               "official_eligible": False,
               "scope": "File consistency, model identity, frame/source hashes, command mapping, journal scoring and usage totals only."}
    (root / "audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    print(json.dumps(audit(parser.parse_args().run), indent=2))
