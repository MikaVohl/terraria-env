"""Evidence checks for the inferred-reference tool harness, not upstream certification."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import struct

from .linux_control import validate_actions
from .reference_scoring import checkpoint_view, reference_score


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(root):
    root = Path(root)
    manifest = json.loads((root/"manifest.json").read_text())
    result = json.loads((root/"result.json").read_text())
    require(result["profile_id"] == "reference-reconstructed-v1", "wrong profile")
    require(manifest["exact_reference_reproduction"] is False, "unjustified exact-reproduction claim")
    receipts = [json.loads(s) for s in (root/"inputs.jsonl").read_text().splitlines()] if (root/"inputs.jsonl").exists() else []
    tool_results = [json.loads(s) for s in (root/"tool-results.jsonl").read_text().splitlines()] if (root/"tool-results.jsonl").exists() else []
    outputs = {event["call_id"]: event for event in tool_results}
    cost, tokens, expected, prior_messages, image_paths = Decimal(0), 0, [], [], set()
    prior_response = None
    responses = sorted(root.glob("response-*.json"))
    for index, path in enumerate(responses):
        response = json.loads(path.read_text())
        require(response["model"] == manifest["model"]["id"], "model mismatch")
        usage = response["usage"]
        cost += Decimal(str(usage["cost"]))
        tokens += usage["prompt_tokens"] + usage["completion_tokens"]
        request = json.loads((root/f"request-{index:03d}.json").read_text())
        messages = request["messages"]
        require(messages[:len(prior_messages)] == prior_messages, "conversation was silently truncated/rewritten")
        if prior_response is not None:
            continuation = messages[len(prior_messages):]
            require(continuation and continuation[0] == prior_response,
                    "assistant response/reasoning metadata was omitted or rewritten")
            prior_calls = prior_response.get("tool_calls", [])
            for offset, call in enumerate(prior_calls, start=1):
                record = outputs.get(call["id"])
                require(record is not None, "missing tool result")
                expected_tool = {"role": "tool", "tool_call_id": call["id"],
                                 "content": json.dumps(record["result"])}
                require(len(continuation) > offset and continuation[offset] == expected_tool,
                        "tool result was omitted or rewritten in context")
        prior_messages = messages
        prior_response = response["choices"][0]["message"]
        require(messages[0]["content"] == manifest["system_prompt"], "system prompt mismatch")
        require(messages[1]["content"] == manifest["task_prompt"], "task prompt mismatch")
        require({t["function"]["name"] for t in request["tools"]} == {"look", "act", "checkpoints"}, "unexpected model tools")
        for message in messages:
            if isinstance(message.get("content"), list):
                for part in message["content"]:
                    if part.get("type") == "image_url":
                        image = part["image_url"]
                        file = root/image["artifact"]
                        data = file.read_bytes()
                        require(hashlib.sha256(data).hexdigest() == image["sha256"], "image hash mismatch")
                        require(struct.unpack(">II", data[16:24]) == (1024,1024), "wrong observation viewport")
                        image_paths.add(image["artifact"])
        for call in response["choices"][0]["message"].get("tool_calls", []):
            record = outputs.get(call["id"])
            if record and call["function"]["name"] == "act" and "dispatched_commands" in record["result"]:
                actions = json.loads(call["function"]["arguments"])["actions"]
                validate_actions(actions, width=1024, height=1024, max_hold_ms=2000)
                expected.extend(actions)
            if record and record["name"] == "checkpoints" and "events" in record["result"]:
                view = record["result"]["events"]
                require(view == checkpoint_view(view), "hidden evaluator state exposed to agent")
    require(len(responses) == result["calls"], "call count mismatch")
    require(expected == [r["action"] for r in receipts], "input commands differ from accepted model tool calls")
    require(all(r["actor"] == "agent" for r in receipts), "operator inputs entered model attempt")
    require(len(receipts) == result["input_commands"], "command count mismatch")
    require(cost == Decimal(result["accounting"]["reported_usd"]), "cost mismatch")
    require(tokens == result["accounting"]["tokens"], "usage mismatch")
    for relative, digest in manifest["source_hashes"].items():
        require(hashlib.sha256((root/"source"/relative).read_bytes()).hexdigest() == digest, "source snapshot changed")
    events = json.loads((root/"evaluation-events.json").read_text())
    require(events[0]["baseline"] == [], "inherited progress in fresh attempt")
    require(events[0]["hostile_mobs_enabled"] is False and events[0]["pve_enabled"] is False, "PvE profile mismatch")
    require(events[0]["starter_prefixes_reset"] is True, "starting items not standardized")
    require(not any(e["event"] == "calibration_probe" for e in events), "operator probe entered a model attempt")
    require(reference_score(events, actions=receipts) == result["score"], "checkpoint score mismatch")
    heartbeat = [e for e in events if e["event"] == "heartbeat"]
    require(heartbeat, "missing liveness evidence")
    require(all(e["hostile_npcs_active"] == 0 and e["hostile_projectiles_active"] == 0 for e in heartbeat), "disabled PvE not enforced")
    summary = {"checks_passed": True, "calls": len(responses), "input_commands": len(receipts),
               "unique_images_verified": len(image_paths), "source_files_verified": len(manifest["source_hashes"]),
               "full_conversation_preserved": True, "agent_checkpoint_access_verified": True,
               "PvE_disabled_verified": True, "reported_usd": str(cost),
               "agency_score_public_subset": result["score"]["agency_score"],
               "mode": manifest["mode"],
               "full_eight_hour_evaluation_verified": False,
               "exact_upstream_prompt_world_and_complete_scorer_verified": False,
               "official_eligible": False}
    (root/"audit.json").write_text(json.dumps(summary,indent=2)+"\n")
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    print(json.dumps(audit(parser.parse_args().run), indent=2))
