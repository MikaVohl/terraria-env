"""Archive public evidence and record unavailable files; never execute downloads."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import urllib.error
import urllib.request

BASE = "https://terrariabench.com/"


def snapshot(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    evidence = {"captured_utc": datetime.now(timezone.utc).isoformat(), "source": BASE, "artifacts": [], "published_runs": []}

    def get(relative):
        url = BASE + relative
        record = {"url": url, "relative_path": relative}
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                data = response.read(5000001)
                if len(data) > 5000000:
                    raise ValueError("reference artifact exceeds 5 MB limit")
                record.update(status=response.status, sha256=hashlib.sha256(data).hexdigest(), bytes=len(data))
                path = output / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
                if data.startswith(b"\x89PNG\r\n\x1a\n"):
                    record["image_size"] = list(struct.unpack(">II", data[16:24]))
        except urllib.error.HTTPError as error:
            record["status"] = error.code
            data = None
        evidence["artifacts"].append(record)
        return data

    charts = json.loads(get("charts/manifest.json"))
    for run in charts["runs"]:
        run_id = run["run_id"]
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", run_id):
            raise ValueError("invalid published run ID")
        data = get(f"runs/{run_id}/result.json")
        if data:
            result = json.loads(data)
            metrics = result["score_metrics"]
            evidence["published_runs"].append({"run_id": run_id, "model": result["model"],
                "harness": result["harness"], "budget_seconds": result["budget_seconds"],
                "reasoning_effort": result.get("reasoning_effort"), "hyperparameters": result.get("hyperparameters"),
                "expected_agency_score": result["agency_score"],
                "direct_tile_control_used": metrics.get("direct_tile_control_used", False),
                "stalled": metrics.get("stalled", False),
                "scoring_checkpoints": [{k: event[k] for k in ("milestone", "category", "agent_driven", "elapsed_seconds") if k in event}
                                        for event in metrics.get("scoring_checkpoints", [])]})
    anchor = "runs/20260507_164917_1_api_google_gemini-3-flash-preview_03_open_ended_progress/"
    for name in ("frames/frame_00001.png", "frames/manifest.json", "hyperparameters.json", "setup.json", "preflight.json", "transcript.jsonl", "checkpoints.jsonl", "actions.jsonl"):
        get(anchor + name)
    for name in ("docs/SPEC.txt", "docs/README.txt", "docs/harness-traces.txt"):
        get(name)
    return evidence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("reference/published"))
    parser.add_argument("--manifest", type=Path, default=Path("reference/evidence.json"))
    args = parser.parse_args()
    result = snapshot(args.output)
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"published_runs": len(result["published_runs"]), "artifacts": len(result["artifacts"]), "manifest": str(args.manifest)}))
