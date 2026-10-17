"""Frozen five-seed deadline/credit/memory/novelty study on unchanged v4.

Prepare once, run preflight and calibration before main trials, then finalize
automatically with a single reserved test. Incomplete runs are never silently
restarted. All jobs and all model selection use the written protocol.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import statistics
import subprocess
import sys
import time


SEEDS = [101, 202, 303, 404, 405]
SCREEN = 4_194_304
SCALE = 16_777_216
METHODS = {
    "legacy_mlp": {"architecture":"mlp", "gae_lambda":.95, "entropy":.01, "bootstrap_time_limit":True},
    "finite_mlp": {"architecture":"mlp", "gae_lambda":.95, "entropy":.01},
    "legacy_targets": {"architecture":"targets", "gae_lambda":.99, "entropy":.03, "bootstrap_time_limit":True},
    "finite_targets": {"architecture":"targets", "gae_lambda":.99, "entropy":.03},
    "undiscounted": {"architecture":"targets", "gae_lambda":.99, "entropy":.03, "gamma":1.0},
    "trace": {"architecture":"targets", "gae_lambda":.995, "entropy":.03},
    "long_rollout": {"architecture":"targets", "gae_lambda":.99, "entropy":.03, "rollout":512, "minibatches":16},
    "memory": {"architecture":"lstm_targets", "gae_lambda":.99, "entropy":.03},
    "novelty": {"architecture":"targets", "gae_lambda":.99, "entropy":.03, "curiosity":.001,
                "balanced_curiosity":True, "persistent_curiosity":True},
}
ALTERNATIVES = ["finite_mlp", "undiscounted", "trace", "long_rollout", "memory", "novelty"]


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    path.write_text(json.dumps(value, indent=2)+"\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hashes(root):
    return {str(f.relative_to(root)):sha(f)
            for folder in ("include", "src", "python/terraria_lite", "tools")
            for f in (root/folder).iterdir()
            if f.suffix in (".c", ".h", ".py", ".dylib", ".so")}


def environment(frozen):
    env=os.environ.copy();env["PYTHONPATH"]=str(frozen/"python");env["PYTHONUNBUFFERED"]="1"
    env.pop("TERRARIA_LITE_LIB", None)
    return env


def prepare(study, root):
    if (study/"production").exists():raise ValueError("Snapshot already exists")
    frozen=study/"production";frozen.mkdir()
    for folder in ("include", "src", "python", "tools", "third_party"):
        shutil.copytree(root/folder, frozen/folder)
    shutil.copy2(root/"Makefile", frozen/"Makefile")
    for binary in ("terraria-lite", "terraria-px"):
        shutil.copy2(root/binary, frozen/binary)
    previous=root/"experiments/learning-v4-20261010.GWpaf4/study-protocol.json"
    old=read(previous)["implementation_sha256"]
    physical={name:digest for name,digest in old.items() if name.startswith(("src/", "include/"))}
    assert all(sha(frozen/name)==digest for name,digest in physical.items()),"Game changed since previous study"
    protocol={"date":"2026-10-11", "environment_version":4, "training_seeds":SEEDS,
        "validation_seeds":[8_000_001,8_000_128], "reserved_test_seeds":[9_000_001,9_000_128], "sampler_seed":54321,
        "methods":METHODS, "screen_steps":SCREEN, "scale_steps":SCALE,
        "scale_control":"finite_targets", "scale_alternatives":ALTERNATIVES,
        "scaling_criterion":"Highest five-seed FINAL screen mean among alternatives; ties lower deaths then name; restart control and alternative from scratch at 16M",
        "test_criterion":"Highest validation mean across all corrected-objective main checkpoints; ties lower deaths, fewer steps, run name. Legacy controls excluded. Test once after all trials finish.",
        "main_transitions":len(METHODS)*len(SEEDS)*SCREEN+2*len(SEEDS)*SCALE,
        "calibration_transitions":len(METHODS)*32_768,
        "common":{"envs":64, "rollout":128, "minibatches":4, "epochs":4, "lr":.0003,
                  "anneal_lr":True, "gamma":.999, "threads":6, "device":"cpu", "workers":3},
        "changes_from_control":{
            "undiscounted":"discount only", "trace":"GAE lambda only",
            "long_rollout":"512-step fragments and 16 minibatches keep 2048 samples/minibatch; batch/refresh cadence also changes",
            "memory":"residual LSTM global memory on the same target encoder/scorer; extra parameters, sequence minibatches and recurrent dynamics also change",
            "novelty":"generic balanced RND, coefficient .001, not annealed; bonus capped .005/action; extrinsic evaluation unchanged"},
        "reward":"new achievement +1; death -1", "legal_masks_only":True, "demonstrations":False,
        "prerequisite_shaping":False,"strategic_masks":False,"gameplay_changed":False,
        "physical_source_sha256_matching_previous_study":physical,
        "implementation_sha256":hashes(frozen),
        "note":"Five paired training seeds are exploratory. Equal transitions are not equal compute. Old consumed splits are not used for selection/test. No default checkpoint promotion."}
    write(study/"study-protocol.json", protocol)
    print(json.dumps({"study":str(study), "main_transitions":protocol["main_transitions"], "methods":list(METHODS)},indent=2))


def method_args(cfg):
    args=[]
    for name,value in cfg.items():
        flag="--"+name.replace("_", "-")
        if isinstance(value,bool):
            if value:args.append(flag)
        else:args.extend([flag,str(value)])
    return args


def verify_run(directory, protocol, steps, calibration=False):
    row=read(directory/"protocol.json");summary=read(directory/"summary.json")
    assert row["environment_version"]==protocol["environment_version"]
    assert summary["steps"]==row["actual_steps"]==steps
    assert row["validation_seeds"]==([8_000_001,8_000_004] if calibration else protocol["validation_seeds"])
    assert row["reserved_test_seeds"]==protocol["reserved_test_seeds"]
    assert read(directory/"curve.json")[-1]["steps"]==steps
    frozen=Path(row["package"])
    assert all(sha(frozen/name)==digest for name,digest in row["implementation_sha256"].items())


def run(study, root):
    protocol=read(study/"study-protocol.json");frozen=study/"production"
    assert hashes(frozen)==protocol["implementation_sha256"],"Frozen implementation changed"
    python=os.path.abspath(sys.executable);env=environment(frozen);logs=study/"logs";logs.mkdir(exist_ok=True)
    active={};stage="preflight"

    def status(**extra):
        write(study/"status.json", {"stage":stage, "runner_pid":os.getpid(),
            "active":{n:item[0].pid for n,item in active.items()}, "updated_utc":time.time(), **extra})

    def interrupted(signum,frame):raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)

    def command(args, logname):
        with (logs/logname).open("w") as log:
            subprocess.run(args,cwd=frozen,env=env,stdout=log,stderr=subprocess.STDOUT,check=True)

    def pool(stage_name,jobs,calibration=False):
        nonlocal stage
        stage=stage_name;pending=[];completed=[]
        (study/stage).mkdir(exist_ok=True)
        for method,seed,steps in jobs:
            name=f"{method}-{seed}";dest=study/stage/name
            if (dest/"summary.json").exists():
                verify_run(dest,protocol,steps,calibration);completed.append(name);continue
            if dest.exists():raise ValueError(f"Incomplete run preserved at {dest}; requires explicit recovery")
            pending.append((name,method,seed,steps,dest))
        while pending or active:
            while pending and len(active)<protocol["common"]["workers"]:
                name,method,seed,steps,dest=pending.pop(0)
                log=logs/f"{stage}-{name}.log";handle=log.open("w")
                cmd=[python,str(frozen/"tools/iterate_ppo.py"),"--out",str(dest),"--steps",str(steps),
                     "--seed",str(seed),"--threads","6","--envs","64",
                     "--validation-seed-start","8000001","--test-seed-start","9000001",
                     "--validation-episodes","4" if calibration else "128",
                     "--interval",str(steps if calibration else SCREEN),*method_args(protocol["methods"][method])]
                process=subprocess.Popen(cmd,cwd=frozen,env=env,stdout=handle,stderr=subprocess.STDOUT)
                active[name]=(process,handle,log,dest,steps)
                print(f"Started {stage}/{name}, PID {process.pid}",flush=True)
            for name,(process,handle,log,dest,steps) in list(active.items()):
                code=process.poll()
                if code is not None:
                    handle.close();del active[name]
                    if code!=0:raise RuntimeError(f"{stage}/{name} exited {code}; see {log}")
                    verify_run(dest,protocol,steps,calibration);completed.append(name)
                    print(f"Completed {stage}/{name}",flush=True)
            status(pending=[j[0] for j in pending],completed=completed)
            if active or pending:time.sleep(2)

    try:
        status()
        if not (study/"preflight.json").exists():
            command([python,"-m","terraria_lite.ppo_selftest"],"ppo-selftest.log")
            command(["make","check","check-pixel"],"mechanics-pixel.log")
            write(study/"preflight.json", {"passed":True,"finite_deadline_and_unfinished_rollout_targets":True,
                "scalar_native_transitions":64000,"workers":[1,2,4,8], "recurrent_targets_step_sequence_reset_gradients_reload":True,
                "mechanics_light_pixel":True,"implementation_sha256":protocol["implementation_sha256"]})
        pool("calibration",[(method,77,32768) for method in protocol["methods"]],True)
        # Each lane sees at most 512 actions in these pilots, below the inherent
        # 3000-action deadline. Toggle-only pairs must therefore be identical.
        # This checks that the control option does not perturb initialization,
        # world sampling, masks or the optimizer before its intended intervention.
        import torch
        for architecture in ("mlp","targets"):
            legacy=torch.load(study/f"calibration/legacy_{architecture}-77/step-32768.pt",weights_only=True)["model"]
            finite=torch.load(study/f"calibration/finite_{architecture}-77/step-32768.pt",weights_only=True)["model"]
            assert legacy.keys()==finite.keys()
            assert all(torch.equal(legacy[name],finite[name]) for name in legacy),architecture
        write(study/"paired-predeadline-parity.json", {"exact":True,"transitions_per_run":32768,
            "max_actions_per_lane":512,"architectures":["mlp","targets"],"all_checkpoint_tensors_equal":True})
        if not (study/"memory-replay-verification.json").exists():
            tape=study/"memory-smoke.tape";checkpoint=study/"calibration/memory-77/step-32768.pt"
            command([python,"-m","terraria_lite.watch","--policy",str(checkpoint),"--seed","9","--out",str(tape)],"memory-replay.log")
            command([python,str(frozen/"tools/verify_replay.py"),str(tape),"--viewer",str(frozen/"terraria-px"),
                     "--checkpoint",str(checkpoint),"--out",str(study/"memory-replay-verification.json")],"memory-replay-verify.log")
        # Seed-major order interleaves methods so hardware drift is not wholly
        # confounded with method. Paired seeds share the world-seed generator.
        pool("screen",[(method,seed,protocol["screen_steps"]) for seed in protocol["training_seeds"] for method in protocol["methods"]])
        ranking=[]
        for method in protocol["scale_alternatives"]:
            evaluations=[read(study/"screen"/f"{method}-{seed}"/"curve.json")[-1]["evaluation"] for seed in protocol["training_seeds"]]
            ranking.append({"method":method,"mean":statistics.mean(e["mean_achievements"] for e in evaluations),
                            "death_rate":statistics.mean(e["death_rate"] for e in evaluations)})
        ranking.sort(key=lambda r:(-r["mean"],r["death_rate"],r["method"]))
        selection={"winner":ranking[0]["method"],"candidates":ranking,"criterion":protocol["scaling_criterion"]}
        if (study/"scaling-selection.json").exists():assert read(study/"scaling-selection.json")==selection
        else:write(study/"scaling-selection.json",selection)
        pool("scale",[(method,seed,protocol["scale_steps"]) for seed in protocol["training_seeds"]
                      for method in (protocol["scale_control"],selection["winner"])])
        stage="finalizing";status()
        eligible=[f"screen/{method}-{seed}" for seed in protocol["training_seeds"] for method,cfg in protocol["methods"].items()
                  if not cfg.get("bootstrap_time_limit",False)]
        eligible.extend(f"scale/{method}-{seed}" for seed in protocol["training_seeds"]
                        for method in (protocol["scale_control"],selection["winner"]))
        if not (study/"selected/test.json").exists():
            # If selection exists without test, never consume/reconsume the split
            # silently; select_policy's fresh-directory guard stops this case.
            command([python,str(frozen/"tools/select_policy.py"),"--study",str(study),"--out",str(study/"selected"),"--runs",*eligible],"reserved-test.log")
        if not (study/"selected-policy-diagnostics.json").exists():
            command([python,str(frozen/"tools/policy_diagnostics.py"),str(study/"selected/model.pt"),"--seed-start","8000001",
                     "--out",str(study/"selected-policy-diagnostics.json")],"selected-diagnostics.log")
        if not (study/"selected-deadline-audit.json").exists():
            command([python,str(frozen/"tools/audit_deadline.py"),str(study/"selected/model.pt"),"--seed-start","8000001",
                     "--out",str(study/"selected-deadline-audit.json")],"selected-deadline.log")
        if not (study/"selected-replay-verification.json").exists():
            command([python,"-m","terraria_lite.watch","--policy",str(study/"selected/model.pt"),"--seed","9",
                     "--out",str(study/"selected-seed9.tape")],"selected-replay.log")
            command([python,str(frozen/"tools/verify_replay.py"),str(study/"selected-seed9.tape"),"--viewer",str(frozen/"terraria-px"),
                     "--checkpoint",str(study/"selected/model.pt"),"--out",str(study/"selected-replay-verification.json")],"selected-replay-verify.log")
        report(study,root)
        stage="complete";status(report=str(root/"CREDIT_V4_2026_10.md"))
        print("Study and one-shot test complete",flush=True)
    except BaseException as exc:
        status(error=f"{type(exc).__name__}: {exc}")
        raise
    finally:
        for process,handle,_,_,_ in active.values():
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            handle.close()


def report(study, root):
    protocol=read(study/"study-protocol.json")
    assert hashes(study/"production")==protocol["implementation_sha256"]
    selection=read(study/"scaling-selection.json");runs=[];groups={}
    for stage,methods,steps in [("screen",protocol["methods"],protocol["screen_steps"]),
                               ("scale",[protocol["scale_control"],selection["winner"]],protocol["scale_steps"])]:
        for method in methods:
            rows=[]
            for seed in protocol["training_seeds"]:
                directory=study/stage/f"{method}-{seed}";verify_run(directory,protocol,steps)
                config=read(directory/"protocol.json");summary=read(directory/"summary.json");curve=read(directory/"curve.json")
                compact_curve=[{**r,"evaluation":{k:v for k,v in r["evaluation"].items() if k!="records"}} for r in curve]
                rows.append({"name":f"{stage}/{method}-{seed}","protocol":config,"training":summary,"curve":compact_curve})
            runs.extend(rows);evals=[r["curve"][-1]["evaluation"] for r in rows]
            means=[e["mean_achievements"] for e in evals]
            groups[f"{stage}/{method}"]={"seed_means":means,"mean":statistics.mean(means),"sample_sd":statistics.stdev(means),
                "death_rate":statistics.mean(e["death_rate"] for e in evals),
                "stone_rate":statistics.mean(e["hits"].get("collect stone",0)/128 for e in evals),
                "furnace_rate":statistics.mean(e["hits"].get("craft furnace",0)/128 for e in evals),
                "anvil_rate":statistics.mean(e["hits"].get("craft anvil",0)/128 for e in evals),
                "mean_wall_seconds":statistics.mean(r["training"]["wall_seconds_including_validation"] for r in rows)}
    paired={}
    for architecture in ("mlp","targets"):
        a=groups[f"screen/legacy_{architecture}"]["seed_means"]
        b=groups[f"screen/finite_{architecture}"]["seed_means"]
        difference=[y-x for x,y in zip(a,b)]
        paired[architecture]={"finite_minus_legacy_per_seed":difference,"mean":statistics.mean(difference),"sample_sd":statistics.stdev(difference)}
    test=read(study/"selected/test.json");manifest=read(study/"selected/selection.json")
    assert test["episodes"]==128 and manifest["test_seeds"]==protocol["reserved_test_seeds"]
    assert manifest["selection"]["checkpoint_sha256"]==sha(study/"selected/model.pt")
    assert all(not read(study/r["run"]/"protocol.json")["config"]["bootstrap_time_limit"] for r in manifest["candidates"])
    total=sum(r["training"]["steps"] for r in runs);assert total==protocol["main_transitions"]
    # Coarse same-wall snapshots are descriptive, not additional model selection.
    scale_runs=[r for r in runs if r["name"].startswith("scale/")]
    wall=min(r["training"]["wall_seconds_including_validation"] for r in scale_runs)
    wall_rows=[]
    for r in scale_runs:
        available=[c for c in r["curve"] if c["elapsed_seconds"]<=wall]
        if available:
            c=available[-1];wall_rows.append({"run":r["name"],"steps":c["steps"],"elapsed_seconds":c["elapsed_seconds"],"mean_achievements":c["evaluation"]["mean_achievements"]})
    extras={}
    for name in ("previous-policy-deadline-audit.json","selected-deadline-audit.json","selected-policy-diagnostics.json",
                 "memory-replay-verification.json","selected-replay-verification.json","preflight.json"):
        value=read(study/name);value.pop("records",None);extras[name]=value
    result={"complete":True,"date":"2026-10-11","study":str(study),"protocol":protocol,"main_transitions":total,
        "runs":runs,"groups":groups,"deadline_paired_comparisons":paired,"scaling_selection":selection,
        "selection":manifest,"test":{k:v for k,v in test.items() if k!="records"},"extra_evidence":extras,
        "coarse_equal_wall_snapshots":{"budget_seconds":wall,"rows":wall_rows,
            "note":"Last recorded checkpoint at or before the shortest final scaling wall time. Coarse 4M intervals, contention/validation included; not exact equal-compute trials."}}
    write(root/"CREDIT_V4_2026_10.json",result)
    lines=["# v4 deadline, credit, memory and exploration experiments","","Status: **complete**.","",
        f"Main training: **{total:,} transitions across {len(runs)} independent runs**, plus {protocol['calibration_transitions']:,} calibration transitions. Five paired training seeds. Unchanged v4 gameplay, primitive actions, legal masks, no demonstrations or prerequisite shaping.","",
        "Validation worlds: 8,000,001–8,000,128; one-shot reserved test: 9,000,001–9,000,128. Sampler 54321. The test split is now consumed.","",
        "## Fixed-budget final results","","| Method | Five seed scores /32 | Mean ± sample SD | Stone | Furnace | Anvil | Death | Wall/run |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name,g in groups.items():
        scores=" / ".join(f"{x:.2f}" for x in g["seed_means"])
        lines.append(f"| {name} | {scores} | {g['mean']:.2f} ± {g['sample_sd']:.2f} | {g['stone_rate']:.1%} | {g['furnace_rate']:.1%} | {g['anvil_rate']:.1%} | {g['death_rate']:.1%} | {g['mean_wall_seconds']/60:.1f} min |")
    lines.extend(["","## Deadline correction","",
        "The C API labels the action budget as a truncation. For our inherent 3000-action objective it has zero future reward, so both feed-forward and recurrent learners now stop value bootstrap there by default. The explicit legacy control preserves the old behavior for this comparison. The simulator itself is unchanged. Unfinished rollout fragments still bootstrap normally.","",
        "Regression tests check exact final-action targets, death/deadline overlap, no reset-world leakage, finite undiscounted Monte Carlo returns and nonterminal fragment bootstrap. Historical mechanics/parity tests did not establish objective correctness."])
    for name,p in paired.items():
        lines.append(f"\n`{name}` finite-minus-legacy final score: mean **{p['mean']:+.3f}**, paired seed differences {p['finite_minus_legacy_per_seed']}. Correct objective semantics do not automatically imply a large performance improvement.")
    chosen=manifest["selection"]
    lines.extend(["","## Frozen selection and fresh test","",
        f"Selected `{chosen['run']}` step {chosen['steps']:,}, validation {chosen['mean_achievements']:.3f}/32. Reserved test: **{test['mean_achievements']:.3f}/32**, death {test['death_rate']:.1%}, furnace {test['hits'].get('craft furnace',0)}/128, anvil {test['hits'].get('craft anvil',0)}/128.","",
        "Legacy controls were excluded from official selection. Selection was written before the test. No default checkpoint or architecture was replaced.","",
        "## Limits and interpretation","",
        "- Undiscounted reward, longer GAE trace, longer fragments, recurrent memory and novelty are separate screen conditions relative to finite_targets. Longer fragments also change batch/refresh cadence; recurrence adds capacity and sequence batching. Do not attribute either package solely to one mechanism.",
        "- RND uses generic observation prediction error, not a recipe/goal controller. It is training-only, capped at .005/action, and persistent; benchmark evaluation contains only achievement/death rewards. This condition is not an extrinsic-only training baseline.",
        "- The alternative was selected by five-seed FINAL 4M means, then both it and finite_targets restarted at 16M. Cross-budget learning-rate schedules differ. Screen selection is optimistic; the matched long comparison and one-shot test are separate evidence.",
        "- Five training seeds improve reliability estimates but do not prove a universal algorithm ranking. Equal-transition trials have different neural compute costs, and up to three jobs shared an active desktop. JSON includes phase timings and coarse same-wall snapshots, not an exact equal-FLOP comparison.",
        "- Ore-supply and tool-ownership limitations from the previous study remain. This study does not change the game to raise scores or claim all achievements are jointly feasible.","",
        f"Artifacts: `{study}`. All protocols, frozen source hashes, curves, checkpoint weights, audits and exactly verified replays are preserved. Numeric evidence: `CREDIT_V4_2026_10.json`."])
    (root/"CREDIT_V4_2026_10.md").write_text("\n".join(lines)+"\n")


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study",type=Path,required=True)
    p.add_argument("--mode",choices=["prepare","run","report"],required=True)
    a=p.parse_args();study=a.study.resolve();root=Path(__file__).resolve().parents[1]
    if a.mode=="prepare":prepare(study,root)
    elif a.mode=="run":run(study,root)
    else:report(study,root)


if __name__=="__main__":main()
