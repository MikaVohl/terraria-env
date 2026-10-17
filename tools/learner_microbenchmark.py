"""Read-only workload pilot: CPU thread counts, not learning-quality evidence."""
import argparse,json,time,statistics
from pathlib import Path
import numpy as np
import torch
from terraria_lite import SPEC,TerrariaLite
from terraria_lite.ppo_agent import ActorCritic

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    if a.out.exists():raise ValueError('Output exists')
    envs=[TerrariaLite() for _ in range(64)]
    try:x=np.stack([e.reset(seed=i)[0] for i,e in enumerate(envs)]);m=np.stack([e.action_mask() for e in envs])
    finally:
        for e in envs:e.close()
    rows=[]
    for threads in [1,2,3,4,6]:
        torch.set_num_threads(threads);torch.manual_seed(1)
        net=ActorCritic(SPEC.obs_size,SPEC.n_actions);opt=torch.optim.Adam(net.parameters(),lr=.0003,eps=1e-5)
        obs=torch.from_numpy(np.tile(x,(32,1)));mask=torch.from_numpy(np.tile(m,(32,1)))
        obs64=obs[:64];mask64=mask[:64]
        action=mask.to(torch.int64).argmax(-1);adv=torch.linspace(-1,1,len(obs));returns=torch.ones(len(obs))
        with torch.no_grad():_,old,_,_=net.act(obs,action,mask)
        inference=[];updates=[]
        for i in range(35):
            t=time.perf_counter()
            with torch.no_grad():net.act(obs64,mask=mask64)
            if i>=5:inference.append(time.perf_counter()-t)
            t=time.perf_counter();_,lp,entropy,value=net.act(obs,action,mask)
            ratio=(lp-old).exp();loss=torch.maximum(-adv*ratio,-adv*ratio.clamp(.8,1.2)).mean()+.5*(value-returns).square().mean()-.01*entropy.mean()
            opt.zero_grad(set_to_none=True);loss.backward();torch.nn.utils.clip_grad_norm_(net.parameters(),.5);opt.step()
            if i>=5:updates.append(time.perf_counter()-t)
        rows.append({'threads':threads,'inference64_seconds':statistics.median(inference),'update2048_seconds':statistics.median(updates)})
    selected=min(rows,key=lambda r:r['update2048_seconds'])['threads']
    result={'environment_version':SPEC.version,'schema':[SPEC.obs_size,SPEC.n_actions],'device':'cpu','measurements':rows,'selected_threads':selected,'note':'Real reset observations, synthetic targets; isolated CPU pilot, not full training SPS or a GPU benchmark. Thread choice made without validation scores.'}
    a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
