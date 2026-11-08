"""Parallel job queue: one job per isolated display (tools/isolated_displays.py), spend-gated, with per-run video.

    python tools/parallel_queue.py --campaign runs/default-game-2026-11-08 --gateway-budget 25 --openrouter-budget 1

Jobs are ~/tb-queue/dg-jobs/*.sh, taken in name order by the first free slot. Header lines:
    # cap gateway=1.5 openrouter=0.2      spend ceiling of the job (its --usd caps)
    # run runs/default-game-2026-11-08/<name>
The job runs with TB_DISPLAY set to the slot's X display. A job starts only if
    campaign spend (tools/pilot_spend.py, incl. live accounting) + extra spend (~/tb-queue/dg-extra.json)
    + caps of running jobs + its own cap  <=  budget
for every provider; otherwise it moves to skipped/. While a job runs, its slot's headless output is recorded to
<run>/desktop.mp4. Afterwards: run_evidence, extended_score and clock_check. ~/tb-queue/dg-STOP ends the queue
after the running jobs (no new starts).
"""
import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Q = Path.home() / "tb-queue"
PY = str(ROOT / ".venv/bin/python")
sys.path.insert(0, str(ROOT / "tools"))
from pilot_spend import tally  # noqa: E402


def log(message):
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {message}"
    print(line, flush=True)
    with (Q / "dg-queue.log").open("a") as stream:
        stream.write(line + "\n")


def header(job):
    text = job.read_text()
    line = next((l for l in text.splitlines() if l.startswith("# cap ")), "")
    caps = {p: Decimal(m.group(1)) if (m := re.search(rf"\b{p}=([0-9.]+)", line)) else Decimal(0)
            for p in ("gateway", "openrouter")}
    run = re.search(r"^# run (\S+)", text, re.M)
    window = re.search(r"^# window (\d+x\d+)", text, re.M)
    return caps, ROOT / run.group(1) if run else None, window.group(1) if window else "1024x1024"


def spent(campaign):
    total = tally(campaign)
    extra = Q / "dg-extra.json"
    if extra.exists():
        for k, v in json.loads(extra.read_text()).items():
            total[k] += Decimal(str(v))
    return total


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--campaign", type=Path, required=True)
    p.add_argument("--gateway-budget", type=Decimal, required=True)
    p.add_argument("--openrouter-budget", type=Decimal, required=True)
    p.add_argument("--display-sets", nargs="+", default=["displays"],
                   help="state files ~/tb-queue/<name>.json from tools/isolated_displays.py")
    a = p.parse_args()
    campaign = (ROOT / a.campaign).resolve() if not a.campaign.is_absolute() else a.campaign
    budget = {"gateway": a.gateway_budget, "openrouter": a.openrouter_budget}
    slots = [{"geometry": "1024x1024", **s} for name in a.display_sets for s in json.loads((Q / f"{name}.json").read_text())]
    for d in ("dg-jobs", "dg-done", "dg-skipped", "dg-logs", "dg-running"):
        (Q / d).mkdir(exist_ok=True)
    running = {}  # slot index -> (job path, process, recorder, caps, run, started)
    log(f"queue started: {len(slots)} slots, budget {budget}")
    while True:
        for i, (job, proc, recorder, caps, run, t0) in list(running.items()):
            if proc.poll() is None:
                continue
            if recorder and recorder.poll() is None:
                recorder.send_signal(2)
                try:
                    recorder.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    recorder.kill()
            for tool in ("run_evidence.py", "extended_score.py", "clock_check.py"):
                subprocess.run([PY, str(ROOT / "tools" / tool), str(run)], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            job.rename(Q / "dg-done" / job.name)
            log(f"done {job.stem} slot {slots[i]['display']} exit={proc.returncode} "
                f"after {round((time.time() - t0) / 60, 1)} min (spent {json.dumps({k: str(v) for k, v in spent(campaign).items()})})")
            del running[i]
        stopping = (Q / "dg-STOP").exists()
        jobs = sorted((Q / "dg-jobs").glob("*.sh"))
        free = [i for i in range(len(slots)) if i not in running]
        # The first job (name order) that has a free slot of its window size.
        pick = next(((job, i) for job in jobs for i in free if slots[i]["geometry"] == header(job)[2]), None)
        if not stopping and pick:
            job, i = pick
            caps, run, _ = header(job)
            used = spent(campaign)
            reserved = {k: sum((r[3][k] for r in running.values()), Decimal(0)) for k in budget}
            if run is None or any(used[k] + reserved[k] + caps[k] > budget[k] for k in budget):
                if not running:  # nothing will free budget: skip
                    log(f"skip {job.stem}: spent {used} + running caps {reserved} + cap {caps} > {budget}")
                    job.rename(Q / "dg-skipped" / job.name)
                time.sleep(5)
                continue
            slot = slots[i]
            target = Q / "dg-running" / job.name
            job.rename(target)
            env = {**__import__("os").environ, "TB_DISPLAY": slot["display"]}
            proc = subprocess.Popen(["bash", str(target)], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                                    stdout=(Q / "dg-logs" / f"{job.stem}.log").open("w"), stderr=subprocess.STDOUT,
                                    start_new_session=True)
            recorder = None
            for _ in range(240):  # the run directory appears once the harness starts
                if run.exists() or proc.poll() is not None:
                    break
                time.sleep(.5)
            if run.exists():
                recorder = subprocess.Popen([PY, str(ROOT / "tools/record_desktop.py"), str(run / "desktop.mp4"), "--fps", "5",
                                             "--output-name", slot["output"], "--until-file", str(run / "result.json"),
                                             "--max-seconds", "14400"], cwd=ROOT, stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            running[i] = (target, proc, recorder, caps, run, time.time())
            log(f"start {job.stem} on {slot['display']}/{slot['output']} (spent {json.dumps({k: str(v) for k, v in used.items()})}, "
                f"running caps {json.dumps({k: str(v) for k, v in reserved.items()})}, cap {json.dumps({k: str(v) for k, v in caps.items()})})")
            continue
        if not running and (stopping or not jobs):
            if stopping:
                log("dg-STOP found and no job running; queue exits")
                return
        time.sleep(5)


if __name__ == "__main__":
    main()
