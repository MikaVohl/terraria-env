"""Batched n-step Double DQN: generic uniform replay, sparse rewards, legal masks.

This is an off-policy reference, not a world model or a replay ablation of PPO.
No demonstrations, recipe logic, reward shaping or strategic exploration.
"""
from collections import deque
import copy
from dataclasses import dataclass
import time
import numpy as np
import torch
from torch import nn
from terraria_lite import SPEC
from terraria_lite.ppo_agent import VecTerraria, layer_init


class ReplayQ(nn.Module):
    def __init__(self, hidden=512):
        super().__init__()
        self.trunk = nn.Sequential(layer_init(nn.Linear(SPEC.obs_size,hidden)),nn.Tanh(),
                                   layer_init(nn.Linear(hidden,hidden)),nn.Tanh())
        self.actor = layer_init(nn.Linear(hidden,SPEC.n_actions),std=1.)

    def forward(self, x):
        return self.actor(self.trunk(x))


class CompactReplay:
    """Lossless one-hot/light compression; status remains exact float32."""
    def __init__(self, capacity):
        self.cap,self.pos,self.size = capacity,0,0
        self.terrain_end = SPEC.cells*SPEC.tile_kinds
        self.status_start = self.terrain_end+SPEC.cells
        status_size = SPEC.obs_size-self.status_start
        self.tiles = np.empty((2,capacity,SPEC.cells),np.uint8)
        self.light = np.empty_like(self.tiles)
        self.status = np.empty((2,capacity,status_size),np.float32)
        self.actions = np.empty(capacity,np.int64)
        self.returns = np.empty(capacity,np.float32)
        self.discounts = np.empty(capacity,np.float32)
        self.next_masks = np.empty((capacity,SPEC.n_actions),bool)

    def push(self, s,a,r,s2,g,m2):
        n=len(a); assert n<=self.cap
        indices=(np.arange(n)+self.pos)%self.cap
        for side,obs in enumerate((s,s2)):
            self.tiles[side,indices]=obs[:,:self.terrain_end].reshape(n,SPEC.cells,SPEC.tile_kinds).argmax(-1)
            self.light[side,indices]=np.rint(obs[:,self.terrain_end:self.status_start]*15).astype(np.uint8)
            self.status[side,indices]=obs[:,self.status_start:]
        self.actions[indices]=a;self.returns[indices]=r;self.discounts[indices]=g;self.next_masks[indices]=m2
        self.pos=(self.pos+n)%self.cap;self.size=min(self.size+n,self.cap)

    def decode(self, side, indices):
        n=len(indices);x=np.zeros((n,SPEC.obs_size),np.float32)
        grid=x[:,:self.terrain_end].reshape(n,SPEC.cells,SPEC.tile_kinds)
        grid[np.arange(n)[:,None],np.arange(SPEC.cells)[None,:],self.tiles[side,indices]]=1
        x[:,self.terrain_end:self.status_start]=(self.light[side,indices].astype(np.float64)/15).astype(np.float32)
        x[:,self.status_start:]=self.status[side,indices]
        return x

    def sample(self,n,rng):
        idx=rng.integers(self.size,size=n)
        return tuple(torch.from_numpy(x) for x in (self.decode(0,idx),self.actions[idx],
                     self.returns[idx],self.decode(1,idx),self.discounts[idx],self.next_masks[idx]))

    @property
    def bytes(self):
        return sum(x.nbytes for x in (self.tiles,self.light,self.status,self.actions,self.returns,self.discounts,self.next_masks))


