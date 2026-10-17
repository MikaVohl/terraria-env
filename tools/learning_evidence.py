"""Curate the frozen v4 causal/learning/scaling study, without retuning it.

This reads artifacts only. Historical v2/v3/v4 reports are not overwritten.
Use --allow-incomplete for an explicitly labelled interim report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
import subprocess


def read(path):
    return json.loads(path.read_text())


def compact(evaluation):
    return {k:v for k,v in evaluation.items() if k!="records"}


def expected_runs(protocol):
    seeds=protocol["training_seeds"]
    names=[("causal",f"{name}-{seed}")
           for name in ["control",*protocol["causal_screen"]["variants"]] for seed in seeds]
    names.extend(("screen",f"{name}-{seed}")
                 for name in protocol["method_screen"]["configurations"] for seed in seeds)
    return names


def aggregate(runs):
    """Each row weights training seeds equally, not by episode survival."""
    by_group={}
    for run in runs:
        stage,name=run["stage"],run["name"]
        if stage=="scale":
            method,budget,_=name.rsplit("-",2); group=f"{stage}/{method}/{budget}"
        else:
            method,_=name.rsplit("-",1);group=f"{stage}/{method}"
        by_group.setdefault(group,[]).append(run)
    result={}
    for group,rows in by_group.items():
        evals=[r["validation_curve"][-1]["evaluation"] for r in rows]
        means=[e["mean_achievements"] for e in evals]
        walls=[r["training"]["wall_seconds_including_validation"] for r in rows]
        result[group]={
            "training_seeds":[r["protocol"]["config"]["seed"] for r in rows],
            "final_seed_means":means,"final_mean":statistics.mean(means),
            "sample_std_between_training_seeds":statistics.stdev(means) if len(means)>1 else None,
            "final_death_rate":statistics.mean(e["death_rate"] for e in evals),
            "final_mean_peak_depth":statistics.mean(e["mean_peak_depth"] for e in evals),
            "final_stone_rate":statistics.mean(e["hits"].get("collect stone",0)/e["episodes"] for e in evals),
            "final_furnace_rate":statistics.mean(e["hits"].get("craft furnace",0)/e["episodes"] for e in evals),
            "final_mean_steps_after_last_achievement":statistics.mean(e["mean_steps_after_last_achievement"] for e in evals),
            "mean_wall_seconds":statistics.mean(walls),
            "mean_end_to_end_sps":statistics.mean(r["training"]["steps"]/w for r,w in zip(rows,walls)),
        }
    return result


def probe_summary(path):
    probe=read(path);records=probe.pop("records")
    modes={}
    for live in (False,True):
        rows=[r for r in records if r["mobs_live"]==live]
        modes["mobs_on" if live else "mobs_off"]={
            "episodes":len(rows),"stone_successes":sum(r["first_stone_step"]>0 for r in rows),
            "furnace_successes":sum(r["first_furnace_step"]>0 for r in rows),
            "deaths":sum(r["health"]<=0 for r in rows),
            "min_remaining_health":min(r["health"] for r in rows),
            "median_first_stone_step":statistics.median(r["first_stone_step"] for r in rows),
            "median_first_furnace_step":statistics.median(r["first_furnace_step"] for r in rows),
            "max_first_stone_step":max(r["first_stone_step"] for r in rows),
            "max_first_furnace_step":max(r["first_furnace_step"] for r in rows),
        }
    return {**probe,"modes":modes,"raw_sha256":hashlib.sha256(path.read_bytes()).hexdigest()}


def markdown(result):
    lines=["# v4 learning and causal study", "",
           "Status: **"+("complete" if result["complete"] else "INCOMPLETE — interim evidence")+"**.", "",
           "The production task is unchanged: a 2×3 body, pass-through trees, 73 primitive actions, "
           "32 achievements and 3000-action episodes. All production learners use legal masks, sparse "
           "achievement rewards, no demonstrations, no prerequisite shaping and no strategic masks.", "",
           f"Completed main training: **{result['completed_main_training_transitions']:,} transitions**, "
           "counted across independent learners, not one continuous agent. Two training seeds per condition; "
           "this is an exploratory comparison, not a precise population ranking.", "",
           "Validation: 6,000,001–6,000,128; sampler 54321. Reserved test: 7,000,001–7,000,128. "
           "A validation-selected checkpoint is frozen before the one-shot test. Historical splits/results "
           "remain historical; do not combine different task versions into a leaderboard.", "",
           "## Final checkpoint comparisons", "",
           "Rows weight training seeds equally. The causal screen uses constant learning rate at 1M; "
           "method and scaling runs anneal learning rate over their own full budget. Compare within "
           "a stage/budget, not intermediate checkpoints across different schedules.", "",
           "| Condition | Seed scores /32 | Mean /32 | Stone | Furnace | Death | Peak feet y | Wall/run |",
           "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name,row in result["aggregates"].items():
        scores=" / ".join(f"{s:.2f}" for s in row["final_seed_means"])
        lines.append(f"| {name} | {scores} | {row['final_mean']:.2f} | "
                     f"{row['final_stone_rate']:.1%} | {row['final_furnace_rate']:.1%} | "
                     f"{row['final_death_rate']:.1%} | {row['final_mean_peak_depth']:.1f} | "
                     f"{row['mean_wall_seconds']/60:.1f} min |")
    if result.get("selection"):
        selected=result["selection"]["selection"];test=result["reserved_test"]
        lines.extend(["", "## Frozen selection and fresh test", "",
                      f"Selected `{selected['run']}` at {selected['steps']:,} steps "
                      f"({selected['mean_achievements']:.3f}/32 validation). "
                      f"Fresh test: **{test['mean_achievements']:.3f}/32**, "
                      f"stone {test['hits'].get('collect stone',0)}/{test['episodes']}, "
                      f"furnace {test['hits'].get('craft furnace',0)}/{test['episodes']}, "
                      f"death {test['death_rate']:.1%}. Test split is now consumed; do not tune against it."])
    if result.get("scaling_selection"):
        lines.extend(["", "Scaling alternative selected by the predeclared two-seed **final** "
                      f"4M validation criterion: `{result['scaling_selection']['winner']}`. "
                      "Both this method and baseline restart from scratch at each long budget."])
    if result["complete"]:
        groups=result["aggregates"]
        lines.extend(["", "## What changed our understanding", "",
                      f"At 16M, the shared-target/longer-trace/higher-entropy package averaged "
                      f"**{groups['scale/targets/16777216']['final_mean']:.2f}/32**, versus "
                      f"{groups['scale/baseline/16777216']['final_mean']:.2f} for baseline. "
                      f"At 32M the respective means were **{groups['scale/targets/33554432']['final_mean']:.2f}** "
                      f"and {groups['scale/baseline/33554432']['final_mean']:.2f}. Both target seeds "
                      "learned mining at both long budgets; only one of the four long baseline runs did. "
                      "However, that baseline run remained the best individual policy. Two seeds do not "
                      "establish a definitive method ranking, and the target package changes architecture, "
                      "trace and entropy together relative to baseline.", "",
                      "More transitions alone were not sufficient: both fresh 32M baseline runs stayed "
                      "surface-bound. This is evidence of a discovery/learning-stability bottleneck under "
                      "these schedules, not a demonstration that additional compute cannot help. "
                      "The shared-target model is a useful reliability candidate, not a replacement "
                      "automatically promoted to the default."])
        diagnostic=result["extra_evidence"].get("selected-policy-diagnostics.json")
        if diagnostic:
            actions=diagnostic["actions"]
            furnace=actions["craft furnace"]
            lines.extend(["", "### Remaining behavioral bottleneck", "",
                          "A separate diagnostic of the selected policy uses the existing validation "
                          "worlds, not additional reserved-test evaluations. Furnace crafting was legal "
                          f"in {furnace['episodes_with_opportunity']}/128 episodes; conditional action "
                          f"probability was {furnace['mean_probability_when_legal']:.1%}. "
                          f"Anvil crafting had opportunities in only {actions['craft anvil']['episodes_with_opportunity']} "
                          "episodes. Iron/gold pickaxes, metal swords and both armor recipes had zero "
                          "legal opportunities. The issue is accumulating ingredients and keeping the "
                          "appropriate stations accessible, not merely increasing those recipes' logits. "
                          "Legality telemetry cannot by itself separate navigation, resource retention "
                          "and station placement as causes.", "",
                          f"On the one-shot test, mean actions after the final new achievement were "
                          f"{result['reserved_test']['mean_steps_after_last_achievement']:.0f}. "
                          "The fixed seed-9 replay earned 21 achievements, then spent its final 1862 "
                          "actions without another. It genuinely excavated 126 original stone cells but "
                          "also placed 130 stone blocks: recycling/building persists alongside progress. "
                          "This one replay is illustrative, not an aggregate success estimate."])
        lines.extend(["", "### Recommended next sequence", "",
                      "1. In a separately versioned game change, fix tool ownership/crafting semantics "
                      "and enforce necessary material supply, retaining real recipes and primitive actions. "
                      "Add regressions for crafting tools out of order and resource sufficiency. "
                      "Do not erase the v4 task or reinterpret its scores.",
                      "2. On that frozen version, compare the target package with a generic recurrent "
                      "spatial policy and an explicit exploration intervention, one factor at a time. "
                      "Longer-horizon credit assignment, resource retention and navigation memory "
                      "are hypotheses to test, not proven fixes. Keep legal masks and sparse achievements; "
                      "do not introduce a mining macro, recipe controller or expert cloning.",
                      "3. Use at least five training seeds for the promising comparison, report both "
                      "equal-transition and equal-wall-time results, and reserve a new test range. "
                      "The 7,000,001–7,000,128 range is consumed. Scale compute after a reproducible "
                      "crafting breakthrough, rather than interpreting one lucky seed as saturation.", "",
                      "No production gameplay or art changed during this study; model defaults and "
                      "existing default checkpoint files were not replaced. All experimental changes "
                      "remain available for the project owner's keep/revert decision."])
    benchmarks=result["extra_evidence"].get("simulator-benchmarks.json")
    if benchmarks:
        measurement=benchmarks["measurements"][0]
        lines.extend(["", "## Performance", "",
                      f"After training and diagnostics stopped, the three-repeat isolated harness "
                      f"measured **{measurement['core']['median_sps']:,.0f} core transitions/s** and "
                      f"**{measurement['batch']['median_sps']:,.0f} native-batch transitions/s**. "
                      "These are random legal-action simulator workloads, not policy-training throughput.", "",
                      "In the long runs, approximately 72–74% of wall time was PPO optimization and "
                      "24–26% collection; validation and other overhead account for the remainder. "
                      "Collection includes policy inference and observation handling, not just C physics. "
                      "Observed process memory was under 1 GiB per learner on a 48 GiB machine. "
                      "The evidence points to neural-network training/inference throughput rather than "
                      "disk I/O, RAM capacity or the raw simulator. No hardware counters were collected, "
                      "so arithmetic versus memory-bandwidth limits remain unproven.", "",
                      "The small MPS calibration was slower end-to-end than CPU, and target scoring "
                      "remains more costly despite fewer parameters. Main runs used CPU and up to three "
                      "concurrent jobs. No simulator optimization speedup is claimed from timing noise."])
    if "resource-census.json" in result["extra_evidence"]:
        census=result["extra_evidence"]["resource-census.json"];s=census["summary"]
        upper=32-(s["iron_shortfalls"]+s["gold_shortfalls"])/s["worlds"]
        lines.extend(["", "## Finite-resource ceiling", "",
                      f"A post-hoc census of seeds 0–255 found **{s['any_shortfall']}/{s['worlds']} worlds** "
                      "cannot support all 32 achievements together even ignoring time, navigation and combat. "
                      f"The anvil + iron pick + iron chainmail require 40 iron bars, or "
                      f"{census['all_achievements_necessary_iron_ore_equivalent']} iron ore; the gold pick "
                      f"requires {census['all_achievements_necessary_gold_ore_equivalent']} gold ore. "
                      f"Iron is insufficient in {s['iron_shortfalls']} worlds, gold in {s['gold_shortfalls']}, "
                      f"both in {s['both_shortfalls']}. Tile drops, initial inventory and chest loot are included.", "",
                      f"These necessary conditions alone bound this sample's mean maximum at **{upper:.2f}/32**; "
                      "actual achievable scores within 3000 actions may be lower. This does not explain "
                      "surface-bound policies or a large gap below that ceiling. Sufficient material is "
                      "not a reachability proof. No census data enters training or model selection, and "
                      "reserved test worlds were not inspected.", "",
                      "For the next game version, prefer a deterministic resource-supply floor after cave/chest "
                      "generation, retaining Terraria recipes, over making recipes artificially cheap. "
                      "Do not change the current game mid-comparison; a generator change needs a new "
                      "version, new evidence and fresh training."])
        lines.extend(["", "There is also a remaining tool-model simplification in `do_craft`/`can_craft`: "
                      "pick recipes grant an irreversible upgrade tier rather than a separately owned tool. "
                      "Gold-first therefore makes the Iron-pick recipe illegal and permanently misses its "
                      "achievement. The mask mirrors the implemented handler, but this is not faithful "
                      "independent-tool crafting. Revisit it in the next version—prefer explicit crafted "
                      "tools/equipment over forcing an ore-ladder order. These rules remain unchanged "
                      "throughout this study. The official wiki describes crafting availability in terms "
                      "of ingredients and stations, not the player's highest tool tier: "
                      "[Recipes](https://terraria.wiki.gg/wiki/Recipes). The current 10-bar pick costs "
                      "match the modern recipes: [Iron Bar](https://terraria.wiki.gg/wiki/Iron_Bar), "
                      "[Gold Pickaxe](https://terraria.wiki.gg/wiki/Gold_Pickaxe)."])
    lines.extend(["", "## Interpretation limits", "",
                  "- Width reduction alone did not restore stone collection at 1M. The old 1×2 body, "
                  "a shorter jump and anchored placement each broke through in one seed, not both. "
                  "This supports interacting geometry/mobility/building effects and seed-dependent "
                  "exploration thresholds, not a single proven width bottleneck.",
                  "- Diagnostic variants have distinct version IDs and retain all 73 target coordinates. "
                  "They are counterfactuals, not official benchmark environments or candidates for test selection. "
                  "The 1×2 variant is not a complete recreation of the old v3 interface.",
                  "- Peak depth means maximum absolute feet y, not depth below local surface. "
                  "Achievement-time means are conditional on reaching that achievement.",
                  "- More GAE trace persistence and entropy remain generic learning choices. Shared-target "
                  "spatial scoring ties mining/placement parameters across target positions; it contains "
                  "no digging controller, preferred recipe, goal order or target priority.",
                  "- Fewer model parameters do not imply faster training. Target scoring was slower in "
                  "CPU pilots; factoring the repeated global projection improved it. MPS was slower "
                  "end-to-end in the small calibration batch, so the main study uses CPU throughout.",
                  "- Across budgets, total steps and the learning-rate schedule change together. "
                  "A breakthrough at the first 4M checkpoint of a 16M run is not evidence that it "
                  "already consumed 16M steps; it retained a higher learning rate than a 4M-ending run.",
                  "- Up to three jobs ran concurrently on the active desktop. Wall times include validation "
                  "and reflect contention; they are not dedicated-machine ceilings or an isolated "
                  "architecture throughput comparison. Equal-transition trials are not equal-compute trials.", "",
                  "## Feasibility and correctness", "",
                  "A white-box diagnostic mined stone and crafted a furnace in all 256 generated worlds "
                  "with mobs enabled and all 256 with mobs disabled. It explicitly starts with 14 wood "
                  "and three torches and observes terrain identity. This establishes physical progression "
                  "given prerequisites, not learned proficiency or end-to-end resource gathering. "
                  "No probe actions or outputs enter the learner.", "",
                  "Scalar/native/worker/encoding parity, legal gradients and checkpoint reloads passed. "
                  "The API-only metadata addition preserves the old frozen v4 rollout digest over "
                  "27,913 transitions. Target scorer factoring was checked against the direct expression "
                  "for forward outputs and gradients at 1e-7 tolerance. Frozen production source hashes "
                  "are recorded in the study protocol and checked by the runner.", "",
                  "## Local artifacts", "",
                  f"Study: `{result['study']}`. Each run preserves its protocol, package snapshot, "
                  "checkpoints, validation episode records, phase timings and training summary. "
                  "The companion JSON retains compact curves, per-achievement timings, source hashes, "
                  "calibration/probe evidence and selection provenance. Old reports were not overwritten."])
    if result["missing_runs"]:
        lines.extend(["", "Pending: "+", ".join(result["missing_runs"])+"."])
    return "\n".join(lines)+"\n"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--allow-incomplete",action="store_true")
    parser.add_argument("--resource-census-binary",type=Path,help="Run the read-only resource_census.c diagnostic on seeds 0–255")
    parser.add_argument("--quiet",action="store_true")
    args=parser.parse_args();study=args.study.resolve();protocol=read(study/"study-protocol.json")
    if args.resource_census_binary:
        census=json.loads(subprocess.check_output([str(args.resource_census_binary.resolve())],text=True))
        assert census["environment_version"]==protocol["environment_version"] and census["seed_range"]==[0,255]
        census["binary_sha256"]=hashlib.sha256(args.resource_census_binary.read_bytes()).hexdigest()
        (study/"resource-census.json").write_text(json.dumps(census,indent=2)+"\n")
    for name,digest in protocol["implementation_sha256"].items():
        assert hashlib.sha256((study/"production"/name).read_bytes()).hexdigest()==digest,name
    expected=expected_runs(protocol)
    scale_selection=read(study/"scaling-selection.json") if (study/"scaling-selection.json").exists() else None
    if scale_selection:
        expected.extend(("scale",f"{name}-{budget}-{seed}")
                        for budget in protocol["scaling"]["budgets"]
                        for name in ("baseline",scale_selection["winner"]) for seed in protocol["training_seeds"])
    runs=[];missing=[]
    for stage,name in expected:
        directory=study/stage/name
        if not (directory/"summary.json").exists():
            missing.append(f"{stage}/{name}");continue
        config=read(directory/"protocol.json");summary=read(directory/"summary.json")
        assert summary["steps"]==config["actual_steps"]
        assert config["validation_seeds"]==protocol["validation_seeds"]
        assert config["reserved_test_seeds"]==protocol["reserved_test_seeds"]
        curve=read(directory/"curve.json")
        assert curve[-1]["steps"]==summary["steps"]
        native=Path(config["package"])/"libterraria.dylib"
        if native.exists():
            assert hashlib.sha256(native.read_bytes()).hexdigest()==config["implementation_sha256"][native.name]
        runs.append({"stage":stage,"name":name,"protocol":config,"training":summary,
                     "validation_curve":[{**row,"evaluation":compact(row["evaluation"])} for row in curve]})
    selected=study/"selected"
    complete=not missing and scale_selection is not None and (selected/"test.json").exists()
    if not args.allow_incomplete and not complete:
        raise RuntimeError("Study/test incomplete; use --allow-incomplete only for an interim report")
    calibration={}
    for name in ["mlp-throughput-pilot","target-throughput-pilot","target-mps-throughput-pilot","target-factored-throughput-pilot"]:
        calibration[name]={"protocol":read(study/name/"protocol.json"),"training":read(study/name/"summary.json")}
    extras={}
    for name in ["baseline4m-policy-diagnostics.json","target2m-policy-diagnostics.json","selected-policy-diagnostics.json",
                 "baseline4m-replay-verification.json","target4m-replay-verification.json","replay-verification.json",
                 "simulator-benchmarks.json","verification.json"]:
        if (study/name).exists():
            value=read(study/name)
            if isinstance(value,dict):value.pop("records",None)
            extras[name]=value
    if (study/"resource-census.json").exists():
        census=read(study/"resource-census.json");rows=census.pop("records")
        census["summary"]={"worlds":len(rows),
            "iron_shortfalls":sum(r["iron_shortfall"] for r in rows),
            "gold_shortfalls":sum(r["gold_shortfall"] for r in rows),
            "any_shortfall":sum(r["iron_shortfall"] or r["gold_shortfall"] for r in rows),
            "both_shortfalls":sum(r["iron_shortfall"] and r["gold_shortfall"] for r in rows),
            "resources":{name:{"min":min(r[name] for r in rows),"median":statistics.median(r[name] for r in rows),
                               "max":max(r[name] for r in rows)}
                         for name in ("wood","copper_ore","iron_ore_equivalent","silver_ore","gold_ore_equivalent")}}
        census["note"]="Necessary material conditions only; sufficient total material does not prove reachability within 3000 actions. Post-hoc design diagnostic, never learner input."
        extras["resource-census.json"]=census
    result={"date":"2026-10-10","study":str(study),"complete":complete,"protocol":protocol,
            "planned_main_training_transitions":247463936,
            "completed_main_training_transitions":sum(r["training"]["steps"] for r in runs),
            "calibration_training_transitions":sum(r["training"]["steps"] for r in calibration.values()),
            "runs":runs,"aggregates":aggregate(runs),"missing_runs":missing,
            "scaling_selection":scale_selection,"calibration":calibration,
            "progression_probe":probe_summary(study/"progression-probe.json"),"extra_evidence":extras}
    result["diagnostic_variant_source_sha256_at_curation"]={
        name:{str(f.relative_to(study/"variants"/name)):hashlib.sha256(f.read_bytes()).hexdigest()
              for folder in ("include","src") for f in (study/"variants"/name/folder).iterdir()
              if f.suffix in (".c",".h")}
        for name in protocol["causal_screen"]["variants"]}
    root=Path(__file__).resolve().parents[1]
    result["curation_and_diagnostic_tool_sha256"]={name:hashlib.sha256((root/name).read_bytes()).hexdigest()
        for name in ["tools/learning_evidence.py","tools/resource_census.c","tools/replay_analysis.c",
                     "tools/generated_progression_probe.c","tools/verify_replay.py","tools/policy_diagnostics.py"]}
    fixture=study/"ui-fixture-iron.png"
    if fixture.exists():
        result["extra_evidence"]["ui_fixture"]={"path":str(fixture),
            "sha256":hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "note":"Off-policy synthetic rendering fixture, visually checked; never training data or an agent performance result."}
    if (selected/"test.json").exists():
        result["selection"]=read(selected/"selection.json")
        result["reserved_test"]=compact(read(selected/"test.json"))
        manifest=result["selection"]
        assert manifest["environment_version"]==protocol["environment_version"]
        assert manifest["validation_seeds"]==protocol["validation_seeds"]
        assert manifest["test_seeds"]==protocol["reserved_test_seeds"]
        assert result["reserved_test"]["episodes"]==128
        assert manifest["selection"]==sorted(manifest["candidates"],key=lambda r:(
            -r["mean_achievements"],r["death_rate"],r["steps"],r["run"]))[0]
        digest=hashlib.sha256((selected/"model.pt").read_bytes()).hexdigest()
        assert digest==manifest["selection"]["checkpoint_sha256"]
        eligible={f"{r['stage']}/{r['name']}" for r in runs
                  if r["protocol"]["environment_version"]==protocol["environment_version"]}
        assert {r["run"] for r in manifest["candidates"]}==eligible
        if "selected-policy-diagnostics.json" in extras:
            diagnostic=extras["selected-policy-diagnostics.json"]
            assert diagnostic["checkpoint_sha256"]==digest
            assert diagnostic["seed_range"]==protocol["validation_seeds"]
        if "replay-verification.json" in extras:
            assert extras["replay-verification.json"]["policy_provenance"]["checkpoint_sha256"]==digest
    args.out.write_text(json.dumps(result,indent=2)+"\n")
    args.out.with_suffix(".md").write_text(markdown(result))
    message={"complete":complete,"transitions":result["completed_main_training_transitions"],
             "missing":missing,"json":str(args.out),"markdown":str(args.out.with_suffix('.md'))}
    if not args.quiet:message["groups"]=result["aggregates"]
    print(json.dumps(message,indent=2))


if __name__=="__main__":main()
