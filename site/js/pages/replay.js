// Replay viewer: loads an audited LLM action tape, replays it in the real
// simulator (viz/terraria.wasm) and compares the rebuilt final state with the
// audited record in data/llm.json.
import { chrome, el, $, data, getJSON, fmt, achIcon, table, fail } from "../common.js";
import { boot, Episode, parseTape, draw, whileVisible } from "../sim.js";

chrome();

const BASE = 12;   // actions per second at 1x
const LEAD = 48;   // an unlock button seeks this many actions before the unlock (1 s at the default 4x)
const DEFAULT = "luna-batch-31000010-full16";

const STUDY = { "sol-smoke": "Sol smoke test", "luna-batch": "Luna development batch", "luna-harness": "Luna harness study" };
const HARNESS = {
  full16: "full observation, 8 turns of history, up to 16 actions per call",
  compact16: "compact observation, 2 turns of history, up to 16 actions per call",
  compact4: "compact observation, 2 turns of history, up to 4 actions per call",
  compact16_interrupt: "compact16, but control returns to the model after the first illegal action",
};
const ENDING = { death: "died", cost_budget: "stopped by the dollar guard", call_budget: "stopped by the call cap" };
const ENDING_SHORT = { death: "died", cost_budget: "dollar guard", call_budget: "call cap" };

const popcount = (m) => { let c = 0; m >>>= 0; while (m) { c += m & 1; m >>>= 1; } return c; };
function modelName(m, high = true) {
  const r = /gpt-([\d.]+)-(\w+)/.exec(m);
  const base = r ? `GPT-${r[1]} ${r[2][0].toUpperCase()}${r[2].slice(1)}` : m;
  return high && m.includes("(high)") ? `${base} (high)` : base;
}
const optionText = (a) => `${modelName(a.model, false)}, ${a.harness}, world ${fmt.int(a.world)}: ${a.score}/32, ${ENDING_SHORT[a.status] || a.status} at ${fmt.int(a.steps)}, ${fmt.usd(a.actual_cost_usd)}`;

