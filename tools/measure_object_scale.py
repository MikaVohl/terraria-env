"""Interleaved footprint-preview timing while the frozen RL study continues.

This deliberately does not label a contended desktop probe as an isolated
measurement. Full changed-task workloads, not identical trajectories/FLOPs.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--baseline",type=Path,required=True);p.add_argument("--preview",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True);p.add_argument("--pairs",type=int,default=5)
    p.add_argument("--active-study",type=Path)
    p.add_argument("--date",default="2026-10-11")
    a=p.parse_args()
    if a.out.exists():raise ValueError("Timing artifact exists")
    def label(root):return 'v'+re.search(r'#define ENV_VERSION (\d+)',(root/'include/env.h').read_text())[1]
    baseline,preview=label(a.baseline),label(a.preview)
    if baseline==preview:raise ValueError('Use distinct version labels')
    roots={baseline:a.baseline.resolve(),preview:a.preview.resolve()};tool_root=Path(__file__).resolve().parent
    ratio_key=f'{preview}_over_{baseline}_sps'
    results=[];status_before=json.loads((a.active_study/"status.json").read_text()) if a.active_study else None
    with tempfile.TemporaryDirectory(prefix="terraria-object-timing-") as directory:
        binaries={}
        for name,root in roots.items():
            binary=Path(directory)/name;binaries[name]=binary
            subprocess.run(["cc","-std=c11","-O2",f"-I{root/'include'}",f"-I{root/'src'}",str(tool_root/"core_benchmark.c"),
                *[str(root/"src"/f) for f in ("sim.c","worldgen.c","light.c","obs.c")],"-lm","-o",str(binary)],check=True)
        for pair in range(a.pairs):
            rows={}
            for name in ((baseline,preview) if pair%2==0 else (preview,baseline)):
                root=roots[name];env=os.environ.copy();env["PYTHONPATH"]=str(root/"python");env.pop("TERRARIA_LITE_LIB",None)
                core=json.loads(subprocess.check_output([str(binaries[name])],text=True))
                batch=json.loads(subprocess.check_output([os.path.abspath(sys.executable),str(tool_root/"v2_benchmark.py"),
                    "--steps","262144","--envs","64","--workers","4"],env=env,text=True))
                assert core["environment_version"]==batch["environment_version"]==int(name[1:])
                rows[name]={"core":core,"batch":batch}
            ratio={kind:rows[preview][kind]["median_sps"]/rows[baseline][kind]["median_sps"] for kind in ("core","batch")}
            results.append({"pair":pair,"order":[baseline,preview] if pair%2==0 else [preview,baseline],"measurements":rows,ratio_key:ratio})
            print(f"pair {pair+1}: core ratio {ratio['core']:.3f}, batch ratio {ratio['batch']:.3f}",flush=True)
    summary={kind:{f"{baseline}_median_sps":statistics.median(r["measurements"][baseline][kind]["median_sps"] for r in results),
                  f"{preview}_median_sps":statistics.median(r["measurements"][preview][kind]["median_sps"] for r in results),
                  "paired_ratio_median":statistics.median(r[ratio_key][kind] for r in results),
                  "paired_ratio_min":min(r[ratio_key][kind] for r in results),
                  "paired_ratio_max":max(r[ratio_key][kind] for r in results)} for kind in ("core","batch")}
    evidence={"date":a.date,"hardware":"Apple M5 Pro, 48 GiB, macOS",
        "context":("Concurrent frozen PPO training on active desktop; " if a.active_study else "No concurrent RL jobs requested; active desktop, not a dedicated machine; ")+"alternate measurement order; five pairs by default, three repeats inside each probe. Changed task trajectories and legal-action workloads, not an exact optimization comparison or end-to-end neural training benchmark.",
        "status_before":status_before,"status_after":json.loads((a.active_study/"status.json").read_text()) if a.active_study else None,
        "measurements":results,"summary":summary,
        "gate":{"max_native_batch_median_sps_loss":.10,"passes":summary["batch"]["paired_ratio_median"]>=.90,
                "note":"Simulator-cost gate only, not end-to-end PPO. Fresh preview RL is required before claiming learning performance is preserved."},
        "source_sha256":{name:{str(f.relative_to(root)):sha(f) for folder in ("include","src") for f in (root/folder).iterdir() if f.suffix in (".h",".c")} for name,root in roots.items()},
        "harness_sha256":{f.name:sha(f) for f in (tool_root/"core_benchmark.c",tool_root/"v2_benchmark.py",Path(__file__))}}
    a.out.write_text(json.dumps(evidence,indent=2)+"\n")
    print(json.dumps({"summary":summary,"gate":evidence["gate"]},indent=2))


if __name__=="__main__":main()
