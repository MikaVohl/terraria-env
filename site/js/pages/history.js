import { chrome, el, $, data, fmt, esc, fail } from "../common.js";
import { scatter, legend } from "../charts.js";

chrome();

/* Repository files behind each version (outside the served root, so shown as code, not links). */
const REPORTS = {
  "tools/freeze_v1.sh": "Freezes the v1 simulator byte for byte",
  "docs/reports/V2.md": "v2: bounded combat and exploration, the written game contract",
  "docs/reports/ITERATION_2026_10.md": "October iteration: faster simulation, coherent harvesting, stronger PPO (v3 scores)",
  "docs/reports/FIDELITY_V4.md": "v4: core Terraria fidelity and fresh measurements",
  "docs/reports/LEARNING_V4_2026_10.md": "v4 learning and causal study",
  "docs/reports/CREDIT_V4_2026_10.md": "v4 deadline, credit, memory and exploration experiments",
  "docs/reports/FOOTPRINT_LEARNING_2026_10.md": "Paired v4 and v5 footprint learning study",
  "docs/reports/OBJECT_SCALE_V5.md": "Native-scale object footprints (v5 preview)",
  "docs/reports/FOOTPRINT_CRAFTING_2026_10.md": "Final-policy crafting diagnostics",
  "docs/reports/V7_REWARD_STUDY_2026_10_17.md": "v7 progression, reward and discount study",
  "docs/reports/DESIGN_DIRECTION_2026_10.md": "Design direction: learnable Terraria, not exhaustive Terraria",
  "docs/reports/LLM_SMOKE_2026_10_17.md": "First LLM API smoke (Sol)",
  "docs/reports/LLM_LUNA_2026_10_17.md": "Luna development batch",
  "docs/reports/LUNA_HARNESS_STUDY_2026_10_17.md": "Luna harness study",
  "docs/reports/EXPLORATION_2026_10_18.md": "Exploration aids and policy inputs on v4",
  "docs/reports/SCALE_FF_2026_10.md": "Scaling feed-forward PPO policies",
  "docs/reports/MEMORY_ARCH_2026_10.md": "Memory architectures",
  "docs/reports/GPU_SHARING_CORRUPTION_2026_10.md": "Silent gradient corruption with two trainers per GPU",
  "notebooks/v8_env_results_2026_10_31.ipynb": "v8 environment-knob results (source of the RL page data)",
  "viz/README.md": "The simulator and policy in the browser",
  "experiments/tml-speed-20261107/README.md": "How fast real Terraria (tModLoader 1.4.4) ticks headless",
  "docs/ENV_V9_DESIGN.md": "v9 design spec (draft)",
};
const SOURCES = {
  v1: ["tools/freeze_v1.sh"],
  "v2-v3": ["docs/reports/V2.md", "docs/reports/ITERATION_2026_10.md"],
  v4: ["docs/reports/FIDELITY_V4.md", "docs/reports/LEARNING_V4_2026_10.md", "docs/reports/CREDIT_V4_2026_10.md", "docs/reports/FOOTPRINT_LEARNING_2026_10.md"],
  v5: ["docs/reports/OBJECT_SCALE_V5.md", "docs/reports/FOOTPRINT_LEARNING_2026_10.md", "docs/reports/FOOTPRINT_CRAFTING_2026_10.md"],
  "v6-v7": ["docs/reports/V7_REWARD_STUDY_2026_10_17.md", "docs/reports/DESIGN_DIRECTION_2026_10.md", "docs/reports/LLM_SMOKE_2026_10_17.md", "docs/reports/LLM_LUNA_2026_10_17.md", "docs/reports/LUNA_HARNESS_STUDY_2026_10_17.md"],
  explore: ["docs/reports/EXPLORATION_2026_10_18.md"],
  eg15: ["docs/reports/SCALE_FF_2026_10.md", "docs/reports/MEMORY_ARCH_2026_10.md", "docs/reports/GPU_SHARING_CORRUPTION_2026_10.md"],
  v8: ["notebooks/v8_env_results_2026_10_31.ipynb"],
  viz: ["viz/README.md"],
  tml: ["experiments/tml-speed-20261107/README.md"],
  v9: ["docs/ENV_V9_DESIGN.md"],
};
/* Pages of this site that continue a version's story. */
const PAGES = {
  v8: [["rl.html", "What helped RL"], ["lite.html", "Leaderboard"]],
  viz: [["viz/index.html", "Open the visualisation"]],
  tml: [["terraria.html", "Official Terraria track"]],
  v9: [["environment.html", "Environment"]],
};

