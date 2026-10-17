"""Freeze and supervise paired v4/v7 learning and a v7 reward/discount factorial.

No reserved evaluation, automatic retries, warm starts or default promotion.
Prepare and seal are distinct so all preflight checks finish before freezing.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import statistics as st
import subprocess
import sys
import time

STEPS = 16_777_216
INTERVAL = 4_194_304
SEEDS = list(range(801, 806))
CELLS = {
    "v4-equal-g999": {"version": "v4", "reward": "equal", "gamma": .999},
    "v7-equal-g999": {"version": "v7", "reward": "equal", "gamma": .999},
    "v7-equal-g1": {"version": "v7", "reward": "equal", "gamma": 1.0},
    "v7-difficulty-g999": {"version": "v7", "reward": "difficulty", "gamma": .999},
    "v7-difficulty-g1": {"version": "v7", "reward": "difficulty", "gamma": 1.0},
}


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def read(p):
    return json.loads(Path(p).read_text())


def write(p, obj, exclusive=False):
    p = Path(p)
    if exclusive:
        with p.open("x") as f:
            json.dump(obj, f, indent=2, allow_nan=False)
            f.write("\n")
    else:
        temporary = p.with_suffix(p.suffix + ".tmp")
        with temporary.open("w") as f:
            json.dump(obj, f, indent=2, allow_nan=False)
            f.write("\n")
        temporary.replace(p)


def manifest(root):
    files = [root / "Makefile", root / "terraria-px"]
    for folder in ("include", "src", "python/terraria_lite", "tools", "third_party"):
        files += [p for p in (root / folder).rglob("*")
                  if p.is_file() and p.suffix in (".py", ".c", ".h", ".dylib", ".so")]
    return {str(p.relative_to(root)): sha(p) for p in sorted(files)}


def environment(study, version):
    v = study / "variants" / version
    return {**os.environ, "PYTHONPATH": str(v / "python"),
            "TERRARIA_LITE_LIB": str(v / "python/terraria_lite/libterraria.dylib"),
            "PYTHONUNBUFFERED": "1"}


def command(study, cell, seed, *, steps=STEPS, interval=INTERVAL, preflight=False):
    c = CELLS[cell]
    version = c["version"]
    dest = study / ("preflight" if preflight else "runs") / f"{cell}-{seed}"
    return [sys.executable, str(study / "variants" / version / "tools/iterate_ppo.py"),
            "--out", str(dest), "--steps", str(steps), "--seed", str(seed),
            "--envs", "64", "--rollout", "128", "--threads", "4",
            "--architecture", "targets", "--entropy", ".03", "--gae-lambda", ".99",
            "--gamma", str(c["gamma"]), "--achievement-reward", c["reward"],
            "--interval", str(interval), "--validation-seed-start", "21000001" if preflight else "17000001",
            "--validation-episodes", "4" if preflight else "128",
            "--test-seed-start", "19000001", "--device", "cpu"]


def prepare(study):
    repo = Path(__file__).resolve().parents[1]
    if study.parent != repo / "experiments" or any(study.iterdir()):
        raise ValueError("Prepare requires an empty directory directly in repo/experiments")
    prefix = "V7_REWARD_STUDY_2026_10_17"
    if any((repo / (prefix + suffix)).exists() for suffix in (".md", ".json")):
        raise FileExistsError("Report targets already exist; do not replace a prior study")
    source = Path(__file__).resolve()
    shutil.copy2(source, study / "supervisor.py")
    for version in ("v4", "v7"):
        dest = study / "variants" / version
        for folder in ("include", "src", "python", "tools", "third_party"):
            shutil.copytree(repo / folder, dest / folder,
                            ignore=shutil.ignore_patterns("*.o", "*.d", "*.dylib", "*.so", "__pycache__"))
        shutil.copy2(repo / "Makefile", dest / "Makefile")
        if version == "v7":
            relative = str(dest.relative_to(repo))
            subprocess.run(["git", "apply", "--check", "--directory=" + relative,
                            str(repo / "CORE_V7.patch")], cwd=repo, check=True)
            subprocess.run(["git", "apply", "--directory=" + relative,
                            str(repo / "CORE_V7.patch")], cwd=repo, check=True)
        with (study / f"build-{version}.log").open("x") as log:
            subprocess.run(["make", "-j4", "all", "lib", "terraria-px", "check", "check-pixel"],
                           cwd=dest, stdout=log, stderr=subprocess.STDOUT, check=True)
            subprocess.run(["cc", "-std=c11", "-O2", "-shared", "-fPIC", "-Iinclude", "-Isrc",
                            "tools/crafting_probe.c", "src/sim.c", "src/worldgen.c", "src/light.c", "src/obs.c",
                            "-lm", "-o", str(study / f"probe-{version}.dylib")],
                           cwd=dest, stdout=log, stderr=subprocess.STDOUT, check=True)
    old = repo / "experiments/core-next-20261012.DAW09u/v7"
    core_files = [p.relative_to(old) for folder in ("include", "src")
                  for p in (old / folder).iterdir() if p.suffix in (".c", ".h")]
    assert all(sha(old / p) == sha(study / "variants/v7" / p) for p in core_files)
    # Rotate cell order across seed blocks rather than running each condition on one date.
    keys = list(CELLS)
    jobs = [(cell, seed) for i, seed in enumerate(SEEDS)
            for cell in keys[i:] + keys[:i]]
    from terraria_lite.achievement_rewards import reward_spec
    setup = {"repository": str(repo), "study": str(study), "report_prefix": prefix,
             "date": "2026-10-17", "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
             "preparation_worktree_status": subprocess.check_output(["git", "status", "--short"], cwd=repo, text=True),
             "cells": CELLS, "training_seeds": SEEDS, "jobs": jobs,
             "steps_per_run": STEPS, "main_transitions": STEPS * len(jobs),
             "workers": 3, "threads_per_worker": 4, "architecture": "targets128",
             "ppo": {"envs": 64, "rollout": 128, "epochs": 4, "minibatches": 4,
                     "gae_lambda": .99, "entropy": .03, "lr": .0003, "anneal_lr": True,
                     "deadline_future_value": "zero; finite 3000-action task"},
             "checkpoint_steps": list(range(INTERVAL, STEPS + 1, INTERVAL)),
             "validation_seeds": [17000001, 17000128], "sampler_seed": 54321,
             "reserved_test_seeds": [19000001, 19000128],
             "test_rule": "Never consumed by this study; no selection, automatic promotion or extra test evaluation",
             "preflight_seeds": [21000001, 21000004], "reward_schemes": {k: reward_spec(k) for k in ("equal", "difficulty")},
             "comparisons": ["v7_equal_minus_v4", "discount_main_effect", "weight_main_effect", "interaction"],
             "analysis": "Final 16M paired training-seed contrasts. Report descriptive 95% paired-t intervals and Bonferroni 98.75% intervals for four primary score contrasts. Five seeds are small; no checkpoint pseudoreplication. Rates and curves are secondary/descriptive. V4/v7 is a bundled environment contrast, not an isolated direct-selection effect.",
             "scope": "Fresh initialized spatial PPO only; fixed C gameplay, original observations/legal masks, unweighted evaluation, no expert data, prerequisite shaping, strategic masks, novelty, recipe controller, API spending, cluster or PufferLib migration. Difficulty weighting is an explicit subjective sparse training-objective intervention.",
             "v7_core_matches_previous_preview": {str(p): sha(old / p) for p in core_files}}
    write(study / "study-setup.json", setup, exclusive=True)
    print(json.dumps({"study": str(study), "main_transitions": setup["main_transitions"], "jobs": jobs}, indent=2))


def seal(study):
    if (study / "started.json").exists():
        raise ValueError("Study already started")
    setup = read(study / "study-setup.json")
    # Exactly one two-update smoke/calibration per condition, disjoint from validation.
    preflight = {}
    for i, cell in enumerate(CELLS):
        d = study / "preflight" / f"{cell}-{901 + i}"
        summary, p = read(d / "summary.json"), read(d / "protocol.json")
        assert summary["steps"] == p["actual_steps"] == 16384
        assert len(read(d / "curve.json")) == 2
        assert p["validation_seeds"] == setup["preflight_seeds"]
        assert p["config"]["achievement_reward"] == CELLS[cell]["reward"]
        assert p["config"]["gamma"] == CELLS[cell]["gamma"]
        preflight[cell] = {"summary": summary, "summary_sha256": sha(d / "summary.json")}
    setup.update({"supervisor_sha256": sha(study / "supervisor.py"),
                  "implementation_sha256": {v: manifest(study / "variants" / v) for v in ("v4", "v7")},
                  "probe_sha256": {v: sha(study / f"probe-{v}.dylib") for v in ("v4", "v7")},
                  "preflight": preflight, "calibration_transitions_excluded": 81920,
                  "sealed_utc": dt.datetime.now(dt.timezone.utc).isoformat()})
    write(study / "study-protocol.json", setup, exclusive=True)
    print("Sealed 25 fresh 16M trials; 419,430,400 main transitions; no reserved tests")


def verify_sources(study, protocol):
    assert sha(study / "supervisor.py") == protocol["supervisor_sha256"]
    for version, expected in protocol["implementation_sha256"].items():
        assert manifest(study / "variants" / version) == expected, f"Frozen sources changed: {version}"
        assert sha(study / f"probe-{version}.dylib") == protocol["probe_sha256"][version]


def interval(values, probability=.975):
    assert len(values) == 5
    # For t(df=4), CDF(t)=.5+.75*x-.25*x^3, x=t/sqrt(t*t+4).
    low, high = 0.0, 100.0
    for _ in range(100):
        t = (low + high) / 2
        x = t / math.sqrt(t*t + 4)
        if .5 + .75*x - .25*x**3 < probability:
            low = t
        else:
            high = t
    mean = st.mean(values)
    half = ((low + high) / 2) * st.stdev(values) / math.sqrt(5)
    return {"per_seed": values, "mean": mean, "interval": [mean-half, mean+half]}


def contrasts(values):
    a, b, c, d, e = (values[key] for key in CELLS)
    return {"v7_equal_minus_v4": b-a, "discount_main_effect": ((c-b)+(e-d))/2,
            "weight_main_effect": ((d-b)+(e-c))/2, "interaction": (e-d)-(c-b)}


def report(study, protocol):
    verify_sources(study, protocol)
    rows = []
    for cell, seed in protocol["jobs"]:
        d = study / "runs" / f"{cell}-{seed}"
        summary, p, curve, crafting = (read(d / f) for f in ("summary.json", "protocol.json", "curve.json", "crafting.json"))
        cfg, expected = p["config"], CELLS[cell]
        assert summary["steps"] == p["actual_steps"] == STEPS
        assert [z["steps"] for z in curve] == protocol["checkpoint_steps"]
        assert cfg["seed"] == seed and cfg["gamma"] == expected["gamma"] and cfg["achievement_reward"] == expected["reward"]
        assert cfg["architecture"] == "targets" and cfg["gae_lambda"] == .99 and cfg["ent_coef"] == .03
        assert not cfg["init"] and not cfg["progress_coef"] and not cfg["curiosity_coef"] and not cfg["bootstrap_time_limit"]
        assert p["reward"] == protocol["reward_schemes"][expected["reward"]]
        for filename, digest in p["implementation_sha256"].items():
            assert sha(d / "implementation" / filename) == digest
            assert sha(study / "variants" / expected["version"] / "python/terraria_lite" / filename) == digest
        for point in curve:
            ev = point["evaluation"]
            assert sorted(z["seed"] for z in ev["records"]) == list(range(17000001, 17000129))
            assert st.mean(z["achievements"] for z in ev["records"]) == ev["mean_achievements"]
        evaluation = curve[-1]["evaluation"]
        assert crafting["mean_achievements"] == evaluation["mean_achievements"]
        assert crafting["checkpoint_sha256"] == sha(d / f"step-{STEPS}.pt")
        assert crafting["probe_sha256"] == protocol["probe_sha256"][expected["version"]]
        assert crafting["seed_range"] == protocol["validation_seeds"]
        assert crafting["episodes"] == 128
        rows.append({"cell": cell, "seed": seed, "summary": summary, "curve": curve,
                     "crafting": crafting, "artifact_sha256": {f.name: sha(f) for f in [d / "summary.json", d / "protocol.json", d / "curve.json", d / "crafting.json", *sorted(d.glob("step-*.pt"))]}})
    assert len(rows) == 25 and sum(r["summary"]["steps"] for r in rows) == protocol["main_transitions"]
    assert not list(study.rglob("*.claim.json")), "Reserved evaluation claim unexpectedly exists"
    by_key = {(r["cell"], r["seed"]): r["curve"][-1]["evaluation"] for r in rows}
    comparisons = {}
    for metric, getter in {"score": lambda e: e["mean_achievements"], "death_rate": lambda e: e["death_rate"],
                           "furnace_rate": lambda e: e["hits"].get("craft furnace", 0)/128,
                           "anvil_rate": lambda e: e["hits"].get("craft anvil", 0)/128}.items():
        seed_contrasts = [contrasts({cell: getter(by_key[cell, seed]) for cell in CELLS}) for seed in SEEDS]
        comparisons[metric] = {name: {"descriptive_95": interval([r[name] for r in seed_contrasts]),
                                    **({"four_contrast_familywise_95": interval([r[name] for r in seed_contrasts], .99375)} if metric == "score" else {})}
                               for name in protocol["comparisons"]}
    result = {"complete": True, "protocol": protocol, "main_transitions": protocol["main_transitions"],
              "reserved_tests_consumed": False, "runs": rows, "paired_contrasts": comparisons}
    write(study / "results.json", result, exclusive=True)
    lines = ["# V7 progression and reward/discount study — 2026-10-17", "", "Status: complete and artifact-audited.", "",
             "25 fresh 16M-ending trials; **419,430,400 main transitions**, five paired training seeds. All headline evaluations retain unweighted achievement counts and native death penalties. No reserved tests or default promotions.", "",
             "| Cell | Mean /32 ± sample SD | Per-seed scores | Bench / furnace / anvil worlds /640 | Death |", "| --- | --- | --- | --- | --- |"]
    for cell in CELLS:
        es = [by_key[cell, s] for s in SEEDS]
        scores = [e["mean_achievements"] for e in es]
        hits = [sum(e["hits"].get(name, 0) for e in es) for name in ("craft workbench", "craft furnace", "craft anvil")]
        lines.append(f"| {cell} | {st.mean(scores):.3f} ± {st.stdev(scores):.3f} | {', '.join(f'{x:.3f}' for x in scores)} | {' / '.join(map(str,hits))} | {st.mean(e['death_rate'] for e in es):.1%} |")
    lines += ["", "## Prespecified score contrasts", "", "| Contrast | Paired mean | Descriptive 95% | Four-contrast familywise 95% |", "| --- | --- | --- | --- |"]
    for name, bounds in comparisons["score"].items():
        a, b = bounds["descriptive_95"], bounds["four_contrast_familywise_95"]
        lines.append(f"| {name} | {a['mean']:+.3f} | [{a['interval'][0]:+.3f}, {a['interval'][1]:+.3f}] | [{b['interval'][0]:+.3f}, {b['interval'][1]:+.3f}] |")
    lines += ["", "Five training seeds—not 640 independent learners or four independent checkpoints. Curves, deaths, per-achievement outcomes and full joint crafting-prerequisite/resource-sink diagnostics are in the numeric report. Intervals crossing zero are inconclusive, not equivalence. V4/v7 compares bundled game versions. Difficulty tiers are subjective and maximum-total-normalized, not a proven optimal objective or a replica of Craftax's health/difficulty rewards.", "",
              "Training is fresh with an unchanged 16M LR schedule, masks and observations. Tests 19,000,001–19,000,128 remain unused. Historical consumed splits were not evaluated. Existing v4 default, old studies, interrupted checkpoints and v5–v7 previews are preserved.", "", f"Study artifacts: `{study}`."]
    repo = Path(protocol["repository"])
    write(repo / (protocol["report_prefix"] + ".json"), result, exclusive=True)
    with (repo / (protocol["report_prefix"] + ".md")).open("x") as f:
        f.write("\n".join(lines) + "\n")
    return str(repo / (protocol["report_prefix"] + ".md"))


def run(study):
    protocol = read(study / "study-protocol.json")
    verify_sources(study, protocol)
    write(study / "started.json", {"pid": os.getpid(), "started_utc": time.time(),
                                  "protocol_sha256": sha(study / "study-protocol.json")}, exclusive=True)
    pending = list(protocol["jobs"])
    active, completed = {}, []
    (study / "logs").mkdir(exist_ok=True)
    inhibitor = subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])

    def status(stage, **extra):
        write(study / "status.json", {"stage": stage, "runner_pid": os.getpid(), "updated_utc": time.time(),
                                     "active": {name: p.pid for name, (p, _) in active.items()},
                                     "completed": completed, "pending": pending, **extra})

    try:
        while pending or active:
            while pending and len(active) < protocol["workers"]:
                cell, seed = pending.pop(0)
                name = f"{cell}-{seed}"
                if (study / "runs" / name).exists():
                    raise FileExistsError(f"Fresh trial required: {name}; do not retry automatically")
                log = (study / "logs" / (name + ".log")).open("x")
                process = subprocess.Popen(command(study, cell, seed), cwd=study / "variants" / CELLS[cell]["version"],
                                           env=environment(study, CELLS[cell]["version"]), stdout=log, stderr=subprocess.STDOUT)
                active[name] = process, log
                print("Started", name, process.pid, flush=True)
            for name, (process, log) in list(active.items()):
                code = process.poll()
                if code is None:
                    continue
                log.close()
                del active[name]
                if code:
                    raise RuntimeError(f"{name} failed rc={code}; all artifacts preserved")
                assert read(study / "runs" / name / "summary.json")["steps"] == STEPS
                completed.append(name)
                print("Completed", name, flush=True)
            status("training")
            time.sleep(3)
        status("diagnostics")
        for cell, seed in protocol["jobs"]:
            version, name = CELLS[cell]["version"], f"{cell}-{seed}"
            dest = study / "runs" / name
            cmd = [sys.executable, str(study / "variants" / version / "tools/crafting_diagnostics.py"),
                   str(dest / f"step-{STEPS}.pt"), "--probe", str(study / f"probe-{version}.dylib"),
                   "--out", str(dest / "crafting.json"), "--episodes", "128", "--seed-start", "17000001"]
            log = (study / "logs" / ("crafting-" + name + ".log")).open("x")
            process = subprocess.Popen(cmd, cwd=study / "variants" / version, env=environment(study, version),
                                       stdout=log, stderr=subprocess.STDOUT)
            active["crafting-" + name] = process, log
            status("diagnostics", latest_diagnostic=name)
            code = process.wait()
            log.close()
            del active["crafting-" + name]
            if code:
                raise RuntimeError(f"Crafting diagnostic failed: {name} rc={code}")
            status("diagnostics", latest_diagnostic=name)
        status("reporting")
        completed_report = report(study, protocol)
        status("complete", report=completed_report)
        print("Complete", completed_report, flush=True)
    except BaseException as error:
        status("failed", error=repr(error))
        raise
    finally:
        for process, log in active.values():
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            log.close()
        if inhibitor.poll() is None:
            inhibitor.terminate()
            inhibitor.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", type=Path, required=True)
    parser.add_argument("--mode", choices=("prepare", "seal", "run"), required=True)
    args = parser.parse_args()
    {"prepare": prepare, "seal": seal, "run": run}[args.mode](args.study.resolve())


if __name__ == "__main__":
    main()
