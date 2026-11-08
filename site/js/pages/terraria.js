import { chrome, el, $, $$, data, fmt, kindBadge, sampleBadge, table, fail } from "../common.js";
import { bars, lines, heatmap, legend } from "../charts.js";
import { videoPlayer, mmss } from "../video.js";

chrome();

/* Decimal step count: 1e8 -> "100M", 2.5e9 -> "2.5B". */
const dsteps = (x) => (x >= 1e9 ? `${+(x / 1e9).toFixed(x < 1e10 ? 2 : 0)}B` : `${+(x / 1e6).toFixed(0)}M`);
const num = (x, d = 0) => fmt.n(x, d);
const mean = (v) => (v.length ? v.reduce((s, x) => s + x, 0) / v.length : null);
const median = (v) => { const a = [...v].sort((x, y) => x - y); const k = a.length >> 1; return a.length ? (a.length % 2 ? a[k] : (a[k - 1] + a[k]) / 2) : null; };
const CLOCK = { realtime: "real time", paused: "paused" };
const AGENT_COLOR = { Haiku: "--rl", Luna: "--shaped", Terra: "--base", Opus: "--llm", "Opus + Jev": "--human" };
const WORLD_DASH = { 401: null, 402: "7 4", 403: "2 3" };
const EXT_SHORT = {
  gel_1: "gel", torch_crafted: "torches crafted", workbench_placed: "bench placed", wood_armor_crafted: "wood armour crafted",
  layer_underground: "underground", layer_cavern: "cavern layer", ore_copper_tin: "copper/tin ore", ore_iron_lead: "iron/lead ore",
  ore_silver_gold_tier: "silver/gold-tier ore", furnace_crafted: "furnace crafted", furnace_placed: "furnace placed", bar_smelted: "bar smelted",
  bar_5: "5 bars", anvil_held: "anvil held", anvil_placed: "anvil placed", metal_gear_crafted: "metal gear crafted", life_crystal: "life crystal",
  eoc_summon_or_lens: "lens or eye", boss_eye_of_cthulhu: "Eye of Cthulhu",
};

/* "Haiku (medium), unforced, paused, smart_cursor on" -> "Haiku (medium), unforced" */
const setupName = (r) => r.setup.replace(/, (realtime|paused)/, "").replace(/, smart_cursor on/, "").replace("Opus (low) planner + Jev executor", "Opus (low) planner + Jev 1.14 executor");
const latency = (r) => (r.latency_median_s == null ? "n/a" : typeof r.latency_median_s === "object"
  ? `${fmt.n(r.latency_median_s.planner, 1)} / ${fmt.n(r.latency_median_s.executor, 2)} s` : `${fmt.n(r.latency_median_s, 1)} s`);
const latencyValue = (r) => (r.latency_median_s == null ? null : typeof r.latency_median_s === "object" ? r.latency_median_s.planner : r.latency_median_s);
const gameMin = (r) => r.game_s / 60;
const status = (r) => (r.not_scored ? `not scored: ${r.not_scored}` : r.censored ? `censored: ${r.stop.replace(/^RuntimeError: /, "")} at ${mmss(r.game_s)}` : r.pilot ? "pilot" : "scored");
const runLink = (id) => el("span", { class: "mono" }, id);