const KIND = {
  rl: { label: "RL, generic", color: "--rl", shape: "circle" },
  shaped: { label: "RL with disclosed priors", color: "--shaped", shape: "diamond" },
  llm: { label: "LLM", color: "--llm", shape: "square" },
};
const DAY = 864e5;
const fmtDate = (t) => new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });

(async () => {
  const [hist] = await data("history");

  // ---- best over time ----
  const pts = hist.best_over_time.map((p) => ({ ...p, t: Date.parse(`${p.date}T00:00:00Z`) }));
  const t0 = Math.min(...pts.map((p) => p.t)) - 3 * DAY, t1 = Math.max(...pts.map((p) => p.t)) + 3 * DAY;
  const ticks = [];
  for (let t = t0; t <= t1; t += 7 * DAY) ticks.push(t);
  scatter($("#best-chart"), pts.map((p) => ({
    x: p.t, y: p.score, color: KIND[p.kind].color, shape: KIND[p.kind].shape, short: p.version, label: `${p.version}, ${p.label}`,
    tip: `<b>${esc(p.version)}</b>: ${fmt.n(p.score)}/32<br>${esc(p.label)}<br>${esc(fmtDate(p.t))}`,
  })), {
    xDomain: [t0, t1], xTicks: ticks, xFmt: fmtDate, yDomain: [14, 32], xLabel: "date reported (2026)", yLabel: "achievements of 32",
    labels: true, label: "Best reported score over time, by version",
  });
  $("#best-legend").replaceChildren(legend(Object.values(KIND).map((k) => ({ color: k.color, label: k.label }))));

  const first = pts[0], last = pts[pts.length - 1];
  $("#best-cap").textContent = `Versions are different tasks, so this is not one learning curve: between the first mark (${first.version}, ${fmt.n(first.score)}) and the last (${last.version}, ${fmt.n(last.score)}) the game changed object footprints and ore supply, and the training budget grew by orders of magnitude. The statistic also differs between marks (test score, five-seed mean, interquartile mean, one selected validation run, one LLM world); hover or focus a mark for it.`;

  // ---- timeline ----
  $("#timeline").replaceChildren(...hist.versions.map((v) => el("li", { id: `v-${v.id}` },
    el("div", { class: "when" }, v.date),
    el("div", {},
      el("h3", {}, v.title),
      el("ul", {}, v.changed.map((c) => el("li", {}, c))),
      el("p", {}, el("b", {}, "Result. "), v.result),
      el("p", { class: "wrong" }, el("b", {}, "What went wrong. "), v.wrong),
      SOURCES[v.id] ? el("p", { class: "note src" }, "Sources: ", SOURCES[v.id].map((s, i) => [i ? ", " : "", el("code", { title: REPORTS[s] }, s)])) : null,
      PAGES[v.id] ? el("p", { class: "note" }, "On this site: ", PAGES[v.id].map(([href, t], i) => [i ? ", " : "", el("a", { href }, t)])) : null))));

  // ---- in progress ----
  $("#progress-list").replaceChildren(...hist.in_progress.map((p) =>
    el("li", {}, el("b", {}, p.what), `: ${p.detail} `, el("span", { class: "note" }, "(", el("code", {}, p.source), ")"))));

  // ---- reports ----
  $("#report-list").replaceChildren(...Object.entries(REPORTS).map(([path, what]) => el("li", {}, el("code", {}, path), `: ${what}`)));
})().catch((e) => fail($("#main"), e));
