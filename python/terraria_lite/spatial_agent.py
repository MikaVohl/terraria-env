"""General spatial encoder: convolutions for cells, an MLP for scalar state."""
import torch
from torch import nn
from terraria_lite import SPEC
from terraria_lite.ppo_agent import ActorCritic, layer_init


class SpatialEncoder(nn.Module):
    def __init__(self, hidden=256):
        super().__init__()
        self.grid = nn.Sequential(
            nn.Conv2d(SPEC.tile_kinds+5, 16, 3, padding=1), nn.ReLU(),
            nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.ReLU(),
            nn.Conv2d(32, 32, 3, stride=2, padding=1), nn.ReLU(), nn.Flatten())
        cells = ((SPEC.view_h+3)//4)*((SPEC.view_w+3)//4)*32
        self.scalars = nn.Sequential(nn.Linear(SPEC.status_entity0,128), nn.ReLU())
        self.fuse = nn.Sequential(nn.Linear(cells+128,hidden), nn.ReLU(),
                                  nn.Linear(hidden,hidden), nn.ReLU())
        for layer in self.modules():
            if isinstance(layer,(nn.Linear,nn.Conv2d)):
                nn.init.orthogonal_(layer.weight, 2**.5)
                nn.init.zeros_(layer.bias)

    def forward(self, x):
        n=x.shape[0]; terrain_end=SPEC.cells*SPEC.tile_kinds
        status_start=terrain_end+SPEC.cells
        tiles=x[:,:terrain_end].reshape(n,SPEC.view_h,SPEC.view_w,SPEC.tile_kinds).permute(0,3,1,2)
        light=x[:,terrain_end:status_start].reshape(n,1,SPEC.view_h,SPEC.view_w)
        status=x[:,status_start:]
        entities=status[:,SPEC.status_entity0:].reshape(n,SPEC.view_h,SPEC.view_w,4).permute(0,3,1,2)
        # On macOS CPU, channels-last input selects slow dilated-convolution
        # backward kernels. Contiguous NCHW reaches the dense/GEMM path.
        grid=self.grid(torch.cat((tiles,light,entities),dim=1).contiguous())
        scalars=self.scalars(status[:,:SPEC.status_entity0])
        return self.fuse(torch.cat((grid,scalars),dim=1))


class SpatialActorCritic(ActorCritic):
    def __init__(self, hidden=256):
        nn.Module.__init__(self)
        self.trunk=SpatialEncoder(hidden)
        self.actor=layer_init(nn.Linear(hidden,SPEC.n_actions),std=.01)
        self.critic=layer_init(nn.Linear(hidden,1),std=1.)


def build_agent(architecture="mlp", hidden=None, extra=0, depth=2, cell_width=32):
    """`extra` appends non-observation input features; only 'targets' supports it.
    `hidden` 0/None selects the architecture's default width; `depth` (global
    trunk layers) applies to 'targets' and 'mlp', `cell_width` to 'targets'."""
    if architecture=="targets":
        from terraria_lite.target_agent import TargetActorCritic
        return TargetActorCritic(hidden or 128,extra,depth,cell_width)
    if extra:
        raise ValueError(f"Architecture {architecture} does not accept extra features")
    if cell_width!=32:
        raise ValueError(f"Architecture {architecture} has no cell_width")
    if architecture=="mlp":
        return ActorCritic(SPEC.obs_size,SPEC.n_actions,hidden=hidden or 512,depth=depth)
    if depth!=2:
        raise ValueError(f"Architecture {architecture} has no depth option")
    if architecture=="tokens":
        from terraria_lite.token_agent import TokenActorCritic
        return TokenActorCritic(hidden or 256)
    if architecture=="separate":
        from terraria_lite.separate_agent import SeparateActorCritic
        return SeparateActorCritic(hidden or 512)
    if architecture!="cnn":
        raise ValueError(f"Unknown architecture: {architecture}")
    return SpatialActorCritic(hidden or 256)


def agent_size(architecture, state):
    """Size knobs (hidden, depth, cell_width) of a feed-forward state_dict, so
    checkpoints of any size restore without extra metadata."""
    size={"hidden":int(state["actor.weight"].shape[1])}
    prefix={"targets":"trunk.global_features.","mlp":"trunk."}.get(architecture)
    if prefix is not None:
        size["depth"]=sum(1 for k in state if k.startswith(prefix) and k.endswith(".weight")
                          and k[len(prefix):-len(".weight")].isdigit())
    if architecture=="targets":
        size["cell_width"]=int(state["trunk.cells.0.weight"].shape[0])
    return size

