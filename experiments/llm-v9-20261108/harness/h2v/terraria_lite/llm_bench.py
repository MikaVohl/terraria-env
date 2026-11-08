"""Budgeted, auditable development evaluation. No code execution or LLM judge."""
from collections import defaultdict
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import statistics as stats
import time

from terraria_lite import SPEC
from terraria_lite.llm_protocol import Session, canonical, digest, validate_seed
from terraria_lite.llm_macros import MACRO_HELP, Prim, Stuck, View, make as make_macro
from terraria_lite.llm_providers import AnthropicGateway, OpenAIGateway, OpenRouter, OpenRouterDecisions, ProviderError
from terraria_lite.llm_text import GUIDE, TEXT_VIEW, cycle_constants, legend, parse_named, reach_table, text_observation
from terraria_lite.scoring import score_masks

HARNESS = "terraria-llm-dev-v0.3"
PAID = ("openrouter", "openrouter_decisions", "anthropic_gateway", "openai_gateway")
DEFAULTS = {
    "provider": "random", "model": None, "reasoning_effort": "high",
    "seeds": [31000001], "replicates": 1, "random_seed": 12345,
    "max_steps": 3000, "max_calls": 256, "max_actions_per_call": 1,
    "max_output_tokens": 8192, "max_total_tokens_per_episode": 1_000_000,
    "max_context_bytes": 100_000, "max_wall_seconds": 1800,
    "request_timeout_seconds": 120, "history_turns": 8, "notes_max_chars": 2048,
    "max_cost_usd_total": 0.0, "input_usd_per_token_ceiling": None,
    "output_usd_per_token_ceiling": None, "pricing_source": None,
    "observation_format": "full", "batch_interrupt": "never",
    # v0.3 factors (defaults reproduce v0.2 behaviour)
    "action_format": "ids", "knowledge": "rules", "history_mode": "sliding",
    "structured_output": True, "cache_read_usd_per_token": None, "cache_write_usd_per_token": None,
    "max_retries": 0, "label": None, "action_set": "primitive", "cooldown_wait": False,
}
EFFORTS = ("none", "low", "medium", "high", "xhigh", "max")


def config(raw):
    if not isinstance(raw, dict) or set(raw) - set(DEFAULTS):
        raise ValueError("Unknown configuration fields")
    c = {**DEFAULTS, **raw}
    if c["provider"] not in ("random", "noop", *PAID):
        raise ValueError("Unknown provider")
    if c["observation_format"] not in ("full", "compact", "text") or c["batch_interrupt"] not in ("never", "illegal", "events"):
        raise ValueError("Unknown observation or batch-interruption format")
    if c["action_format"] not in ("ids", "names") or c["knowledge"] not in ("rules", "guide") or c["history_mode"] not in ("sliding", "chunked"):
        raise ValueError("Unknown action format, knowledge track or history mode")
    if c["observation_format"] == "text" and c["action_format"] != "names":
        raise ValueError("Text observations use named actions")
    if c["action_set"] not in ("primitive", "macro") or type(c["cooldown_wait"]) is not bool:
        raise ValueError("Unknown action set or cooldown policy")
    if c["action_set"] == "macro" and c["action_format"] != "names":
        raise ValueError("Macros use named actions")
    for key, maximum in {"replicates": 10, "max_steps": max(3000, SPEC.default_steps), "max_calls": 20000,
                         "max_actions_per_call": 64, "max_output_tokens": 128000,
                         "max_total_tokens_per_episode": 1_000_000_000,
                         "max_context_bytes": 1_000_000, "max_wall_seconds": 86400,
                         "request_timeout_seconds": 600, "history_turns": 64,
                         "notes_max_chars": 8192}.items():
        if type(c[key]) is not int or not 1 <= c[key] <= maximum:
            raise ValueError(f"Invalid positive integer budget: {key}")
    if type(c["max_retries"]) is not int or not 0 <= c["max_retries"] <= 5:
        raise ValueError("Invalid retry count")
    if type(c["random_seed"]) is not int or not 0 <= c["random_seed"] < 2**32:
        raise ValueError("Invalid random seed")
    if not isinstance(c["seeds"], list) or not 1 <= len(c["seeds"]) <= 128 or len(set(c["seeds"])) != len(c["seeds"]):
        raise ValueError("Provide 1..128 distinct world seeds; use replicates explicitly")
    for seed in c["seeds"]:
        validate_seed(seed)
    if type(c["max_cost_usd_total"]) not in (int, float) or not math.isfinite(c["max_cost_usd_total"]) or c["max_cost_usd_total"] < 0:
        raise ValueError("Invalid total dollar budget")
    if c["provider"] in PAID:
        if not isinstance(c["model"], str) or not re.fullmatch(r"[A-Za-z0-9_./:-]+", c["model"]):
            raise ValueError("An explicit model ID is required")
        if c["reasoning_effort"] not in EFFORTS:
            raise ValueError("Invalid reasoning effort")
        for key in ("input_usd_per_token_ceiling", "output_usd_per_token_ceiling"):
            if type(c[key]) not in (int, float) or not math.isfinite(c[key]) or c[key] <= 0:
                raise ValueError("Explicit positive pricing ceilings required for paid calls")
        for key in ("cache_read_usd_per_token", "cache_write_usd_per_token"):
            if c[key] is not None and (type(c[key]) not in (int, float) or not math.isfinite(c[key]) or c[key] < 0):
                raise ValueError("Invalid cache price")
        if not isinstance(c["pricing_source"], str) or not c["pricing_source"] or c["max_cost_usd_total"] <= 0:
            raise ValueError("Paid runs require pricing provenance and a positive spend limit")
    return c


