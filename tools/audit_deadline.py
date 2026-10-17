"""Read-only finite-deadline critic audit; never changes policy or game rules."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from terraria_lite import SPEC, TerrariaLite
from terraria_lite.batch import NativeBatch
from terraria_lite.ppo_eval import load_agent


@torch.no_grad()
def audit(agent, seeds):
    torch.manual_seed(54321)
    records=[]
    for start in range(0,len(seeds),64):
        cohort=seeds[start:start+64]
        envs=[TerrariaLite() for _ in cohort]
        try:
            obs=np.stack([e.reset(seed=s)[0] for e,s in zip(envs,cohort)])
            mask=np.stack([e.action_mask() for e in envs]); active=np.ones(len(envs),bool)
            native=NativeBatch(envs,workers=4)
            recurrent=hasattr(agent,"initial_state")
            if recurrent:
                state=agent.initial_state(len(envs),"cpu"); done=torch.zeros(len(envs))
            while active.any():
                x=torch.from_numpy(obs)
                if recurrent:
                    h,state=agent.core_step(x,state,done)
                else:
                    h=agent.trunk(x)
                logits=agent.actor(h).masked_fill(~torch.from_numpy(mask),float("-inf"))
                action=torch.distributions.Categorical(logits=logits).sample().numpy()
                _,term,trunc=native.step(action,obs,mask)
                ended=np.flatnonzero(active & (term|trunc))
                if not len(ended): continue
                if recurrent:
                    sliced=tuple(s[:,ended].contiguous() for s in state)
                    value,_=agent.value_step(torch.from_numpy(obs[ended]),sliced,torch.zeros(len(ended)))
                else:
                    value=agent.value(torch.from_numpy(obs[ended]))
                for lane,v in zip(ended,value.tolist()):
                    records.append({"seed":cohort[lane],**envs[lane]._info(),
                        "deadline":bool(trunc[lane] and not term[lane]),"final_critic_value":v})
                active[ended]=False
        finally:
            for e in envs:e.close()
    values=[r["final_critic_value"] for r in records if r["deadline"]]
    return {"episodes":len(records),"deadline_episodes":len(values),
            "mean_achievements":float(np.mean([r["achievements"] for r in records])),
            "deadline_value_mean":float(np.mean(values)) if values else None,
            "deadline_value_min":min(values) if values else None,
            "deadline_value_max":max(values) if values else None,
            "deadline_value_quantiles":np.quantile(values,[.1,.5,.9]).tolist() if values else [],
            "records":records}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("checkpoint",type=Path); p.add_argument("--out",type=Path,required=True)
    p.add_argument("--seed-start",type=int,required=True); p.add_argument("--episodes",type=int,default=128)
    a=p.parse_args();torch.set_num_threads(6)
    if a.out.exists():raise ValueError("Audit output exists")
    result=audit(load_agent(a.checkpoint),list(range(a.seed_start,a.seed_start+a.episodes)))
    result.update(environment_version=SPEC.version,seed_range=[a.seed_start,a.seed_start+a.episodes-1],
                  checkpoint_sha256=hashlib.sha256(a.checkpoint.read_bytes()).hexdigest(),sample_seed=54321,
                  note="Terminal value must be zero for the finite objective. These are learned critic predictions, not measured future rewards. Validation diagnostic only.")
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({k:v for k,v in result.items() if k!="records"}))


if __name__=="__main__":main()
