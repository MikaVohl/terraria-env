// Boot, scroll timeline, and the per-frame dispatcher.
import { loadWasm, halfToFloat } from "./wasm.js";
import { loadArt } from "./terraria.js";
import { WorldRenderer } from "./render.js";
import { Focus } from "./play.js";
import { Grid, drawTraining } from "./grid.js";
import { Replay } from "./replay.js";
import { Lab } from "./lab.js";
import { ObsZoom } from "./obs.js";
import { ActZoom, RewZoom } from "./actrew.js";
import { NetZoom, weightViews } from "./net.js";
import { SimZoom } from "./csim.js";
import { OutroZoom } from "./outro.js";
import { $, $$, el, clamp, smooth, lerp, ease, fitCanvas, human } from "./ui.js";

const REPLAY_SEED = 23000001, PX_PER_STEP = 22, FOCUS_CELL = 7 * 16 + 8, ZOOM_CELL = 3 * 16 + 4;

async function boot() {
  const S = { focusSeed: 42 };
  [S.core, S.core2] = await Promise.all([loadWasm(), loadWasm()]);
  S.art = await loadArt();
  S.items = S.art.items; S.achIcons = S.art.ach;
  S.run = await (await fetch("data/run.json")).json();
  S.blobs = {};
  await Promise.all(S.run.checkpoints.map(async (c) => { S.blobs[c.steps] = await (await fetch("data/" + c.file)).arrayBuffer(); }));
  const best = S.run.checkpoints[S.run.checkpoints.length - 1];
  S.policy = best;
  S.core.loadPolicy(S.blobs[best.steps], best.hidden, best.cell_width);
  S.core2.loadPolicy(S.blobs[best.steps], best.hidden, best.cell_width);
  S.W2 = weightViews(halfToFloat(new Uint16Array(S.blobs[best.steps]), new Float32Array(best.floats)), best.hidden, best.cell_width);
  S.renderer = new WorldRenderer(S.core, S.art);
  S.renderer2 = new WorldRenderer(S.core2, S.art);
  S.focus = new Focus(S);
  S.grid = new Grid(S);
  S.replay = new Replay(S.core2, REPLAY_SEED);
  S.lab = new Lab(S);
  S.zooms = { obs: new ObsZoom(S, S.lab), act: new ActZoom(S, S.lab), rew: new RewZoom(S, S.lab), net: new NetZoom(S, S.lab), sim: new SimZoom(S, S.lab), outro: new OutroZoom(S) };
  $("#z-seed").textContent = REPLAY_SEED;
  $("#o-bytes").textContent = S.core.L.ENV_BYTES.toLocaleString("en-US");
  checkpointPickers(S);
  for (const b of $$("#pace-pick button")) b.addEventListener("click", () => {
    $$("#pace-pick button").forEach((x) => x.classList.toggle("on", x === b)); S.grid.setPace(b.dataset.max === "1");
  });
  chapterNav();
  document.body.classList.remove("loading");
  let last = performance.now();
  const frame = (now) => { const dt = Math.min(0.1, (now - last) / 1000); last = now; tick(S, dt, now); requestAnimationFrame(frame); };
  requestAnimationFrame(frame);
}

function checkpointPickers(S) {
  const label = (c) => (c.steps ? human(c.steps) : "untrained");
  const pickers = [$("#ckpt-pick"), el("div", { class: "ckpt-pick" })];
  $("#agent-panel").insertBefore(pickers[1], $("#agent-probs"));
  const sync = () => {
    for (const p of pickers) [...p.children].forEach((b, i) => b.classList.toggle("on", S.run.checkpoints[i] === S.policy));
    const c = S.policy;
    $("#ckpt-label").textContent = `· ${c.steps ? label(c) + " steps" : "untrained"}${c.mean_achievements ? ` · scored ${c.mean_achievements.toFixed(1)}/32` : ""}`;
  };
  for (const p of pickers) for (const c of S.run.checkpoints) p.append(el("button", { onclick: () => {
    S.policy = c; S.core.loadPolicy(S.blobs[c.steps], c.hidden, c.cell_width); S.grid.policyChanged(); sync(); drawTraining(S);
  } }, label(c)));
  sync();
}

