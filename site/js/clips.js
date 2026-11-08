// Skill clips cut from one live-recorded episode of the viz policy: each clip
// replays the steps around an achievement's first unlock, looping.
import { boot, Episode, rng, draw, whileVisible } from "./sim.js";
import { el, achIcon, fmt } from "./common.js";

const BEFORE = 70, AFTER = 25, STEP = 1 / 14;

export async function clips(root, spec) {
  const status = el("p", { class: "note" }, "Recording one episode of the policy in your browser...");
  root.append(status);
  let S;
  try { S = await boot(); } catch (e) { status.textContent = `The simulator could not load: ${e.message}`; return; }
  const ep = new Episode(S, spec.seed);
  await ep.record({ policy: true, rand: rng(0x2545f491) });
  const first = new Map();
  for (const u of ep.unlocks) { const n = S.core.achNames[u.bit]; if (!first.has(n)) first.set(n, u.step); }
  const shown = spec.clips.filter((c) => first.has(c.ach));
  const missing = spec.clips.filter((c) => !first.has(c.ach)).map((c) => c.ach);
  status.textContent = `World ${spec.seed}: the 2.1B-step policy unlocked ${first.size} of 32 achievements in ${fmt.int(ep.length)} steps. Each clip loops the ${BEFORE + AFTER} steps around a first unlock.` +
    (missing.length ? ` Not reached in this episode: ${missing.join(", ")}.` : "");
  const grid = el("div", { class: "clips" });
  root.append(grid);
  for (const c of shown) {
    const at = first.get(c.ach), from = Math.max(0, at - BEFORE), to = Math.min(ep.length, at + AFTER);
    const canvas = el("canvas", { class: "px", role: "img", "aria-label": `${c.title}: the policy's own play around step ${at}` });
    grid.append(el("figure", { class: "clip" }, canvas,
      el("figcaption", {}, el("b", {}, achIcon(c.ach), " ", c.title), el("span", { class: "muted" }, `${c.text} First unlock at step ${fmt.int(at)}.`))));
    // each clip keeps its own Episode view (shares recorded actions and snapshots)
    const view = new Episode(S, spec.seed, ep.actions, ep.every);
    view.snaps = ep.snaps; view.length = ep.length;
    view.seek(from);
    let prev = { x: view.env.px, y: view.env.py }, acc = 0, lerp = 1, last = 0, on = false;
    whileVisible(canvas, (v) => { on = v; });
    const frame = (now) => {
      const dt = Math.min(0.1, (now - (last || now)) / 1000); last = now;
      if (on) {
        acc += dt;
        if (acc >= STEP) {
          acc = 0; prev = { x: view.env.px, y: view.env.py }; lerp = 0;
          if (view.cur >= to) { view.seek(from); prev = { x: view.env.px, y: view.env.py }; } else view.stepOnce();
        }
        lerp = Math.min(1, lerp + dt / STEP);
        const p = { x: prev.x + (view.env.px - prev.x) * lerp, y: prev.y + (view.env.py - prev.y) * lerp };
        draw(S, canvas, view.env, { tiles: 11, player: p, time: now / 1000, walking: view.env.px !== prev.x && lerp < 1 });
      }
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }
}
