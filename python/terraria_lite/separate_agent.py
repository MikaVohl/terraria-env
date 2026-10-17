"""Independent actor and critic features, a general PPO architecture control."""
import torch
from torch import nn
from terraria_lite import SPEC
from terraria_lite.ppo_agent import ActorCritic,layer_init,sample_categorical


class SeparateActorCritic(ActorCritic):
    def __init__(self,hidden=512):
        nn.Module.__init__(self)
        def trunk():
            return nn.Sequential(layer_init(nn.Linear(SPEC.obs_size,hidden)),nn.Tanh(),
                                  layer_init(nn.Linear(hidden,hidden)),nn.Tanh())
        self.trunk=trunk(); self.critic_trunk=trunk()
        self.actor=layer_init(nn.Linear(hidden,SPEC.n_actions),std=.01)
        self.critic=layer_init(nn.Linear(hidden,1),std=1.)

    def value(self,x):
        return self.critic(self.critic_trunk(x)).squeeze(-1)

    def act(self,x,action=None,mask=None):
        logits=self.actor(self.trunk(x))
        if mask is not None: logits=logits.masked_fill(~mask,float("-inf"))
        dist=torch.distributions.Categorical(logits=logits)
        if action is None: action=sample_categorical(dist,mask)
        return action,dist.log_prob(action),dist.entropy(),self.value(x)
