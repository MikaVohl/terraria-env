"""Cross-checkout transition evidence for simulator optimization parity."""
import hashlib
import json
import numpy as np
from terraria_lite import TerrariaLite
digest=hashlib.sha256(); rng=np.random.default_rng(91); steps=0
env=TerrariaLite(max_steps=317)
try:
    for seed in range(100):
        obs,info=env.reset(seed=seed)
        for t in range(317):
            mask=env.action_mask()
            action=int(rng.choice(np.flatnonzero(mask)))
            obs,reward,te,tr,info=env.step(action)
            digest.update(obs.tobytes()); digest.update(mask.tobytes())
            digest.update(json.dumps([action,reward,te,tr,info],sort_keys=True).encode())
            steps+=1
            if te or tr: break
finally: env.close()
print(json.dumps({"transitions":steps,"sha256":digest.hexdigest()}))
