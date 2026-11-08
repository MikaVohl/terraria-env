"""Display-settings perception probe for default-v1 (stock player options only).

    python tools/settings_probe.py capture --fixture F --out D --variant NAME=:11 ...   # unpaid: screenshots + truth
    python tools/settings_probe.py ask --out D --models claude-haiku-5-5:medium gpt-5.6-luna:low --usd 0.5

capture: one game per variant on its isolated Xwayland display (the display size must equal the variant window).
The same operator script runs in every variant: spawn (v0), walk right 3 s (v1), walk left 6 s (v2), dig down with
the pickaxe for 10 s (v3). At each viewpoint two screenshots: A with the cursor parked in the sky, B with the cursor on
a target (v0-v2: the nearest tree trunk; v3: the ground under the feet). Ground truth comes from the observer's
privileged agent-state snapshot (TERRARIABENCH_STATE_FILE), written for this probe only; no agent ever sees it.

ask: per screenshot pair, one question set to each model: A -> pixel of the nearest tree trunk base and the hotbar
slot holding the axe (number and pixel); B -> what is under the mouse cursor. Scored against the truth.
"""
import argparse
import base64
import io
import json
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path
import shutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench import gateway  # noqa: E402
from terrariabench.combo import gateway_text  # noqa: E402
from terrariabench.linux_control import XGameControl, launch, stop_owned_game  # noqa: E402
from terrariabench.reference_live import LIGHTING_MODES, setup_keys  # noqa: E402
VARIANTS = {  # name: (window, zoom, ui_scale, lighting, smart_cursor, minimap)
    "base": ("1024x1024", 1.0, 0.9, "color", "off", "frame"),
    "zoom075": ("1024x1024", 0.75, 0.9, "color", "off", "frame"),
    "zoom150": ("1024x1024", 1.5, 0.9, "color", "off", "frame"),
    "smartcursor_on": ("1024x1024", 1.0, 0.9, "color", "on", "frame"),
    "lighting_white": ("1024x1024", 1.0, 0.9, "white", "off", "frame"),
    "lighting_retro": ("1024x1024", 1.0, 0.9, "retro", "off", "frame"),
    "minimap_off": ("1024x1024", 1.0, 0.9, "color", "off", "off"),
    "minimap_overlay": ("1024x1024", 1.0, 0.9, "color", "off", "overlay"),
    "ui125": ("1024x1024", 1.0, 1.25, "color", "off", "frame"),
    "window1280x720": ("1280x720", 1.0, 0.9, "color", "off", "frame"),
}


