"""Curate completed v4 runs, paired comparisons, timing and provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from terraria_lite import SPEC
from terraria_lite.rules import player_knowledge


def read(path):
    return json.loads(path.read_text())


def compact(evaluation):
    return {k:v for k,v in evaluation.items() if k != "records"}


def main():
    if SPEC.version != 4:
        raise RuntimeError("This report requires the v4 environment")
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    runs=[]
    for architecture in ("mlp","separate"):
        for seed in (101,202,303):
            name=f"v4-{architecture}-{seed}"; directory=a.study/name
            protocol=read(directory/"protocol.json")
            summary=read(directory/"summary.json")
            assert protocol["environment_version"] == 4
            assert summary["steps"] == protocol["actual_steps"] == 4_194_304
            assert protocol["reserved_test_seeds"] == [4_000_001,4_000_128]
            assert not protocol["demonstrations"] and not protocol["prerequisite_shaping"]
            assert not protocol["training_novelty"]
            assert protocol["config"]["progress_coef"] == 0
            matched={k:v for k,v in protocol["config"].items() if k not in ("architecture","seed")}
            if runs:
                assert matched == matched_config
            matched_config=matched
            curve=read(directory/"curve.json")
            runs.append({"name":name,"protocol":protocol,"training":summary,
                "validation_curve":[{**row,"evaluation":compact(row["evaluation"])} for row in curve]})
    aggregates={}
    for architecture in ("mlp","separate"):
        group=[r for r in runs if r["protocol"]["config"]["architecture"]==architecture]
        evaluations=[r["validation_curve"][-1]["evaluation"] for r in group]
        means=[e["mean_achievements"] for e in evaluations]
        aggregates[architecture]={"final_seed_means":means,"final_mean":statistics.mean(means),
            "model_parameters":{"mlp":1_817_162,"separate":3_596_362}[architecture],
            "sample_std_between_training_seeds":statistics.stdev(means),
            "mean_death_rate":statistics.mean(e["death_rate"] for e in evaluations),
            "mean_wall_seconds_including_validation":statistics.mean(r["training"]["wall_seconds_including_validation"] for r in group),
            "mean_collection_seconds":statistics.mean(r["training"]["collection_seconds"] for r in group),
            "mean_optimisation_seconds":statistics.mean(r["training"]["optimisation_seconds"] for r in group),
            "mean_achievement_hit_rates":{n:statistics.mean(e["hits"].get(n,0)/e["episodes"] for e in evaluations) for n in SPEC.achievement_names}}
    differences=[b-a for a,b in zip(aggregates["mlp"]["final_seed_means"],aggregates["separate"]["final_seed_means"])]
    benchmarks=read(a.study/"benchmarks.json")
    old,uncached,optimized=benchmarks["measurements"]
    root=Path(__file__).resolve().parents[1]
    source_files=[*root.glob("src/*.c"),*root.glob("src/*.h"),*root.glob("include/*.h"),
                  *root.glob("python/terraria_lite/*.py"),*root.glob("python/terraria_lite/libterraria.*")]
    # No simulator/learner edits may have slipped in while these policies trained.
    current={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files if f.parent==root/"python/terraria_lite"}
    for run in runs:
        assert run["protocol"]["implementation_sha256"] == current
    for name,digest in optimized["core_source_sha256"].items():
        if name not in ("src/px_main.c","src/px_render.c","src/main.c","src/render.c"):
            assert hashlib.sha256((root/name).read_bytes()).hexdigest() == digest
    result={"date":"2026-10-10","environment_version":4,"rules":player_knowledge(),
        "completed_training_transitions":sum(r["training"]["steps"] for r in runs),
        "protocol_context":"Two architectures, three matched training seeds, 4M each; six-thread CPU trials with at most three concurrent jobs. Validation selects checkpoints; reserved test is used once.",
        "aggregates":aggregates,"paired_separate_minus_mlp":{"seed_differences":differences,"mean":statistics.mean(differences),
            "sample_std":statistics.stdev(differences),"note":"Three seeds are exploratory evidence, not a precise architecture ranking."},
        "benchmarks":benchmarks,
        "same_v4_station_cache_speedup":{"core":optimized["core"]["median_sps"]/uncached["core"]["median_sps"],
            "native_batch":optimized["batch"]["median_sps"]/uncached["batch"]["median_sps"]},
        "v4_vs_v3_workload_ratio":{"core":optimized["core"]["median_sps"]/old["core"]["median_sps"],
            "native_batch":optimized["batch"]["median_sps"]/old["batch"]["median_sps"],
            "note":"Different geometry/actions/trajectories; not a same-task optimization comparison."},
        "verification":{"mechanics_seed_invariants":100,"arbitrary_light_edits_exact":24000,
            "scalar_native_exact_transitions":64000,"workers":[1,2,4,8],"raw_flat_encoding_exact":True,
            "station_cache_identical_rollout_transitions":27913,
            "station_cache_identical_rollout_sha256":"9d4d1b34c8ecdc1fbbb7275829b34c6a0ce69f57e5b231fe50e27bb6a8ad2539",
            "asan_ubsan":"mechanics, fidelity and light suites passed",
            "pixel":"72 original assets audited; tree before/after, three armor variants and UI hit targets visually inspected",
            "api":"Gym v4, 73 actions, 2961 observations, geometry/rules queries and v3 checkpoint rejection passed"},
        "local_assembly_constants":{"player_hitbox_pixels":[20,42],"tileSolid[5]":0,
            "tileSolidTop[16]":1,"tileSolidTop[18]":1,"tileSolidTop[19]":1,
            "tileSolid[30]":1,"tileBlockLight[30]":1,
            "source":"Read from installed Terraria.exe with tools/terraria_fidelity_audit.py; assembly SHA256 is in asset_audit."},
        "runs":runs,"validation_uniform_legal":compact(read(a.study/"v4-random.json")),
        "excluded_provisional_runs":{"reason":"Pre-release v4 half-defense rounding was corrected before final trials; no reserved test used.",
            "completed_runs":["v4-mlp-101","v4-mlp-202","v4-separate-101"],
            "completed_transitions":12_582_912,"interrupted_runs":["v4-mlp-303","v4-separate-202"],
            "snapshot":"provisional/v4; never load these checkpoints into the final v4 rules"},
        "selection":read(a.study/"selected/selection.json"),"reserved_test":compact(read(a.study/"selected/test.json")),
        "diagnostic_controls":{name:compact(read(a.study/name)) for name in ("mlp101-diagnostics.json","separate101-diagnostics.json")},
        "diagnostics":compact(read(a.study/"selected-diagnostics.json")),"asset_audit":read(a.study/"asset-audit.json"),
        "replay":read(a.study/"replay-verification.json"),
        "final_implementation_sha256":{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in source_files}}
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:result[k] for k in ("completed_training_transitions","aggregates","paired_separate_minus_mlp")},indent=2))


if __name__=="__main__": main()
