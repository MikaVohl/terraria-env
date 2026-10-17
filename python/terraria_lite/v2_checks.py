"""Scalar/native parity including resets, policy support and recurrent boundaries."""
import numpy as np
import torch
from terraria_lite import SPEC, TerrariaLite
from terraria_lite.batch import NativeBatch
from terraria_lite.ppo_agent import ActorCritic
from terraria_lite.recurrent_ppo_agent import RecurrentActorCritic


def check_target_factoring():
    """The speed optimization must preserve the shared scorer and its gradients."""
    from terraria_lite.target_agent import TargetActor
    from torch.nn import functional as F
    for hidden in (64,128):
        actor=TargetActor(hidden).double()
        h=torch.randn(7,hidden+SPEC.reach_count*64,dtype=torch.float64,requires_grad=True)
        g=h[:,:hidden]
        context=h[:,hidden:].reshape(7,SPEC.reach_count,64)
        direct_input=torch.cat((g[:,None,:].expand(-1,SPEC.reach_count,-1),context,
                                actor.coordinates[None,:,:].expand(7,-1,-1)),dim=-1)
        scores=actor.target(direct_input)
        other=F.linear(g,actor.weight,actor.bias)
        direct=torch.cat((other[:,:SPEC.mine_first],scores[:,:,0],scores[:,:,1],other[:,SPEC.mine_first:]),dim=-1)
        factored=actor(h)
        torch.testing.assert_close(factored,direct,atol=1e-10,rtol=1e-10)
        probe=torch.randn_like(direct);inputs=[h,*actor.parameters()]
        expected=torch.autograd.grad((direct*probe).sum(),inputs)
        actual=torch.autograd.grad((factored*probe).sum(),inputs)
        for a,b in zip(actual,expected):
            torch.testing.assert_close(a,b,atol=1e-10,rtol=1e-10)


def check_recurrent_targets():
    from terraria_lite.recurrent_ppo_agent import RecurrentTargetActorCritic
    from terraria_lite.ppo_eval import load_agent
    import tempfile
    from pathlib import Path
    net = RecurrentTargetActorCritic(64)
    x = torch.rand(9, 4, SPEC.obs_size)
    done = torch.zeros(9, 4); done[0, 0] = done[3, 1] = done[5, 3] = 1
    state = tuple(torch.randn(1, 4, 64) for _ in range(2))
    initial = tuple(s.clone() for s in state)
    out = []
    for t in range(len(x)):
        h, state = net.core_step(x[t], state, done[t]); out.append(h)
    seq, last = net.sequence(x, initial, done)
    torch.testing.assert_close(seq, torch.stack(out), atol=2e-6, rtol=2e-5)
    for a, b in zip(last, state):
        torch.testing.assert_close(a, b, atol=2e-6, rtol=2e-5)
    # A reset lane cannot retain history from an unrelated episode.
    zero = net.initial_state(4, "cpu")
    fresh, _ = net.core_step(x[0], zero, torch.zeros(4))
    torch.testing.assert_close(seq[0, 0], fresh[0], atol=2e-6, rtol=2e-5)
    mask = torch.zeros(4, SPEC.n_actions, dtype=torch.bool)
    mask[:, 0] = mask[:, SPEC.mine_first] = True
    action, lp, entropy, value, _ = net.act_step(x[0], initial, done[0], mask=mask)
    assert mask[torch.arange(4), action].all()
    (lp.mean() + entropy.mean()*.01 + value.square().mean()).backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in net.parameters())
    assert net.lstm.weight_ih_l0.grad.abs().sum() > 0
    assert net.actor.target[-1].weight.grad.abs().sum() > 0
    # Exercise sequence heads exactly as recurrent PPO's optimizer does, not
    # just single-step inference (target heads require flat batches).
    net.zero_grad()
    seq, _ = net.sequence(x, initial, done)
    flat = seq.reshape(-1, seq.shape[-1])
    logits = net.actor(flat).reshape(9, 4, SPEC.n_actions)
    values = net.critic(flat).reshape(9, 4)
    (logits.square().mean() + values.square().mean()).backward()
    assert all(p.grad is None or torch.isfinite(p.grad).all() for p in net.parameters())
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory)/"policy.pt"
        torch.save({"model": net.state_dict(), "architecture": "lstm_targets", "encoder": 64, "hidden": 64,
                    "environment_version": SPEC.version, "obs_size": SPEC.obs_size, "n_actions": SPEC.n_actions}, path)
        restored = load_agent(path)
        expected, _ = net.core_step(x[0], initial, done[0])
        actual, _ = restored.core_step(x[0], initial, done[0])
        torch.testing.assert_close(restored.actor(actual), net.actor(expected))
        from terraria_lite.watch import _load
        act, kind = _load(path)
        assert kind == "recurrent-ppo"
        act.reset()
        assert mask[0, act(x[0, 0].numpy(), mask[0].numpy(), False)]