function chapterNav() {
  const nav = $("#chapters");
  for (const s of $$(".chapter")) nav.append(el("a", { href: "#" + s.id, onclick: (e) => { e.preventDefault(); scrollTo({ top: s.offsetTop + 2, behavior: "smooth" }); } }, el("span", {}, s.dataset.title)));
}

/* Which chapter holds the viewport's centre line, progress through it, and
   which of its text steps is current. */
function timeline() {
  const mid = scrollY + innerHeight / 2, ch = $$(".chapter");
  let i = ch.findIndex((s) => mid >= s.offsetTop && mid < s.offsetTop + s.offsetHeight);
  if (i < 0) i = mid < ch[0].offsetTop ? 0 : ch.length - 1;
  const s = ch[i], p = clamp((mid - s.offsetTop) / s.offsetHeight);
  const steps = $$(".step", s);
  const line = innerHeight * 0.62;
  let card = 0; steps.forEach((st, k) => { if (st.getBoundingClientRect().top < line) card = k; });
  // progress from this card crossing the line to the next card (or section end) crossing it
  const a = steps[card]?.getBoundingClientRect().top ?? 0;
  const b = steps[card + 1]?.getBoundingClientRect().top ?? s.getBoundingClientRect().bottom - innerHeight * 0.38;
  const cardP = clamp((line - a) / Math.max(1, b - a));
  return { i, id: s.id, p, X: i + p, card, cardP, sections: ch };
}

const on = (sel, v) => $(sel).classList.toggle("on", !!v);

function tick(S, dt, now) {
  const T = timeline(), X = T.X, id = T.id;
  document.body.className = `ch-${id}`;
  $$("#chapters a").forEach((a, i) => a.classList.toggle("on", i === T.i));
  const world = $("#world");
  const showWorld = X < 4.62;
  world.style.display = showWorld ? "block" : "none";
  on("#hud", X < 2.12);
  on("#agent-panel", X >= 1 && X < 2.05);
  on("#grid-panel", X >= 2.25 && X < 3);
  on("#train-panel", X >= 3 && X < 4);
  on("#lab", X >= 4.55);

  // focused world: human, then agent
  S.focus.setMode(X < 1 ? "human" : "agent");
  S.focus.update(dt, X < 2.4);
  if (X >= 1 && X < 2.05) S.focus.drawPanel();

  // grid workers only while they can be seen
  S.grid.setRunning(X >= 1.9 && X < 4.7);
  if (X >= 2.25 && X < 3) S.grid.panel(now);
  if (X >= 3 && X < 4 && !S.trainDrawn) { drawTraining(S); S.trainDrawn = true; }
  if (X < 3 || X >= 4) S.trainDrawn = false;

  // replay step from scroll position, starting partway into "zoom"
  const zoomSec = T.sections[4], start = zoomSec.offsetTop + zoomSec.offsetHeight * 0.3;
  const sf = Math.max(0, (scrollY + innerHeight / 2 - start) / PX_PER_STEP);
  const k = S.lab.at(Math.floor(sf));
  if (!S.replay.done) S.replay.extend(X > 4 ? 30 : 6);

  if (showWorld) drawWorld(S, world, X, now);
  if (X >= 4.55) drawLab(S, T, sf - Math.floor(sf), k);
  else for (const z of ["obs", "act", "rew", "net", "sim", "outro"]) on("#zoom-" + z, false);
}

