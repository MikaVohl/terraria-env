"""Matched-data network microbenchmarks; not learning-quality experiments."""
import json
import time
import torch
from terraria_lite import SPEC
from terraria_lite.ppo_agent import ActorCritic

def sync(device):
    if device=='mps':torch.mps.synchronize()

for device in ['cpu','mps']:
    if device=='mps' and not torch.backends.mps.is_available():continue
    for threads in ([2,6] if device=='cpu' else [2]):
        torch.set_num_threads(threads)
        for mode,sizes in [('inference',[16,64,256]),('update',[512,2048,8192])]:
            for n in sizes:
                torch.manual_seed(321)
                model=ActorCritic(SPEC.obs_size,SPEC.n_actions).to(device)
                x=torch.randn(n,SPEC.obs_size).to(device)
                mask=torch.ones(n,SPEC.n_actions,dtype=torch.bool,device=device)
                actions=(torch.arange(n)%SPEC.n_actions).to(device)
                opt=torch.optim.Adam(model.parameters(),lr=3e-4,eps=1e-5)
                def step():
                    if mode=='inference':
                        with torch.no_grad():model.act(x,mask=mask)[0].cpu()
                    else:
                        _,logp,entropy,value=model.act(x,action=actions,mask=mask)
                        # PPO-shaped matched arithmetic; fixed old logp/targets.
                        ratio=(logp+3.5).exp()
                        loss=-torch.minimum(ratio,ratio.clamp(.8,1.2)).mean()+.5*value.square().mean()-.01*entropy.mean()
                        opt.zero_grad(set_to_none=True);loss.backward()
                        torch.nn.utils.clip_grad_norm_(model.parameters(),.5);opt.step()
                for _ in range(5):step()
                sync(device);start=time.perf_counter()
                repeats=50 if mode=='inference' else 20
                for _ in range(repeats):step()
                sync(device);elapsed=time.perf_counter()-start
                print(json.dumps({'device':device,'threads':threads,'mode':mode,'batch':n,'ms_per_call':elapsed/repeats*1000,'samples_per_second':n*repeats/elapsed}),flush=True)
