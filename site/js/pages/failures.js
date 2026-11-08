// Failure gallery: one card per item in data/failures.json, text left and a
// visual right. Visuals are drawn from data/rl.json and data/llm.json; cards
// with a replay get a live clip of the audited tape and a link into replay.html.
import { chrome, el, $, $$, data, fmt, esc, kindBadge, sampleBadge, table, fail } from "../common.js";
import { bars, scatter, legend } from "../charts.js";
import { videoPlayer, mmss } from "../video.js";
import { boot, Episode, parseTape, draw, whileVisible } from "../sim.js";

chrome();

const ENDING = { death: "died", cost_budget: "dollar guard", call_budget: "call cap" };
const ENDING_COLOR = { death: "--bad", cost_budget: "--llm", call_budget: "--base" };
const STUDY = { "sol-smoke": "Sol smoke", "luna-batch": "Luna batch", "luna-harness": "Luna harness study" };
const CONFIG_SHORT = { v8_default: "Standard arm, default supply", o3t2_standard: "Standard arm, ore 3x + trees 2x", generic_g9998: "Generic, gamma .9998", shaped_g9998: "Shaped, gamma .9998" };
const CLIP_STEP = 1 / 12;

const world = (w) => fmt.int(w);
const modelShort = (m) => { const r = /gpt-[\d.]+-(\w+)/.exec(m); return r ? r[1][0].toUpperCase() + r[1].slice(1) : m; };
const mean = (v) => v.reduce((s, x) => s + x, 0) / v.length;
const configColor = (key) => (key.startsWith("generic") ? "--rl" : "--shaped");
const replayHref = (id, t) => `replay.html?id=${encodeURIComponent(id)}${t ? `&t=${t}` : ""}`;

