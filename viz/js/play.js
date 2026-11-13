// Chapters "Play" and "Agent": one focused world, first driven by the reader,
// then by the policy, with live policy charts.
import { $, el, fitCanvas, lineChart, clamp, fmt, icon, iconCanvas } from "./ui.js";

const TICK_HUMAN = 0.11, TICK_AGENT = 1 / 9;

export class Focus {
  constructor(S) {
    this.S = S; const core = S.core, K = core.L;
    this.env = core.env(0).reset(S.focusSeed);
    this.prev = { x: this.env.px, y: this.env.py }; this.lerp = 1;
    this.keys = new Set(); this.acc = 0; this.mode = "human"; this.walkUntil = 0;
    this.hover = -1; this.mouse = null; this.queue = [];
    this.hist = { value: [], entropy: [], ret: [] };
    this.lastAch = this.env.achievements; this.rng = 0x9e3779b9;
    this.trace = null; this.lastAction = 0;
    this.buildHud();
    addEventListener("keydown", (e) => this.onKey(e, true));
    addEventListener("keyup", (e) => this.onKey(e, false));
    const w = $("#world");
    w.addEventListener("mousemove", (e) => { this.mouse = { x: e.clientX, y: e.clientY }; });
    w.addEventListener("mouseleave", () => { this.mouse = null; });
    w.addEventListener("mousedown", (e) => {
      if (this.mode !== "human" || this.hover < 0) return;
      this.queue.push((e.button === 2 ? K.PLACE_FIRST : K.MINE_FIRST) + this.hover); e.preventDefault();
    });
    w.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  buildHud() {
    const S = this.S, core = S.core;
    this.invEl = $("#hud-inv"); this.craftEl = $("#hud-crafts"); this.achEl = $("#hud-ach");
    this.advs = core.achNames.map((name, i) => {
      const d = el("div", { class: "adv", title: name }); const c = iconCanvas(S.achIcons[i]); d.append(c); this.achEl.append(d); return d;
    });
    this.crafts = core.recipes.map((r) => {
      const d = el("div", { class: "craft", title: `${r.name}: ${r.inputs.map((x) => `${x.qty} ${core.itemNames[x.item]}`).join(" + ")}` });
      const c = iconCanvas(S.items[r.out]); d.append(c);
      d.addEventListener("click", () => { if (this.mode === "human") this.queue.push(r.action); });
      this.craftEl.append(d); return d;
    });
    this.hearts = $("#hud-hearts");
  }

  onKey(e, down) {
    if (this.mode !== "human" || !document.body.classList.contains("ch-play")) return;
    const k = e.key.toLowerCase(), K = this.S.core.L;
    const single = { w: 3, " ": 3, e: K.PLACE_FIRST + 2 * K.REACH_COUNT, f: 64, z: 65, s: 0 };
    if (["a", "d"].includes(k)) { down ? this.keys.add(k) : this.keys.delete(k); e.preventDefault(); }
    else if (down && k in single && !e.repeat) { this.queue.push(k === "f" ? this.S.core.actionNames.indexOf("attack") : k === "z" ? this.S.core.actionNames.indexOf("open chest") : single[k]); if (k === " ") e.preventDefault(); }
  }

  setMode(m) {
    if (m === this.mode) return;
    this.mode = m; this.keys.clear(); this.queue = [];
    const b = $("#mode-badge");
    b.textContent = m === "human" ? "YOU ARE PLAYING" : "AGENT IS PLAYING";
    b.classList.toggle("agent", m === "agent");
    this.craftEl.style.display = m === "human" ? "" : "none";
  }

  /* Time only passes on a step. While the player is in the air or a tool is
     cooling down, idle ticks become real NOOP steps, as the agent would take. */
  mustWait() {
    const K = this.S.core.L, e = this.env;
    return e.i32(K.JUMP_LEFT) > 0 || e.i32(K.FALL) > 0 || e.i32(K.MINE_CD) > 0 || e.i32(K.ATTACK_CD) > 0;
  }

  sample(mask) {
    const core = this.S.core, K = core.L;
    const op = this.env.observe();
    // greedy-free sampling from the masked softmax; trace computes probs for the panel
    const tr = core.trace(op, this.env.maskPtr, -1);
    let r = this.rand(), a = 0;
    for (let i = 0; i < K.ACT_COUNT; i++) { if (!mask[i]) continue; r -= tr.probs[i]; a = i; if (r <= 0) break; }
    this.trace = tr;
    return a;
  }
  rand() { let x = this.rng; x ^= x << 13; x >>>= 0; x ^= x >>> 17; x ^= x << 5; this.rng = x >>> 0; return this.rng / 4294967296; }

  doStep(a) {
    const env = this.env;
    this.prev = { x: env.px, y: env.py }; this.lerp = 0; this.lastAction = a;
    if (a === 1 || a === 2) this.walkUntil = performance.now() + 250;
    env.step(a);
    const ach = env.achievements, newBits = ach & ~this.lastAch;
    if (newBits) for (let b = 0; b < 32; b++) if ((newBits >>> b) & 1) this.unlocked(b);
    this.lastAch = ach;
    if (this.mode === "agent") {
      const tr = this.trace;
      if (tr) { push(this.hist.value, tr.value); push(this.hist.entropy, tr.entropy); }
      push(this.hist.ret, env.epReturn);
    }
    if (env.done) {
      env.reset(this.S.focusSeed = this.S.focusSeed + 1);
      this.prev = { x: env.px, y: env.py }; this.lastAch = 0; this.hist.ret = [];
      this.advs.forEach((d) => d.classList.remove("got"));
      $("#agent-unlocks").replaceChildren();
    }
  }

  unlocked(b) {
    const d = this.advs[b]; d.classList.add("got", "flash"); setTimeout(() => d.classList.remove("flash"), 1000);
    const feed = $("#agent-unlocks");
    const c = iconCanvas(this.S.achIcons[b]);
    feed.prepend(el("div", {}, c, el("b", {}, "+1"), ` ${this.S.core.achNames[b]} `, el("span", { class: "muted" }, `@ step ${this.env.steps}`)));
    while (feed.children.length > 6) feed.lastChild.remove();
  }

  update(dt, active) {
    if (!active) return;
    const K = this.S.core.L;
    this.acc += dt;
    if (this.mode === "human") {
      if (this.acc >= TICK_HUMAN) {
        this.acc = 0;
        let a = -1;
        if (this.queue.length) a = this.queue.shift();
        else if (this.keys.has("a")) a = 1; else if (this.keys.has("d")) a = 2;
        else if (this.mustWait()) a = 0;
        if (a >= 0) { const m = this.env.mask(); if (m[a] || a === 0) this.doStep(a); else this.flashMsg(a); }
      }
    } else if (this.acc >= TICK_AGENT) {
      this.acc = 0;
      const m = this.env.mask();
      this.doStep(this.sample(m));
    }
    this.lerp = clamp(this.lerp + dt / (this.mode === "human" ? TICK_HUMAN : TICK_AGENT));
    this.hudUpdate(K);
  }

  flashMsg(a) { $("#hud-msg").textContent = `${this.S.core.actionNames[a]}: not possible here`; }

  walking() { return performance.now() < this.walkUntil; }

  playerPos() {
    const t = this.lerp, e = this.env;
    return { x: this.prev.x + (e.px - this.prev.x) * t, y: this.prev.y + (e.py - this.prev.y) * t };
  }

  /* reach index under the mouse, in the current camera */
  pickHover(view) {
    this.hover = -1;
    if (!this.mouse || this.mode !== "human") return;
    const cx = Math.floor(view.x + this.mouse.x / view.scale), cy = Math.floor(view.y + this.mouse.y / view.scale);
    const K = this.S.core.L, m = this.env.mask();
    let best = -1, bd = 1e9;
    this.S.core.reach.forEach((r, i) => {
      const x = this.env.px + r.dx, y = this.env.py + r.dy;
      const d = Math.hypot(x - cx, y - cy);
      if (d < bd && d < 1.5 && (m[K.MINE_FIRST + i] || m[K.PLACE_FIRST + i])) { bd = d; best = i; }
    });
    this.hover = best;
  }

  drawOverlay(g, view) {
    const K = this.S.core.L, s = view.scale, m = this.env.mask(), core = this.S.core;
    if (this.mode === "human") {
      core.reach.forEach((r, i) => {
        const mine = m[K.MINE_FIRST + i], place = m[K.PLACE_FIRST + i];
        if (!mine && !place) return;
        const x = (this.env.px + r.dx - view.x) * s, y = (this.env.py + r.dy - view.y) * s;
        g.strokeStyle = i === this.hover ? "#ffd84a" : mine ? "rgba(111,211,155,.55)" : "rgba(255,255,255,.25)";
        g.lineWidth = i === this.hover ? 3 : 1.5;
        g.strokeRect(x + 2, y + 2, s - 4, s - 4);
      });
    } else if (this.trace) {
      // agent: heat on reach cells = max(mine, place) probability
      core.reach.forEach((r, i) => {
        const p = Math.max(this.trace.probs[K.MINE_FIRST + i], this.trace.probs[K.PLACE_FIRST + i]);
        if (p < 0.01) return;
        const x = (this.env.px + r.dx - view.x) * s, y = (this.env.py + r.dy - view.y) * s;
        g.fillStyle = `rgba(239,123,95,${Math.min(0.6, p * 1.5)})`; g.fillRect(x, y, s, s);
      });
      const a = this.lastAction;
      if (a >= K.MINE_FIRST && a < K.PLACE_FIRST + K.REACH_COUNT) {
        const i = (a - K.MINE_FIRST) % K.REACH_COUNT, r = core.reach[i];
        const x = (this.env.px + r.dx - view.x) * s, y = (this.env.py + r.dy - view.y) * s;
        g.strokeStyle = a < K.PLACE_FIRST ? "#ffd84a" : "#6aa8ff"; g.lineWidth = 3; g.strokeRect(x + 1.5, y + 1.5, s - 3, s - 3);
      }
    }
  }

  hudUpdate(K) {
    const env = this.env, core = this.S.core, S = this.S;
    const hp = env.health, maxHp = env.maxHealth;
    const n = Math.ceil(maxHp / 20);
    if (this.hearts.children.length !== n) this.hearts.replaceChildren(...Array.from({ length: n }, () => el("i")));
    [...this.hearts.children].forEach((h, i) => { const f = clamp((hp - i * 20) / 20); h.style.background = `linear-gradient(90deg,#e8314f ${f * 100}%,#3a1f25 ${f * 100}%)`; h.style.clipPath = "path('M7 13 L1 7 A3.2 3.2 0 0 1 7 3 A3.2 3.2 0 0 1 13 7 Z')"; });
    $("#hud-stats").textContent = `step ${env.steps}/${env.maxSteps}  ·  depth ${env.py}  ·  return ${env.epReturn.toFixed(0)}  ·  seed ${env.seed}`;
    if (this.mode === "agent" || env.msg) $("#hud-msg").textContent = this.mode === "agent" ? `${core.actionNames[this.lastAction]}${env.msg ? "  ·  " + env.msg : ""}` : env.msg;
    // inventory: non-empty items, selected placeable highlighted
    const sel = core.placeables[env.selected];
    const held = []; for (let i = 0; i < K.ITEM_COUNT; i++) if (env.inv(i) > 0) held.push(i);
    const key = held.map((i) => i + ":" + env.inv(i)).join() + "|" + sel;
    if (key !== this.invKey) {
      this.invKey = key;
      this.invEl.replaceChildren(...held.map((i) => {
        const c = iconCanvas(S.items[i]);
        return el("div", { class: "slot" + (i === sel ? " sel" : ""), title: core.itemNames[i] }, c, el("b", {}, env.inv(i)));
      }));
    }
    const m = env.mask();
    this.crafts.forEach((d, r) => d.classList.toggle("ok", !!m[core.recipes[r].action]));
    const ach = env.achievements;
    this.advs.forEach((d, b) => d.classList.toggle("got", !!((ach >>> b) & 1)));
  }

  drawPanel() {
    const tr = this.trace, core = this.S.core;
    if (!tr) return;
    {
      const { g, w, h } = fitCanvas($("#agent-probs"));
      g.clearRect(0, 0, w, h);
      const top = [...tr.probs.keys()].sort((a, b) => tr.probs[b] - tr.probs[a]).slice(0, 7);
      g.font = "11px ui-monospace, Menlo, monospace"; g.fillStyle = "#8b8b94"; g.fillText("π(a|s) · top actions", 0, 11);
      top.forEach((a, i) => {
        const y = 20 + i * 18, p = tr.probs[a];
        g.fillStyle = a === this.lastAction ? "#ef7b5f" : "#3b3b46"; g.fillRect(118, y, (w - 160) * p, 12);
        g.fillStyle = "#e9e6e1"; g.fillText(core.actionNames[a].slice(0, 17), 0, y + 10);
        g.fillStyle = "#8b8b94"; g.fillText((p * 100).toFixed(0) + "%", w - 34, y + 10);
      });
    }
    const pv = fitCanvas($("#agent-value"));
    pv.g.clearRect(0, 0, pv.w, pv.h);
    lineChart(pv.g, 0, 0, pv.w, pv.h, [{ values: this.hist.value, color: "#ef7b5f" }], { label: "V(s) · critic", right: tr.value.toFixed(2), n: 200 });
    const pe = fitCanvas($("#agent-entropy"));
    pe.g.clearRect(0, 0, pe.w, pe.h);
    lineChart(pe.g, 0, 0, pe.w, pe.h, [{ values: this.hist.entropy, color: "#c39bff" }], { label: "entropy H(π)", right: tr.entropy.toFixed(2), n: 200, min: 0 });
    const pr = fitCanvas($("#agent-return"));
    pr.g.clearRect(0, 0, pr.w, pr.h);
    lineChart(pr.g, 0, 0, pr.w, pr.h, [{ values: this.hist.ret, color: "#f3c63c" }], { label: "episode return", right: fmt(this.env.epReturn), n: Math.max(200, this.hist.ret.length), min: 0 });
  }
}
function push(a, v, n = 200) { a.push(v); if (a.length > n) a.shift(); }
