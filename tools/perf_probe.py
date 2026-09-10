"""Exploratory benchmarks; run from repository root with .venv/bin/python."""
import argparse
import ctypes as C
import json
import time
import numpy as np
import torch
from terraria_lite import SPEC, _lib
import terraria_lite.ppo_agent as ppo

class Obs(C.Structure):
    _fields_=[('tile',C.c_ubyte*SPEC.cells),('light',C.c_ubyte*SPEC.cells),
              ('status',C.c_float*SPEC.status_len)]

class Batch(ppo.VecTerraria):
    def __init__(self,n,seed=1):
        super().__init__(n,seed)
        self.handles=(C.c_void_p*n)(*[e._h for e in self.envs])
        self.raw=(Obs*n)()
        self.tiles=np.ndarray((n,SPEC.cells),np.uint8,buffer=self.raw,strides=(C.sizeof(Obs),1))
        self.lights=np.ndarray((n,SPEC.cells),np.uint8,buffer=self.raw,offset=Obs.light.offset,strides=(C.sizeof(Obs),1))
        self.status=np.ndarray((n,SPEC.status_len),np.float32,buffer=self.raw,offset=Obs.status.offset,strides=(C.sizeof(Obs),4))
        self.masks=np.zeros((n,SPEC.n_actions),np.uint8)
        self.rewards=np.zeros(n,np.float32);self.ends=np.zeros(n,np.int32)
        _lib.probe_batch.argtypes=[C.c_void_p,C.c_int,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
        _lib.probe_batch.restype=None
        _lib.probe_obs_bytes.restype=C.c_int
        assert _lib.probe_obs_bytes()==C.sizeof(Obs)
    def step(self,actions):
        actions=np.ascontiguousarray(actions,dtype=np.int32)
        _lib.probe_batch(self.handles,self.n,actions.ctypes.data,self.raw,self.masks.ctypes.data,self.rewards.ctypes.data,self.ends.ctypes.data)
        self.obs.fill(0)
        onehot=self.obs[:,:SPEC.cells*SPEC.tile_kinds].reshape(self.n,SPEC.cells,SPEC.tile_kinds)
        onehot[np.arange(self.n)[:,None],np.arange(SPEC.cells),self.tiles]=1
        np.divide(self.lights,15.0,out=self.obs[:,SPEC.cells*SPEC.tile_kinds:SPEC.cells*(SPEC.tile_kinds+1)],casting='unsafe')
        self.obs[:,SPEC.cells*(SPEC.tile_kinds+1):]=self.status
        self.mask[:]=self.masks
        term=self.ends==1;trunc=self.ends==2
        final=np.zeros_like(self.obs);finished=[]
        for i in np.flatnonzero(self.ends):
            final[i]=self.obs[i];e=self.envs[i]
            finished.append((int(i),e._info()))
            self.obs[i]=e.reset(seed=self._fresh_seed())[0]
            self.mask[i]=e.action_mask()
        return self.obs,self.mask,self.rewards.copy(),term,trunc,final,finished

def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['check','vector','train'],required=True)
    p.add_argument('--batch',action='store_true');p.add_argument('--threads',type=int,default=6)
    p.add_argument('--workers',type=int,default=1)
    p.add_argument('--envs',type=int,default=16);p.add_argument('--steps',type=int,default=65536)
    p.add_argument('--save',default='')
    p.add_argument('--device',default='cpu');a=p.parse_args();torch.set_num_threads(a.threads)
    _lib.probe_workers.argtypes=[C.c_int];_lib.probe_workers.restype=None
    _lib.probe_workers(a.workers)
    if a.mode=='check':
        x=ppo.VecTerraria(a.envs,seed=876);y=Batch(a.envs,seed=876)
        x.reset();y.reset();rng=np.random.default_rng(99)
        _lib.probe_check.argtypes=[C.c_void_p];_lib.probe_check.restype=C.c_int
        for t in range(a.steps//a.envs):
            actions=np.where(x.mask,rng.random(x.mask.shape),-1).argmax(1)
            left=x.step(actions);right=y.step(actions)
            for i in range(6):np.testing.assert_array_equal(left[i],right[i])
            assert left[6]==right[6]
            for e in y.envs:assert _lib.probe_check(e._h),'lighting differs'
        print(json.dumps({'check':'passed','transitions':a.steps,'envs':a.envs}))
        x.close();y.close()
    elif a.mode=='vector':
        v=(Batch if a.batch else ppo.VecTerraria)(a.envs,seed=876)
        rng=np.random.default_rng(99);samples=[]
        for repeat in range(3):
            v.reset();start=time.perf_counter()
            for t in range(a.steps//a.envs):
                actions=np.where(v.mask,rng.random(v.mask.shape),-1).argmax(1)
                v.step(actions)
            samples.append(time.perf_counter()-start)
        v.close();print(json.dumps({**vars(a),'seconds':samples,'median_sps':a.steps/np.median(samples)}))
    else:
        if a.batch:ppo.VecTerraria=Batch
        if a.device=='mps' and not torch.backends.mps.is_available():
            print(json.dumps({'skip':'MPS unavailable'}));return
        if a.device=='mps':torch.mps.synchronize()
        start=time.perf_counter()
        result=ppo.train(ppo.Config(total_steps=a.steps,num_envs=a.envs,device=a.device,quiet=True,save=a.save,seed=987))
        if a.device=='mps':torch.mps.synchronize()
        elapsed=time.perf_counter()-start
        print(json.dumps({**vars(a),'wall_seconds':elapsed,'wall_sps':result['steps']/elapsed,'result':result}))

if __name__=='__main__':main()