(async () => {
  const [llm] = await data("llm");
  const attempts = llm.attempts;
  const byId = new Map(attempts.map((a) => [a.id, a]));
  const q = new URLSearchParams(location.search);
  const first = byId.get(q.get("id")) || byId.get(DEFAULT) || attempts[0];
  const deepT = q.has("t") ? Math.max(0, parseInt(q.get("t"), 10) || 0) : null;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;

  const canvas = $("#screen"), status = $("#status"), scrub = $("#scrub"), playBtn = $("#play");
  const sel = $("#attempt");
  for (const study of [...new Set(attempts.map((a) => a.study))]) {
    sel.append(el("optgroup", { label: STUDY[study] || study },
      attempts.filter((a) => a.study === study).map((a) => el("option", { value: a.id }, optionText(a)))));
  }

  // ---- player state ----
  let S = null, scratch = null, ep = null, cur = null, ill = null, illCum = null, died = false, token = 0;
  let playing = false, speed = +$("#speed").value, acc = 0, prev = { x: 0, y: 0 }, shown = -1, lastFrame = 0, visible = true;
  let unlockBtns = [];
  const sim = boot().then((s) => { S = s; scratch = s.core.env(); return s; });

  const enable = (on) => { for (const n of [playBtn, $("#back"), $("#fwd"), scrub]) n.disabled = !on; };
  const syncUrl = () => {
    if (!cur) return;
    const t = ep && ep.cur ? `&t=${ep.cur}` : "";
    history.replaceState(null, "", `?id=${encodeURIComponent(cur.id)}${t}`);
  };
  const setPlaying = (v) => {
    if (!ep) v = false;
    if (v && ep.cur >= ep.length) seek(0);
    playing = v; acc = 0;
    if (!v && ep) syncUrl();
    playBtn.textContent = v ? "Pause" : "Play";
  };
  function seek(k) {
    if (!ep) return;
    ep.seek(Math.max(0, Math.min(k, ep.length)));
    prev = { x: ep.env.px, y: ep.env.py }; acc = 0; shown = -1;
  }
  function stepFwd() {
    if (!ep || ep.cur >= ep.length) return;
    prev = { x: ep.env.px, y: ep.env.py };
    ep.stepOnce(); shown = -1;
  }

  function showStep() {
    const env = ep.env, k = ep.cur;
    shown = k;
    scrub.value = String(k);
    scrub.setAttribute("aria-valuetext", `step ${k} of ${ep.length}`);
    const parts = [`step ${fmt.int(k)} of ${fmt.int(ep.length)}`, `health ${env.health}/${env.maxHealth}`,
      `${popcount(env.achievements)} achievements`, `${fmt.int(illCum[k])} illegal so far`];
    if (k > 0) parts.push(`last action: ${S.core.actionNames[ep.actions[k - 1]]}${ill[k - 1] ? " (illegal)" : ""}`);
    if (k === ep.length) parts.push(died ? "episode over: died" : `tape ends: ${ENDING[cur.status] || cur.status}`);
    status.textContent = parts.join(" \u00b7 ");
    for (const b of unlockBtns) b.classList.toggle("future", +b.dataset.step > k);
  }

  // ---- attempt text that needs no simulator ----
  function describe(a) {
    $("#attempt-sub").textContent = `${modelName(a.model)} with the ${a.harness} harness ${a.harness_version} (${HARNESS[a.harness] || a.harness}), ${STUDY[a.study] || a.study}, world ${fmt.int(a.world)}. Score ${a.score}/32 after ${fmt.int(a.steps)} actions; ${ENDING[a.status] || a.status}.`;
    canvas.setAttribute("aria-label", `Replay of ${modelName(a.model)} with the ${a.harness} harness on world ${a.world}, rendered with Terraria art`);
    const nat = a.native;
    const facts = [
      ["Score", `${a.score}/32`, `native return ${fmt.n(nat.episode_return, 0)}`],
      ["Actions", fmt.int(a.steps), `of 3,000; ${ENDING_SHORT[a.status] || a.status}`],
      ["Model calls", fmt.int(a.calls), `${fmt.n(a.steps / a.calls, 1)} actions per call`],
      ["Tokens", fmt.int(a.tokens), `${fmt.int(a.tokens / a.calls)} per call`],
      ["Illegal attempts", fmt.int(a.illegal_attempts), `${fmt.pct(a.illegal_attempts / a.steps, 1)} of actions`],
      ["Cost", fmt.usd(a.actual_cost_usd), `provider-reported; guard accounted ${fmt.usd(a.accounted_cost_usd)}`],
      ["Wall time", fmt.hours(a.elapsed_seconds / 3600), "whole episode, model and game"],
      ["World", fmt.int(a.world), a.study === "luna-harness" ? "public world, played by all four harnesses" : "public development world"],
    ];
    $("#facts").replaceChildren(...facts.map(([k, v, s]) => el("div", {}, el("dt", {}, k), el("dd", {}, v, " ", el("small", {}, s)))));
    $("#facts-note").replaceChildren("Source: ", el("code", {}, a.source), ". Tape: ", el("a", { href: a.tape }, el("code", {}, `site/${a.tape}`)), ".");
    $("#verify-summary").className = "verify-summary";
    $("#verify-summary").textContent = "Replaying the tape...";
    $("#verify-table").replaceChildren();
    $("#unlocks").replaceChildren();
    unlockBtns = [];
  }

  // ---- verification ----
  function verify(a, tape, e, illegalCount) {
    const fin = e.final, nat = a.native, names = S.core.achNames;
    const firstAt = {};
    for (const u of e.unlocks) if (!(names[u.bit] in firstAt)) firstAt[names[u.bit]] = u.step;
    const replayed = new Set(Object.keys(firstAt));
    const audited = new Set(a.achievements);
    const sameSet = replayed.size === audited.size && [...audited].every((n) => replayed.has(n));
    const fuKeys = Object.keys(a.first_unlock);
    const fuSame = fuKeys.filter((k) => firstAt[k] === a.first_unlock[k]).length;
    const pc = popcount(fin.achievements);
    const yn = (b) => (b ? "yes" : "no");
    const rows = [
      { check: "World seed (tape header vs record)", rec: fmt.int(a.world), got: fmt.int(tape.seed), ok: tape.seed === a.world },
      { check: "Actions on the tape", rec: fmt.int(nat.steps), got: fmt.int(tape.actions.length), ok: tape.actions.length === nat.steps && tape.count === tape.actions.length },
      { check: "Final step counter", rec: fmt.int(nat.steps), got: fmt.int(fin.steps), ok: fin.steps === nat.steps },
      { check: "Achievement mask", rec: String(nat.achievement_mask), got: String(fin.achievements), ok: fin.achievements === nat.achievement_mask >>> 0 },
      { check: "Achievements unlocked (score)", rec: `${a.score}`, got: `${pc}`, ok: pc === a.score && pc === nat.achievements },
      { check: "Health at the end", rec: `${nat.health}`, got: `${fin.health}`, ok: fin.health === nat.health },
      { check: "Native episode return", rec: fmt.n(nat.episode_return, 1), got: fmt.n(fin.ret, 1), ok: Math.abs(fin.ret - nat.episode_return) < 1e-4 },
      { check: "Achievement names", rec: `${audited.size} names`, got: `${replayed.size} names`, ok: sameSet,
        title: sameSet ? null : `Only in record: ${[...audited].filter((n) => !replayed.has(n)).join(", ") || "none"}. Only in replay: ${[...replayed].filter((n) => !audited.has(n)).join(", ") || "none"}.` },
      { check: "First-unlock step of each achievement", rec: `${fuKeys.length} steps`, got: `${fuSame} of ${fuKeys.length} equal`, ok: fuSame === fuKeys.length && replayed.size === fuKeys.length },
      { check: "Ended in death", rec: yn(a.died), got: yn(died), ok: died === a.died },
      { check: "Illegal attempts (legal-action mask)", rec: fmt.int(a.illegal_attempts), got: fmt.int(illegalCount), ok: illegalCount === a.illegal_attempts },
    ];
    const good = rows.filter((r) => r.ok).length;
    const sum = $("#verify-summary");
    sum.className = `verify-summary ${good === rows.length ? "check-ok" : "check-bad"}`;
    sum.textContent = good === rows.length
      ? `All ${rows.length} checks match: the browser rebuilt the audited episode exactly.`
      : `${rows.length - good} of ${rows.length} checks do not match the audited record.`;
    $("#verify-table").replaceChildren(table([
      { key: "check", label: "Check", render: (r) => el("span", { title: r.title }, r.check) },
      { key: "rec", label: "Audited record", cls: "r", render: (r) => el("span", { class: "num" }, r.rec) },
      { key: "got", label: "Browser replay", cls: "r", render: (r) => el("span", { class: "num" }, r.got) },
      { key: "ok", label: "Result", render: (r) => el("span", { class: r.ok ? "check-ok" : "check-bad" }, r.ok ? "match" : "mismatch") },
    ], rows, { caption: `Replay checks for ${a.id}` }));
  }

  // ---- load one attempt ----
  async function load(a, t = 0, autoplay = false) {
    const my = ++token;
    cur = a; ep = null; setPlaying(false); enable(false); sel.value = a.id;
    describe(a);
    status.textContent = "Loading the simulator...";
    try { await sim; } catch (e) {
      status.textContent = `The simulator could not load. It needs the viz build and local Terraria textures (make -C site serve). ${e.message}`;
      $("#verify-summary").textContent = "No replay: the simulator did not load.";
      return;
    }
    status.textContent = `Replaying ${fmt.int(a.steps)} actions from the tape...`;
    const res = await fetch(a.tape);
    if (!res.ok) throw new Error(`${a.tape}: HTTP ${res.status}`);
    const tape = parseTape(await res.text());
    if (my !== token) return;
    const e = new Episode(S, tape.seed, tape.actions);
    await e.record();
    if (my !== token) return;
    died = e.env.terminated;
    // recount illegal attempts: actions the legal-action mask rejected in the state where they were issued
    const n = e.length;
    ill = new Uint8Array(n); illCum = new Uint32Array(n + 1);
    scratch.reset(tape.seed);
    for (let i = 0; i < n; i++) {
      ill[i] = scratch.mask()[e.actions[i]] ? 0 : 1;
      illCum[i + 1] = illCum[i] + ill[i];
      scratch.step(e.actions[i]);
    }
    ep = e;
    scrub.max = String(n);
    unlockBtns = e.unlocks.map((u) => {
      const name = S.core.achNames[u.bit];
      return el("button", { type: "button", "data-step": u.step, "aria-label": `${name}, unlocked at step ${u.step}. Play from ${LEAD} actions before.`,
        onclick: () => { seek(u.step - LEAD); setPlaying(!reduce); syncUrl(); } },
      achIcon(name), name, el("span", { class: "at num" }, fmt.int(u.step)));
    });
    $("#unlocks").replaceChildren(...unlockBtns);
    verify(a, tape, e, illCum[n]);
    seek(t);
    enable(true);
    if (autoplay && !reduce && ep.cur < ep.length) setPlaying(true);
  }

  // ---- render loop ----
  whileVisible(canvas, (v) => { visible = v; });
  const frame = (now) => {
    const dt = Math.min(0.1, (now - (lastFrame || now)) / 1000); lastFrame = now;
    if (ep) {
      if (playing) {
        acc += dt * BASE * speed;
        while (acc >= 1 && ep.cur < ep.length) { prev = { x: ep.env.px, y: ep.env.py }; ep.stepOnce(); acc -= 1; }
        if (ep.cur >= ep.length) setPlaying(false);
      }
      const env = ep.env, f = playing ? Math.min(1, acc) : 1;
      const p = { x: prev.x + (env.px - prev.x) * f, y: prev.y + (env.py - prev.y) * f };
      if (visible) draw(S, canvas, env, { tiles: 18, player: p, time: now / 1000, walking: playing && env.px !== prev.x && f < 1 });
      if (ep.cur !== shown) showStep();
    }
    requestAnimationFrame(frame);
  };
  requestAnimationFrame(frame);

  // ---- controls ----
  const select = (id, scroll = false) => {
    const a = byId.get(id);
    if (!a) return;
    sel.value = id;
    load(a, 0).then(syncUrl).catch((e) => fail($("#viewer"), e));
    if (scroll) $("#viewer").scrollIntoView({ behavior: reduce ? "auto" : "smooth" });
  };
  sel.addEventListener("change", () => select(sel.value));
  playBtn.addEventListener("click", () => setPlaying(!playing));
  $("#back").addEventListener("click", () => { setPlaying(false); seek((ep?.cur ?? 0) - 1); syncUrl(); });
  $("#fwd").addEventListener("click", () => { setPlaying(false); stepFwd(); syncUrl(); });
  $("#speed").addEventListener("change", (e) => { speed = +e.target.value; });
  scrub.addEventListener("input", () => { setPlaying(false); seek(+scrub.value); });
  scrub.addEventListener("change", syncUrl);
  document.addEventListener("keydown", (e) => {
    if (!ep || e.altKey || e.ctrlKey || e.metaKey) return;
    const tag = e.target.tagName;
    if (e.key === " ") {
      if (["BUTTON", "SELECT", "INPUT", "TEXTAREA", "A", "SUMMARY"].includes(tag)) return;
      e.preventDefault(); setPlaying(!playing);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
      if (["SELECT", "INPUT", "TEXTAREA"].includes(tag)) return;
      e.preventDefault(); setPlaying(false);
      if (e.key === "ArrowLeft") seek(ep.cur - 1); else stepFwd();
      syncUrl();
    }
  });

  // ---- all attempts ----
  $("#all-table").append(table([
    { key: "agent", label: "Attempt", sort: (a) => a.id, render: (a) => el("span", {},
      el("a", { class: "agent-name", href: `replay.html?id=${encodeURIComponent(a.id)}`, onclick: (ev) => { ev.preventDefault(); select(a.id, true); } },
        `${modelName(a.model, false)}, ${a.harness}`),
      el("span", { class: "agent-sub" }, `${STUDY[a.study] || a.study}, harness ${a.harness_version}`)) },
    { key: "world", label: "World", cls: "r", sort: (a) => a.world, render: (a) => el("span", { class: "num" }, fmt.int(a.world)) },
    { key: "score", label: "Score /32", cls: "r", sort: (a) => a.score, render: (a) => el("b", { class: "num" }, a.score) },
    { key: "steps", label: "Actions", cls: "r", sort: (a) => a.steps, render: (a) => el("span", { class: "num" }, fmt.int(a.steps)) },
    { key: "status", label: "Ending", sort: (a) => a.status, render: (a) => ENDING_SHORT[a.status] || a.status },
    { key: "ill", label: "Illegal", cls: "r", sort: (a) => a.illegal_attempts / a.steps, render: (a) => el("span", { class: "num" }, fmt.pct(a.illegal_attempts / a.steps, 1)) },
    { key: "calls", label: "Calls", cls: "r", sort: (a) => a.calls, render: (a) => el("span", { class: "num" }, fmt.int(a.calls)) },
    { key: "cost", label: "Cost", cls: "r", sort: (a) => a.actual_cost_usd, render: (a) => el("span", { class: "num" }, fmt.usd(a.actual_cost_usd)) },
    { key: "min", label: "Wall time", cls: "r", sort: (a) => a.elapsed_seconds, render: (a) => el("span", { class: "num" }, fmt.hours(a.elapsed_seconds / 3600)) },
  ], attempts, { caption: "All audited LLM attempts" }));

  // ---- the PPO policy on the viz page ----
  Promise.all([getJSON("viz/data/run.json"), data("rl")]).then(([run, [rl]]) => {
    const ck = run.checkpoints[run.checkpoints.length - 1];
    const match = rl.runs.find((r) => r.seed === run.config.seed && r.steps === ck.steps &&
      Math.abs(r.score - ck.mean_achievements) < 1e-6 && Math.abs(r.deaths - ck.death_rate) < 1e-6);
    $("#ppo-note").textContent = `The viz page runs one of those checkpoints live in your browser, with its action probabilities, value estimate and entropy next to the game: the ${fmt.steps(ck.steps)}-step policy from training seed ${run.config.seed}${match ? ` (${match.variant}, ${match.arm})` : ""}, which scored ${fmt.n(ck.mean_achievements, 2)}/32 with ${fmt.pct(ck.death_rate, 1)} deaths on ${ck.episodes} validation worlds.`;
  }).catch((e) => console.warn(e));

  await load(first, deepT ?? 0, deepT != null);
})().catch((e) => fail($("#main"), e));
