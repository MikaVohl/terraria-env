"""TerraBot harness entry points (Omarchy).

    # in-game API tests (test mode: truth ops for ground truth; never a scored run)
    python tools/terrabot/run.py live-test --fixture runs/terrabot-fixtures/tb-41100101 --run runs/terrabot-live-01
    # unpaid scripted proof: run the programs of a directory in order, each in the sandbox
    python tools/terrabot/run.py scripted --fixture ... --run runs/terrabot-proof-01 --programs tools/terrabot/proof

Every program file may start with `# timeout: <seconds>` (default 60). The directory's `lib/` is copied into the
run's workspace (the scripted agent's own helper library, written against the public tb API only).
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
from session import Session  # noqa: E402
import sandbox  # noqa: E402
from audit import audit  # noqa: E402

TB_SRC = ROOT / "terrariabench/tb"


def timeout_of(code, default=60.0):
    first = code.lstrip().splitlines()[0] if code.strip() else ""
    if first.startswith("# timeout:"):
        return float(first.split(":", 1)[1])
    return default


def run_in_session(session, code, name, workspace, timeout, log):
    session.proxy.program, session.proxy.workspace = name, str(workspace)
    t0 = time.time()
    # Programs see only a frozen copy of the tb package (not the rest of terrariabench/).
    tb_dir = session.run / "tblib"
    if not (tb_dir / "tb").exists():
        shutil.copytree(TB_SRC, tb_dir / "tb", ignore=shutil.ignore_patterns("__pycache__", "*.md"))
    res = sandbox.run_program(code, workspace=workspace, socket_path=str(session.proxy.path), tb_dir=tb_dir,
                              timeout=timeout, name=name)
    session.proxy.program = "harness"
    res.update(started_unix=t0, ended_unix=time.time())
    with (session.run / "programs.jsonl").open("a") as f:
        f.write(json.dumps(res) + "\n")
    log(f"program {name}: {res['exit']} in {res['seconds']:.1f}s")
    return res


def live_test(a):
    s = Session(a.run, a.fixture, display=a.display, test_mode=True, record=False,
                manifest={"agent_kind": "test", "purpose": "live API tests"}).start()
    try:
        env = {**os.environ, "TB_SOCKET": str(s.proxy.path)}
        s.proxy.program = "live_tests"
        subprocess.run([sys.executable, str(HERE / "live_tests.py"), str(s.run)], env=env, check=False, timeout=900)
        if a.extra:
            for script in a.extra:
                s.proxy.program = Path(script).stem
                subprocess.run([sys.executable, script, str(s.run)], env=env, check=False, timeout=1800)
    finally:
        s.stop({"kind": "live-test"})


def scripted(a):
    progs = sorted(p for p in Path(a.programs).glob("*.py"))
    s = Session(a.run, a.fixture, display=a.display, record=not a.no_record,
                manifest={"agent_kind": "scripted", "programs_dir": str(a.programs), "helped_by":
                          "human-written scripted programs (proof that the public API suffices); no LLM"}).start()
    s.proxy.agent_kind = "scripted"
    ws = s.run / "workspace"
    ws.mkdir()
    if (Path(a.programs) / "lib").exists():
        shutil.copytree(Path(a.programs) / "lib", ws / "lib")
    results, t0 = [], time.time()
    try:
        for p in progs:
            code = p.read_text()
            res = run_in_session(s, code, p.stem, ws, timeout_of(code), s.log)
            results.append({k: res[k] for k in ("name", "exit", "seconds")} | {"tail": res["stdout"][-600:]})
            if res["exit"] != "ok" and not a.keep_going:
                break
    finally:
        s.stop({"kind": "scripted", "programs": results, "wall_seconds": time.time() - t0})
        print(json.dumps(audit(s.run)))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("live-test", "scripted"):
        q = sub.add_parser(name)
        q.add_argument("--fixture", required=True)
        q.add_argument("--run", required=True)
        q.add_argument("--display", default=":15")
        if name == "live-test":
            q.add_argument("--extra", nargs="*", help="more test scripts run with TB_SOCKET set")
        else:
            q.add_argument("--programs", required=True)
            q.add_argument("--keep-going", action="store_true")
            q.add_argument("--no-record", action="store_true")
    a = p.parse_args()
    {"live-test": live_test, "scripted": scripted}[a.cmd](a)


if __name__ == "__main__":
    main()
