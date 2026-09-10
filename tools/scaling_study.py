"""Two independent, auditable large-batch unshaped PPO runs."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    p.add_argument('--child',choices=['train','eval']);p.add_argument('--steps',type=int)
    p.add_argument('--checkpoint',type=Path);a=p.parse_args();out=a.out.resolve()
    if a.child:
        import torch
        torch.set_num_threads(2)
        if a.child=='eval':
            from terraria_lite.ppo_eval import evaluate,load_agent
            report=evaluate(load_agent(a.checkpoint),list(range(1000001,1000129)),sample_seed=54321,num_envs=64)
            dest=a.checkpoint.with_suffix('.eval.json');dest.write_text(json.dumps(report))
            print(json.dumps({'event':'evaluation','checkpoint':a.checkpoint.name,**{k:v for k,v in report.items() if k not in ('records','hits')}}),flush=True)
            return
        from terraria_lite import _lib
        import ctypes
        import terraria_lite.ppo_agent as ppo
        from perf_probe import Batch
        assert torch.backends.mps.is_available()
        class CheckedSamplingPolicy(ppo.ActorCritic):
            def act(self,x,action=None,mask=None):
                h=self.trunk(x);logits=self.actor(h)
                if mask is not None:logits=logits.masked_fill(~mask,float('-inf'))
                dist=torch.distributions.Categorical(logits=logits)
                if action is None:
                    # Avoid the invalid categorical sample observed on MPS.
                    # Network/gradients remain on GPU; the distribution and
                    # legal mask are unchanged. CPU multinomial samples it.
                    probs=dist.probs.detach().cpu()
                    sampled=torch.multinomial(probs,1)
                    assert bool((probs.gather(1,sampled)>0).all()),'zero-probability action'
                    if mask is not None:
                        assert bool(mask.detach().cpu().gather(1,sampled).all()),'illegal action'
                    action=sampled.squeeze(1).to(logits.device)
                return action,dist.log_prob(action),dist.entropy(),self.critic(h).squeeze(-1)
        ppo.ActorCritic=CheckedSamplingPolicy
        _lib.probe_workers.argtypes=[ctypes.c_int];_lib.probe_workers(4)
        ppo.VecTerraria=Batch
        cfg=ppo.Config(total_steps=a.steps,num_envs=256,rollout=128,device='mps',seed=101,quiet=True,save='',init='',progress_coef=0.)
        (out/'config.json').write_text(json.dumps(asdict(cfg),indent=2))
        actual=a.steps//cfg.batch*cfg.batch
        targets=sorted({min(n,actual) for n in [1_000_000,4_000_000,8_000_000,16_000_000,24_000_000,a.steps]})
        torch.mps.synchronize();start=time.perf_counter();last=start
        def checkpoint(agent,steps,timing):
            nonlocal last
            now=time.perf_counter()
            if targets and steps>=targets[0]:
                targets.pop(0);torch.mps.synchronize()
                state={k:v.detach().cpu() for k,v in agent.state_dict().items()}
                assert all(torch.isfinite(v).all() for v in state.values()),'nonfinite model'
                path=out/f'step-{steps}.pt';torch.save(state,path.with_suffix('.tmp'));path.with_suffix('.tmp').replace(path)
                print(json.dumps({'event':'checkpoint','steps':steps,'wall_seconds':time.perf_counter()-start,'path':str(path)}),flush=True)
            if now-last>=45:
                print(json.dumps({'event':'progress','steps':steps,'requested':a.steps,'wall_seconds':now-start}),flush=True);last=now
        report=ppo.train(cfg,checkpoint_callback=checkpoint)
        torch.mps.synchronize();report['synchronized_wall_seconds']=time.perf_counter()-start
        (out/'training.json').write_text(json.dumps(report,indent=2))
        return
    out.mkdir(parents=True,exist_ok=False)
    root=Path.cwd();sources=[*root.glob('src/*.[ch]'),*root.glob('include/*.h'),*root.glob('tools/*.py'),*root.glob('tools/*.c'),*root.glob('python/terraria_lite/*.py'),root/'Makefile',root/'pyproject.toml',root/'uv.lock',root/'LARGE_SCALE_STUDY.md',root/'PERFORMANCE_EXPLORATION.md']
    hashes={}
    for src in sources:
        rel=src.relative_to(root);dest=out/'source'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(src.read_bytes());hashes[str(rel)]=hashlib.sha256(src.read_bytes()).hexdigest()
    (out/'manifest.json').write_text(json.dumps({'platform':platform.platform(),'source_sha256':hashes,'training_seed':101,'validation_worlds':[1000001,1000128],'evaluation_sample_seed':54321,'budgets':[16000000,32000000],'test_set':'unused','protocol':'LARGE_SCALE_STUDY.md'},indent=2))
    build=['cc','-std=c11','-O2','-g','-fPIC','-Iinclude','-Isrc']
    subprocess.run(build+['-Dlight_recompute=light_reference','-c','src/light.c','-o',str(out/'light-ref.o')],check=True)
    for lib in ['reference','cached']:
        subprocess.run(build+['-shared']+(['-DPROBE_CACHE'] if lib=='cached' else [])+['src/sim.c','src/worldgen.c','src/obs.c','src/capi.c','tools/perf_probe.c',str(out/'light-ref.o'),'-o',str(out/(lib+'.dylib'))],check=True)
    for budget in [16000000,32000000]:
        run=out/str(budget);run.mkdir()
        env={**os.environ,'TERRARIA_LITE_LIB':str(out/'cached.dylib')}
        subprocess.run([sys.executable,__file__,'--out',str(run),'--child','train','--steps',str(budget)],env=env,check=True)
        for ckpt in sorted(run.glob('step-*.pt'),key=lambda x:int(x.stem.split('-')[1])):
            # Separate processes, original lighting, CPU eval: no cache lifecycle
            # accumulation and no evaluation random state leaking into training.
            subprocess.run([sys.executable,__file__,'--out',str(run),'--child','eval','--checkpoint',str(ckpt)],env={**env,'TERRARIA_LITE_LIB':str(out/'reference.dylib')},check=True)
    (out/'COMPLETE').write_text('Both runs and all checkpoint evaluations completed.\n')

if __name__=='__main__':main()