def jpeg(path):
    from PIL import Image
    buffer = io.BytesIO()
    Image.open(path).convert("RGB").save(buffer, "JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode()


def capture_variant(name, display, fixture, out):
    window, zoom, ui, lighting, smart, minimap = VARIANTS[name]
    w, h = (int(v) for v in window.split("x"))
    root = out / name
    shutil.copytree(fixture, root / "tml", ignore=shutil.ignore_patterns("Logs", "*.log", "*.bak"))
    state = root / "state.json"
    pid = launch(root / "tml", root / "client.log", root / "telemetry", skipselect=True, width=w, height=h, display=display,
                 config_updates={"UIScale": ui, "ResetDefaultUIScale": False, "Zoom": zoom, "LightingMode": LIGHTING_MODES[lighting]},
                 extra_env={"TERRARIABENCH_PROFILE": "reference-reconstructed-v1", "TERRARIABENCH_PVE": "enabled",
                            "TERRARIABENCH_HOSTILE_DAMAGE": "on", "TERRARIABENCH_REFERENCE_STARTER_PREFIXES": "plain",
                            "TERRARIABENCH_CHECKPOINT_CHAT": "disabled", "TERRARIABENCH_STATE_FILE": str(state)})
    game, shots = None, []
    try:
        deadline = time.monotonic() + 150
        while not state.exists():
            if time.monotonic() > deadline or not Path(f"/proc/{pid}").exists():
                raise RuntimeError("startup failed")
            time.sleep(.5)
        time.sleep(2)
        game = XGameControl(pid, root / "inputs.jsonl", display=display, width=w, height=h, max_hold_ms=2000)
        game.setup_window()
        keys = setup_keys(argparse.Namespace(smart_cursor=smart, minimap=minimap))
        if keys:
            game.act(keys, actor="operator_setup")
        cx, cy, tile = w // 2, h // 2, 16 * zoom
        moves = {"v0": [{"ms": 1000}], "v1": [{"keys": ["d"], "ms": 2000}, {"keys": ["d"], "ms": 1000}, {"ms": 800}],
                 "v2": [{"keys": ["a"], "ms": 2000}] * 3 + [{"ms": 800}],
                 "v3": [{"keys": ["2"], "ms": 60}, {"ms": 200}] + [{"x": cx, "y": int(cy + 1.9 * tile), "mouse": "left", "ms": 2000}] * 6 + [{"ms": 1000}]}
        for view, actions in moves.items():
            game.act(actions, actor="operator_probe")
            game.act([{"x": cx, "y": int(h * .22), "ms": 300}], actor="operator_probe")
            a = root / f"{view}-A.png"
            game.capture(a)
            truth = json.loads(state.read_text())
            p = truth["player"]
            trees = [{"px": round(cx + (t["sx"] - p["sx"]) * zoom), "py": round(cy + (t["sy"] - p["sy"]) * zoom),
                      "height_px": round(t["height"] * tile), "dx_tiles": t["dx"]} for t in truth["trees"]]
            trees = [t for t in trees if 0 <= t["px"] < w and 0 <= t["py"] < h]
            nearest = min(trees, key=lambda t: abs(t["dx_tiles"])) if trees else None
            if view != "v3" and nearest:
                target, kind = (nearest["px"], nearest["py"] - int(tile)), "tree"
            else:
                target, kind = (cx, int(cy + 1.9 * tile)), "ground" if p["on_ground"] else "unknown"
            game.act([{"x": max(0, min(w - 1, target[0])), "y": max(0, min(h - 1, target[1])), "ms": 300}], actor="operator_probe")
            b = root / f"{view}-B.png"
            game.capture(b)
            axe_slot = next((s["slot"] for s in truth["hotbar"] if s["axe"]), None)
            shots.append({"variant": name, "view": view, "A": str(a.relative_to(out)), "B": str(b.relative_to(out)),
                          "window": [w, h], "zoom": zoom, "ui_scale": ui, "trees": trees, "nearest_tree": nearest,
                          "cursor_target": list(target), "cursor_truth": kind, "axe_slot": axe_slot,
                          "player": p, "hostiles_on_screen": sum(1 for x in truth["hostiles"] if x["on_screen"])})
    finally:
        if game:
            game.close()
        stop_owned_game(pid, root / "tml")
    (root / "truth.json").write_text(json.dumps(shots, indent=2) + "\n")


QUESTION_A = ("This is a {w}x{h} screenshot of Terraria. Coordinates are screenshot pixels (x 0-{w1}, y 0-{h1}). Return JSON "
              "only: {{\"tree\": [x, y] = the base of the trunk of the tree nearest to the player character, or null if no "
              "tree is visible, \"axe_slot\": the hotbar slot number (1-10) that holds the axe, \"axe_slot_xy\": [x, y] = "
              "the centre of that hotbar slot}}.")
QUESTION_B = ("This is a {w}x{h} screenshot of Terraria. Return JSON only: {{\"under_cursor\": one of \"tree\", \"ground\" "
              "(dirt, grass, stone or another solid block), \"air\", \"water\", \"other\" = what is directly under the tip of "
              "the mouse cursor}}.")


def ask(out, models, usd):
    truth = [s for f in sorted(out.glob("*/truth.json")) for s in json.loads(f.read_text())]
    key, results, spent = gateway.load_key(), [], Decimal(0)
    for spec in models:
        model, reasoning = spec.split(":")
        for s in truth:
            w, h = s["window"]
            for which, question in (("A", QUESTION_A), ("B", QUESTION_B)):
                if spent > Decimal(str(usd)):
                    raise SystemExit(f"probe budget {usd} reached")
                content = [{"type": "text", "text": question.format(w=w, h=h, w1=w - 1, h1=h - 1)},
                           {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": jpeg(out / s[which])}}]
                row = {"model": model, "variant": s["variant"], "view": s["view"], "shot": which}
                try:
                    response = gateway_text(model, reasoning, "You answer questions about game screenshots.", content, key)
                    cost = Decimal(str(response["usage"]["cost"]))
                    spent += cost
                    text = response["choices"][0]["message"]["content"] or "{}"
                    body = json.loads(text[text.index("{"): text.rindex("}") + 1])
                    row.update(answer=body, usd=str(cost))
                except Exception as error:  # recorded, scored as wrong
                    row.update(error=f"{type(error).__name__}: {error}"[:300].replace(key, "[redacted]"))
                    body = {}
                if which == "A":
                    t, z = s["nearest_tree"], s["zoom"]
                    p = body.get("tree")
                    if t is None:
                        row["tree_ok"] = p is None
                    else:
                        row["tree_ok"] = isinstance(p, list) and len(p) == 2 and abs(p[0] - t["px"]) <= 24 * z \
                            and t["py"] - t["height_px"] - 8 <= p[1] <= t["py"] + 24 * z
                    row["tree_err_px"] = (abs(p[0] - t["px"]) if isinstance(p, list) and t else None)
                    row["axe_slot_ok"] = body.get("axe_slot") == s["axe_slot"]
                else:
                    row["cursor_ok"] = body.get("under_cursor") == s["cursor_truth"]
                    row["cursor_truth"] = s["cursor_truth"]
                results.append(row)
                print(json.dumps(row), flush=True)
    (out / "answers.json").write_text(json.dumps(results, indent=2) + "\n")
    table = {}
    for r in results:
        cell = table.setdefault(f'{r["variant"]}|{r["model"]}', {"tree_ok": 0, "tree_n": 0, "axe_ok": 0, "axe_n": 0,
                                                                  "cursor_ok": 0, "cursor_n": 0})
        if r["shot"] == "A":
            cell["tree_ok"] += bool(r["tree_ok"]); cell["tree_n"] += 1
            cell["axe_ok"] += bool(r["axe_slot_ok"]); cell["axe_n"] += 1
        else:
            cell["cursor_ok"] += bool(r["cursor_ok"]); cell["cursor_n"] += 1
    (out / "summary.json").write_text(json.dumps({"usd": str(spent), "cells": table}, indent=2) + "\n")
    print(json.dumps({"usd": str(spent), "cells": table}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("phase", choices=("capture", "ask"))
    p.add_argument("--fixture", type=Path)
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--variant", nargs="*", default=[], help="NAME=DISPLAY")
    p.add_argument("--models", nargs="*", default=[])
    p.add_argument("--usd", type=float, default=0.5)
    a = p.parse_args()
    if a.phase == "capture":
        a.out.mkdir(parents=True, exist_ok=True)
        threads = [threading.Thread(target=capture_variant, args=(n, d, a.fixture.resolve(), a.out.resolve()))
                   for n, d in (v.split("=") for v in a.variant)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    else:
        ask(a.out.resolve(), a.models, a.usd)


if __name__ == "__main__":
    main()
