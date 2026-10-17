"""Freeze production v4 and distinct, diagnostic-only counterfactual builds."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study",type=Path,required=True)
    p.add_argument("--refresh-learner",action="store_true",help="Before trials only: refresh Python snapshot after throughput calibration")
    a=p.parse_args(); root=Path(__file__).resolve().parents[1]
    frozen=a.study/"production"
    if a.refresh_learner:
        if any((a.study/folder).exists() for folder in ("causal","screen","scale")):
            raise ValueError("Trials already exist; the learner must stay frozen")
        for destination in [frozen,*sorted((a.study/"variants").iterdir())]:
            for source in (root/"python/terraria_lite").glob("*.py"):
                shutil.copy2(source,destination/"python/terraria_lite"/source.name)
        path=a.study/"study-protocol.json";data=json.loads(path.read_text())
        data["implementation_sha256"]={str(f.relative_to(frozen)):hashlib.sha256(f.read_bytes()).hexdigest()
            for folder in ("src","include","python/terraria_lite") for f in (frozen/folder).iterdir() if f.suffix in (".c",".h",".py",".dylib",".so")}
        path.write_text(json.dumps(data,indent=2)+"\n");print("Refreshed pre-trial learner snapshot");return
    if frozen.exists():raise ValueError("Snapshot already exists")
    frozen.mkdir()
    for name in ("include","src","python","tools","third_party"):
        shutil.copytree(root/name,frozen/name)
    shutil.copy2(root/"Makefile",frozen/"Makefile")
    for name in ("terraria-lite","terraria-px"):
        shutil.copy2(root/name,frozen/name)
    variants={"width1":{"version":401,"width":1},"height2":{"version":402,"height":2},
              "body1x2":{"version":403,"width":1,"height":2},
              "jump3":{"version":404,"jump":3},
              "anchored":{"version":405,"anchoring":True}}
    # Copying snapshots is deliberately separate from applying source changes:
    # print explicit patch targets for the caller to edit with apply_patch.
    for name,changes in variants.items():
        dest=a.study/"variants"/name
        for directory in ("include","src","python","tools"):
            shutil.copytree(frozen/directory,dest/directory)
        shutil.copy2(frozen/"Makefile",dest/"Makefile")
        print(f"Prepared {dest}: {changes}")
    protocol={"environment_version":4,"production_snapshot":str(frozen.resolve()),
        "validation_seeds":[6_000_001,6_000_128],"reserved_test_seeds":[7_000_001,7_000_128],
        "sampler_seed":54321,"training_seeds":[101,202],
        "causal_screen":{"steps_per_run":1_048_576,"constant_lr":True,"variants":variants,
            "note":"All retain the same 73 action coordinates. Experimental version IDs reject production checkpoint loading. Not official benchmark variants or proposed game changes."},
        "method_screen":{"steps_per_run":4_194_304,"configurations":{
            "baseline":{"architecture":"mlp","gae_lambda":.95,"entropy":.01},
            "trace":{"architecture":"mlp","gae_lambda":.99,"entropy":.01},
            "explore":{"architecture":"mlp","gae_lambda":.99,"entropy":.03},
            "targets":{"architecture":"targets","gae_lambda":.99,"entropy":.03}}},
        "scaling":{"budgets":[16_777_216,33_554_432],
            "methods":"baseline and highest two-seed final validation mean among new methods; ties lower death rate, then name",
            "fresh_training":True,"reward":"achievement +1; death -1","demonstrations":False,"strategic_masks":False},
        "test_selection":"After all production runs finish: highest validation mean across production checkpoints; ties death rate, fewer steps, run name. Test once, never use ablations as candidates.",
        "implementation_sha256":{str(f.relative_to(frozen)):hashlib.sha256(f.read_bytes()).hexdigest()
            for folder in ("src","include","python/terraria_lite") for f in (frozen/folder).iterdir() if f.suffix in (".c",".h",".py",".dylib",".so")}}
    (a.study/"study-protocol.json").write_text(json.dumps(protocol,indent=2)+"\n")


if __name__=="__main__":main()
