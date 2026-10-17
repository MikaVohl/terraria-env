"""Compare a versioned action tape's Python and headless SDL final state."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from terraria_lite import SPEC, TerrariaLite


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("tape",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--viewer",type=Path,default=Path(__file__).resolve().parents[1]/"terraria-px")
    p.add_argument("--analysis-binary",type=Path,help="Optional replay_analysis.c executable built against the same frozen rules")
    p.add_argument("--checkpoint",type=Path,help="Also reproduce the sampled tape from this frozen checkpoint")
    p.add_argument("--sample-seed",type=int,default=12345)
    a=p.parse_args()
    lines=[line.strip() for line in a.tape.read_text().splitlines() if line.strip() and not line.startswith("#")]
    header={}; actions=None
    for i,line in enumerate(lines):
        key,value=line.split(maxsplit=1)
        header[key]=value
        if key=="actions":
            actions=[int(x) for x in lines[i+1:]];break
    assert int(header["environment"])==SPEC.version
    assert len(actions)==int(header["actions"]) and all(0<=x<SPEC.n_actions for x in actions)
    env=TerrariaLite(max_steps=int(header["max_steps"]))
    try:
        env.reset(seed=int(header["seed"]))
        for action in actions: _,_,_,_,info=env.step(action)
    finally:
        env.close()
    output=subprocess.check_output([str(a.viewer.resolve()),"--watch",str(a.tape.resolve()),"--verify"],text=True)
    actual=json.loads(output.splitlines()[-1])
    expected={"environment_version":SPEC.version,**{k:info[k] for k in ("steps","health","achievement_mask","episode_return")}}
    assert actual==expected,(actual,expected)
    result={"tape_sha256":hashlib.sha256(a.tape.read_bytes()).hexdigest(),"seed":int(header["seed"]),
            "action_count":len(actions),"python_sdl_final_state_exact":True,"state":actual}
    if a.checkpoint:
        import numpy as np
        import torch
        from terraria_lite.watch import _load,rollout
        torch.set_num_threads(1)
        act,kind=_load(a.checkpoint)
        torch.manual_seed(a.sample_seed);np.random.seed(a.sample_seed)
        reproduced,_,_=rollout(act,int(header["seed"]),False,int(header["max_steps"]))
        assert reproduced==actions,"Checkpoint/sample seed do not reproduce the tape"
        result["policy_provenance"]={"checkpoint":str(a.checkpoint.resolve()),
             "checkpoint_sha256":hashlib.sha256(a.checkpoint.read_bytes()).hexdigest(),
             "sample_seed":a.sample_seed,"model_kind":kind,"sampled_tape_exactly_reproduced":True}
    if a.analysis_binary:
        trace=json.loads(subprocess.check_output([str(a.analysis_binary.resolve()),str(a.tape.resolve())],text=True))
        assert trace["environment_version"]==SPEC.version
        assert trace["final_state"]=={k:info[k] for k in ("steps","health","achievement_mask","episode_return")}
        assert trace["tape_actions"]==len(actions)
        result["physical_trace"]=trace
        result["analysis_binary_sha256"]=hashlib.sha256(a.analysis_binary.read_bytes()).hexdigest()
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result))


if __name__=="__main__":main()
