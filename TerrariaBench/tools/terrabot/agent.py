"""TerraBot LLM agent loop (programmatic track, tb-api-1.0-rc1).

The model writes a short Python program against `tb`; it runs in the sandbox while the game keeps going; the model
then reads the printed output, the new game events, a status summary and (on request) a screenshot, and writes the
next program. It also keeps a notes file and a code workspace (its own helper library) across turns.

    python tools/terrabot/agent.py --fixture runs/terrabot-fixtures/tb-41100102 --run runs/terrabot-pilot-01 \
        --model claude-opus-5-5 --reasoning medium --usd-cap 6 --wall-minutes 60

Spending is checked against a ledger shared by all TerraBot runs (runs/terrabot-ledger.jsonl, --ledger-cap, default
$10): before every call a reservation (prompt estimate at input price + max output at output price) is journaled and
the call is refused if spent + reservation would exceed either the run cap or the ledger cap. The settled cost is the
gateway's X-Token-Usage-Cost when present, else list price.
"""
import argparse
import base64
import inspect
import io
import json
from pathlib import Path
import re
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "terrariabench"))
from session import Session  # noqa: E402
from run import run_in_session  # noqa: E402
from audit import audit  # noqa: E402
from terrariabench import gateway, unified  # noqa: E402
from terrariabench.openrouter import ProviderError  # noqa: E402
import tb  # noqa: E402  (only to render the API reference from its docstrings)
from tb.grid import Grid  # noqa: E402

LEDGER = ROOT / "runs/terrabot-ledger.jsonl"
MAX_OUT = 12000
KEEP_TURNS = 6


def api_reference():
    lines = []
    for name in tb.__all__:
        obj = getattr(tb, name)
        if inspect.isfunction(obj):
            lines.append(f"tb.{name}{inspect.signature(obj)}\n    {inspect.getdoc(obj) or ''}".replace("\n", "\n    "))
    lines.append("tb.store: dict persisted across programs (JSON values). tb.TbError: raised when the game refuses a call.")
    lines.append("Grid (from tb.tiles): " + "; ".join(
        f"{n}{inspect.signature(getattr(Grid, n))}" for n in ("at", "known", "solid", "platform", "empty", "liquid", "kind",
                                                              "remembered", "find", "render")) + "\n    " + (inspect.getdoc(Grid.render) or ""))
    from tb import path
    lines.append("Pathfinder capabilities (tb.goto / tb.path_to):\n" + getattr(path, "CAPABILITIES", ""))
    return "\n\n".join(lines)


SYSTEM = """You are playing Terraria (the real game, tModLoader 1.4.4, single player, Classic difficulty, normal enemies,
a world you have never seen, a fresh character) by writing Python programs against the `tb` bot library
(API contract tb-api-1.0-rc1).

Goal: defeat the Eye of Cthulhu. Progress along the way is also scored (wood, work bench, torches, furnace, metal bars,
anvil, life crystals, ...), as are deaths, game time and wall time. The game runs in real time: it keeps going while
you think and while your programs run (enemies, day/night). Night falls ~15 game-minutes after the start.

How a turn works:
- You reply with exactly one program in <program timeout="SECONDS">...</program> (default 60 s, max 600 s). It runs
  in a sandbox: Python standard library + `import tb` + your own modules in the workspace (e.g. `from lib.mine import
  dig`), no network, files only inside the workspace. Print what you want to read next turn (output is truncated to
  ~6000 characters). A program that raises shows its traceback. All keys are released when it ends.
- Optional in the same reply: <notes>full new content of notes.md</notes> (your persistent memory; older turns are
  dropped from the conversation, notes are not), and any number of <file path="lib/NAME.py">content</file> to create or
  replace helper modules. Add screenshot="yes" to <program ...> to receive a screenshot after it ends.
- Values persist between programs in tb.store (a dict).

Rules of the API: you only see what the player has seen (tiles lit on screen as they are now; other revealed tiles as
the player's map remembers them, which may be out of date; NPCs and items on screen). Actions use the player's own
controls and the game's real item-use, crafting, equip and chest code: reach limits, tool power, recipes and crafting
stations are the game's own. There are no teleports or cheats.

The library only moves you (tb.goto: walking, jumps, digging, pillaring, surface swims); it never keeps you alive.
Enemies, falls, lava and drowning are yours to handle: in water, tb.me() gives breath, breath_max and submerged
(head in liquid; at 0 breath you lose ~17 life/s), and nothing in tb reacts to them unless your program does.

API reference (coordinates in tiles, y grows downward; 60 ticks per second):

{api}
"""

