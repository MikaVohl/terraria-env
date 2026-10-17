"""Offline JSON-lines model interface; no provider, credentials or API calls.

One action per request, one simulator tick. The model sees only RL observation
information plus public rules. This is a harness prototype, not a leaderboard.
"""
import argparse,json,re,sys,time
from pathlib import Path
from terraria_lite import SPEC,TerrariaLite
from terraria_lite.rules import player_knowledge
import terraria_lite

def tile_legend():
    # Static player knowledge from this exact checkout, never world state.
    header=(Path(terraria_lite.__file__).resolve().parents[2]/'include/tiles.h').read_text()
    table=header.split('TILE_INFO[TILE_COUNT] = {',1)[1].split('\n};',1)[0]
    names=re.findall(r'\{"([^"]+)"',table)
    assert len(names)==SPEC.tile_kinds-1
    return names+['unknown (unlit)']


class Session:
    def __init__(self, seed, max_steps=3000):
        if type(seed) is not int or not 0<=seed<2**64:raise ValueError('Seed must be an unsigned 64-bit integer')
        # No reuse of published/declared reserved test worlds for smoke tests.
        for lo,n in ((3000001,256),(7000001,128),(9000001,128),(11000001,128),(15000001,128)):
            if lo<=seed<lo+n:raise ValueError('Reserved test world: refuse prototype run')
        if not 1<=max_steps<=3000:raise ValueError('Primitive action budget must be 1..3000')
        self.env=TerrariaLite(max_steps=max_steps);self.obs,self.info=self.env.reset(seed=seed)
        self.ended=False;self.invalid_requests=0

    def packet(self):
        n=SPEC.cells*SPEC.tile_kinds;status=self.obs[n+SPEC.cells:]
        entities=status[SPEC.status_entity0:].reshape(SPEC.cells,4)
        return {'environment_version':SPEC.version,'steps':self.info['steps'],'score':self.info['achievements'],
            'terminated':self.ended,'tiles':self.obs[:n].reshape(SPEC.cells,SPEC.tile_kinds).argmax(-1).reshape(SPEC.view_h,SPEC.view_w).tolist(),
            'light':(self.obs[n:n+SPEC.cells]*15).round().astype(int).reshape(SPEC.view_h,SPEC.view_w).tolist(),
            'status':status[:SPEC.status_entity0].tolist(),
            'inventory':{name:int(round(float(status[SPEC.status_inv0+i])*SPEC.inventory_clip)) for i,name in enumerate(SPEC.item_names)},
            'achievements':[name for i,name in enumerate(SPEC.achievement_names) if status[SPEC.status_ach0+i]>.5],
            'visible_entities':[{'cell':i,'features':x.tolist()} for i,x in enumerate(entities) if x.any()],
            'legal_actions':[i for i,v in enumerate(self.env.action_mask()) if v],
            'invalid_requests':self.invalid_requests}

    def act(self, request):
        if self.ended:raise ValueError('Episode ended; cannot reset within scored session')
        action=request.get('action') if isinstance(request,dict) else None
        if isinstance(action,str):
            action=SPEC.action_names.index(action) if action in SPEC.action_names else None
        invalid=type(action) is not int or not 0<=action<SPEC.n_actions
        if invalid:self.invalid_requests+=1;action=0
        # Known but currently illegal actions are still physical attempts, not
        # silently replaced by a helpful legal or recipe action.
        self.obs,reward,term,trunc,self.info=self.env.step(action);self.ended=term or trunc
        return {**self.packet(),'reward':reward,'invalid_request':invalid,'executed_action':action}

    def close(self):self.env.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,default=9)
    p.add_argument('--max-steps',type=int,default=3000)
    p.add_argument('--out',type=Path,help='Exclusive local transcript; never overwrites an earlier run')
    a=p.parse_args()
    s=Session(a.seed,a.max_steps)
    log=None
    try:
        if a.out:log=a.out.open('x')
        def emit(response,request=None):
            if log:
                log.write(json.dumps({'seed':a.seed,'environment_version':SPEC.version,'monotonic_ns':time.monotonic_ns(),'request':request,'response':response,'provider_usage':None,'provider_cost':None})+'\n');log.flush()
            print(json.dumps(response),flush=True)
        emit({'protocol':'terraria-jsonl-v1','knowledge':player_knowledge(),
            'tile_names':tile_legend(),'observation_layout':{'view':[SPEC.view_w,SPEC.view_h],'unknown_tile':SPEC.unknown_tile,'status_entity0':SPEC.status_entity0,'status_inventory0':SPEC.status_inv0,'status_achievements0':SPEC.status_ach0,'inventory_clip':SPEC.inventory_clip},
            'view_anchor':{'row':SPEC.view_h//2,'column':SPEC.view_w//2,'meaning':'player left-feet cell'},
            'reach_actions':[{'mine_action':SPEC.mine_first+i,'place_action':SPEC.place_first+i,'dx':dx,'dy':dy} for i,(dx,dy) in enumerate(SPEC.reach_offsets)],
            'status_schema':{'initial_scalars':['health_fraction','mining_tier_fraction','facing','jump','fall','depth','horizontal_position','elapsed_time_fraction','max_health','weapon','armor','attack_cooldown','heal_cooldown','hurt_cooldown','air_jump_used','mine_cooldown','safe_time'],
                'then':'selected-placeable one-hot (10), item inventory counts/999, achievement bits; visible entity features follow separately',
                'entity_features':['blue_slime_presence','cave_bat_presence','health','movement_phase']},
            'tool_rules':'Independent iron/gold tool ownership, duplicates cost normal ingredients, automatically mine with strongest owned tier' if SPEC.version>=6 else 'Legacy tier ownership: use matching version rules',
            'action_budget':a.max_steps,'response_schema':{'action':'one integer ID or exact action name'},
            'invalid_requests':'malformed/out-of-range consumes one noop action; no multi-action macros',
            'observation':s.packet()})
        for line in sys.stdin:
            try:request=json.loads(line)
            except json.JSONDecodeError:request=None
            emit(s.act(request),line.rstrip('\n'))
            if s.ended:break
    finally:
        s.close()
        if log:log.close()


if __name__=='__main__':main()
