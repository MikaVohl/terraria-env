"""Random Network Distillation over observations; no recipes or objectives.

Fixed random targets make unfamiliar observations harder to predict. Running
input statistics give continuous inventory values comparable scale to cells.
The bonus is training-only; benchmark rewards and masks remain the core's.
"""
import torch
from torch import nn
from terraria_lite import SPEC


class Moments:
    def __init__(self, shape, device):
        self.mean=torch.zeros(shape,device=device)
        self.var=torch.ones(shape,device=device)
        self.count=1e-4

    @torch.no_grad()
    def update(self,x):
        n=len(x); mean=x.mean(0); var=x.var(0,unbiased=False)
        delta=mean-self.mean; total=self.count+n
        self.var=(self.var*self.count+var*n+delta.square()*self.count*n/total)/total
        self.mean+=delta*n/total; self.count=total


class RND:
    def __init__(self, obs_size, device, lr=1e-4, balanced=False):
        # Initialization cannot perturb the policy's sampling RNG stream.
        with torch.random.fork_rng():
            self.target=nn.Sequential(nn.Linear(obs_size,128),nn.ReLU(),nn.Linear(128,64)).to(device)
            self.predictor=nn.Sequential(nn.Linear(obs_size,256),nn.ReLU(),
                                         nn.Linear(256,128),nn.ReLU(),nn.Linear(128,64)).to(device)
        self.target.requires_grad_(False)
        self.inputs=Moments(obs_size,device); self.errors=Moments((),device)
        self.optimizer=torch.optim.Adam(self.predictor.parameters(),lr=lr)
        self.balanced=balanced

    def bonus_and_update(self,x):
        self.inputs.update(x)
        normalized=((x-self.inputs.mean)/torch.sqrt(self.inputs.var+1e-4)).clamp(-5,5)
        if self.balanced:
            # Equal scale for spatial and global modalities. All observed fields
            # participate; no item, recipe, achievement or desirable state selected.
            start=SPEC.cells*(SPEC.tile_kinds+1)
            end=start+SPEC.status_entity0
            normalized[:,:start]/=start**.5
            normalized[:,start:end]/=SPEC.status_entity0**.5
            normalized[:,end:]/=(x.shape[-1]-SPEC.status_entity0-start)**.5
        with torch.no_grad():
            target=self.target(normalized)
            errors=(self.predictor(normalized)-target).square().mean(-1)
            self.errors.update(errors)
            bonus=(errors/torch.sqrt(self.errors.var+1e-8)).clamp(max=5)
        # One predictor epoch over this rollout; train on exactly the same
        # normalization and fixed targets that produced the bonus.
        for start in range(0,len(x),2048):
            loss=(self.predictor(normalized[start:start+2048])-target[start:start+2048]).square().mean()
            self.optimizer.zero_grad(set_to_none=True); loss.backward(); self.optimizer.step()
        return bonus.detach(),float(errors.mean())
