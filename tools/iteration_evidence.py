"""Curate completed iteration runs without relabeling historical v2 evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import statistics
from terraria_lite import SPEC


def main():
    if SPEC.version != 3:
        raise RuntimeError("Historical v3 evidence requires the frozen v3 package")
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    names=["mlp-baseline-101","mlp-optimized-screen-101","mlp-horizon-101",
           "tokens-sparse-101","mlp-rnd-101","mlp-balanced-rnd-fixed-101",
           "cnn-mps-101","cnn-mps-throughput","mlp16m-101",
           "v3-mlp-101","v3-mlp-202","v3-mlp-303","v3-tokens-101","v3-separate-101","v3-separate-202"]
    runs=[]
    for name in names:
        directory=a.study/name
        protocol=json.loads((directory/"protocol.json").read_text())
        summary=json.loads((directory/"summary.json").read_text())
        assert summary["steps"]==protocol["actual_steps"]
        curve=json.loads((directory/"curve.json").read_text())
        compact=[]
        for row in curve:
            evaluation={k:v for k,v in row["evaluation"].items() if k!="records"}
            evaluation["hits"]={n:evaluation["hits"].get(n,0) for n in SPEC.achievement_names}
            compact.append({"steps":row["steps"],"elapsed_seconds":row["elapsed_seconds"],"evaluation":evaluation})
        runs.append({"name":name,"protocol":protocol,"training":summary,"validation_curve":compact})
    baselines=[r for r in runs if r["name"] in ["v3-mlp-101","v3-mlp-202","v3-mlp-303"]]
    means=[r["validation_curve"][-1]["evaluation"]["mean_achievements"] for r in baselines]
    batched=[{"label":"original v2, native raw + NumPy encoding","seconds":[1.941514707985334,1.9645446249924134,1.9320546250091866]},
             {"label":"optimized v2 light, native raw + NumPy encoding","seconds":[.4204347910126671,.4287695000239182,.41923875000793487]},
             {"label":"optimized v2 light + native flat encoding","seconds":[.32679279102012515,.310783499997342,.3045102079922799]}]
    core=[{"label":"original v2","env_bytes":38576,"seconds":[5.403368,5.353660,5.374374],"checksum":572013},
          {"label":"optimized v2","env_bytes":38704,"seconds":[.247276,.247664,.246269],"checksum":572013}]
    for group in (batched,core):
        for row in group: row["median_sps"]=262144/statistics.median(row["seconds"])
    root=Path(__file__).resolve().parents[1]
    files=[*root.glob("src/*.c"),*root.glob("include/*.h"),*root.glob("python/terraria_lite/*.py"),*root.glob("python/terraria_lite/libterraria.*")]
    result={"date":"2026-10-10","current_environment_version":SPEC.version,
            "completed_training_transitions":sum(r["training"]["steps"] for r in runs),
            "v3_plain_ppo_three_seed_final":{"mean":statistics.mean(means),"sample_std_between_training_seeds":statistics.stdev(means),"seed_means":means},
            "same_v2_task_benchmarks":{"transitions_per_repeat":262144,"repeats":3,"envs":64,"workers_batched":4,
                "batched":batched,"single_thread_core":core,
                "batched_speedup":batched[-1]["median_sps"]/batched[0]["median_sps"],
                "core_speedup":core[-1]["median_sps"]/core[0]["median_sps"],
                "context":"M5 Pro macOS, active desktop with concurrent training. Not dedicated-machine ceilings. Matched task/sampler; raw C and Python use different samplers."},
            "current_v3_benchmarks":{"note":"Different game rules from v2; do not use for same-task speedup.","env_bytes":38712,
                "core_seconds":[.238151,.238351,.242864],"core_median_sps":1099823.4,"core_checksum":774105,
                "batched_seconds":[.2637580420123413,.2587316250137519,.2576070830109529],"batched_median_sps":1013188.8592516154},
            "verification":{"cross_v2_rollout_transitions":30032,"cross_v2_rollout_sha256":"dc56bc86ba953de9b110b2b40c31c0c42c7b2bb0202bc351175a18a17b19bb03",
                "optimized_v2_same_1m_seed101_weights_bit_identical":True,"arbitrary_light_edits_exact":24000,
                "scalar_native_exact_transitions":64000,"worker_counts":[1,2,4,8],"raw_flat_encoding_exact":True,
                "asan_ubsan_mechanics_and_light":"passed","pixel_fixture":"72 original asset PNGs audited; 22/22 tiles and 31/31 inventory; tree felling/axe display; three armor variants"},
            "runs":runs,"excluded_incomplete_trials":["cnn-pilot-101 (CPU kernel, interrupted)","cnn-contiguous-101 (CPU performance, interrupted)","mlp-balanced-rnd-101 (NameError; fixed fresh trial)"],
            "diagnostics":{n:json.loads((a.study/n).read_text()) for n in ["old-policy-diagnostics.json","mlp4m-diagnostics.json","v3-policy-diagnostics.json","selected-policy-diagnostics.json"]},
            "asset_audit":json.loads((a.study/"asset-audit.json").read_text()),
            "selection":json.loads((a.study/"v3-selected/selection.json").read_text()),
            "reserved_test":json.loads((a.study/"v3-selected/test.json").read_text()),
            "validation_uniform_legal":json.loads((a.study/"v3-random.json").read_text()),
            "post_iteration_implementation_sha256":{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    # Per-episode diagnostics remain in local artifacts; compact tracked evidence.
    for entry in result["diagnostics"].values(): entry.pop("records",None)
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    for r in runs:
        e=r["validation_curve"][-1]["evaluation"]
        print(f"{r['name']:32} v{r['protocol']['environment_version']} {r['training']['steps']:>10,} {e['mean_achievements']:6.3f} death={e['death_rate']:.1%} bench={e['hits']['craft workbench']} furnace={e['hits']['craft furnace']} wall={r['training']['wall_seconds_including_validation']:.1f}s")
    print(json.dumps({k:result[k] for k in ["completed_training_transitions","v3_plain_ppo_three_seed_final"]}))


if __name__=="__main__": main()