PROGRAM_RE = re.compile(r"<program([^>]*)>(.*?)</program>", re.S)
FILE_RE = re.compile(r'<file\s+path="([^"]+)"\s*>(.*?)</file>', re.S)
NOTES_RE = re.compile(r"<notes>(.*?)</notes>", re.S)


def strip_fence(code):
    code = code.strip("\n")
    m = re.match(r"^\s*```(?:python)?\n(.*?)\n```\s*$", code, re.S)
    return m.group(1) if m else code


# ------------------------------------------------------------------ ledger
# Fitted with tools/terrabot/probe_price.py on 2026-11-10 (gateway X-Token-Usage-Cost, 2 probes), rounded up.
EXTRA_PRICES = {"gpt-6-astra": (8.5e-6, 34.0e-6)}


def price_of(model):
    if model in gateway.MODELS:
        p = gateway.MODELS[model]["price"]
        return p["input"], p["output"]
    if model in EXTRA_PRICES:
        return EXTRA_PRICES[model]
    p = unified.MODELS[model]["price"]
    return p["input"], p["output"]


def ledger_spent():
    spent = 0.0
    open_res = {}
    if LEDGER.exists():
        for line in LEDGER.read_text().splitlines():
            e = json.loads(line)
            if e["kind"] == "reserve":
                open_res[e["call"]] = e["usd"]
            elif e["kind"] == "settle":
                open_res.pop(e["call"], None)
                spent += e["usd"]
    return spent + sum(open_res.values())  # unsettled reservations count as spent (conservative)


def ledger_write(entry):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps({**entry, "unix": time.time()}) + "\n")


# ------------------------------------------------------------------ model calls
class Model:
    def __init__(self, model, reasoning, run_name, run_cap, ledger_cap):
        self.model, self.reasoning, self.run_name = model, reasoning, run_name
        self.run_cap, self.ledger_cap = run_cap, ledger_cap
        self.key = gateway.load_key()
        self.session = gateway.session_id()
        self.spent, self.calls = 0.0, 0
        self.anthropic = model in gateway.MODELS

    def call(self, system, history):
        pin, pout = price_of(self.model)
        est_prompt = sum(len(json.dumps(m)) for m in history) // 3 + len(system) // 3
        reserve = est_prompt * pin + MAX_OUT * pout
        total = ledger_spent()
        if self.spent + reserve > self.run_cap or total + reserve > self.ledger_cap:
            raise BudgetStop(f"budget: run spent ${self.spent:.3f}, ledger ${total:.3f}, reservation ${reserve:.3f}")
        self.calls += 1
        cid = f"{self.run_name}:{self.calls}"
        ledger_write({"kind": "reserve", "call": cid, "run": self.run_name, "model": self.model, "usd": reserve})
        t0 = time.time()
        try:
            for attempt in range(4):
                try:
                    norm = self._request(system, history)
                    break
                except ProviderError as e:
                    if not e.retryable or attempt == 3:
                        raise
                    time.sleep(getattr(e, "retry_after", None) or 5 * (attempt + 1))
        except Exception:
            # Unknown outcome: keep the reservation as spent.
            ledger_write({"kind": "settle", "call": cid, "run": self.run_name, "model": self.model, "usd": reserve,
                          "source": "reservation_kept_after_error"})
            self.spent += reserve
            raise
        cost = float(norm["usage"]["cost"])
        self.spent += cost
        ledger_write({"kind": "settle", "call": cid, "run": self.run_name, "model": self.model, "usd": cost,
                      "source": norm["usage"]["cost_source"], "prompt_tokens": norm["usage"]["prompt_tokens"],
                      "completion_tokens": norm["usage"]["completion_tokens"], "seconds": round(time.time() - t0, 1)})
        return norm

    def _request(self, system, history):
        if self.anthropic:
            msgs = []
            for m in history:
                blocks = []
                for part in m["content"]:
                    if part["type"] == "text":
                        blocks.append({"type": "text", "text": part["text"]})
                    else:
                        blocks.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": part["b64"]}})
                msgs.append({"role": m["role"], "content": blocks})
            last = msgs[-1]["content"][-1]
            msgs[-1]["content"][-1] = {**last, "cache_control": {"type": "ephemeral"}}
            body = gateway.body(self.model, self.reasoning, system, msgs, [], self.session)
            body.pop("tools", None)
            body["max_tokens"] = MAX_OUT
            message, meta = gateway.messages(body, key=self.key, session=self.session, timeout=300)
            return gateway.normalize(message, meta, self.model)
        msgs = [{"role": "system", "content": system}]
        for m in history:
            if m["role"] == "assistant":
                msgs.append({"role": "assistant", "content": m["content"][0]["text"]})
            else:
                parts = [{"type": "text", "text": p["text"]} if p["type"] == "text" else
                         {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + p["b64"]}} for p in m["content"]]
                msgs.append({"role": "user", "content": parts})
        body = {"model": self.model, "messages": msgs, "max_completion_tokens": MAX_OUT, "reasoning_effort": self.reasoning}
        header, data = unified._post("/chat/completions", body, self.key, 300)
        if not isinstance(data, dict) or not data.get("choices"):
            raise ProviderError("unified response without choices; charge uncertain", retryable=True)
        usage = data.get("usage") or {}
        pin, pout = price_of(self.model)
        prompt, out = usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0
        listed = pin * prompt + pout * out
        reported = header if header is not None else usage.get("total_cost")
        msg = data["choices"][0].get("message") or {}
        return {"choices": [{"message": {"content": msg.get("content"), "reasoning": None}}],
                "usage": {"prompt_tokens": prompt, "completion_tokens": out,
                          "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                          "cost": f"{float(reported):.10f}" if reported is not None else f"{listed:.10f}",
                          "cost_source": "gateway_header" if header is not None else
                                         "usage_total_cost" if reported is not None else "list_price",
                          "list_price_cost": f"{listed:.10f}"}, "model_version": data.get("model")}


