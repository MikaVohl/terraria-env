"""Check observation fairness/action accounting; never invokes an LLM."""
import numpy as np
from terraria_lite import SPEC,TerrariaLite
from llm_protocol import Session

def main():
    session=Session(9,10);reference=TerrariaLite(max_steps=10);obs,_=reference.reset(seed=9)
    try:
        packet=session.packet();assert packet['environment_version']==SPEC.version and packet['steps']==0
        n=SPEC.cells*SPEC.tile_kinds
        reconstructed=np.zeros_like(obs);grid=reconstructed[:n].reshape(SPEC.cells,SPEC.tile_kinds)
        tiles=np.array(packet['tiles']).reshape(-1);grid[np.arange(SPEC.cells),tiles]=1
        reconstructed[n:n+SPEC.cells]=(np.array(packet['light']).reshape(-1)/15).astype(np.float32)
        status=reconstructed[n+SPEC.cells:];status[:SPEC.status_entity0]=packet['status']
        for entity in packet['visible_entities']:status[SPEC.status_entity0+4*entity['cell']:SPEC.status_entity0+4*entity['cell']+4]=entity['features']
        np.testing.assert_array_equal(reconstructed,obs)
        for action in [None,{'actions':[1,2]}, {'action':True},{'action':999}, {'action':'noop'}, {'action':1}]:
            out=session.act(action);executed=out['executed_action'];r=reference.step(executed)
            np.testing.assert_array_equal(session.obs,r[0]);assert session.info==r[4]
        assert session.invalid_requests==4 and session.info['steps']==6
        while not session.ended:session.act({'action':0})
        assert session.info['steps']==10
        try:session.act({'action':0})
        except ValueError:pass
        else:raise AssertionError('Extra step after deadline')
        for seed in (3000001,7000001,9000001,11000001,15000001,2**64+11000001):
            try:Session(seed)
            except ValueError:pass
            else:raise AssertionError('Reserved split consumed')
        print('LLM protocol tests passed: exact RL-information roundtrip, action costs, invalid requests, deadline, reserved-world guards; no APIs called')
    finally:session.close();reference.close()

if __name__=='__main__':main()
