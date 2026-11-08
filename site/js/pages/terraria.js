import { chrome, el, $, $$, data, fmt, achIcon, kindBadge, sampleBadge, table, ciCell, fail } from "../common.js";
import { bars, scatter, lines, heatmap, legend } from "../charts.js";

chrome();

const COLOR = { rl: "--rl", shaped: "--shaped", llm: "--llm", human: "--human", baseline: "--base" };
const SHAPE = { rl: "circle", shaped: "diamond", llm: "square", human: "triangle", baseline: "circle" };
const TIER_WEIGHT = { 1: 1, 2: 3, 3: 5, 4: 8 }; // Terraria-Lite v9 tier weights (docs/ENV_V9_DESIGN.md section 8)
const TIER_NAME = { 1: "Basic", 2: "Intermediate", 3: "Advanced", 4: "Very advanced" };

/* Decimal step count: 1e8 -> "100M", 2.5e9 -> "2.5B". */
const dsteps = (x) => (x >= 1e9 ? `${+(x / 1e9).toFixed(x < 1e10 ? 2 : 0)}B` : `${+(x / 1e6).toFixed(0)}M`);
const num = (x, d = 0) => fmt.n(x, d);

(async () => {
  const [terr, env, costs] = await data("terraria", "environment", "costs");
  const c = terr.contract, b = c.budget, ms = terr.milestones, entries = terr.entries;
  const tml = env.speed.tml;

  // ---- contract ----
  const crow = (k, v) => ({ k, v });
  $("#contract-table").append(table([
    { key: "k", label: "Rule", render: (r) => el("b", {}, r.k) },
    { key: "v", label: "Draft text" },
  ], [
    crow("Status", c.status),
    crow("Game", c.game),
    crow("Harness", c.harness),
    crow("Observation", c.observation),
    crow("Actions", c.actions),
    crow("Budget", `${fmt.int(b.actions)} actions, ${b.game_minutes} game minutes, ${b.wall_hours} wall-clock hours, ${fmt.usd(b.usd_cap_per_episode)} cap per episode, whichever comes first`),
    crow("Scoring", c.scoring),
    crow("Validity", c.validity),
  ], { caption: "Official Terraria track contract (draft)" }));
  const tps = 60, ticksPerAction = tml.ticks_per_action;
  $("#budget-note").textContent = `${fmt.int(b.actions)} actions at ${ticksPerAction} ticks each is ${fmt.int(b.actions * ticksPerAction)} ticks, or ${(b.actions * ticksPerAction / tps / 60).toFixed(1)} minutes of game time at ${tps} ticks per second.`;

  // ---- leaderboard ----
  $("#board-badge").append(sampleBadge());
  $("#board-table").append(table([
    { key: "agent", label: "Agent", render: (r) => el("div", {}, el("span", { class: "agent-name" }, r.agent), " ", r.placeholder ? sampleBadge() : null, el("span", { class: "agent-sub" }, r.sub)) },
    { key: "kind", label: "Kind", render: (r) => kindBadge(r.kind), sort: (r) => r.kind },
    { key: "score", label: "Score, % [95% CI]", sort: (r) => (r.valid ? r.score : -1), render: (r) => (r.valid ? ciCell(r.score, r.ci, [0, 100], 0) : el("span", { class: "muted" }, "not scored")) },
    { key: "worlds", label: "Worlds", cls: "r", sort: (r) => r.worlds },
    { key: "cost", label: "Cost", cls: "r", sort: (r) => r.cost_usd, title: "LLM: per episode; RL: training compute",
      render: (r) => el("span", { class: "num", title: r.cost_note || null }, r.cost_usd == null ? "n/a" : fmt.usd(r.cost_usd), r.cost_note ? el("span", { class: "agent-sub" }, r.cost_note) : null) },
    { key: "wall", label: "Wall time", cls: "r", sort: (r) => r.wall_hours, render: (r) => fmt.hours(r.wall_hours) },
    { key: "actions", label: "Actions", cls: "r", sort: (r) => r.actions, render: (r) => fmt.int(r.actions) },
    { key: "valid", label: "Valid", sort: (r) => (r.valid ? 1 : 0), render: (r) => (r.valid ? el("span", { class: "verified" }, "valid") : el("span", { class: "check-bad" }, `invalid: ${r.invalid_reason}`)) },
  ], entries, { sortKey: "score", caption: "Official Terraria leaderboard (sample data)" }));

  // ---- score vs cost and time ----
  $("#pareto-badge").append(sampleBadge());
  const valid = entries.filter((e) => e.valid);
  const pt = (e, x, xs) => ({
    x, y: e.score, ylo: e.ci?.[0], yhi: e.ci?.[1], label: e.agent, short: e.agent.split(",")[0].replace(/^Frontier /, ""),
    color: COLOR[e.kind], shape: SHAPE[e.kind], sample: e.placeholder,
    tip: `<b>${e.agent}</b><br>${e.score}% ${fmt.ci(e.ci, 0)}<br>${xs}${e.placeholder ? "<br><i>sample data</i>" : ""}`,
  });
  scatter($("#cost-chart"), valid.filter((e) => e.cost_usd != null).map((e) => pt(e, e.cost_usd, `${fmt.usd(e.cost_usd)}${e.kind === "llm" ? " per episode" : " training"}`)),
    { xLog: true, xDomain: [0.1, 100], yDomain: [0, 100], xLabel: "US dollars (log scale)", yLabel: "score, %", xFmt: fmt.usd, yFmt: (v) => `${v}%`, frontier: true, labels: true, label: "Score against cost, sample data" });
  scatter($("#time-chart"), valid.map((e) => pt(e, e.wall_hours, `${fmt.hours(e.wall_hours)} wall clock`)),
    { xLog: true, xDomain: [0.1, 10], yDomain: [0, 100], xLabel: "wall-clock hours (log scale)", yLabel: "score, %", xFmt: (v) => `${v} h`, yFmt: (v) => `${v}%`, frontier: true, labels: true, label: "Score against wall-clock time, sample data" });
  $("#pareto-legend").append(legend([
    { color: "--llm", label: "LLM", sample: true }, { color: "--rl", label: "RL, generic", sample: true },
    { color: "--shaped", label: "RL with disclosed priors", sample: true }, { color: "--human", label: "Human", sample: true },
  ]));

  // ---- progress over game time ----
  $("#progress-badge").append(sampleBadge());
  $("#game-min").textContent = b.game_minutes;
  const fu = terr.first_unlock_minutes;
  const byId = Object.fromEntries(entries.map((e) => [e.id, e]));
  const maxW = ms.reduce((s, m) => s + TIER_WEIGHT[m.tier], 0);
  const agents = Object.keys(fu.agents);
  const series = (measure) => agents.map((id) => {
    const e = byId[id];
    const hits = fu.agents[id].map((t, i) => [t, i]).filter(([t]) => t != null).sort((p, q) => p[0] - q[0]);
    let acc = 0;
    const pts = [[0, 0]];
    for (const [t, i] of hits) { acc += measure === "count" ? 1 : (100 * TIER_WEIGHT[ms[i].tier]) / maxW; pts.push([t, acc]); }
    pts.push([b.game_minutes, acc]);
    return { label: e.agent, short: e.agent.split(",")[0].replace(/^Frontier /, ""), color: COLOR[e.kind], points: pts, step: true, sample: fu.placeholder,
      tip: `<b>${e.agent}</b><br>${measure === "count" ? `${hits.length} of ${ms.length} milestones` : `${acc.toFixed(0)}% of max weighted score`} by minute ${b.game_minutes}<br><i>sample data</i>` };
  });
  const drawProgress = (measure) => {
    $("#progress-chart").replaceChildren();
    lines($("#progress-chart"), series(measure), {
      xDomain: [0, b.game_minutes], yDomain: measure === "count" ? [0, ms.length] : [0, 100],
      xLabel: "game minutes", yLabel: measure === "count" ? "milestones reached" : "weighted score, %",
      yFmt: (v) => (measure === "count" ? v : `${v}%`), endLabels: true, rightPad: 90, label: "Progress over game time, sample data",
    });
  };
  drawProgress("count");
  for (const btn of $$("#progress .seg button")) btn.addEventListener("click", () => {
    $$("#progress .seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === btn))); drawProgress(btn.dataset.measure);
  });
  $("#progress-legend").append(legend(agents.map((id) => ({ color: COLOR[byId[id].kind], label: byId[id].agent, line: true, sample: true }))));

  // ---- first-unlock heatmap ----
  $("#heat-badge").append(sampleBadge());
  $("#n-milestones").textContent = ms.length;
  $("#heat").append(heatmap(
    agents.map((id) => ({ label: byId[id].agent, sample: fu.placeholder, cells: fu.agents[id] })),
    ms.map((m) => ({ label: `${m.name} (tier ${m.tier})`, icon: achIcon(m.name) })),
    { fmt: (v) => v.toFixed(1), scale: (v) => 1 - v / b.game_minutes, corner: "minute of first unlock" }));
  const tiers = [...new Set(ms.map((m) => m.tier))];
  $("#tier-key").replaceChildren(...tiers.map((t) => el("span", { style: { marginRight: "14px" } },
    `Tier ${t} (${TIER_NAME[t]}, weight ${TIER_WEIGHT[t]}): ${ms.filter((m) => m.tier === t).map((m) => m.name).join(", ")}.`)));

  // ---- speed (real) ----
  const rows = env.speed.rows;
  const one = rows.find((r) => r.kind === "terraria" && /1 process/.test(r.name));
  const four = rows.find((r) => r.kind === "terraria" && /4 processes/.test(r.name));
  const sim = rows.find((r) => r.kind === "lite" && /v8/.test(r.name));
  const train = rows.find((r) => r.kind === "lite-train");
  const facts = [
    ["Per tick, world only", `${tml.per_tick_us.world} \u00b5s`, "no player"],
    ["Per tick, with player", `${tml.per_tick_us.player} \u00b5s`, `${tml.per_tick_us.player_mining} \u00b5s while mining`],
    ["Actions per second, 1 process", fmt.int(one.sps), `${tml.ticks_per_action} ticks per action, mining`],
    ["Actions per second, 4 processes", fmt.int(four.sps), "aggregate, mining"],
    ["Startup", `${tml.startup_s} s`, "process start to world loaded"],
    ["World generation", `${tml.worldgen_s.toFixed(0)} s`, "small world, 4200 x 1200"],
    ["Memory per process", `${tml.rss_mib[0]} to ${tml.rss_mib[1]} MiB`, "RSS at end of run"],
    ["To match one Terraria-Lite run", `${tml.cores_to_match_lite_training} cores`, `and about ${tml.ram_gb_to_match} GB of RAM (estimate)`],
  ];
  $("#tml-facts").replaceChildren(...facts.map(([k, v, s]) => el("div", {}, el("dt", {}, k), el("dd", {}, v, " ", el("small", {}, s)))));
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