class BudgetStop(Exception):
    pass


# ------------------------------------------------------------------ turn content
def trim(text, limit):
    if len(text) <= limit:
        return text
    head = limit * 2 // 3
    return text[:head] + f"\n... [{len(text) - limit} characters cut] ...\n" + text[-(limit - head):]


def status(link):
    p = link.call("me")
    t = link.call("time")
    inv = link.call("inventory")
    held = p["held"]["name"] if p["held"] else None
    return (f"Player at x={p['x']:.1f} y={p['y']:.1f} (feet row {p['foot_y']}), {p['layer']}, life {p['life']}/{p['life_max']}"
            f"{' DEAD (respawn in %ds)' % (p['respawn_ticks'] // 60) if p['dead'] else ''}"
            f"{', HEAD UNDER WATER breath %d/%d' % (p['breath'], p['breath_max']) if p.get('submerged') else ''}, holding {held}, "
            f"stations near: {p['stations_near'] or 'none'}. Time {t['clock']} ({'day' if t['day'] else 'night'}), "
            f"game updates {t['game_updates']}.\nInventory: " + ", ".join(f"{i['name']} x{i['stack']}" for i in inv))


def event_summary(events):
    if not events:
        return "none"
    counts = {}
    for e in events:
        key = e["event"] + (":" + str(e.get("item") or e.get("kind") or e.get("name") or "") if e["event"] in
                            ("pickup", "tile_broken", "placed", "killed", "crafted") else "")
        counts[key] = counts.get(key, 0) + 1
    notable = [e for e in events if e["event"] in ("hurt", "death", "respawn", "boss_awoke", "dawn", "dusk", "killed")][-15:]
    return (", ".join(f"{k} x{v}" for k, v in sorted(counts.items())) + "\nNotable: " +
            "; ".join(json.dumps({k: v for k, v in e.items() if k not in ("seq",)}) for e in notable))


