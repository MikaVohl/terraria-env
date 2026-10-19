"""Learned spatial action-target sharing; no goals, recipes or digging routine.

`extra` > 0 appends that many non-observation features (e.g. memory_features)
after the observation; they join only the global MLP input. extra=0 builds the
exact original module, so pre-existing checkpoints load unchanged.
"""
import torch
from torch import nn
from torch.nn import functional as F
from terraria_lite import SPEC
from terraria_lite.ppo_agent import ActorCritic, layer_init


class TargetEncoder(nn.Module):
    def __init__(self, hidden=128, extra=0):
        super().__init__()
        self.hidden=hidden;self.extra=extra
        self.cells=nn.Sequential(layer_init(nn.Linear(SPEC.tile_kinds+5,32)),nn.ReLU(),
                                 layer_init(nn.Linear(32,32)),nn.ReLU())
        self.global_features=nn.Sequential(layer_init(nn.Linear(SPEC.cells*32+SPEC.status_entity0+extra,hidden)),nn.Tanh(),
                                          layer_init(nn.Linear(hidden,hidden)),nn.Tanh())
        neighborhoods=[]
        for dx,dy in SPEC.reach_offsets:
            x,y=SPEC.view_w//2+dx,SPEC.view_h//2+dy
            assert 1<=x<SPEC.view_w-1 and 1<=y<SPEC.view_h-1
            neighborhoods.append([(y+oy)*SPEC.view_w+x+ox for oy in (-1,0,1) for ox in (-1,0,1)])
        self.register_buffer("neighborhoods",torch.tensor(neighborhoods,dtype=torch.long))
        self.context=nn.Sequential(layer_init(nn.Linear(9*32,64)),nn.ReLU())

    def forward(self,x):
        if self.extra:
            x,memory=x[:,:-self.extra],x[:,-self.extra:]
        n=x.shape[0];end=SPEC.cells*SPEC.tile_kinds;status=x[:,end+SPEC.cells:]
        tiles=x[:,:end].reshape(n,SPEC.cells,SPEC.tile_kinds)
        light=x[:,end:end+SPEC.cells].unsqueeze(-1)
        entities=status[:,SPEC.status_entity0:].reshape(n,SPEC.cells,4)
        cells=self.cells(torch.cat((tiles,light,entities),dim=-1))
        scalars=(cells.flatten(1),status[:,:SPEC.status_entity0])+((memory,) if self.extra else ())
        global_features=self.global_features(torch.cat(scalars,dim=-1))
        context=self.context(cells[:,self.neighborhoods,:].reshape(n,SPEC.reach_count,9*32))
        return torch.cat((global_features,context.flatten(1)),dim=-1)


class TargetActor(nn.Linear):
    """One shared scorer per action type, evaluated at each physical target."""
    def __init__(self,hidden):
        super().__init__(hidden,SPEC.n_actions-2*SPEC.reach_count)
        layer_init(self,std=.01)
        self.target=nn.Sequential(layer_init(nn.Linear(hidden+64+2,64)),nn.Tanh(),
                                  layer_init(nn.Linear(64,2),std=.01))
        self.register_buffer("coordinates",torch.tensor(SPEC.reach_offsets,dtype=torch.float32)
                             /torch.tensor((SPEC.view_w/2,SPEC.view_h/2)))

    def forward(self,h):
        n=h.shape[0];g=h[:,:self.in_features]
        context=h[:,self.in_features:].reshape(n,SPEC.reach_count,64)
        # The shared global projection is identical at every target. Factor the
        # first linear layer algebraically instead of multiplying it 20 times
        # or materializing the repeated global/coordinate concatenation.
        first=self.target[0];width=self.in_features
        z=F.linear(g,first.weight[:,:width])[:,None,:]
        z=z+F.linear(context,first.weight[:,width:width+64])
        z=z+F.linear(self.coordinates,first.weight[:,width+64:],first.bias)[None,:,:]
        scores=self.target[2](self.target[1](z))
        other=super().forward(g)
        assert SPEC.place_first==SPEC.mine_first+SPEC.reach_count
        return torch.cat((other[:,:SPEC.mine_first],scores[:,:,0],scores[:,:,1],other[:,SPEC.mine_first:]),dim=-1)


class GlobalCritic(nn.Linear):
    def forward(self,h):
        return super().forward(h[:,:self.in_features])


class TargetActorCritic(ActorCritic):
    def __init__(self,hidden=128,extra=0):
        nn.Module.__init__(self)
        self.trunk=TargetEncoder(hidden,extra)
        self.actor=TargetActor(hidden)
        self.critic=layer_init(GlobalCritic(hidden,1),std=1.)