(async () => {
  const [tb, vids, terr, env, costs] = await data("terrariabench", "videos", "terraria", "environment", "costs");
  const tml = env.speed.tml;
  const cat = tb.catalog;
  const extName = Object.fromEntries(cat.extended.map((c) => [c.id, c.name]));
  const all = tb.runs;
  const scored = all.filter((r) => !r.not_scored);
  const main20 = scored.filter((r) => !r.long);
  const videoOf = Object.fromEntries(vids.videos.map((v) => [v.run, v]));

  // ---- status and key numbers ----
  const done = (c) => main20.filter((r) => r.clock === c);
  $("#status").replaceChildren(el("p", {},
    el("b", {}, "Interim results. "),
    `The default-v2 campaign was still running when this page was exported (${tb.exported_utc} UTC): ${scored.length} runs are scored so far (${done("realtime").length} real time, ${done("paused").length} paused${scored.length > main20.length ? `, ${scored.length - main20.length} of 40 game-minutes` : ""}), ${all.length - scored.length} more ran but are not scored, with the reason in the run table. Runs that finish later appear after `,
    el("code", {}, "python3 site/tools/export_terrariabench.py"), ". Source: ", el("code", {}, tb.report), "."));
  const bestExt = [...scored].sort((a, b) => b.extended_count - a.extended_count || b.published_score - a.published_score)[0];
  const bestPub = [...scored].sort((a, b) => b.published_score - a.published_score || b.extended_count - a.extended_count)[0];
  const deaths = (c) => mean(done(c).map((r) => r.deaths));
  const spend = all.reduce((s, r) => s + (r.usd || 0), 0);
  const pub = tb.earlier.published;
  const facts = [
    ["Best extended score", `${bestExt.extended_count} of ${cat.extended.length}`, `${setupName(bestExt)}, ${CLOCK[bestExt.clock]}, ${fmt.n(gameMin(bestExt), 1)} game-min`],
    ["Best published score", `${bestPub.published_score} of ${cat.published.length}`, `${setupName(bestPub)}, ${CLOCK[bestPub.clock]}`],
    ["terrariabench.com best", `${pub.best}`, `${pub.best_agent}, ${pub.hours}-hour budget, PvE off`],
    ["Deaths per 20 min, real time", fmt.n(deaths("realtime"), 1), `mean of ${done("realtime").length} runs`],
    ["Deaths per 20 min, paused", fmt.n(deaths("paused"), 1), `mean of ${done("paused").length} runs`],
    ["Spent so far", fmt.usd(spend), "every run, list prices"],
  ];
  $("#facts").replaceChildren(...facts.map(([k, v, s]) => el("div", {}, el("dt", {}, k), el("dd", {}, v, " ", el("small", {}, s)))));

  // ---- leaderboards ----
  const perWorld = (rs, f) => el("span", { class: "agent-sub num" }, rs.map((r) => `w${r.world}: ${f(r)}${r.censored ? "*" : ""}`).join(", "));
  const board = (clock) => {
    const groups = new Map();
    for (const r of main20.filter((x) => x.clock === clock)) {
      const k = setupName(r);
      if (!groups.has(k)) groups.set(k, { agent: k, short: r.agent, rs: [] });
      groups.get(k).rs.push(r);
    }
    const rows = [...groups.values()].map((g) => {
      g.rs.sort((a, b) => a.world - b.world);
      g.ext = mean(g.rs.map((r) => r.extended_count));
      g.pub = mean(g.rs.map((r) => r.published_score));
      g.deaths = mean(g.rs.map((r) => r.deaths));
      g.noact = g.rs.reduce((s, r) => s + (r.no_action_turns || 0), 0);
      g.calls = g.rs.reduce((s, r) => s + r.calls, 0);
      g.lat = median(g.rs.map(latencyValue).filter((x) => x != null));
      g.usd = mean(g.rs.map((r) => r.usd));
      return g;
    });
    return table([
      { key: "agent", label: "Agent", cls: "col-agent", render: (g) => el("span", {}, el("span", { class: "agent-name" }, g.agent), el("span", { class: "agent-sub" }, `${g.rs.length} run${g.rs.length > 1 ? "s" : ""}: ${g.rs.map((r) => r.run).join(", ")}`)) },
      { key: "ext", label: "Extended", cls: "r", sort: (g) => g.ext, title: "Mean extended-catalog facts (of 19) over the runs; per-world values below", render: (g) => el("span", {}, el("b", { class: "num" }, fmt.n(g.ext, 1)), perWorld(g.rs, (r) => r.extended_count)) },
      { key: "pub", label: "Published", cls: "r", sort: (g) => g.pub, title: "Mean published-subset score (of 13)", render: (g) => el("span", {}, el("span", { class: "num" }, fmt.n(g.pub, 1)), perWorld(g.rs, (r) => r.published_score)) },
      { key: "deaths", label: "Deaths", cls: "r", sort: (g) => g.deaths, title: "Mean deaths per run", render: (g) => el("span", {}, el("span", { class: "num" }, fmt.n(g.deaths, 1)), perWorld(g.rs, (r) => r.deaths)) },
      { key: "noact", label: "No-action turns", cls: "r", sort: (g) => g.noact / g.calls, title: "Replies without a valid act call, summed over the runs, out of all calls", render: (g) => el("span", { class: "num" }, `${fmt.int(g.noact)} of ${fmt.int(g.calls)}`) },
      { key: "lat", label: "Latency", cls: "r", sort: (g) => g.lat, title: "Median model latency per call (combination: the planner)", render: (g) => el("span", { class: "num" }, g.rs.length === 1 ? latency(g.rs[0]) : `${fmt.n(g.lat, 1)} s`) },
      { key: "usd", label: "Cost per run", cls: "r", sort: (g) => g.usd, render: (g) => el("span", { class: "num" }, fmt.usd(g.usd)) },
    ], rows, { sortKey: "ext", caption: `Official Terraria leaderboard, default-v2, ${CLOCK[clock]} (interim)` });
  };
  $("#board-realtime").append(board("realtime"));
  $("#board-paused").append(board("paused"));
  const cens = main20.filter((r) => r.censored);
  $("#board-note").textContent = `* censored: ${cens.map((r) => `${r.run} stopped by its dollar cap at ${mmss(r.game_s)} game time`).join("; ")}. Censored runs keep what they reached before the cap. Haiku with thinking off was a pilot of the forced tool call and is not part of the matrix. Not scored: ${all.filter((r) => r.not_scored).map((r) => r.run).join(", ")} (see the run table).`;
  for (const b of $$("#board-tabs button")) b.addEventListener("click", () => {
    for (const x of $$("#board-tabs button")) {
      const on = x === b;
      x.setAttribute("aria-selected", String(on));
      $(`#${x.getAttribute("aria-controls")}`).hidden = !on;
    }
  });

  // ---- agent systems ----
  const v1 = tb.earlier.default_v1.runs;
  const sys = [...scored.filter((r) => r.agent === "Opus" || r.agent === "Opus + Jev").map((r) => ({ ...r, profile: "default-v2" })),
    ...v1.filter((r) => r.agent === "Opus + Jev").map((r) => ({ ...r, profile: "default-v1" }))];
  const split = (o, f) => (o && typeof o === "object" ? `${f(o.planner)} + ${f(o.executor)}` : null);
  $("#systems-table").append(table([
    { key: "run", label: "Run", render: (r) => el("span", {}, runLink(r.run), el("span", { class: "agent-sub" }, `${setupName(r)}; ${r.profile}`)) },
    { key: "clock", label: "Clock", render: (r) => CLOCK[r.clock] },
    { key: "game", label: "Game min", cls: "r", sort: gameMin, render: (r) => el("span", { class: "num" }, `${fmt.n(gameMin(r), 1)}${r.censored ? "*" : ""}`) },
    { key: "pub", label: "Published", cls: "r", sort: (r) => r.published_score, render: (r) => el("span", { class: "num" }, r.published_score) },
    { key: "ext", label: "Extended", cls: "r", sort: (r) => r.extended_count, render: (r) => el("b", { class: "num" }, r.extended_count) },
    { key: "bench", label: "Bench placed", cls: "r", sort: (r) => r.extended_game_s?.workbench_placed, render: (r) => el("span", { class: "num" }, r.extended_game_s?.workbench_placed != null ? mmss(r.extended_game_s.workbench_placed) : "never") },
    { key: "deaths", label: "Deaths", cls: "r", sort: (r) => r.deaths, render: (r) => el("span", { class: "num" }, r.deaths) },
    { key: "calls", label: "Calls", cls: "r", render: (r) => el("span", { class: "num" }, split(r.calls_by_role, fmt.int) || fmt.int(r.calls)) },
    { key: "lat", label: "Latency", cls: "r", render: (r) => el("span", { class: "num" }, latency(r)) },
    { key: "age", label: "Screenshot age", cls: "r", title: "Median wall-clock age of the newest screenshot when an action batch starts", render: (r) => el("span", { class: "num" }, r.screenshot_age_median_s == null ? "n/a" : `${fmt.n(r.screenshot_age_median_s, 1)} s`) },
    { key: "usd", label: "Cost", cls: "r", sort: (r) => r.usd, render: (r) => el("span", { class: "num" }, split(r.usd_by_role, (x) => fmt.usd(Number(x))) || fmt.usd(r.usd)) },
  ], sys, { sortKey: "ext", caption: "Opus alone against Opus planner with Jev executor" }));
  $("#systems-note").textContent = "Calls, latency and cost for the combination are planner + executor. * censored by the run's dollar cap. default-v1 is the same game and interface with continuation messages instead of the no-action rule (earlier the same day). Sources: " + `${tb.report}; ${tb.earlier.default_v1.report}.`;

  // ---- milestone timelines ----
  const steps = (r) => {
    const ts = Object.values(r.extended_game_s || {}).sort((a, b) => a - b);
    return [[0, 0], ...ts.map((t, i) => [t / 60, i + 1]), [gameMin(r), ts.length]];
  };
  const tlRuns = (clock) => main20.filter((r) => r.clock === clock).sort((a, b) => a.agent.localeCompare(b.agent) || a.world - b.world);
  const drawTl = (clock) => {
    $("#tl-chart").replaceChildren();
    lines($("#tl-chart"), tlRuns(clock).map((r) => ({
      label: `${r.run} (${setupName(r)}, world ${r.world})`, color: AGENT_COLOR[r.agent] || "--fg", dash: WORLD_DASH[r.world], step: true, points: steps(r),
      tip: `<b>${r.run}</b><br>${setupName(r)}, ${CLOCK[r.clock]}, world ${r.world}<br>extended ${r.extended_count}, published ${r.published_score}, ${r.deaths} deaths<br>${Object.entries(r.extended_game_s || {}).sort((a, b) => a[1] - b[1]).map(([k, t]) => `${mmss(t)} ${extName[k] || k}`).join("<br>")}`,
    })), { xDomain: [0, 20], yDomain: [0, 8], xLabel: "game minutes", yLabel: "extended facts reached", label: `Extended facts over game time, ${CLOCK[clock]} runs` });
    const agents = [...new Set(tlRuns(clock).map((r) => r.agent))];
    $("#tl-legend").replaceChildren(legend([...agents.map((a) => ({ color: AGENT_COLOR[a], label: a, line: true })),
      { color: "--muted", label: "world 401: solid", line: true }, { color: "--muted", label: "402: long dashes, 403: short dashes", line: true, dash: true }]));
  };
  drawTl("realtime");
  for (const b of $$("#tl-filter button")) b.addEventListener("click", () => {
    $$("#tl-filter button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    drawTl(b.dataset.clock);
  });
  const pubIds = cat.published.map((c) => c.id).filter((id) => main20.some((r) => r.published_game_s?.[id] != null));
  const extIds = cat.extended.map((c) => c.id).filter((id) => main20.some((r) => r.extended_game_s?.[id] != null));
  const heatRows = ["realtime", "paused"].flatMap((c) => [{ group: c === "paused" ? "Paused" : "Real time" },
    ...tlRuns(c).map((r) => ({ label: r.run, title: `${r.run}: ${setupName(r)}`, cells: [...pubIds.map((id) => r.published_game_s?.[id] ?? null), ...extIds.map((id) => r.extended_game_s?.[id] ?? null)].map((s) => (s == null ? null : s / 60)) }))]);
  const hcol = (text) => el("span", { class: "hcol", "aria-hidden": "true" }, text);
  $("#tl-heat").append(heatmap(heatRows, [
    ...pubIds.map((id) => ({ label: `${id.replace(/_/g, " ")} (published)`, icon: hcol(id.replace(/_/g, " ")) })),
    ...extIds.map((id) => ({ label: `${extName[id]} (extended)`, icon: hcol(EXT_SHORT[id] || extName[id]) })),
  ], { fmt: (v) => v.toFixed(1), scale: (v) => 1 - v / 20, corner: "game minute of first unlock" }));

  // ---- videos ----
  const byRun = Object.fromEntries([...all, ...v1].map((r) => [r.run, r]));
  const paused = vids.videos.filter((v) => v.clock === "paused" && v.freeze_recall != null);
  const dev = Math.max(...paused.map((v) => Math.abs(v.trimmed_s - v.game_s) / v.game_s));
  const rtDev = Math.max(...vids.videos.filter((v) => v.clock === "realtime").map((v) => (v.trimmed_s - v.game_s) / v.game_s));
  $("#videos-intro").textContent = `${vids.videos.length} recordings of the game window (960 x 960, 10 frames/s), cut to the evaluation window. Paused runs: the harness logs a freeze and a thaw around every model call (the game process is stopped in between); those intervals were cut from the recording (${fmt.int(paused.reduce((s, v) => s + v.freezes, 0))} freezes over ${paused.length} videos), so the video shows only game time. The recording's wall-clock start was fitted against the stills in the video: ${fmt.pct(Math.min(...paused.filter((v) => !v.run.includes("combo")).map((v) => v.freeze_recall)), 1)} or more of the logged freeze time falls on unchanging frames (${fmt.pct(Math.min(...paused.map((v) => v.freeze_recall)), 1)} for the planner + executor run, whose 0.3 s executor freezes are shorter than the 0.6 s still detector), and every trimmed paused video is within ${fmt.pct(dev, 1)} of the game time the observer counted (the game catches up a little after each resume). Real-time videos are wall time, up to ${fmt.pct(rtDev, 0)} longer than game time where the game ran slightly under 60 updates per second. The buttons under each video jump to the moments the observer logged; 2x to 8x skims. A desktop notification sits over the minimap in some recordings; it is not part of the game.`;
  const chapters = (r, v) => {
    if (!r) return [];
    const evs = [...Object.entries(r.extended_game_s || {}).map(([k, t]) => ({ t, label: extName[k] || k })),
      ...Object.entries(r.published_game_s || {}).filter(([k]) => /wood_100|workbench_1|torch_10|furnace_1|early_bar_5/.test(k)).map(([k, t]) => ({ t, label: k.replace(/_/g, " ") }))];
    const scale = v.trimmed_s / v.game_s; // video seconds per game second
    return evs.filter((c) => c.t * scale < v.trimmed_s).map((c) => ({ ...c, game: c.t, t: c.t * scale })).sort((a, b) => a.t - b.t).slice(0, 9);
  };
  $("#video-grid").replaceChildren(...vids.videos.map((v) => {
    const r = byRun[v.run];
    const title = r ? `${setupName(r)}, ${CLOCK[v.clock]}, world ${r.world}` : v.run;
    return videoPlayer(v, { title, sub: v.why, chapters: chapters(r, v) });
  }));

  // ---- every run ----
  $("#runs-table").append(table([
    { key: "run", label: "Run", sort: (r) => r.run, render: (r) => el("span", {}, runLink(r.run), el("span", { class: "agent-sub" }, setupName(r))) },
    { key: "clock", label: "Clock", sort: (r) => r.clock, render: (r) => CLOCK[r.clock] },
    { key: "world", label: "World", cls: "r", sort: (r) => r.world, render: (r) => el("span", { class: "num" }, r.world) },
    { key: "game", label: "Game min", cls: "r", sort: gameMin, render: (r) => el("span", { class: "num" }, fmt.n(gameMin(r), 1)) },
    { key: "ext", label: "Ext.", cls: "r", sort: (r) => r.extended_count, render: (r) => el("b", { class: "num" }, r.extended_count) },
    { key: "pub", label: "Pub.", cls: "r", sort: (r) => r.published_score, render: (r) => el("span", { class: "num" }, r.published_score) },
    { key: "deaths", label: "Deaths", cls: "r", sort: (r) => r.deaths, render: (r) => el("span", { class: "num" }, r.deaths) },
    { key: "depth", label: "Depth", cls: "r", title: "Deepest point below the surface, tiles", sort: (r) => r.max_depth_tiles, render: (r) => el("span", { class: "num" }, r.max_depth_tiles) },
    { key: "noact", label: "No-action", cls: "r", sort: (r) => r.no_action_turns, render: (r) => el("span", { class: "num" }, r.no_action_turns ?? "n/a") },
    { key: "calls", label: "Calls", cls: "r", sort: (r) => r.calls, render: (r) => el("span", { class: "num" }, fmt.int(r.calls)) },
    { key: "lat", label: "Latency", cls: "r", sort: latencyValue, render: (r) => el("span", { class: "num" }, latency(r)) },
    { key: "usd", label: "Cost", cls: "r", sort: (r) => r.usd, render: (r) => el("span", { class: "num" }, fmt.usd(r.usd)) },
    { key: "status", label: "Status", render: (r) => el("span", { class: r.not_scored ? "check-bad" : null }, status(r)) },
    { key: "note", label: "Notes", render: (r) => (r.note ? el("details", {}, el("summary", {}, videoOf[r.run] ? "notes (video above)" : "notes"), el("p", { class: "run-note" }, r.note)) : "") },
  ], all, { sortKey: "run", desc: false, caption: "Every run of the default-v2 campaign so far" }));

  // ---- comparison ----
  const benchShare = (rs) => `${rs.filter((r) => r.extended_game_s?.workbench_placed != null).length} of ${rs.length} runs`;
  const maxOf = (rs, k) => Math.max(...rs.map((r) => r[k] ?? -1));
  const camp = tb.earlier.camp_v2.runs, ref = tb.earlier.reference_gw.runs.filter((r) => r.played_s > 300);
  const cmp = [
    { src: "terrariabench.com published runs", rules: "PvE off, published API harness", len: "8 h", n: pub.runs, pub: pub.best, ext: null, bench: "none reported", ref: pub.source },
    { src: "Reference profile through our gateway (Oct 18 to 19)", rules: "PvE off, checkpoint tool shown or hidden, real time", len: "10 to 45 min", n: ref.length, pub: maxOf(ref, "score"), ext: null, bench: "crafted in every run (the checkpoint fires on crafting)", ref: tb.earlier.reference_gw.report },
    { src: "camp-v2 (Nov 8 morning)", rules: "enemies cannot hurt, interface card, checkpoint tool", len: "15 min (two 40-min runs)", n: camp.length, pub: maxOf(camp, "published_score"), ext: maxOf(camp, "extended_count"), bench: "Opus 2 of 2; cheap models 0 of 17 within 15 min", ref: tb.earlier.camp_v2.report },
    { src: "default-v1 (Nov 8)", rules: "unmodified game, normal PvE, minimal prompt, continuation messages", len: "20 game-min", n: v1.length, pub: maxOf(v1, "published_score"), ext: maxOf(v1, "extended_count"), bench: benchShare(v1), ref: tb.earlier.default_v1.report },
    { src: "default-v2 (this campaign, interim)", rules: "default-v1 plus the no-action rule, a third (unseen) world", len: "20 game-min", n: main20.length, pub: maxOf(main20, "published_score"), ext: maxOf(main20, "extended_count"), bench: benchShare(main20), ref: tb.report },
  ];
  $("#compare-table").append(table([
    { key: "src", label: "Protocol", cls: "col-agent", render: (r) => el("span", {}, el("span", { class: "agent-name" }, r.src), el("span", { class: "agent-sub" }, r.rules)) },
    { key: "len", label: "Length" },
    { key: "n", label: "Runs", cls: "r", render: (r) => el("span", { class: "num" }, r.n) },
    { key: "pub", label: "Best published", cls: "r", render: (r) => el("b", { class: "num" }, r.pub) },
    { key: "ext", label: "Best extended", cls: "r", render: (r) => el("span", { class: "num" }, r.ext ?? "n/a") },
    { key: "bench", label: "Work bench placed", render: (r) => r.bench },
    { key: "ref", label: "Source", render: (r) => el("code", { class: "src" }, r.ref) },
  ], cmp, { caption: "Official Terraria results under each protocol" }));
  $("#compare-note").textContent = "The published catalog counts possession, so chest loot (bars, torches) scores without any crafting; the extended catalog was added on Nov 8 and does not exist for the older protocols. Reference runs shorter than 5 minutes are left out of the count. Best extended for default-v1 is a run that crashed at 11:04 (a harness bug since fixed); the best complete run had 5.";

  // ---- harness card ----
  $("#profile-table").append(table([{ key: "k", label: "Setting", render: (r) => el("b", {}, r[0]) }, { key: "v", label: "default-v2", render: (r) => r[1] }],
    tb.profile, { caption: "Profile default-v2" }));
  $("#prompt").textContent = tb.harness.prompt;
  $("#prompt-note").textContent = tb.harness.prompt_note;
  $("#tool-text").replaceChildren("One tool, act, with 1 to 16 primitives per call (a key press or hold, a mouse move, a click or hold at screenshot pixels, or a wait). It returns ", el("code", {}, tb.harness.tool_result), `. ${tb.harness.no_action}`);
  $("#schema").textContent = tb.harness.tool_schema;
  $("#harness-src").textContent = `Sources: ${tb.harness.source}.`;

  // ---- planned (sample) ----
  $("#planned-badge").append(sampleBadge());
  $("#planned-table").append(table([
    { key: "agent", label: "Agent", cls: "col-agent", render: (r) => el("span", {}, kindBadge(r.kind), " ", el("span", { class: "agent-name" }, r.agent), " ", sampleBadge(), el("span", { class: "agent-sub" }, r.sub)) },
    { key: "extended", label: "Extended", cls: "r", render: (r) => el("span", { class: "num" }, r.extended) },
    { key: "published", label: "Published", cls: "r", render: (r) => el("span", { class: "num" }, r.published) },
    { key: "cost", label: "Cost", cls: "r", render: (r) => el("span", { class: "num" }, r.cost_usd == null ? "n/a" : fmt.usd(r.cost_usd)) },
  ], terr.planned.entries, { caption: "Planned official-Terraria entries (sample data)" }));

  // ---- speed (real) ----
  const rows = env.speed.rows;
  const one = rows.find((r) => r.kind === "terraria" && /1 process/.test(r.name));
  const four = rows.find((r) => r.kind === "terraria" && /4 processes/.test(r.name));
  const sim = rows.find((r) => r.kind === "lite" && /v8/.test(r.name));
  const train = rows.find((r) => r.kind === "lite-train");
  const speedFacts = [
    ["Per tick, world only", `${tml.per_tick_us.world} \u00b5s`, "no player"],
    ["Per tick, with player", `${tml.per_tick_us.player} \u00b5s`, `${tml.per_tick_us.player_mining} \u00b5s while mining`],
    ["Actions per second, 1 process", fmt.int(one.sps), `${tml.ticks_per_action} ticks per action, mining`],
    ["Actions per second, 4 processes", fmt.int(four.sps), "aggregate, mining"],
    ["Startup", `${tml.startup_s} s`, "process start to world loaded"],
    ["World generation", `${tml.worldgen_s.toFixed(0)} s`, "small world, 4200 x 1200"],
    ["Memory per process", `${tml.rss_mib[0]} to ${tml.rss_mib[1]} MiB`, "RSS at end of run"],
    ["To match one Terraria-Lite run", `${tml.cores_to_match_lite_training} cores`, `and about ${tml.ram_gb_to_match} GB of RAM (estimate)`],
  ];
  $("#tml-facts").replaceChildren(...speedFacts.map(([k, v, s]) => el("div", {}, el("dt", {}, k), el("dd", {}, v, " ", el("small", {}, s)))));
  const sc = { lite: "--rl", "lite-train": "--shaped", terraria: "--llm" };
  bars($("#speed-chart"), [sim, train, four, one].map((r) => ({ label: r.name, value: r.sps, color: sc[r.kind], tip: `<b>${r.name}</b><br>${fmt.int(r.sps)} actions/s<br>${r.hw}<br>${r.source}` })),
    { domain: [100, 3e6], log: true, fmt: (v) => fmt.rate(v), tickFmt: (t) => fmt.rate(t), xLabel: "agent actions per second (log scale)", label: "Terraria-Lite against headless Terraria" });
  $("#speed-legend").append(legend([{ color: "--rl", label: "Terraria-Lite simulator, 1 thread" }, { color: "--shaped", label: "Terraria-Lite PPO training, 1 GPU" }, { color: "--llm", label: "Real Terraria, headless tModLoader" }]));
  $("#not-sim").textContent = `Not simulated: ${tml.not_simulated}. On a dedicated server, item pickup, contact damage and melee hits are client-side, so the scripted player never took damage and dropped items piled up. The Terraria-Lite simulator is about ${fmt.int(sim.sps / one.sps)} times faster than one tModLoader process (${fmt.int(sim.sps)} against ${fmt.int(one.sps)} actions per second), and that comparison flatters Terraria.`;

  // ---- RL cost estimator ----
  const aps = terr.rl_cost_model.actions_per_core_second;
  const cores = tml.cores_to_match_lite_training;
  const cpu = costs.cpu, gpu = costs.gpu;
  $("#aps").textContent = fmt.int(aps);
  const slider = $("#steps");
  const fact = (k, v, s, sample) => el("div", {}, el("dt", {}, k, sample ? [" ", sampleBadge("placeholder rate")] : null), el("dd", {}, v, " ", el("small", {}, s)));
  const update = () => {
    const steps = 10 ** Number(slider.value);
    $("#steps-out").textContent = dsteps(steps);
    slider.setAttribute("aria-valuetext", `${dsteps(steps)} steps`);
    const coreH = steps / aps / 3600;
    const gpuH = steps / train.sps / 3600;
    $("#est-tml").replaceChildren(
      fact("CPU core-hours", num(coreH), `at ${fmt.int(aps)} actions/s per core`),
      fact("Dollars", fmt.usd(coreH * cpu.usd_per_core_hour), `at ${fmt.usd(cpu.usd_per_core_hour)} per core-hour`, cpu.placeholder),
      fact(`Wall time on ${cores} cores`, fmt.hours(coreH / cores), "simulation only, no learner"));
    $("#est-lite").replaceChildren(
      fact("GPU-hours", num(gpuH, 2), `at ${fmt.int(train.sps)} steps/s per GPU (measured median)`),
      fact("Dollars", fmt.usd(gpuH * gpu.usd_per_gpu_hour), `at ${fmt.usd(gpu.usd_per_gpu_hour)} per GPU-hour`, gpu.placeholder),
      fact("Wall time on 1 GPU", fmt.hours(gpuH), "includes learning, not just simulation"));
  };
  slider.addEventListener("input", update);
  update();
  $("#est-note").textContent = `Terraria core-hours = steps / ${aps} / 3600, an underestimate: it excludes the client-side player, observation extraction, resets and the learner itself. Terraria-Lite GPU-hours = steps / ${fmt.int(train.sps)} / 3600 (estimate; median over 84 runs on an AMD MI350X with 1,024 environments). Rates: CPU ${fmt.usd(cpu.usd_per_core_hour)} per core-hour and GPU ${fmt.usd(gpu.usd_per_gpu_hour)} per GPU-hour, both placeholder assumptions dated ${gpu.date}. The ${cores}-core figure is the speed README's estimate for matching about 240k actions/s. Sources: ${terr.rl_cost_model.source}; data/costs.json.`;
})().catch((e) => fail($("#main"), e));
