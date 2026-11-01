import hashlib, numpy as np, sys, json
from terraria_lite import TerrariaLite, SPEC
import os; h=hashlib.sha256(); W,H=int(os.environ.get("PROBE_WORLD_W","128")),96
counts={'iron ore':[], 'gold ore':[], 'log':[], 'wood':[]}
e=TerrariaLite()
for s in list(range(256))+list(range(23000001,23000129)):
    obs,_=e.reset(seed=s); st=e.save_state(); h.update(st); h.update(obs.tobytes())
    t=np.frombuffer(st[:W*H],np.uint8)
    if s>=23000001:
        for k in counts: counts[k].append(int((t==SPEC.tile_names.index(k)).sum()))
rng=np.random.default_rng(0); envs=[TerrariaLite() for _ in range(8)]
for i,x in enumerate(envs): x.reset(seed=500+i)
for t in range(2000):
    for i,x in enumerate(envs):
        o,r,te,tr,info=x.step(int(rng.choice(np.flatnonzero(x.action_mask()))))
        h.update(o.tobytes()); h.update(np.float32(r).tobytes())
        if te or tr: x.reset(seed=10000+t*8+i)
print(json.dumps({'hash':h.hexdigest()[:16],'view':[SPEC.view_w,SPEC.view_h],'obs':SPEC.obs_size,**{k:[int(np.median(v)),min(v),max(v)] for k,v in counts.items()}}))
