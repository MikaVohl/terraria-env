"""Inventory accumulation, legal-action opportunities and policy choices."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import torch
from terraria_lite import SPEC, TerrariaLite
from terraria_lite.scoring import score_masks
from terraria_lite.batch import NativeBatch
from terraria_lite.ppo_eval import load_agent


@torch.no_grad()
def diagnose(agent, seeds, sample_seed=54321, max_steps=0):
    torch.manual_seed(sample_seed)
    totals=np.zeros(SPEC.n_actions,np.int64); legal=np.zeros_like(totals)
    probability=np.zeros(SPEC.n_actions,np.float64); maxes=[]; records=[]
    held_steps=np.zeros(SPEC.n_items,np.int64)   # v10 EXPLICIT_TOOLS: item in hand per step
    inv0=SPEC.cells*(SPEC.tile_kinds+1)+SPEC.status_inv0
    for base in range(0,len(seeds),64):
        cohort=seeds[base:base+64]; envs=[TerrariaLite(max_steps=max_steps or None) for _ in cohort]
        try:
            obs=np.stack([e.reset(seed=s)[0] for e,s in zip(envs,cohort)])
            mask=np.stack([e.action_mask() for e in envs]); active=np.ones(len(envs),bool)
            peak=np.zeros((len(envs),SPEC.n_items),np.int32)
            opportunities=np.zeros((len(envs),SPEC.n_actions),np.int32)
            layer_steps=np.zeros((len(envs),3),np.int64)   # v9: surface/underground/caverns
            native=NativeBatch(envs)
            recurrent=hasattr(agent,"initial_state")
            if recurrent:
                state=agent.initial_state(len(envs),"cpu")
                done=torch.zeros(len(envs))
            for t in range(max_steps or SPEC.default_steps):
                inv=np.rint(obs[:,inv0:inv0+SPEC.n_items]**2*SPEC.inventory_clip).astype(np.int32)
                peak[active]=np.maximum(peak[active],inv[active])
                x=torch.from_numpy(obs); m=torch.from_numpy(mask)
                if recurrent:
                    features,state=agent.core_step(x,state,done)
                else:
                    features=agent.trunk(x)
                logits=agent.actor(features).masked_fill(~m,float("-inf"))
                dist=torch.distributions.Categorical(logits=logits)
                actions=dist.sample().numpy()
                legal+=mask[active].sum(0); probability+=dist.probs.numpy()[active].sum(0)
                totals+=np.bincount(actions[active],minlength=SPEC.n_actions)
                opportunities[active]+=mask[active]
                if SPEC.status_layer0 is not None:
                    s0=SPEC.cells*(SPEC.tile_kinds+1)+SPEC.status_layer0
                    layer_steps[active]+=(obs[active,s0:s0+3]>.5)
                if SPEC.status_held0 is not None:
                    h0=SPEC.cells*(SPEC.tile_kinds+1)+SPEC.status_held0
                    held_steps+=np.bincount(obs[active,h0:h0+SPEC.n_items].argmax(1),minlength=SPEC.n_items)
                _,te,tr=native.step(actions,obs,mask)
                # Include pickups/crafts on an episode's final action too.
                inv=np.rint(obs[:,inv0:inv0+SPEC.n_items]**2*SPEC.inventory_clip).astype(np.int32)
                peak[active]=np.maximum(peak[active],inv[active])
                for i in np.flatnonzero(active & (te|tr)):
                    rec={"seed":cohort[i],"info":envs[i]._info(),
                         "inventory_peak":peak[i].tolist(),"legal_steps":opportunities[i].tolist()}
                    if SPEC.status_night is not None:
                        s=SPEC.cells*(SPEC.tile_kinds+1)
                        rec.update(layer_steps=layer_steps[i].tolist(),
                                   died_at_night=bool(te[i] and obs[i,s+SPEC.status_night]>.5),
                                   boss_present_at_end=bool(obs[i,s+SPEC.status_boss]>.5))
                    records.append(rec)
                    active[i]=False
                if not active.any(): break
            maxes.extend(peak)
        finally:
            for e in envs: e.close()
    maxes=np.asarray(maxes)
    return {"episodes":len(records),"inventory_peak":{name:{"mean":float(maxes[:,i].mean()),
                "median":float(np.median(maxes[:,i])),"max":int(maxes[:,i].max())} for i,name in enumerate(SPEC.item_names)},
            "actions":{name:{"legal_steps":int(legal[i]),"chosen":int(totals[i]),
                  "mean_probability_when_legal":float(probability[i]/max(1,legal[i])),
                  "episodes_with_opportunity":sum(r["legal_steps"][i]>0 for r in records)}
                       for i,name in enumerate(SPEC.action_names)},"records":records,
            # v9: tiered score, night deaths and time per layer (absent before v9)
            **({"score":score_masks([r["info"]["achievement_mask"] for r in records]),
                "deaths_at_night":sum(r["died_at_night"] for r in records),
                "layer_step_fraction":(lambda t:{k:float(v) for k,v in zip(("surface","underground","caverns"),t/max(1,t.sum()))})(
                    np.sum([r["layer_steps"] for r in records],0))}
               if SPEC.status_night is not None else {}),
            # v10: Demon Altar found (within crafting range) per episode
            **({"altar_found_rate":float(np.mean([r["info"]["achievement_mask"]>>SPEC.achievement_names.index("find a Demon Altar")&1
                                                  for r in records]))}
               if "find a Demon Altar" in SPEC.achievement_names else {}),
            # v10: share of steps each item was in hand (absent without EXPLICIT_TOOLS)
            **({"held_fraction":{name:float(v) for name,v in zip(SPEC.item_names,held_steps/max(1,held_steps.sum())) if v}}
               if SPEC.status_held0 is not None else {})}


def main():
    p=argparse.ArgumentParser(); p.add_argument("checkpoint",type=Path)
    p.add_argument("--out",type=Path,required=True); p.add_argument("--episodes",type=int,default=128)
    p.add_argument("--seed-start",type=int,default=2_000_001)
    p.add_argument("--max-steps",type=int,default=0,help="episode step limit; 0 = game default")
    a=p.parse_args(); torch.set_num_threads(6)
    result=diagnose(load_agent(a.checkpoint),list(range(a.seed_start,a.seed_start+a.episodes)),max_steps=a.max_steps)
    result["max_steps"]=a.max_steps or SPEC.default_steps
    result["seed_range"]=[a.seed_start,a.seed_start+a.episodes-1]
    result["sample_seed"]=54321
    result["environment_version"]=SPEC.version
    result["checkpoint_sha256"]=hashlib.sha256(a.checkpoint.read_bytes()).hexdigest()
    result["diagnostic_source_sha256"]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"wood":result["inventory_peak"]["wood"],"bench":result["actions"]["craft workbench"],
                      **({"weighted_score":result["score"].get("weighted_score")} if "score" in result else {}),
                      **({"lens_peak":result["inventory_peak"]["lens"]} if "lens" in SPEC.item_names else {}),
                      **({"altar_found_rate":result["altar_found_rate"]} if "altar_found_rate" in result else {})}))


if __name__=="__main__": main()
