"""Shared cell features plus global-state features, using only dense kernels."""
import torch
from torch import nn
from terraria_lite import SPEC
from terraria_lite.ppo_agent import ActorCritic,layer_init


class TokenEncoder(nn.Module):
    def __init__(self,hidden=256):
        super().__init__()
        self.cell=nn.Sequential(layer_init(nn.Linear(SPEC.tile_kinds+5,16)),nn.Tanh())
        self.status=nn.Sequential(layer_init(nn.Linear(SPEC.status_entity0,128)),nn.Tanh())
        self.fuse=nn.Sequential(layer_init(nn.Linear(SPEC.cells*16+128,hidden)),nn.Tanh(),
                                layer_init(nn.Linear(hidden,hidden)),nn.Tanh())

    def forward(self,x):
        n=len(x); end=SPEC.cells*SPEC.tile_kinds; start=end+SPEC.cells
        tiles=x[:,:end].reshape(n,SPEC.cells,SPEC.tile_kinds)
        light=x[:,end:start].reshape(n,SPEC.cells,1)
        status=x[:,start:]
        entities=status[:,SPEC.status_entity0:].reshape(n,SPEC.cells,4)
        cells=self.cell(torch.cat((tiles,light,entities),dim=-1)).flatten(1)
        scalar=self.status(status[:,:SPEC.status_entity0])
        return self.fuse(torch.cat((cells,scalar),dim=-1))


class TokenActorCritic(ActorCritic):
    def __init__(self,hidden=256):
        nn.Module.__init__(self)
        self.trunk=TokenEncoder(hidden)
        self.actor=layer_init(nn.Linear(hidden,SPEC.n_actions),std=.01)
        self.critic=layer_init(nn.Linear(hidden,1),std=1.)