(async () => {
  const [fx, rl, llm, tb, vids] = await data("failures", "rl", "llm", "terrariabench", "videos");
  const tbRuns = new Map([...tb.runs, ...tb.earlier.default_v1.runs].map((r) => [r.run, r]));
  const videos = new Map(vids.videos.map((v) => [v.run, v]));
  const tbMain = tb.runs.filter((r) => !r.not_scored && !r.long);
  const tbSetup = (r) => r.setup.replace(/, smart_cursor on/, "").replace("realtime", "real time");
  const runs = new Map(rl.runs.map((r) => [r.id, r]));
  const attempts = new Map(llm.attempts.map((a) => [a.id, a]));
  const finals = Object.entries(rl.final).map(([key, f]) => ({ key, name: CONFIG_SHORT[key] || f.name, full: f.name, rs: f.runs.map((id) => runs.get(id)).filter(Boolean) }));
  const [v0, v1] = rl.validation_worlds;

  $("#intro-data").textContent = `LLM failures on Terraria-Lite come from the ${llm.attempts.length} audited LLM attempts on frozen v7, every one of which can be replayed in your browser. RL failures come from the ${rl.runs.length} v8 PPO runs, each evaluated on the 128 validation worlds ${world(v0)} to ${world(v1)}; "final configurations" are the four configurations trained with 5 seeds for 2B steps. Official Terraria failures come from the ${tb.runs.length} runs of the default-v2 campaign so far (interim) and its default-v1 predecessor, with recordings of the game. Every card names its source.`;

  // per-seed rows for the final configurations: bar = mean over seeds, dots = seeds
  const finalRows = (field, f = (v) => fmt.n(v, 1)) => finals.map((c) => {
    const vals = c.rs.map((r) => r[field]);
    return { label: c.name, value: mean(vals), dots: vals, color: configColor(c.key),
      tip: `<b>${esc(c.full)}</b><br>mean ${f(mean(vals))}<br>${c.rs.map((r) => `seed ${r.seed}: ${f(r[field])}`).join("<br>")}` };
  });
  const armShort = (r) => (r.arm.includes("frontier_surface") ? "surface-frontier shaping" : r.arm.includes("frontier") ? "frontier shaping" : r.arm.startsWith("no shaping") ? "generic" : r.arm);
  const runLabel = (r) => `${r.budget} ${armShort(r)}, gamma ${String(r.gamma).replace(/^0/, "")}, seed ${r.seed}`;
  const longShaped = rl.runs.filter((r) => (r.budget === "4B" || r.budget === "6B") && r.arm.includes("frontier") && r.variant.includes("log inventory") && r.anvils_crafted_per_ep != null);

  const figcap = (...kids) => el("figcaption", {}, ...kids);
  const chart = (vis) => vis.appendChild(el("div", { class: "chart" }));
  const sub = (vis, text) => vis.append(el("p", { class: "fail-sub" }, text));

  // ---- visuals ----
  const VIS = {
    illegal(vis) {
      const groups = new Map();
      for (const a of llm.attempts) {
        const k = `${a.study}|${a.harness}`;
        if (!groups.has(k)) groups.set(k, { study: a.study, harness: a.harness, version: a.harness_version, model: a.model, ill: 0, steps: 0, n: 0 });
        const g = groups.get(k); g.ill += a.illegal_attempts; g.steps += a.steps; g.n += 1;
      }
      bars(chart(vis), [...groups.values()].map((g) => ({
        label: `${STUDY[g.study]}, ${g.harness}`, value: g.ill / g.steps, color: "--llm",
        tip: `<b>${esc(modelShort(g.model))}, ${esc(g.harness)} (harness ${esc(g.version)})</b><br>${fmt.int(g.ill)} illegal of ${fmt.int(g.steps)} actions (${fmt.pct(g.ill / g.steps, 1)})<br>${g.n} world${g.n > 1 ? "s" : ""}, pooled`,
      })), { domain: [0, 0.5], fmt: (v) => fmt.pct(v, 1), tickFmt: (t) => fmt.pct(t), xLabel: "illegal attempts, share of executed actions", label: "Illegal action share per LLM harness arm" });
      vis.append(figcap("Illegal attempts divided by actions, pooled over each arm's worlds (1 to 3). An illegal attempt is an action the legal-action mask rejects; it still costs a tick. Data: data/llm.json."));
    },

    "llm-endings"(vis) {
      const rows = llm.attempts.map((a) => ({
        label: `${modelShort(a.model)} ${a.harness}, ${world(a.world)}: ${a.score}/32`, value: a.steps, color: ENDING_COLOR[a.status] || "--muted",
        tip: `<b>${esc(modelShort(a.model))}, ${esc(a.harness)}, world ${world(a.world)}</b><br>score ${a.score}/32 after ${fmt.int(a.steps)} actions<br>ending: ${esc(ENDING[a.status] || a.status)}<br>${fmt.int(a.calls)} calls, ${fmt.usd(a.actual_cost_usd)}`,
      }));
      bars(chart(vis), rows, { domain: [0, 3000], fmt: (v) => fmt.int(v), tickFmt: (t) => fmt.int(t), rowH: 22, xLabel: "actions taken before the episode ended (budget 3,000)", label: "How each LLM attempt ended" });
      vis.append(legend(Object.keys(ENDING).map((k) => ({ color: ENDING_COLOR[k], label: ENDING[k] }))));
      vis.append(figcap(`Each bar is one audited attempt: label shows model, harness, world and score. ${llm.attempts.filter((a) => a.died).length} of ${llm.attempts.length} died; none reached 3,000 actions. Data: data/llm.json.`));
    },

    "surface-seeds"(vis) {
      bars(chart(vis), finalRows("return to surface", (v) => fmt.n(v, 0)), { domain: [0, 128], fmt: (v) => fmt.n(v, 1), tickFmt: (t) => fmt.int(t), xLabel: "validation worlds (of 128) with a return to the surface", label: "Return to surface per seed, final configurations" });
      vis.append(legend([{ color: "--rl", label: "Generic" }, { color: "--shaped", label: "With disclosed priors (shaping)" }, { color: "--muted", label: "dots: individual training seeds" }]));
      vis.append(figcap("Bar: mean over 5 training seeds; dots: each seed's final policy. Seeds land near 0 or near 128, rarely in between. Data: data/rl.json."));
    },

    anvils(vis) {
      const extra = longShaped.map((r) => ({ label: runLabel(r), value: r.anvils_crafted_per_ep, color: "--shaped",
        tip: `<b>${esc(runLabel(r))}</b><br>${fmt.n(r.anvils_crafted_per_ep, 2)} anvils per episode<br>peak held at once: ${fmt.int(r.anvil_peak_max)}<br>iron pickaxe in ${fmt.int(r["craft iron pickaxe"])} of 128 worlds` }));
      sub(vis, "Anvils crafted per episode (mean over 128 validation worlds)");
      bars(chart(vis), [...finalRows("anvils_crafted_per_ep", (v) => fmt.n(v, 2)), ...extra], { fmt: (v) => fmt.n(v, 2), rowH: 22, ref: 1, refLabel: "one anvil", xLabel: "anvils crafted per episode", label: "Anvils crafted per episode" });
      const peak = (r) => r.anvil_peak_max;
      const peakRows = [...finals.map((c) => ({ label: c.name, value: Math.max(...c.rs.map(peak)), dots: c.rs.map(peak), color: configColor(c.key),
        tip: `<b>${esc(c.full)}</b><br>${c.rs.map((r) => `seed ${r.seed}: ${fmt.int(peak(r))}`).join("<br>")}` })),
      ...longShaped.map((r) => ({ label: runLabel(r), value: peak(r), color: "--shaped" }))];
      sub(vis, "Most anvils held at once in any validation episode");
      bars(chart(vis), peakRows, { domain: [0, 6], fmt: (v) => fmt.int(v), tickFmt: (t) => fmt.int(t), rowH: 22, xLabel: "anvil inventory peak, maximum over episodes", label: "Anvil inventory peak" });
      vis.append(figcap("Top rows: the four final configurations (first chart: mean over 5 seeds; second chart: maximum over 5 seeds; dots: seeds). Below: every 4B and 6B shaped run with log inventory. Data: data/rl.json (diag.json)."));
    },

    "pickaxe-legal"(vis) {
      const rs = rl.runs.filter((r) => (r.iron_pick_legal_eps || 0) > 0).sort((a, b) => b.iron_pick_legal_eps - a.iron_pick_legal_eps);
      const shapeOf = { "2B": "circle", "4B": "diamond", "6B": "square" };
      scatter(chart(vis), rs.map((r) => ({
        x: r.iron_pick_legal_eps, y: r["craft iron pickaxe"], label: runLabel(r), short: r.iron_pick_legal_eps > 50 ? `${r.budget}, seed ${r.seed}` : null,
        color: armShort(r) === "generic" ? "--rl" : "--shaped", shape: shapeOf[r.budget] || "triangle",
        tip: `<b>${esc(runLabel(r))}</b><br>legal in ${fmt.int(r.iron_pick_legal_eps)} of 128 worlds<br>crafted in ${fmt.int(r["craft iron pickaxe"])}`,
      })), { xDomain: [0, 130], yDomain: [0, 130], xLabel: "worlds where crafting the iron pickaxe was legal at least once", yLabel: "worlds where it was crafted", labels: true, height: 280, xFmt: (v) => fmt.int(v), yFmt: (v) => fmt.int(v), label: "Iron pickaxe: legal versus crafted" });
      vis.append(legend([{ color: "--shaped", label: "circle 2B, diamond 4B, square 6B" }]));
      vis.append(table([
        { key: "run", label: "Run", render: (r) => runLabel(r) },
        { key: "legal", label: "Legal in", cls: "r", sort: (r) => r.iron_pick_legal_eps, render: (r) => el("span", { class: "num" }, fmt.int(r.iron_pick_legal_eps)) },
        { key: "hit", label: "Crafted in", cls: "r", sort: (r) => r["craft iron pickaxe"], render: (r) => el("span", { class: "num" }, fmt.int(r["craft iron pickaxe"])) },
        { key: "bars", label: "Median iron bars", cls: "r", sort: (r) => r.iron_bars_med, render: (r) => el("span", { class: "num" }, r.iron_bars_med == null ? "n/a" : fmt.n(r.iron_bars_med, 1)) },
      ], rs, { caption: "Runs where the iron pickaxe was ever legal" }));
      vis.append(figcap(`The ${rs.length} runs (of ${rl.runs.length}) where crafting the iron pickaxe was legal in at least one of 128 validation worlds. The three runs where it is often legal lie on the diagonal: crafted in every world where it became legal. Data: data/rl.json (diag.json).`));
    },

    bench(vis, item) {
      const f = item.facts;
      sub(vis, "Newer recurrent policy, actions summed over 128 validation worlds");
      bars(chart(vis), [
        { label: "Actions carrying a workbench", value: f.carried, color: "--shaped" },
        { label: "Actions with the bench selected", value: f.selected, color: "--shaped" },
      ], { fmt: (v) => fmt.int(v), tickFmt: (t) => fmt.int(t), xLabel: "actions", label: "Workbench carried versus selected" });
      sub(vis, "Episodes (of 128) with any legal furnace opportunity");
      bars(chart(vis), [
        { label: "Newer recurrent policy", value: f.furnace_opportunities_recurrent, color: "--shaped" },
        { label: "Earlier MLP policy", value: f.furnace_opportunities_mlp, color: "--shaped" },
      ], { domain: [0, 128], fmt: (v) => fmt.int(v), tickFmt: (t) => fmt.int(t), xLabel: "validation episodes", label: "Furnace opportunities" });
      vis.append(figcap("Two preserved v4 policies on validation worlds 8,000,001 to 8,000,128 (scores 18.91 and 21.27 of 32). Numbers copied from docs/reports/CRAFTING_BOTTLENECKS_2026_10.md."));
    },

    world(vis) {
      const ab = rl.ablations.find((a) => a.dimension === "world");
      const ref = ab.settings.find((s) => s.label === ab.reference) || ab.settings[0];
      bars(chart(vis), ab.settings.map((s) => ({
        label: s.label, value: s.mean, dots: s.seeds.length > 1 ? s.seeds.map((x) => x.score) : null, color: /generic/.test(s.label) ? "--rl" : "--shaped",
        tip: `<b>${esc(s.label)}</b><br>mean ${fmt.n(s.mean, 2)}/32 over ${s.seeds.length} seed${s.seeds.length > 1 ? "s" : ""}<br>change vs reference ${s.delta >= 0 ? "+" : ""}${fmt.n(s.delta, 2)}`,
      })), { domain: [0, 30], fmt: (v) => fmt.n(v, 2), rowH: 24, ref: ref.mean, refLabel: "128x96 reference", xLabel: "validation score, achievements out of 32", label: "Larger world ablation" });
      vis.append(figcap(`${ab.title}: the reference is ${ab.reference} (5 seeds); every 256-wide row is 1 or 2 seeds, so read single rows with care. Data: data/rl.json (ablations).`));
    },

    idle(vis) {
      bars(chart(vis), finalRows("idle_steps", (v) => fmt.int(v)), { domain: [0, 3000], fmt: (v) => fmt.int(v), tickFmt: (t) => fmt.int(t), xLabel: "steps after the last achievement, mean per episode (episodes last up to 3,000)", label: "Idle steps after the last achievement" });
      vis.append(figcap("Bar: mean over 5 training seeds; dots: each seed, each the mean over 128 validation episodes. Data: data/rl.json (diag.json)."));
    },

    "tb-placed"(vis) {
      vis.append(table([
        { key: "run", label: "Run", render: (q) => el("span", {}, el("span", { class: "mono" }, q.run), el("span", { class: "agent-sub" }, tbSetup(tbRuns.get(q.run)))) },
        { key: "t", label: "Game time", cls: "r", render: (q) => el("span", { class: "num" }, q.game_s == null ? "n/a" : mmss(q.game_s)) },
        { key: "text", label: "The model said", render: (q) => el("q", {}, q.text) },
        { key: "obs", label: "Observer journal", render: (q) => { const r = tbRuns.get(q.run); const c = r.published_game_s?.workbench_1; const p = r.extended_game_s?.workbench_placed;
          return `bench crafted ${c != null ? mmss(c) : "never"}, placed ${p != null ? mmss(p) : "never"}`; } },
      ], tb.quotes, { caption: "Model claims of a placed work bench against the observer journal" }));
      const hk = tbMain.filter((r) => r.agent === "Haiku" && /medium/.test(r.setup));
      vis.append(figcap(`Haiku (thinking medium) on default-v2: bench crafted in ${hk.filter((r) => r.published_game_s?.workbench_1 != null).length} of ${hk.length} runs, placed in ${hk.filter((r) => r.extended_game_s?.workbench_placed != null).length}. Data: data/terrariabench.json (quotes from each run's evidence/timeline.md).`));
    },

    "tb-deaths"(vis) {
      const groups = new Map();
      for (const r of tbMain) {
        if (/none/.test(r.setup)) continue; // Haiku thinking-off pilot
        const k = `${r.agent}, ${r.clock === "realtime" ? "real time" : "paused"}`;
        if (!groups.has(k)) groups.set(k, { k, clock: r.clock, rs: [] });
        groups.get(k).rs.push(r);
      }
      const rows = [...groups.values()].sort((a, b) => a.k.localeCompare(b.k));
      bars(chart(vis), rows.map((g) => ({ label: g.k, value: mean(g.rs.map((r) => r.deaths)), dots: g.rs.length > 1 ? g.rs.map((r) => r.deaths) : null, color: g.clock === "realtime" ? "--bad" : "--rl",
        tip: `<b>${esc(g.k)}</b><br>${g.rs.map((r) => `${r.run}: ${r.deaths} deaths in ${fmt.n(r.game_s / 60, 1)} game-min`).join("<br>")}` })),
      { domain: [0, 25], fmt: (v) => fmt.n(v, 1), xLabel: "deaths per run (bar: mean, dots: runs)", label: "Deaths per run, real time against paused" });
      vis.append(legend([{ color: "--bad", label: "real time" }, { color: "--rl", label: "paused" }]));
      vis.append(figcap("default-v2 runs scored so far, 20 game-minutes (the censored Opus paused run: 15.6). Data: data/terrariabench.json (observer death events)."));
    },

    "tb-noaction"(vis) {
      const rs = tbMain.filter((r) => r.no_action_turns > 0).sort((a, b) => b.no_action_turns / b.calls - a.no_action_turns / a.calls);
      bars(chart(vis), rs.map((r) => ({ label: r.run, value: r.no_action_turns / r.calls, color: r.clock === "paused" ? "--rl" : "--bad",
        tip: `<b>${r.run}</b><br>${esc(tbSetup(r))}<br>${r.no_action_turns} of ${r.calls} replies without an action` })),
      { domain: [0, 0.7], fmt: (v) => fmt.pct(v, 0), tickFmt: (t) => fmt.pct(t), xLabel: "share of replies without a valid act call", label: "No-action turns per run" });
      vis.append(legend([{ color: "--bad", label: "real time" }, { color: "--rl", label: "paused" }]));
      vis.append(figcap("Runs with at least one no-action turn. Data: data/terrariabench.json."));
    },

    "tb-videos"() {},

    "tb-notscored"(vis) {
      const rs = tb.runs.filter((r) => r.not_scored || r.censored);
      vis.append(table([
        { key: "run", label: "Run", render: (r) => el("span", { class: "mono" }, r.run) },
        { key: "game", label: "Game time", cls: "r", render: (r) => el("span", { class: "num" }, mmss(r.game_s)) },
        { key: "status", label: "Status", render: (r) => el("span", { class: r.not_scored ? "check-bad" : null }, r.not_scored ? "not scored" : "censored") },
        { key: "reason", label: "Reason", render: (r) => r.not_scored || `${r.stop.replace(/^RuntimeError: /, "")}; keeps published ${r.published_score}, extended ${r.extended_count}` },
        { key: "usd", label: "Cost", cls: "r", render: (r) => el("span", { class: "num" }, fmt.usd(r.usd)) },
      ], rs, { caption: "Official Terraria runs that are not scored or censored" }));
      vis.append(figcap("default-v2 so far. Data: data/terrariabench.json."));
    },
  };

  // ---- official-Terraria recordings (start and chapter times are game seconds, mapped to video seconds) ----
  function recordings(vis, specs) {
    for (const sp of specs) {
      const v = videos.get(sp.run);
      if (!v) { vis.append(el("p", { class: "note" }, `No recording exported for ${sp.run} (site/tools/fetch_videos.py).`)); continue; }
      const r = tbRuns.get(sp.run);
      const scale = v.trimmed_s / v.game_s;
      const chapters = sp.deaths && r ? r.deaths_game_s.map((t, i) => ({ t: t * scale, game: t, label: `death ${i + 1}` })) : [];
      vis.append(videoPlayer(v, { start: Math.round((sp.start || 0) * scale), chapters, title: r ? tbSetup(r) : sp.run, sub: sp.note }));
    }
  }

  // ---- live replay clip for cards with a tape ----
  async function clip(vis, item, link) {
    const a = attempts.get(item.replay.tape);
    if (!a) return;
    const canvas = el("canvas", { class: "px", role: "img", "aria-label": `Replay of ${modelShort(a.model)} on world ${a.world}, from its audited action tape` });
    const live = el("span", { class: "mono" });
    const cap = el("figcaption", {}, el("span", {}, "Loading the replay..."), live);
    vis.append(el("figure", { class: "clip fail-clip" }, canvas, cap));
    let S;
    try { S = await boot(); } catch (e) { cap.firstChild.textContent = `The simulator could not load (make -C site serve): ${e.message}`; return; }
    const res = await fetch(a.tape);
    if (!res.ok) { cap.firstChild.textContent = `${a.tape}: HTTP ${res.status}`; return; }
    const tape = parseTape(await res.text());
    const ep = new Episode(S, tape.seed, tape.actions);
    await ep.record();
    const n = ep.length;
    // legality of each action in the state where it was issued
    const env = S.core.env().reset(tape.seed), illegal = new Uint8Array(n);
    for (let i = 0; i < n; i++) { illegal[i] = env.mask()[ep.actions[i]] ? 0 : 1; env.step(ep.actions[i]); }
    let from, to, text;
    if (item.facts?.climb_up != null) {
      // the 60-action window with the most illegal climbing attempts
      const climb = new Set(["climb up", "climb down"].map((nm) => S.core.actionNames.indexOf(nm)));
      const bad = (i) => (illegal[i] && climb.has(ep.actions[i]) ? 1 : 0);
      const W = 60;
      let c = 0, best = -1, at = 0, total = 0;
      for (let i = 0; i < n; i++) total += bad(i);
      for (let i = 0; i < n; i++) { c += bad(i); if (i >= W) c -= bad(i - W); if (i >= W - 1 && c > best) { best = c; at = i - W + 1; } }
      from = at; to = Math.min(n, at + W);
      text = `World ${world(a.world)}, actions ${fmt.int(from + 1)} to ${fmt.int(to)}: ${best} of these ${to - from} actions are illegal climbs. The replay counts ${total} illegal climbing attempts in the episode.`;
      link.href = replayHref(a.id, from);
      link.lastChild.textContent = `Open in the replay viewer at step ${fmt.int(from)}`;
    } else {
      from = Math.max(0, n - 90); to = n;
      text = `World ${world(a.world)}, the last ${to - from} actions before the episode ends (${a.died ? "death" : ENDING[a.status]} at ${fmt.int(n)}).`;
    }
    cap.firstChild.textContent = `${text} Replayed live from the tape.`;
    const view = new Episode(S, tape.seed, ep.actions, ep.every);
    view.snaps = ep.snaps; view.length = ep.length;
    view.seek(from);
    let prev = { x: view.env.px, y: view.env.py }, acc = 0, lerp = 1, last = 0, on = false;
    whileVisible(canvas, (v) => { on = v; });
    const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
    const frame = (now) => {
      const dt = Math.min(0.1, (now - (last || now)) / 1000); last = now;
      if (on) {
        if (!reduce) acc += dt;
        if (acc >= CLIP_STEP) {
          acc = 0; prev = { x: view.env.px, y: view.env.py }; lerp = 0;
          if (view.cur >= to) { view.seek(from); prev = { x: view.env.px, y: view.env.py }; } else view.stepOnce();
          const k = view.cur;
          live.textContent = k > 0 ? `action ${fmt.int(k)}: ${S.core.actionNames[view.actions[k - 1]]}${illegal[k - 1] ? " (illegal)" : ""}` : "";
        }
        lerp = Math.min(1, lerp + dt / CLIP_STEP);
        const p = { x: prev.x + (view.env.px - prev.x) * lerp, y: prev.y + (view.env.py - prev.y) * lerp };
        draw(S, canvas, view.env, { tiles: 12, player: p, time: now / 1000, walking: view.env.px !== prev.x && lerp < 1 });
      }
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  }

  // ---- cards ----
  const source = (s) => s.split(/[,;]\s+(?=docs\/|data\/|experiments\/|TerrariaBench\/|evidence\/|https?:\/\/)/).flatMap((p, i) => [i ? ", " : "", /^https?:/.test(p) ? el("a", { href: p }, p) : el("code", {}, p)]);
  const firstStep = (note) => { const m = /step ([\d,]+)/.exec(note || ""); return m ? +m[1].replace(/,/g, "") : null; };
  const gallery = $("#gallery");
  for (const item of fx.items) {
    const vis = el("figure", { class: "fig fail-vis" });
    let link = null;
    if (item.replay) {
      const a = attempts.get(item.replay.tape);
      const at = firstStep(item.replay.note) ?? a?.steps ?? 0;
      const t = Math.max(0, at - 48);
      link = el("a", { class: "btn", href: replayHref(item.replay.tape, t) }, el("img", { class: "px", src: "viz/textures/Item_50.png", alt: "" }), el("span", {}, `Open in the replay viewer at step ${fmt.int(t)}`));
    }
    const card = el("article", { class: "fail", id: item.id, "data-agent": item.agent, "data-track": item.track || "lite", "aria-labelledby": `${item.id}-h` },
      el("div", {},
        el("h3", { id: `${item.id}-h` }, item.title, item.placeholder ? [" ", sampleBadge()] : null),
        el("p", { class: "tag" }, kindBadge(item.agent), " Source: ", source(item.source)),
        el("p", {}, item.text),
        item.replay ? el("p", { class: "note" }, item.replay.note) : null,
        link),
      vis);
    gallery.append(card);
    try {
      if (item.viz && VIS[item.viz]) VIS[item.viz](vis, item);
      if (item.video || item.videos) recordings(vis, item.videos || [item.video]);
      if (item.replay) clip(vis, item, link).catch((e) => { console.warn(e); vis.append(el("p", { class: "note" }, `Replay unavailable: ${e.message}`)); });
    } catch (e) { fail(vis, e); }
  }

  // ---- filter ----
  const count = () => {
    const shown = $$("#gallery .fail").filter((c) => !c.hidden).length;
    $("#filter-count").textContent = `Showing ${shown} of ${fx.items.length} failures.`;
  };
  for (const b of $$("#filter button")) b.addEventListener("click", () => {
    $$("#filter button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    const k = b.dataset.kind;
    for (const c of $$("#gallery .fail")) c.hidden = k !== "all" && (k === "official" ? c.dataset.track !== "official" : c.dataset.agent !== k || c.dataset.track === "official");
    count();
  });
  count();
})().catch((e) => fail($("#main"), e));
