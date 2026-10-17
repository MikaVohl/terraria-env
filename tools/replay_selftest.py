"""Regression checks; synthetic transitions are tests, never training data."""
import numpy as np
import torch
import tempfile
from pathlib import Path
from terraria_lite import SPEC,TerrariaLite
from terraria_lite.replay_agent import CompactReplay,BatchedNStep,targets

def main():
    envs=[TerrariaLite() for _ in range(4)]
    try:
        s=np.stack([e.reset(seed=i)[0] for i,e in enumerate(envs)]);m=np.stack([e.action_mask() for e in envs])
        r=CompactReplay(7);r.push(s,np.arange(4),np.ones(4),s,np.zeros(4),m)
        np.testing.assert_array_equal(r.decode(0,np.arange(4)),s)
        r.push(s,np.arange(4),np.ones(4),s,np.zeros(4),m);assert r.size==7 and r.pos==1
        np.testing.assert_array_equal(r.decode(0,np.array([4,5,6,0])),s)
        rows=[];n=BatchedNStep(3,.5,lambda *x:rows.append(x))
        for tick in range(4):
            ended=np.array([tick==1,False]);n.push(np.ones((2,1))*tick,np.zeros(2,int),np.array([1.,2.]),np.ones((2,1))*(tick+1),ended,np.ones((2,1),bool))
        n.flush();assert len(rows)==4
        np.testing.assert_allclose(rows[0][2],[1.5,3.5]);np.testing.assert_allclose(rows[0][4],[0,.125]);np.testing.assert_allclose(rows[0][3][:,0],[2,3])
        np.testing.assert_allclose(rows[1][2],[1,3.5]);np.testing.assert_allclose(rows[1][4],[0,.125])
        np.testing.assert_allclose(rows[-1][2],[1,2]);np.testing.assert_allclose(rows[-1][4],[.5,.5])
        class Q(torch.nn.Module):
            def __init__(self,x):super().__init__();self.x=torch.tensor(x,dtype=torch.float32)
            def forward(self,s):return self.x.expand(len(s),-1)
        y=targets(Q([1,10,100]),Q([8,3,999]),torch.zeros((2,1)),torch.tensor([2.,4.]),torch.tensor([.5,0]),torch.tensor([[True,True,False],[True,True,True]]))
        torch.testing.assert_close(y,torch.tensor([3.5,4.]))
        from terraria_lite.replay_agent import ReplayQ
        from terraria_lite.ppo_eval import load_agent
        from terraria_lite.watch import _load
        q=ReplayQ(64)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'q.pt'
            torch.save({'model':q.state_dict(),'architecture':'double_dqn','hidden':64,'environment_version':SPEC.version,'obs_size':SPEC.obs_size,'n_actions':SPEC.n_actions},path)
            restored=load_agent(path);torch.testing.assert_close(q(torch.from_numpy(s)),restored(torch.from_numpy(s)))
            act,kind=_load(path);assert kind=='double-dqn-greedy' and m[0,act(s[0],m[0],False)]
        print('Replay tests passed: exact compression/wrap, n-step lane endings/tails, legal Double DQN target, zero deadline bootstrap')
    finally:
        for e in envs:e.close()

if __name__=='__main__':main()