def main():
    from terraria_lite.checkpoints import validate_checkpoint
    validate_checkpoint({"environment_version":SPEC.version,"obs_size":SPEC.obs_size,
                         "n_actions":SPEC.n_actions})
    for bad in ({}, {"environment_version":SPEC.version,"obs_size":SPEC.obs_size-1,
                      "n_actions":SPEC.n_actions}):
        try:
            validate_checkpoint(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("incompatible checkpoint accepted")
    owner=TerrariaLite(); owner.reset(seed=9)
    b=NativeBatch(e for e in [owner])
    try:
        NativeBatch([owner,owner])
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate parallel lane accepted")
    owner.close()
    try:
        b.step([0],np.zeros((1,SPEC.obs_size),np.float32),np.zeros((1,SPEC.n_actions),bool))
    except RuntimeError:
        pass
    else:
        raise AssertionError("closed batch owner accepted")
    for workers in (1,2,4,8):
        scalar=[TerrariaLite(max_steps=37) for _ in range(16)]
        native=[TerrariaLite(max_steps=37) for _ in range(16)]
        try:
            for i in range(16): scalar[i].reset(seed=i+100); native[i].reset(seed=i+100)
            b=NativeBatch(native,workers)
            obs=np.zeros((16,SPEC.obs_size),np.float32)
            mask=np.zeros((16,SPEC.n_actions),bool)
            rng=np.random.default_rng(5)
            for t in range(1000):
                actions=rng.integers(SPEC.n_actions,size=16)
                reward,term,trunc=b.step(actions,obs,mask)
                for i in range(16):
                    x,r,te,tr,info=scalar[i].step(int(actions[i]))
                    np.testing.assert_array_equal(obs[i],x)
                    np.testing.assert_array_equal(mask[i],scalar[i].action_mask())
                    assert (float(reward[i]),bool(term[i]),bool(trunc[i]))==(r,te,tr)
                    assert info==native[i]._info()
                    if t==0:
                        # Native stepping must not leave Python debug views stale.
                        np.testing.assert_array_equal(native[i].view(),scalar[i].view())
                    if te or tr:
                        seed=10000+t*16+i
                        scalar[i].reset(seed=seed); native[i].reset(seed=seed)
        finally:
            for e in scalar+native: e.close()
    torch.set_num_threads(2)
    model=ActorCritic(SPEC.obs_size,SPEC.n_actions)
    x=torch.zeros(32,SPEC.obs_size); mask=torch.zeros(32,SPEC.n_actions,dtype=torch.bool)
    mask[:,0]=True; mask[:,3]=True
    a,lp,ent,val=model.act(x,mask=mask)
    assert mask[torch.arange(32),a].all() and torch.isfinite(lp).all() and torch.isfinite(ent).all()
    lstm=RecurrentActorCritic(SPEC.obs_size,SPEC.n_actions,64,64)
    x=torch.rand(8,4,SPEC.obs_size); done=torch.zeros(8,4); done[3,1]=1; done[5,3]=1
    state=lstm.initial_state(4,"cpu"); out=[]
    for t in range(8):
        h,state=lstm.core_step(x[t],state,done[t]); out.append(h)
    seq,last=lstm.sequence(x,lstm.initial_state(4,"cpu"),done)
    torch.testing.assert_close(seq,torch.stack(out),atol=2e-6,rtol=2e-5)
    torch.testing.assert_close(last[0],state[0],atol=2e-6,rtol=2e-5)
    from terraria_lite.spatial_agent import build_agent
    from terraria_lite.curiosity import RND
    from terraria_lite.ppo_eval import load_agent
    import tempfile
    from pathlib import Path
    for kind in ("cnn","tokens","separate","targets"):
        net=build_agent(kind); x=torch.rand(8,SPEC.obs_size)
        m=torch.zeros(8,SPEC.n_actions,dtype=torch.bool); m[:,0]=m[:,3]=True
        a,lp,ent,v=net.act(x,mask=m)
        assert m[torch.arange(8),a].all() and torch.isfinite(lp).all()
        (lp.mean()+v.square().mean()).backward()
        assert all(p.grad is None or torch.isfinite(p.grad).all() for p in net.parameters())
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"policy.pt"
            torch.save({"model":net.state_dict(),"architecture":kind,"environment_version":SPEC.version,
                        "obs_size":SPEC.obs_size,"n_actions":SPEC.n_actions},path)
            restored=load_agent(path)
            torch.testing.assert_close(restored.value(x),net.value(x))
            torch.testing.assert_close(restored.actor(restored.trunk(x)),net.actor(net.trunk(x)))
        if kind=="targets":
            net.zero_grad()
            all_legal=torch.ones_like(m)
            forced=torch.arange(8)+SPEC.mine_first
            _,lp,entropy,v=net.act(x,action=forced,mask=all_legal)
            (lp.mean()+.01*entropy.mean()+v.square().mean()).backward()
            assert net.actor.target[-1].weight.grad.abs().sum()>0
    check_target_factoring()
    check_recurrent_targets()
    for balanced in (False,True):
        rnd=RND(SPEC.obs_size,"cpu",balanced=balanced)
        target=[p.detach().clone() for p in rnd.target.parameters()]
        bonus,error=rnd.bonus_and_update(torch.rand(64,SPEC.obs_size))
        assert torch.isfinite(bonus).all() and (bonus>=0).all()
        assert all(torch.equal(p,q) for p,q in zip(target,rnd.target.parameters()))
    # Exercise the retained raw/NumPy path against direct C encoding too.
    owners=[TerrariaLite(max_steps=37) for _ in range(8)]
    try:
        for i,e in enumerate(owners): e.reset(seed=900+i%4)
        raw=NativeBatch(owners[:4],encoded=False)
        flat=NativeBatch(owners[4:])
        ro=np.zeros((4,SPEC.obs_size),np.float32); fo=np.zeros_like(ro)
        rm=np.zeros((4,SPEC.n_actions),bool); fm=np.zeros_like(rm)
        for t in range(50):
            actions=np.full(4,t%SPEC.n_actions)
            rr,rt,rx=raw.step(actions,ro,rm); fr,ft,fx=flat.step(actions,fo,fm)
            for a,b in ((ro,fo),(rm,fm),(rr,fr),(rt,ft),(rx,fx)):
                np.testing.assert_array_equal(a,b)
    finally:
        for e in owners: e.close()
    print(f"v{SPEC.version} Python checks passed: 64,000 scalar/batch transitions at 1/2/4/8 workers; raw/flat encoding; legal support; recurrent boundaries; model reloads; RND")

if __name__=="__main__": main()
