"""Version-neutral scalar/vector throughput probe. Emits JSON evidence."""
import argparse
import json
import time
import numpy as np
from terraria_lite import SPEC, TerrariaLite

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--steps",type=int,default=65536)
    p.add_argument("--envs",type=int,default=64)
    p.add_argument("--workers",type=int,default=0)
    a=p.parse_args(); samples=[]; actual=a.steps//a.envs*a.envs
    envs=[TerrariaLite() for _ in range(a.envs)]
    native=None
    if a.workers:
        from terraria_lite.batch import NativeBatch
        native=NativeBatch(envs,a.workers)
    obs=np.zeros((a.envs,SPEC.obs_size),np.float32)
    masks=np.zeros((a.envs,SPEC.n_actions),bool)
    try:
        for repeat in range(3):
            rng=np.random.default_rng(54321)
            # Reset before timing to exclude initial world construction, but
            # subsequent episode resets are part of measured rollout cost.
            for i,e in enumerate(envs): e.reset(seed=100+i); masks[i]=e.action_mask()
            start=time.perf_counter()
            for t in range(actual//a.envs):
                actions=np.where(masks,rng.random(masks.shape),-1).argmax(1)
                if native:
                    _,term,trunc=native.step(actions,obs,masks)
                    for i in np.flatnonzero(term|trunc):
                        envs[i].reset(seed=100000+t*a.envs+int(i)); masks[i]=envs[i].action_mask()
                else:
                    for i,e in enumerate(envs):
                        _,_,te,tr,_=e.step(int(actions[i]))
                        if te or tr: e.reset(seed=100000+t*a.envs+i)
                        masks[i]=e.action_mask()
            samples.append(time.perf_counter()-start)
    finally:
        for e in envs: e.close()
    print(json.dumps({"environment_version":getattr(SPEC,"version",1),
        "transitions":actual,"envs":a.envs,"workers":a.workers,
        "seconds":samples,"median_sps":actual/float(np.median(samples))}))
if __name__=="__main__": main()