def screenshot_b64(path):
    from PIL import Image
    img = Image.open(path).convert("RGB")
    img.thumbnail((768, 768))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=80)
    return base64.b64encode(buf.getvalue()).decode()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fixture", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--reasoning", default="medium")
    p.add_argument("--usd-cap", type=float, required=True)
    p.add_argument("--ledger-cap", type=float, default=10.0)
    p.add_argument("--wall-minutes", type=float, default=60)
    p.add_argument("--max-turns", type=int, default=200)
    p.add_argument("--display", default=":15")
    a = p.parse_args()
    run_name = Path(a.run).name
    model = Model(a.model, a.reasoning, run_name, a.usd_cap, a.ledger_cap)
    system = SYSTEM.replace("{api}", api_reference())
    s = Session(a.run, a.fixture, display=a.display, manifest={
        "agent_kind": "llm", "model": a.model, "reasoning": a.reasoning, "usd_cap": a.usd_cap,
        "wall_minutes": a.wall_minutes, "helped_by": "nobody (generic API + pathfinder library; no strategy hints)"}).start()
    s.proxy.agent_kind = "llm"
    ws = s.run / "workspace"
    (ws / "lib").mkdir(parents=True)
    (ws / "notes.md").write_text("")
    (s.run / "system_prompt.txt").write_text(system)
    turns_log = (s.run / "turns.jsonl").open("a")
    history, last_seq, t0, stop_reason = [], 0, time.time(), "max_turns"
    first = "This is the first turn; nothing has run yet.\n"
    user_text = first
    want_shot = True
    shot = None
    try:
        for turn in range(1, a.max_turns + 1):
            if time.time() - t0 > a.wall_minutes * 60:
                stop_reason = "wall_budget"
                break
            evs = s.link.call("events", since=last_seq)
            if evs:
                last_seq = evs[-1]["seq"]
            notes = (ws / "notes.md").read_text()
            files = sorted(str(f.relative_to(ws)) for f in ws.rglob("*.py") if "programs" not in f.parts)
            text = (f"Turn {turn}. Wall time used {(time.time() - t0) / 60:.1f} of {a.wall_minutes:.0f} min; "
                    f"spent ${model.spent:.3f} of ${a.usd_cap:.2f}.\n{user_text}\nEvents since last turn: "
                    f"{event_summary(evs)}\n\nStatus: {status(s.link)}\n\nWorkspace modules: {files or 'none'}\n"
                    f"notes.md:\n{notes or '(empty)'}")
            content = [{"type": "text", "text": text}]
            if want_shot:
                shot = s.proxy.screenshot()
                content.append({"type": "image", "b64": screenshot_b64(ws / shot if not Path(shot).is_absolute() else shot)})
            history.append({"role": "user", "content": content})
            # Keep the newest turns; images only on the latest user turn.
            for m in history[:-1]:
                m["content"] = [c for c in m["content"] if c["type"] == "text"]
            history = history[-(2 * KEEP_TURNS + 1):]
            try:
                norm = model.call(system, history)
            except BudgetStop as e:
                stop_reason = str(e)
                break
            reply = norm["choices"][0]["message"]["content"] or ""
            history.append({"role": "assistant", "content": [{"type": "text", "text": reply or "(empty reply)"}]})
            m_notes = NOTES_RE.search(reply)
            if m_notes:
                (ws / "notes.md").write_text(m_notes.group(1).strip() + "\n")
            written = []
            for path, body in FILE_RE.findall(reply):
                target = (ws / path).resolve()
                if ws.resolve() in target.parents and target.suffix == ".py":
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(strip_fence(body))
                    written.append(path)
            progs = PROGRAM_RE.findall(reply)
            rec = {"turn": turn, "unix": time.time(), "usage": norm["usage"], "reply": reply,
                   "reasoning": norm["choices"][0]["message"].get("reasoning"), "files": written}
            if not progs:
                user_text = "Your reply had no <program>...</program>; nothing ran. Reply with a program.\n"
                want_shot = False
                turns_log.write(json.dumps(rec) + "\n")
                turns_log.flush()
                continue
            attrs, code = progs[-1]
            m_t = re.search(r'timeout="?(\d+)', attrs)
            timeout = min(600, max(5, int(m_t.group(1)))) if m_t else 60
            want_shot = bool(re.search(r'screenshot="?(yes|true|1)', attrs))
            res = run_in_session(s, strip_fence(code), f"t{turn:03d}", ws, timeout, s.log)
            rec["program"] = {k: res[k] for k in ("name", "exit", "seconds")}
            turns_log.write(json.dumps(rec) + "\n")
            turns_log.flush()
            user_text = (f"Program t{turn:03d} ({'wrote ' + ', '.join(written) + '; ' if written else ''}timeout {timeout}s) "
                         f"ended: {res['exit']} after {res['seconds']:.1f}s.\n--- stdout ---\n{trim(res['stdout'], 6000)}\n"
                         + (f"--- stderr ---\n{trim(res['stderr'], 2500)}\n" if res["stderr"].strip() else ""))
            if s.link.call("world")["eye_of_cthulhu_defeated"]:
                stop_reason = "eye_of_cthulhu_defeated"
                break
    finally:
        turns_log.close()
        s.stop({"kind": "llm", "model": a.model, "stop_reason": stop_reason, "turns": turn, "usd": model.spent,
                "calls": model.calls, "wall_seconds": time.time() - t0})
        print(json.dumps(audit(s.run)))


if __name__ == "__main__":
    main()
