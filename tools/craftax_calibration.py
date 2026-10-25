"""Run pinned upstream PPO with local logging only; do not change its algorithm.

Use the separate environment in experiments/craftax-calibration/.venv.
See docs/reports/V2.md for pinned sources/dependencies. Arguments after --out are forwarded.
"""
import argparse
import json
import os
from pathlib import Path
import runpy
import sys
import time
import numpy as np

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,default=Path("experiments/craftax-calibration/run"))
    a,forward=p.parse_known_args()
    if any((a.out/name).exists() for name in ("protocol.json","curve.json","summary.json")):
        raise ValueError("Calibration output already exists; use a fresh --out directory")
    a.out.mkdir(parents=True,exist_ok=True)
    for key,val in {"WANDB_MODE":"disabled","WANDB_SILENT":"true",
                    "WANDB_DISABLE_CODE":"true","WANDB_DISABLE_GIT":"true",
                    "JAX_PLATFORMS":"cpu","PYGAME_HIDE_SUPPORT_PROMPT":"1"}.items():
        os.environ[key]=val
    root=Path(__file__).resolve().parents[1]
    source=root/"experiments/craftax-calibration/upstream/ppo.py"
    if not source.exists(): raise FileNotFoundError("Fetch the pinned upstream source first; see docs/reports/V2.md")
    import jax
    import wandb
    rows=[]; began=time.perf_counter(); original_init=wandb.init
    def log(data,*args,**kwargs):
        row={k:np.asarray(v).tolist() for k,v in data.items()}
        row["elapsed_seconds"]=time.perf_counter()-began; rows.append(row)
        (a.out/"curve.json").write_text(json.dumps(rows,indent=2)+"\n")
        if len(rows)%16==0:
            print(f"Craftax update {len(rows)}: achievements={row.get('achievements')}",flush=True)
    def init(*args,**kwargs):
        kwargs["mode"]="disabled"
        result=original_init(*args,**kwargs); wandb.log=log; return result
    wandb.init=init
    (a.out/"protocol.json").write_text(json.dumps({"upstream_commit":
        "7ce36fa05b84a2c9e758012f1e6da402e1e3a891","args":forward,
        "devices":[str(d) for d in jax.devices()],"logging_only_patch":True,
        "health_rewards":"upstream environment unchanged","telemetry":"disabled"},indent=2)+"\n")
    sys.path.insert(0,str(source.parent)); sys.argv=[str(source),*forward]
    runpy.run_path(str(source),run_name="__main__")
    jax.effects_barrier()
    (a.out/"summary.json").write_text(json.dumps({"updates":len(rows),
        "wall_seconds":time.perf_counter()-began,"final_training_metrics":rows[-1] if rows else {}},indent=2)+"\n")

if __name__=="__main__": main()
