"""Verify old primitive-action trajectories agree between v6 and v7."""
import argparse,json,os,subprocess,sys
from pathlib import Path

CODE = '''
import hashlib,json,numpy as np
from terraria_lite import TerrariaLite,SPEC
h=hashlib.sha256();rng=np.random.default_rng(91);env=TerrariaLite(max_steps=317);steps=0
try:
 for seed in range(100):
  obs,info=env.reset(seed=seed)
  for t in range(317):
   mask=env.action_mask()[:73];action=int(rng.choice(np.flatnonzero(mask)))
   obs,reward,te,tr,info=env.step(action);h.update(obs.tobytes());h.update(mask.tobytes());h.update(json.dumps([action,reward,te,tr,info],sort_keys=True).encode());steps+=1
   if te or tr:break
finally:env.close()
print(json.dumps({'version':SPEC.version,'obs_size':SPEC.obs_size,'actions':SPEC.n_actions,'transitions':steps,'sha256':h.hexdigest()}))
'''

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--study',type=Path,required=True);a=p.parse_args();root=a.study.resolve()
    rows=[]
    for version in ('v6','v7'):
        env={**os.environ,'PYTHONPATH':str(root/version/'python'),'TERRARIA_LITE_LIB':str(root/version/'python/terraria_lite/libterraria.dylib')}
        rows.append(json.loads(subprocess.check_output([sys.executable,'-c',CODE],env=env,text=True)))
    assert rows[0]['sha256']==rows[1]['sha256'] and rows[0]['transitions']==rows[1]['transitions']
    result={'passed':True,'versions':rows,'note':'Same seeds/legal draws over original 73 actions; v7 extra selection actions excluded only for this parity test, never for training.'}
    (root/'interface-parity.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
