// Header band: the 2.1B-step policy playing a world live in the page, in the
// real simulator with Terraria art. Pauses off screen and on request.
import { boot, policyAction, rng, draw, achBits, whileVisible } from "./sim.js";
import { el, achIcon } from "./common.js";

const STEP = 1 / 9; // seconds per step, as viz's agent mode

export async function hero(fig, { seed = 42 } = {}) {
  const canvas = fig.querySelector("canvas");
  const feed = fig.querySelector(".ach-feed");
  const btn = fig.querySelector("button.pause");
  const status = fig.querySelector(".status");
  let S;
  try { S = await boot(); } catch (e) {
    fig.append(el("div", { class: "err" }, `The live simulator needs the viz build and local Terraria textures (make -C site serve). ${e.message}`));
    console.warn(e);
    return;
  }
  const env = S.core.env();
  let world = seed, rand = rng(0x9e3779b9);
  env.reset(world);
  let prev = { x: env.px, y: env.py }, lerp = 1, acc = 0, last = 0, running = true, visible = true, lastAch = 0;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) running = false;
  const setBtn = () => { btn.textContent = running ? "Pause" : "Play"; btn.setAttribute("aria-pressed", String(!running)); };
  setBtn();
  btn.addEventListener("click", () => { running = !running; setBtn(); });
  whileVisible(fig, (v) => { visible = v; });
  const unlocked = (bit) => {
    const name = S.core.achNames[bit];
    feed.prepend(el("div", {}, achIcon(name), `${name}, step ${env.steps}`));
    while (feed.children.length > 4) feed.lastChild.remove();
  };
  const frame = (now) => {
    const dt = Math.min(0.1, (now - (last || now)) / 1000); last = now;
    if (visible) {
      if (running) {
        acc += dt;
        if (acc >= STEP) {
          acc = 0;
          prev = { x: env.px, y: env.py }; lerp = 0;
          env.step(policyAction(S, env, rand));
          const a = env.achievements >>> 0;
          if (a !== lastAch) { for (const b of achBits((a & ~lastAch) >>> 0)) unlocked(b); lastAch = a; }
          if (env.done) {
            world += 1; env.reset(world); lastAch = 0; feed.replaceChildren(); prev = { x: env.px, y: env.py };
          }
        }
        lerp = Math.min(1, lerp + dt / STEP);
      }
      const p = { x: prev.x + (env.px - prev.x) * lerp, y: prev.y + (env.py - prev.y) * lerp };
      draw(S, canvas, env, { tiles: 15, player: p, time: now / 1000, walking: running && Math.abs(env.px - prev.x) > 0 && lerp < 1 });
      status.textContent = `world ${world}, step ${env.steps.toLocaleString("en-US")} of 3,000, ${countBits(env.achievements >>> 0)} achievements`;
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);
}

function countBits(m) { let c = 0; while (m) { c += m & 1; m >>>= 1; } return c; }
