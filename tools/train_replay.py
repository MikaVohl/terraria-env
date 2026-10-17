"""Fresh-budget Double DQN pilot with saved provenance; no reserved testing."""
import argparse
from dataclasses import asdict
import hashlib,json,shutil
from pathlib import Path
import torch
import terraria_lite
from terraria_lite import SPEC
from terraria_lite.replay_agent import Config,train
from terraria_lite.ppo_eval import evaluate

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--steps',type=int,default=4194304)
    p.add_argument('--seed',type=int,required=True);p.add_argument('--threads',type=int,default=3)
    p.add_argument('--validation-seed-start',type=int,default=13000001)
    p.add_argument('--validation-episodes',type=int,default=32)
    a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False);torch.set_num_threads(a.threads)
    cfg=Config(steps=a.steps,seed=a.seed);package=Path(terraria_lite.__file__).parent
    files=[*package.glob('*.py'),*package.glob('libterraria.*')];snapshot=a.out/'implementation';snapshot.mkdir()
    for f in files:shutil.copy2(f,snapshot/f.name)
    protocol={'config':asdict(cfg),'environment_version':SPEC.version,'obs_size':SPEC.obs_size,'n_actions':SPEC.n_actions,'torch_threads':a.threads,'implementation_sha256':{f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in files},'validation_seeds':[a.validation_seed_start,a.validation_seed_start+a.validation_episodes-1],'sampler_seed':54321,'evaluation':'greedy masked Q policy','reward':'new achievements +1; death -1','deadline_future_value':'zero','replay':'uniform, losslessly compressed observations, n-step Double DQN','demonstrations':False,'strategic_masks':False,'shaping':False,'reserved_tests_consumed':False,'resume_or_warmstart':False,'caveat':'Standard uncorrected n-step off-policy targets; this package comparison does not isolate replay causally.'}
    (a.out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');curve=[]
    def callback(q,steps,profile):
        if steps%1048576:return
        torch.save({'model':q.state_dict(),'architecture':'double_dqn','hidden':512,'environment_version':SPEC.version,'obs_size':SPEC.obs_size,'n_actions':SPEC.n_actions},a.out/f'step-{steps}.pt')
        with torch.random.fork_rng():e=evaluate(q,list(range(a.validation_seed_start,a.validation_seed_start+a.validation_episodes)),greedy=True,sample_seed=54321)
        curve.append({'steps':steps,'profile':profile,'evaluation':e});(a.out/'curve.json').write_text(json.dumps(curve,indent=2)+'\n')
        print(f"{a.out.name}: {steps:,} {e['mean_achievements']:.3f}/32 furnace={e['hits'].get('craft furnace',0)} loss={profile['loss']}",flush=True)
    summary=train(cfg,callback);(a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

if __name__=='__main__':main()