function drawWorld(S, canvas, X, now) {
  const { g, w, h } = fitCanvas(canvas);
  const f = S.focus, env = f.env;
  const full = Math.max(22, Math.round(h / 24));
  const zoomOut = ease(smooth(2.0, 2.35, X));
  const zoomIn = ease(smooth(4.05, 4.55, X));
  g.fillStyle = "#121214"; g.fillRect(0, 0, w, h);
  let gridRect = null;
  if (zoomOut > 0) gridRect = S.grid.draw(g, w, h, Math.min(1, zoomOut * 1.4) * (1 - zoomIn), zoomIn > 0 ? ZOOM_CELL : -1);
  // focused world: full screen -> its grid cell
  if (zoomIn < 1) {
    const cell = gridRect ? S.grid.cellRect(gridRect, FOCUS_CELL) : { x: 0, y: 0, w, h };
    const r = { x: lerp(0, cell.x, zoomOut), y: lerp(0, cell.y, zoomOut), w: lerp(w, cell.w, zoomOut), h: lerp(h, cell.h, zoomOut) };
    const scale = lerp(full, cell.w / 32, zoomOut);
    const p = f.playerPos();
    const view = { x: p.x + 1 - r.w / scale / 2, y: p.y - 1 - r.h / scale / 2, scale, w: r.w, h: r.h };
    g.save(); g.translate(r.x, r.y); g.beginPath(); g.rect(0, 0, r.w, r.h); g.clip();
    g.globalAlpha = 1 - zoomIn;
    S.renderer.draw(g, env, view, { player: p, walking: f.walking(), time: now / 1000 });
    if (zoomOut < 0.05) { f.pickHover({ ...view, x: view.x - r.x / scale, y: view.y - r.y / scale }); f.drawOverlay(g, view); }
    g.restore();
    if (zoomOut > 0.3) { g.save(); g.globalAlpha = 1 - zoomIn; g.strokeStyle = "#ef7b5f"; g.lineWidth = 2; g.strokeRect(r.x - 2, r.y - 2, r.w + 4, r.h + 4); g.restore(); }
  }
  // zoom into another world: the replay episode grows from its cell to the lab's world panel
  if (zoomIn > 0 && gridRect) {
    const cell = S.grid.cellRect(gridRect, ZOOM_CELL), lw = $("#lab-world").getBoundingClientRect();
    const target = lw.width > 0 ? lw : { left: 470, top: 90, width: w * 0.35, height: h * 0.5 };
    const r = { x: lerp(cell.x, target.left, zoomIn), y: lerp(cell.y, target.top, zoomIn), w: lerp(cell.w, target.width, zoomIn), h: lerp(cell.h, target.height, zoomIn) };
    const e = S.replay.view, final = Math.max(8, Math.floor(Math.min(target.width / 30, target.height / 18)));
    const scale = lerp(cell.w / 32, final, zoomIn);
    const view = { x: e.px + 1 - r.w / scale / 2, y: e.py - 1 - r.h / scale / 2, scale, w: r.w, h: r.h };
    g.save(); g.translate(r.x, r.y); g.beginPath(); g.rect(0, 0, r.w, r.h); g.clip();
    S.renderer2.draw(g, e, view, { time: now / 1000 });
    g.restore();
    g.strokeStyle = "#ef7b5f"; g.lineWidth = 2; g.strokeRect(r.x - 2, r.y - 2, r.w + 4, r.h + 4);
  }
}

function drawLab(S, T, frac, k) {
  const lab = S.lab, id = T.id;
  lab.head();
  const zoom = { obs: "obs", action: "act", reward: "rew", net: "net", csim: "sim", outro: "outro" }[id];
  for (const z of ["obs", "act", "rew", "net", "sim", "outro"]) on("#zoom-" + z, z === zoom);
  if (!zoom) {
    lab.drawWorld($("#lab-world"));
    lab.envMachine();
    lab.drawAgentMini(clamp((frac - 0.3) / 0.35));
    lab.drawExchange(frac);
    return;
  }
  if (zoom === "obs") S.zooms.obs.draw(T.card);
  else if (zoom === "act") S.zooms.act.draw();
  else if (zoom === "rew") S.zooms.rew.draw();
  else if (zoom === "net") {
    const c = T.card, q = T.cardP;
    const phase = c === 0 ? q * 0.6 : c === 1 ? 0.6 + q * 0.4 : c === 2 ? 1 + Math.min(1, q * 1.3) : 2 + q;
    S.zooms.net.draw(phase);
  } else if (zoom === "sim") S.zooms.sim.draw(T.card);
  else S.zooms.outro.draw();
}

boot().catch((e) => { $("#loader").innerHTML = `<div class="mono" style="color:#ff6060">failed to start: ${e.message}</div>`; console.error(e); });