class BatchedNStep:
    def __init__(self,n,gamma,sink):
        self.n,self.gamma,self.sink=n,gamma,sink;self.queue=deque()

    def push(self,s,a,r,s2,ended,m2):
        self.queue.append(tuple(x.copy() for x in (s,a,r,s2,ended,m2)))
        if len(self.queue)>=self.n:self.emit()

    def emit(self):
        s,a=self.queue[0][:2];count=len(a)
        ret=np.zeros(count,np.float32);discount=np.ones(count,np.float32);alive=np.ones(count,bool)
        nxt=s.copy();mask=self.queue[0][-1].copy()
        for _,_,reward,s2,ended,m2 in self.queue:
            ret[alive]+=discount[alive]*reward[alive]
            nxt[alive]=s2[alive];mask[alive]=m2[alive]
            discount[alive]*=self.gamma
            discount[alive&ended]=0;alive&=~ended
        self.sink(s,a,ret,nxt,discount,mask);self.queue.popleft()

    def flush(self):
        while self.queue:self.emit()


def targets(q,target,s2,reward,discount,m2):
    with torch.no_grad():
        next_action=q(s2).masked_fill(~m2,float('-inf')).argmax(-1)
        boot=target(s2).gather(1,next_action[:,None]).squeeze(1)
        return reward+discount*boot


@dataclass
class Config:
    steps:int=4194304
    seed:int=601
    envs:int=64
    capacity:int=131072
    nstep:int=20
    gamma:float=.999
    batch:int=512
    train_every:int=256
    learn_start:int=16384
    target_sync:int=8192
    lr:float=.0001
    epsilon_end:float=.05


def train(cfg,callback=None):
    torch.manual_seed(cfg.seed);rng=np.random.default_rng(cfg.seed)
    q=ReplayQ();target=copy.deepcopy(q).requires_grad_(False)
    optimizer=torch.optim.Adam(q.parameters(),lr=cfg.lr)
    replay=CompactReplay(cfg.capacity);nstep=BatchedNStep(cfg.nstep,cfg.gamma,replay.push)
    envs=VecTerraria(cfg.envs,cfg.seed);obs,mask=envs.reset()
    collection=optimization=0.;updates=0;last_loss=None;start=time.perf_counter()
    actual=cfg.steps//cfg.envs*cfg.envs
    assert cfg.train_every%cfg.envs==0 and cfg.target_sync%cfg.envs==0
    try:
        for steps in range(cfg.envs,actual+1,cfg.envs):
            begin=time.perf_counter();before=obs.copy()
            epsilon=1-(1-cfg.epsilon_end)*min(1,steps/(actual*.5))
            with torch.no_grad():actions=q(torch.from_numpy(obs)).masked_fill(~torch.from_numpy(mask),float('-inf')).argmax(-1).numpy()
            # Uniform random choice over every legal action, not over goals.
            random_actions=(rng.random(mask.shape)*mask-~mask).argmax(-1)
            random_lanes=rng.random(cfg.envs)<epsilon;actions[random_lanes]=random_actions[random_lanes]
            obs,mask,reward,term,trunc,_,_=envs.step(actions)
            nstep.push(before,actions,reward,obs,term|trunc,mask)
            collection+=time.perf_counter()-begin
            if steps%cfg.train_every==0 and replay.size>=cfg.learn_start:
                begin=time.perf_counter();s,a,r,s2,g,m2=replay.sample(cfg.batch,rng)
                predicted=q(s).gather(1,a[:,None]).squeeze(1)
                y=targets(q,target,s2,r,g,m2)
                loss=nn.functional.smooth_l1_loss(predicted,y)
                if not torch.isfinite(loss):raise FloatingPointError('Non-finite Double DQN loss')
                optimizer.zero_grad(set_to_none=True);loss.backward();nn.utils.clip_grad_norm_(q.parameters(),10.)
                optimizer.step();updates+=1;last_loss=float(loss.detach())
                optimization+=time.perf_counter()-begin
            if steps%cfg.target_sync==0:target.load_state_dict(q.state_dict())
            if callback:callback(q,steps,{'collection_seconds':collection,'optimisation_seconds':optimization,'updates':updates,'loss':last_loss,'epsilon':epsilon,'replay_entries':replay.size})
        nstep.flush()
        return {'steps':actual,'updates':updates,'collection_seconds':collection,'optimisation_seconds':optimization,'replay_bytes':replay.bytes,'wall_seconds_including_validation':time.perf_counter()-start,'last_loss':last_loss}
    finally:envs.close()
