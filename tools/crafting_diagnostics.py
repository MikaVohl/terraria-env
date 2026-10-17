"""Joint prerequisites and resource/station events on diagnostic worlds only.

The observer reads true station positions for attribution, never policy input.
No demonstrations, rewards, masks, state mutations or recipe controllers.
"""
import argparse
from collections import Counter
import ctypes as C
import hashlib
import json
from pathlib import Path
import time
import numpy as np
import torch
from terraria_lite import SPEC,TerrariaLite
from terraria_lite.batch import NativeBatch
from terraria_lite.ppo_agent import sample_categorical
from terraria_lite.ppo_eval import load_agent

FIELDS=['wood','stone','torch','bench_inventory','furnace_inventory','anvil_inventory',
        'bench_near','furnace_near','anvil_near','selected_item','x','y',
        'physical_bench_spaces','physical_furnace_spaces','nearest_bench_distance',
        'world_benches','steps','health']
GATES=['wood>=4','stone>=20','torches>=3','workbench_near']

def gate_code(a):
    return (a[:,0]>=4).astype(np.int32)+2*(a[:,1]>=20)+4*(a[:,2]>=3)+8*a[:,6]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('checkpoint',type=Path);p.add_argument('--probe',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--episodes',type=int,default=128)
    p.add_argument('--seed-start',type=int,default=8000001);p.add_argument('--threads',type=int,default=1)
    p.add_argument('--greedy',action='store_true',help='Match greedy Q-policy evaluation; no categorical sampling')
    a=p.parse_args()
    if a.out.exists():raise ValueError('Diagnostic output exists; use a fresh path')
    probe=C.CDLL(str(a.probe.resolve()));probe.cp_fields.restype=C.c_int;probe.cp_version.restype=C.c_int
    probe.cp_selftest.restype=C.c_int;assert probe.cp_selftest()==1
    assert probe.cp_fields()==len(FIELDS) and probe.cp_version()==SPEC.version
    probe.cp_read.argtypes=[C.c_void_p,C.c_void_p];probe.cp_read.restype=None
    torch.set_num_threads(a.threads);agent=load_agent(a.checkpoint);torch.manual_seed(54321)
    furnace=SPEC.action_names.index('craft furnace');bench_item=SPEC.item_names.index('workbench')
    ach0=SPEC.cells*(SPEC.tile_kinds+1)+SPEC.status_ach0
    furnace_ach=SPEC.achievement_names.index('craft furnace')
    records=[];start=time.perf_counter()
    with torch.no_grad():
      for base in range(0,a.episodes,64):
        seeds=list(range(a.seed_start+base,a.seed_start+min(base+64,a.episodes)))
        envs=[TerrariaLite() for _ in seeds];n=len(envs)
        try:
          obs=np.stack([e.reset(seed=s)[0] for e,s in zip(envs,seeds)])
          mask=np.stack([e.action_mask() for e in envs]);batch=NativeBatch(envs)
          active=np.ones(n,bool);snap=np.zeros((n,len(FIELDS)),np.int32)
          hist=np.zeros((n,16),np.int64);after_stone=np.zeros_like(hist)
          before_furnace=np.zeros_like(hist);before_furnace_stone=np.zeros_like(hist)
          pre_sinks=[Counter() for _ in seeds]
          stats=[Counter() for _ in seeds];wood_sinks=[Counter() for _ in seeds]
          events=[[] for _ in seeds];first=np.full(n,-1,np.int32)
          was_ready=np.zeros(n,bool);previous_bench_near=np.zeros(n,bool)
          recurrent=hasattr(agent,'initial_state')
          if recurrent:state=agent.initial_state(n,'cpu');done=torch.zeros(n)
          for tick in range(SPEC.default_steps):
            for i,e in enumerate(envs):probe.cp_read(e._h,snap[i].ctypes.data)
            codes=gate_code(snap)
            assert np.array_equal(codes[active]==15,mask[active,furnace]),'Observer/handler legality mismatch'
            x=torch.from_numpy(obs);m=torch.from_numpy(mask)
            if recurrent:features,state=agent.core_step(x,state,done)
            else:features=agent.trunk(x)
            dist=torch.distributions.Categorical(logits=agent.actor(features).masked_fill(~m,float('-inf')))
            actions=(dist.logits.argmax(-1) if a.greedy else sample_categorical(dist,m)).numpy()
            probs=(np.eye(SPEC.n_actions,dtype=np.float32)[actions] if a.greedy else dist.probs.numpy())
            before=snap.copy();live=np.flatnonzero(active)
            unearned=obs[:,ach0+furnace_ach]<.5
            for i in live:
              c=int(codes[i]);hist[i,c]+=1
              if snap[i,1]>=20:after_stone[i,c]+=1
              if unearned[i]:
                before_furnace[i,c]+=1
                if snap[i,1]>=20:before_furnace_stone[i,c]+=1
              ready=c==15
              if ready and first[i]<0:first[i]=tick
              if ready and not was_ready[i] and len(events[i])<60:
                events[i].append({'tick':tick,'event':'furnace_opportunity_starts','snapshot':dict(zip(FIELDS,map(int,snap[i])))})
              st=stats[i];st['observed_actions']+=1
              if ready:st['furnace_legal_steps']+=1;st['furnace_probability_sum']+=float(probs[i,furnace])
              st['furnace_chosen']+=int(actions[i]==furnace)
              if snap[i,3]>0:
                st['bench_owned_steps']+=1;st['bench_selected_steps']+=int(snap[i,9]==bench_item)
                st['bench_owned_with_space_steps']+=int(snap[i,12]>0)
              if snap[i,15]>0 and snap[i,6]==0:st['bench_exists_but_far_steps']+=1
              if previous_bench_near[i] and not snap[i,6]:st['left_bench_range']+=1
              previous_bench_near[i]=bool(snap[i,6]);was_ready[i]=ready
            _,te,tr=batch.step(actions,obs,mask)
            for i in live:
              probe.cp_read(envs[i]._h,snap[i].ctypes.data)
              wood_loss=max(0,int(before[i,0]-snap[i,0]));action=SPEC.action_names[int(actions[i])]
              if wood_loss:
                wood_sinks[i][action]+=wood_loss
                if unearned[i]:pre_sinks[i][action]+=wood_loss
              if snap[i,15]>before[i,15]:stats[i]['bench_placements']+=int(snap[i,15]-before[i,15])
              if snap[i,15]<before[i,15]:stats[i]['bench_removals']+=int(before[i,15]-snap[i,15])
              if snap[i,0]>before[i,0]:stats[i]['wood_acquired']+=int(snap[i,0]-before[i,0])
              if wood_loss and before[i,0]>=4 and snap[i,0]<4:
                stats[i]['wood_crossed_below_furnace_threshold']+=1
                if len(events[i])<60:events[i].append({'tick':tick+1,'event':'wood_below_four','action':action,'wood_before':int(before[i,0]),'wood_after':int(snap[i,0])})
              if te[i] or tr[i]:
                active[i]=False
                records.append({'seed':seeds[i],'info':envs[i]._info(),'gate_steps':hist[i].tolist(),
                    'gate_steps_after_stone_sufficient':after_stone[i].tolist(),'first_furnace_opportunity':int(first[i]),
                    'gate_steps_before_first_furnace':before_furnace[i].tolist(),
                    'gate_steps_before_first_furnace_stone_sufficient':before_furnace_stone[i].tolist(),
                    'wood_consumed_before_first_furnace':dict(pre_sinks[i]),
                    'counters':dict(stats[i]),'wood_consumed_by_action':dict(wood_sinks[i]),'events':events[i],
                    'final_snapshot':dict(zip(FIELDS,map(int,snap[i])))})
            if not active.any():break
        finally:
          for e in envs:e.close()
    counters=Counter();sinks=Counter()
    for z in records:counters.update(z['counters']);sinks.update(z['wood_consumed_by_action'])
    gates=np.sum([z['gate_steps'] for z in records],axis=0).tolist()
    stones=np.sum([z['gate_steps_after_stone_sufficient'] for z in records],axis=0).tolist()
    pre=np.sum([z['gate_steps_before_first_furnace'] for z in records],axis=0).tolist()
    pre_stone=np.sum([z['gate_steps_before_first_furnace_stone_sufficient'] for z in records],axis=0).tolist()
    pre_wood=Counter()
    for z in records:pre_wood.update(z['wood_consumed_before_first_furnace'])
    result={'environment_version':SPEC.version,'checkpoint':str(a.checkpoint.resolve()),
        'checkpoint_sha256':hashlib.sha256(a.checkpoint.read_bytes()).hexdigest(),
        'probe_sha256':hashlib.sha256(a.probe.read_bytes()).hexdigest(),
        'diagnostic_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'seed_range':[a.seed_start,a.seed_start+a.episodes-1],'sample_seed':54321,'episodes':len(records),
        'policy_mode':'greedy' if a.greedy else 'categorical sampled',
        'mean_achievements':float(np.mean([z['info']['achievements'] for z in records])),
        'gate_names':GATES,'gate_code':'bit set means prerequisite satisfied; 15 means all four',
        'gate_steps':gates,'gate_steps_after_stone_sufficient':stones,'counters':dict(counters),
        'gate_steps_before_first_furnace':pre,'gate_steps_before_first_furnace_stone_sufficient':pre_stone,
        'wood_consumed_before_first_furnace':dict(pre_wood),
        'opportunity_episodes':sum(z['first_furnace_opportunity']>=0 for z in records),
        'wood_consumed_by_action':dict(sinks),'wall_seconds':time.perf_counter()-start,
        'note':'Read-only white-box observer for attribution only; no hidden information enters policy, reward or masks. Counts are pre-action; events post-action. No reserved test worlds used.',
        'records':records}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'},indent=2))

if __name__=='__main__':main()
