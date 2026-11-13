// One recorded episode of the trained policy, generated lazily, seekable to
// any step by restoring the nearest Env snapshot (one memcpy) and replaying
// the recorded actions: the same property the training code relies on.

const EVERY = 25;

export class Replay {
  constructor(core, seed) {
    this.core = core; this.seed = seed;
    const K = core.L;
    this.gen = core.env(0).reset(seed);        // generator, always at the frontier
    this.view = core.env(0).reset(seed);       // what the page shows
    this.actions = []; this.rewards = []; this.values = []; this.ach = []; this.entropy = [];
    this.snaps = new Map([[0, this.gen.save(new Uint8Array(K.ENV_BYTES))]]);
    this.done = false; this.cur = 0; this.rng = 0x2545f491;
    this.scratch = new Uint8Array(K.ENV_BYTES);
  }
  rand() { let x = this.rng; x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; this.rng = x >>> 0; return this.rng / 4294967296; }

  /* Generate up to `budget` more steps. Returns true while unfinished. */
  extend(budget = 40) {
    const core = this.core, K = core.L, e = this.gen;
    for (let i = 0; i < budget && !this.done; i++) {
      const op = e.observe(), mask = e.mask();
      const tr = core.trace(op, e.maskPtr, -1);
      let r = this.rand(), a = 0;
      for (let k = 0; k < K.ACT_COUNT; k++) { if (!mask[k]) continue; r -= tr.probs[k]; a = k; if (r <= 0) break; }
      this.values.push(tr.value); this.entropy.push(tr.entropy);
      e.step(a);
      this.actions.push(a); this.rewards.push(e.reward); this.ach.push(e.achievements);
      const n = this.actions.length;
      if (n % EVERY === 0) this.snaps.set(n, e.save(new Uint8Array(K.ENV_BYTES)));
      if (e.done) this.done = true;
    }
    return !this.done;
  }
  get length() { return this.actions.length; }

  /* Put this.view at state k (k actions applied). */
  seek(k) {
    while (k > this.length && !this.done) this.extend(64);
    k = Math.max(0, Math.min(k, this.length));
    if (k === this.cur) return k;
    if (k === this.cur + 1) { this.prevBytes = this.view.save(this.scratch); this.view.step(this.actions[this.cur]); this.cur = k; return k; }
    const base = Math.floor(k / EVERY) * EVERY;
    this.view.load(this.snaps.get(base));
    for (let i = base; i < k - 1; i++) this.view.step(this.actions[i]);
    this.prevBytes = k > 0 ? this.view.save(this.scratch) : null;
    if (k > 0) this.view.step(this.actions[k - 1]);
    this.cur = k;
    return k;
  }

  /* Discounted return G_t = sum_k gamma^k r_{t+k+1}, over the recorded part. */
  returns(gamma) {
    const G = new Float32Array(this.length);
    let g = 0;
    for (let t = this.length - 1; t >= 0; t--) { g = this.rewards[t] + gamma * g; G[t] = g; }
    return G;
  }
  /* GAE(gamma, lambda) advantages from the recorded values and rewards. */
  advantages(gamma, lambda) {
    const n = this.length, A = new Float32Array(n);
    let adv = 0;
    for (let t = n - 1; t >= 0; t--) {
      const next = t + 1 < n ? this.values[t + 1] : 0, terminal = this.done && t === n - 1;
      const delta = this.rewards[t] + (terminal ? 0 : gamma * next) - this.values[t];
      adv = delta + gamma * lambda * (terminal ? 0 : adv);
      A[t] = adv;
    }
    return A;
  }
}