def response_schema(c):
    if c["action_format"] == "names":
        # No length keywords: strict-mode providers differ in support; lengths are enforced on parse.
        return {"type": "object", "properties": {
            "plan": {"type": "string"},
            "actions": {"type": "array", "items": {"type": "string"}},
            "memory": {"type": "string"}},
            "required": ["plan", "actions", "memory"], "additionalProperties": False}
    return {"type": "object", "properties": {
        "actions": {"type": "array", "minItems": 1, "maxItems": c["max_actions_per_call"],
                    "items": {"type": "integer", "minimum": 0, "maximum": SPEC.n_actions-1}},
        "memory": {"type": "string", "maxLength": c["notes_max_chars"]}},
        "required": ["actions", "memory"], "additionalProperties": False}


def extract_json(text):
    """Outermost JSON object in a reply (tolerates code fences and surrounding prose)."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object")
    return json.loads(text[start:end+1])


def parse_response(text, c):
    try:
        if c["action_format"] == "names":
            obj = extract_json(text)
            assert isinstance(obj, dict) and isinstance(obj.get("actions"), list)
            memory = obj.get("memory")
            assert memory is None or isinstance(memory, str)
            actions = parse_named(obj["actions"], c["max_actions_per_call"], macros=c["action_set"] == "macro")
            assert actions is not None
            return actions, None if memory is None else memory[:c["notes_max_chars"]], True
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


def library_path(root):
    if os.environ.get("TERRARIA_LITE_LIB"):
        return Path(os.environ["TERRARIA_LITE_LIB"]).resolve()
    lib = root / "python/terraria_lite/libterraria.dylib"
    return lib if lib.exists() else root / "python/terraria_lite/libterraria.so"


def provenance(environment_root):
    root = Path(environment_root).resolve()
    header = (root / "include/env.h").read_text()
    if int(re.search(r"#define ENV_VERSION (\d+)", header)[1]) != SPEC.version:
        raise ValueError("Environment source root differs from loaded library version")
    lib = library_path(root)
    sources = [p for folder in ("src", "include") for p in (root / folder).glob("*") if p.suffix in (".c", ".h")]
    here = Path(__file__)
    harness = [here] + [here.with_name(n) for n in ("llm_protocol.py", "llm_providers.py", "llm_text.py", "llm_macros.py", "rules.py", "scoring.py", "__init__.py")]
    return {"environment_root": str(root), "environment_version": SPEC.version,
            "native_library": lib.name, "native_library_sha256": file_sha(lib),
            "native_sources": {str(p.relative_to(root)): file_sha(p) for p in sorted(sources)},
            "harness_sources": {p.name: file_sha(p) for p in harness}}


def prompt(session, c):
    names = c["action_format"] == "names"
    interrupt = {"never": "",
                 "illegal": "After an illegal attempt consumes its tick, the remaining list is discarded and you receive a new observation. ",
                 "events": ("The remaining list is discarded and you receive a new observation right after any of these events: an illegal attempt "
                            "(its tick is still consumed), taking damage, unlocking an achievement, a new kind of mob coming into view, nightfall or dawn. ")}
    text = ("Play this scaled-down Terraria environment to earn as many distinct achievements as possible within the primitive action budget. "
            + ("Public game rules are supplied below; they are not a strategy guide. " if c["knowledge"] == "rules" else
               "Public game rules and a game guide are supplied below. ")
            + ("Return ONLY a JSON object {\"plan\": short reasoning about what to do next, \"actions\": list of exact action names, "
               "\"memory\": your persistent notes}. An action may be written 'name xN' to repeat it N times (e.g. 'right x5', 'noop x2'). "
               if names else "Return ONLY a JSON object with actions (integer IDs) and memory (your own concise notes). ")
            + f"Submit at most {c['max_actions_per_call']} primitive ticks per call (after expanding repeats{' and macros' if c['action_set'] == 'macro' else ''}). Each tick advances the world. "
            + ("Apart from the declared macros, there is no observation or conditional control inside a submitted list. " if c["action_set"] == "macro" else
               "There is no observation or conditional control inside a submitted list. An action list is not a macro, pathfinder or recipe executor. ")
            + ("Cooldown wait: a 'mine ...' or 'attack' issued during its cooldown is preceded automatically by noop ticks until it is ready (the noops cost ticks). " if c["cooldown_wait"] else "")
            + "A malformed response, or a list that is blocked immediately, costs one noop. Known illegal actions remain attempts. No reset, undo, external tools or code execution. "
            "No time passes during inference. Memory is reset between episodes; only your own notes and the configured recent turns persist. "
            + f"Your notes (max {c['notes_max_chars']} characters) replace the previous notes on every call: keep goals, known locations and lessons there. "
            + interrupt[c["batch_interrupt"]]
            + ("Compact observations omit the redundant flat status array; named scalars, inventory, achievement names, selected_placeable_one_hot and entities preserve its information. " if c["observation_format"] == "compact" else "")
            + "\n")
    if c["action_set"] == "macro":
        text += MACRO_HELP + "\n"
    if c["observation_format"] == "text":
        text += legend() + "\n" + reach_table() + "\n"
    if c["knowledge"] == "guide":
        text += GUIDE + "\n"
    return text + "PUBLIC RULES (machine-readable):\n" + canonical(session.knowledge())


def model_observation(packet, c, max_steps=None, cycle=None):
    """Remove only redundant fields or re-encode; never reveal additional world information."""
    if c["observation_format"] == "full":
        return packet
    if c["observation_format"] == "text":
        return text_observation(packet, max_steps, cycle)
    result = {k: v for k, v in packet.items() if k != "status"}
    result["selected_placeable_one_hot"] = packet["v9"]["selected_slot_one_hot"] if "v9" in packet else packet["status"][17:SPEC.status_inv0]
    return result


def mob_kinds(packet):
    return {i for e in packet["visible_entities"] for i in range(SPEC.entity_channels-2) if e["features"][i] > .5}


def batch_events(before, after, illegal):
    """Observation-derived events between two packets (used for interrupts and feedback)."""
    events = []
    if illegal:
        events.append("illegal")
    if after["scalars"]["health_fraction"]*after["scalars"]["max_health_fraction"] < before["scalars"]["health_fraction"]*before["scalars"]["max_health_fraction"] - 1e-6:
        events.append("damage")
    if len(after["achievements"]) > len(before["achievements"]):
        events.append("achievement")
    if mob_kinds(after) - mob_kinds(before):
        events.append("new_mob")
    if "v9" in after and after["v9"]["is_night"] != before["v9"]["is_night"]:
        events.append("nightfall" if after["v9"]["is_night"] else "dawn")
    return events


def feedback(submitted, executed, stop_action, events, unlocked, damage, stuck=None, capped=False):
    if not submitted:
        return "Previous response was malformed: it cost one noop."
    parts = [f"Last call: {submitted} list items, {executed} ticks executed."]
    if stop_action is not None:
        parts.append(f"After '{SPEC.action_names[stop_action]}': {', '.join(events)}.")
    if stuck:
        parts.append(f"Blocked: {stuck}; rest of the list discarded.")
    if capped:
        parts.append("Per-call tick limit reached; rest of the list discarded.")
    if unlocked:
        parts.append("Unlocked: " + ", ".join(unlocked) + ".")
    if damage:
        parts.append(f"Health lost during the call: {damage}.")
    return " ".join(parts)


def user_message(session, c, memory, note, cycle):
    observation = model_observation(session.packet(), c, c["max_steps"], cycle)
    if c["observation_format"] != "text":
        return canonical({"observation": observation, "memory": memory,
                          "remaining_primitive_actions": c["max_steps"]-session.info["steps"]})
    return (observation + "\n" + (note + "\n" if note else "") + "Your notes: " + (memory or "(none)") + "\n"
            "Reply with the JSON object {\"plan\", \"actions\", \"memory\"}.")


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
            "tiered": score_masks([r["achievement_mask"] for r in usable]) if usable else {},
            "achievement_rates": rates,
            "crafter_style_coverage_secondary": math.expm1(stats.mean(math.log1p(100*r) for r in rates.values())) if usable else None,
            "death_rate": stats.mean(r["died"] for r in usable) if usable else None,
            "stop_reasons": {name: sum(r["status"] == name for r in records) for name in sorted({r["status"] for r in records})},
            "interpretation": "Development only; no best-of selection. Incomplete aggregate is not a valid leaderboard score. Bootstrap resamples world means, not repeated calls or correlated replicates."}


def estimate_cost(usage, c):
    """List-price estimate; cache prices default to the full input ceiling (conservative)."""
    inp, out = c["input_usd_per_token_ceiling"], c["output_usd_per_token_ceiling"]
    read = usage.get("cache_read_tokens") or 0
    write = usage.get("cache_write_tokens") or 0
    fresh = usage["prompt_tokens"] - read - write
    cr = inp if c["cache_read_usd_per_token"] is None else c["cache_read_usd_per_token"]
    cw = inp if c["cache_write_usd_per_token"] is None else c["cache_write_usd_per_token"]
    return fresh*inp + read*cr + write*cw + usage["completion_tokens"]*out


def make_adapter(c, key, credentials):
    if c["provider"] == "openrouter":
        return OpenRouter(c, key=key)
    if c["provider"] == "openrouter_decisions":
        if c["observation_format"] != "text":
            raise ValueError("Decisions provider needs text observations")
        return OpenRouterDecisions(c, key=key)
    if c["provider"] == "anthropic_gateway":
        return AnthropicGateway(c, credentials)
    if c["provider"] == "openai_gateway":
        return OpenAIGateway(c, credentials)
    return None


def run(raw_config, environment_root, out, *, allow_api=False, key=None, credential_source=None, provider=None, credentials=None):
    c = config(raw_config)
    if c["provider"] in PAID and not allow_api:
        raise ValueError("Paid/network execution requires explicit --allow-api")
    out = Path(out).resolve()
    out.mkdir(parents=True, exist_ok=False)
    sources = provenance(environment_root)
    cycle = cycle_constants(environment_root) if SPEC.status_day_phase is not None else None
    manifest = {"harness": HARNESS, "created_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "config": c, "provenance": sources, "credential_source": credential_source,
                "track": ("symbolic-primitive" if c["max_actions_per_call"] == 1 else "symbolic-open-loop")
                         + ("+guide" if c["knowledge"] == "guide" else ""),
                "text_view": TEXT_VIEW if c["observation_format"] == "text" else None,
                "day_night_cycle": cycle,
                "external_knowledge": "Public rules and recipes" + ("; game guide (tier list, mechanics facts, typical progression)" if c["knowledge"] == "guide" else "")
                                      + "; pretrained-model priors allowed, unlike scratch RL",
                "private_holdout": False, "automatic_retries": c["max_retries"],
                "retry_policy": "Failed requests are retried up to max_retries times; each failed attempt keeps its full conservative reservation as charged.",
                "cost_guard": "Pre-request conservative UTF8-byte token reservation + declared price ceilings. Charged = max(list-price estimate, provider-reported cost). Not a substitute for a provider account billing limit; unknown charges stop the run.",
                "planned_episodes": len(c["seeds"])*c["replicates"]}
    manifest["batch_policy"] = c["batch_interrupt"]
    (out / "manifest.json").write_text(canonical(manifest) + "\n")
    adapter = provider or make_adapter(c, key, credentials)
    records, total_cost, total_reported_cost = [], 0.0, 0.0
    abort = False
    summary = None
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
            calls = tokens = interrupted_batches = discarded_actions = invalid_responses = failed_requests = 0
            interrupt_reasons = defaultdict(int)
            episode_cost = episode_reported = 0.0
            begin, status = time.monotonic(), "running"
            error_type = error_message = None
            note = ""
            reserve_cost = 0.0
            system = prompt(session, c)
            journal.append("initial", seed=seed, max_steps=c["max_steps"], observation_sha256=digest(session.packet()),
                           system_sha256=digest(system))
            try:
                while not session.ended:
                    remaining = c["max_wall_seconds"] - (time.monotonic()-begin)
                    if remaining <= 0:
                        status = "wall_budget"; break
                    if calls >= c["max_calls"]:
                        status = "call_budget"; break
                    user = user_message(session, c, memory, note, cycle)
                    messages = [{"role": "system", "content": system}, *history, {"role": "user", "content": user}]
                    if len(canonical(messages).encode()) > c["max_context_bytes"]:
                        status = "context_budget"; break
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
                        journal.append("request_started", call=calls, payload=payload, user=user,
                                       reserved_cost_usd=reserve_cost, input_token_bound=input_bound)
                        for attempt in range(c["max_retries"]+1):
                            request_begin = time.monotonic()
                            try:
                                reply = adapter.call(payload, min(c["request_timeout_seconds"], max(1.0, remaining)))
                                break
                            except ProviderError as error:
                                if attempt == c["max_retries"] or total_cost + 2*reserve_cost > c["max_cost_usd_total"]:
                                    raise
                                failed_requests += 1
                                total_cost += reserve_cost
                                episode_cost += reserve_cost
                                journal.append("request_failed", call=calls, attempt=attempt, error_message=str(error),
                                               charged_reservation_usd=reserve_cost)
                                time.sleep(5 * (attempt+1))
                        reply["latency_seconds"] = time.monotonic() - request_begin
                        usage = reply["usage"]
                        cost = usage.get("cost")
                        if cost is not None and (type(cost) not in (int, float) or not math.isfinite(cost) or cost < 0):
                            raise ProviderError("Invalid provider cost field")
                        estimate = estimate_cost(usage, c)
                        charged = max(estimate, cost or 0.0)
                        episode_cost += charged
                        total_cost += charged
                        if cost is not None:
                            total_reported_cost += cost
                            episode_reported += cost
                        tokens += usage["total_tokens"]
                        journal.append("response_received", call=calls, response=reply, accounted_cost_usd=charged, estimate_usd=estimate)
                        if usage["prompt_tokens"] > input_bound or usage["completion_tokens"] > c["max_output_tokens"] or charged > reserve_cost + 1e-9:
                            raise ProviderError("Provider exceeded reserved token/cost bound; stop")
                    else:
                        calls += 1
                        journal.append("offline_request", call=calls, user=user)
                        legal = session.packet()["legal_actions"]
                        choice = 0 if c["provider"] == "noop" else rng.choice(legal)
                        if c["action_format"] == "names":
                            text = canonical({"plan": "", "actions": [SPEC.action_names[choice]], "memory": ""})
                        else:
                            text = canonical({"actions": [choice], "memory": ""})
                        reply = {"text": text, "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0},
                                 "model": c["provider"], "finish_reason": "stop"}
                        journal.append("offline_response", call=calls, response=reply)
                    chosen, new_memory, valid = parse_response(reply["text"], c)
                    if reply.get("finish_reason") not in ("stop", "tool_calls"):
                        chosen, new_memory, valid = [None], None, False
                    if valid and new_memory is not None:
                        memory = new_memory
                    if not valid:
                        invalid_responses += 1
                    executed_batch, stop_action, events, unlocked, stuck, capped = 0, None, [], [], None, False
                    start_packet = session.packet()
                    controllers = [make_macro(*item) if isinstance(item, tuple) else Prim(item, c["cooldown_wait"])
                                   for item in chosen] if valid else [None]
                    for index, ctrl in enumerate(controllers):
                        remaining_work = False
                        while not session.ended:
                            if executed_batch >= c["max_actions_per_call"]:
                                capped = True
                                break
                            if ctrl is None:
                                action = None
                            else:
                                try:
                                    action = ctrl.next_action(View(session.packet()))
                                except Stuck as error:
                                    stuck = f"'{ctrl.name}' stopped: {error}"
                                    break
                                if action is None:
                                    break
                            before = session.packet()
                            illegal_before = session.illegal_attempts
                            result = session.act({"action": action})
                            executed_batch += 1
                            actions.append(result["executed_action"])
                            for achievement in result["achievements"]:
                                if achievement not in first:
                                    first[achievement] = result["steps"]
                                    unlocked.append(achievement)
                            journal.append("step", action=action, executed_action=result["executed_action"], item=index,
                                           reward=result["reward"], observation_sha256=digest(session.packet()))
                            if ctrl is None:
                                break
                            if c["batch_interrupt"] == "never" or session.ended:
                                continue
                            events = batch_events(before, session.packet(), session.illegal_attempts > illegal_before)
                            if c["batch_interrupt"] == "illegal":
                                events = [e for e in events if e == "illegal"]
                            if events:
                                stop_action = result["executed_action"]
                                remaining_work = index < len(controllers)-1 or not (isinstance(ctrl, Prim) and ctrl.done)
                                break
                        if stuck or remaining_work or capped or session.ended:
                            break
                    if stuck or remaining_work or capped:
                        discarded = len(controllers) - index - (1 if isinstance(ctrl, Prim) and ctrl.done else 0)
                        if stuck or remaining_work:
                            interrupted_batches += 1
                            discarded_actions += discarded
                            for e in (["stuck"] if stuck else events):
                                interrupt_reasons[e] += 1
                            journal.append("batch_interrupted", reason=["stuck"] if stuck else events, discarded_items=discarded, stuck=stuck)
                    if valid and executed_batch == 0 and not session.ended:
                        # A call must consume time: an immediately blocked list costs one noop, like a malformed reply.
                        result = session.act({"action": 0})
                        executed_batch = 1
                        actions.append(0)
                        journal.append("step", action=0, executed_action=0, item=-1,
                                       reward=result["reward"], observation_sha256=digest(session.packet()))
                    end_packet = session.packet()
                    s0, s1 = start_packet["scalars"], end_packet["scalars"]
                    damage = max(0, round((s0["health_fraction"]*s0["max_health_fraction"] - s1["health_fraction"]*s1["max_health_fraction"])*SPEC.health_cap))
                    note = feedback(len(chosen) if valid else 0, executed_batch, stop_action, events, unlocked, damage, stuck, capped)
                    journal.append("batch_end", call=calls, submitted_items=len(chosen), executed_actions=executed_batch,
                                   native_info=session.info, accounted_cost_usd=episode_cost)
                    history += [{"role": "user", "content": user}, {"role": "assistant", "content": reply["text"] or "(empty)"}]
                    if c["history_mode"] == "sliding":
                        history = history[-2*c["history_turns"]:]
                    elif len(history) > 4*c["history_turns"]:
                        # Chunked window: keeps a stable cached prefix for history_turns calls at a time.
                        history = history[-2*c["history_turns"]:]
                if session.ended:
                    status = "death" if session.terminated else "action_budget"
            except Exception as error:
                # Do not log arbitrary exception strings: they can contain remote secrets.
                status, error_type, abort = "infrastructure_error", type(error).__name__, True
                error_message = str(error) if isinstance(error, ProviderError) else None
                if adapter:
                    total_cost += reserve_cost  # retain conservative uncertainty reservation
                    episode_cost += reserve_cost
                journal.append("infrastructure_error", error_type=error_type, error_message=error_message, charge_may_be_unknown=bool(adapter))
            finally:
                packet = session.packet()
                mask = int(session.info["achievement_mask"])
                record = {"seed": seed, "replicate": replicate, "status": status, "error_type": error_type, "error_message": error_message,
                          "score": packet["score"], "achievement_mask": mask,
                          "weighted_score": score_masks([mask]).get("weighted_score"),
                          "achievements": packet["achievements"], "died": session.terminated,
                          "steps": session.info["steps"], "calls": calls, "tokens": tokens,
                          "first_achievement_steps": first, "native_info": session.info,
                          "invalid_requests": session.invalid_requests, "invalid_responses": invalid_responses,
                          "illegal_attempts": session.illegal_attempts,
                          "interrupted_batches": interrupted_batches, "discarded_actions": discarded_actions,
                          "interrupt_reasons": dict(interrupt_reasons), "failed_requests": failed_requests,
                          "accounted_cost_usd": episode_cost, "reported_cost_usd": episode_reported,
                          "elapsed_seconds": time.monotonic()-begin,
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
                print(f"world={seed} rep={replicate} status={status} score={record['score']}/{SPEC.n_achievements} "
                      f"weighted={record['weighted_score']} steps={record['steps']} calls={calls} accounted=${total_cost:.4f}", flush=True)
                summary = {**score(records, manifest["planned_episodes"]), "episodes": records,
                           "accounted_cost_usd_total": total_cost, "provider_reported_cost_usd_total": total_reported_cost,
                           "charge_uncertain": abort and bool(adapter)}
                (out / "summary.json").write_text(canonical(summary) + "\n")
    return summary


def verify(directory, environment_root, relaxed_harness=False):
    """Replay-verify a run. relaxed_harness only waives harness-source hash equality (reported), never the environment's."""
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text())
    current, frozen = provenance(environment_root), manifest["provenance"]
    harness_diff = sorted(k for k in set(current["harness_sources"]) | set(frozen["harness_sources"])
                          if current["harness_sources"].get(k) != frozen["harness_sources"].get(k))
    if {k: v for k, v in current.items() if k != "harness_sources"} != {k: v for k, v in frozen.items() if k != "harness_sources"}:
        raise ValueError("Environment hash changed; use the original frozen environment")
    if harness_diff and not relaxed_harness:
        raise ValueError("Harness hash changed; use the original frozen implementation")
    c = manifest["config"]
    c = {**DEFAULTS, **c}
    cycle = manifest.get("day_night_cycle")
    cycle = tuple(cycle) if cycle else None
    count = 0
    for episode in sorted(directory.glob("world-*-rep-*")):
        rows = read_journal(episode / "events.jsonl")
        initial, final = rows[0], rows[-1]
        assert initial["event"] == "initial" and final["event"] == "final"
        session = Session(initial["seed"], initial["max_steps"], environment_root)
        try:
            assert digest(session.packet()) == initial["observation_sha256"]
            for row in rows:
                if row["event"] in ("request_started", "offline_request"):
                    observation = model_observation(session.packet(), c, c["max_steps"], cycle)
                    if c["observation_format"] == "text":
                        assert row["user"].startswith(observation + "\n"), "Model observation mismatch"
                    else:
                        assert json.loads(row["user"])["observation"] == observation, "Model observation mismatch"
                    if row["event"] == "request_started":
                        assert canonical(row["user"])[1:-1] in canonical(row["payload"]), "Logged user turn not in payload"
                if row["event"] == "step":
                    result = session.act({"action": row["action"]})
                    assert result["executed_action"] == row["executed_action"]
                    assert result["reward"] == row["reward"]
                    assert digest(session.packet()) == row["observation_sha256"]
            assert session.info == final["record"]["native_info"]
            assert digest(session.packet()) == final["record"]["final_observation_sha256"]
            assert final["record"]["achievement_mask"] == session.info["achievement_mask"]
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
    return {"verified_episodes": count, "checks": "hash chain, model observation per request, each native transition/reward/observation and final state",
            "harness_files_differing_from_run": harness_diff, "api_calls": 0}
