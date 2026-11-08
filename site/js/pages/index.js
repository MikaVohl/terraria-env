import { chrome, el, $, $$, data, fmt, achIcon, icon, kindBadge, sampleBadge, table, fail } from "../common.js";
import { bars, scatter, heatmap, legend, log10 } from "../charts.js";
import { loadLite } from "../board.js";
import { hero } from "../hero.js";
import { clips } from "../clips.js";

chrome();
hero($("#hero"), { seed: 42 });

(async () => {
  const [{ rows, rl, llm, costs }, env, tb, cal, hist] = await Promise.all([
    loadLite(), ...["environment", "terrariabench", "calibration", "history"].map((n) => data(n).then((x) => x[0]))]);
  const byId = Object.fromEntries(rows.map((r) => [r.id, r]));

  // ---- key numbers ----
  const best = byId["v8-generic-g9998"], six = byId["v8-best-run"], luna = byId["v7-luna-batch"];
  const g10 = byId["v10-generic-1b"], s10 = byId["v10-shaped-1b"], haiku = byId["v9-llm-haiku"];
  const facts = [
    ["Simulator speed, 1 CPU thread", `${fmt.rate(1290000)} steps/s`, "v8; v9 1.23M"],
    ["PPO training, 1 GPU", `${fmt.rate(286626)} steps/s`, "median of 84 runs"],
    ["Real Terraria, headless", "about 1k actions/s", "per process, 4 ticks/action"],
    ["PPO on v10 (release candidate), 1B", `${fmt.n(g10.value, 1)}% / ${fmt.n(s10.value, 1)}%`, "generic / shaped, mean of 3 seeds, validation worlds"],
    ["Best PPO, v8 test worlds", `${fmt.n(best.value)}/32`, `IQM ${fmt.ci(best.ci)}, 5 seeds`],
    ["Best single PPO run (6B)", `${fmt.n(six.value)}/32`, "v8, validation, 1 seed"],
    ["Claude Haiku 5.5 on v9", `${fmt.n(haiku.value, 1)}%`, `guide + macros, mean of 3 worlds, ${fmt.usd(haiku.epUsd)} per episode`],
    ["GPT-6 Luna, v7", `${fmt.n(luna.value, 1)}/32`, `mean of 3 worlds, ${fmt.usd(luna.epUsd)} per episode`],
  ];
  $("#facts").replaceChildren(...facts.map(([k, v, s]) => el("div", {}, el("dt", {}, k), el("dd", {}, v, " ", el("small", {}, s)))));

  // ---- mini leaderboards ----
  const lite = rows.filter((r) => r.version === "v8" && !r.placeholder && r.split === "test").sort((a, b) => b.value - a.value);
  $("#mini-lite").append(table([
    { key: "agent", label: "Agent", render: (r) => el("span", {}, kindBadge(r.kind), " ", el("span", { class: "agent-name" }, r.agent)) },
    { key: "value", label: "IQM [95% CI]", cls: "r", render: (r) => el("span", { class: "num" }, el("b", {}, fmt.n(r.value)), " ", el("span", { class: "muted" }, fmt.ci(r.ci))) },
    { key: "gpu", label: "GPU-h", cls: "r", render: (r) => el("span", { class: "num" }, fmt.n(r.gpuHours, 1)) },
  ], lite, { caption: "Terraria-Lite v8 top entries" }));
  const off = tb.runs.filter((r) => !r.not_scored && !r.long).sort((a, b) => b.extended_count - a.extended_count || b.published_score - a.published_score).slice(0, 5);
  $("#mini-official").append(table([
    { key: "agent", label: "Run", render: (r) => el("span", {}, el("span", { class: "agent-name" }, r.setup.split(",")[0].replace(" executor", "")), el("span", { class: "agent-sub" }, `${r.clock === "realtime" ? "real time" : "paused"}, world ${r.world}${r.censored ? `, stopped by its cap at ${Math.round(r.game_s / 60)} min` : ""}`)) },
    { key: "ext", label: "Extended", cls: "r", title: "Facts reached of the 19-fact extended catalog", render: (r) => el("b", { class: "num" }, r.extended_count) },
    { key: "pub", label: "Published", cls: "r", title: "terrariabench.com 13-checkpoint subset", render: (r) => el("span", { class: "num" }, r.published_score) },
    { key: "cost", label: "Cost", cls: "r", render: (r) => el("span", { class: "num" }, fmt.usd(r.usd)) },
  ], off, { caption: "Official Terraria, best default-v2 runs so far" }));

  // ---- fast ----
  const colors = { lite: "--rl", "lite-train": "--shaped", published: "--base", terraria: "--llm" };
  const sp = env.speed.rows;
  bars($("#speed-chart"), sp.map((r) => ({
    label: r.name, value: r.sps, color: colors[r.kind], sample: false,
    tip: `<b>${r.name}</b><br>${fmt.int(r.sps)} steps/s<br>${r.hw}<br><span class="muted">${r.source}</span>`,
  })), { domain: [100, 3e6], fmt: (v) => fmt.rate(v), tickFmt: (t) => fmt.rate(t), xLabel: "agent actions per second (log scale)", label: "Speed comparison", log: true });
  $("#speed-legend").replaceChildren(legend([
    { color: "--rl", label: "Terraria-Lite simulator (measured)" }, { color: "--shaped", label: "Terraria-Lite PPO training (measured)" },
    { color: "--llm", label: "Real Terraria, tModLoader (measured)" }, { color: "--base", label: "Published (Craftax paper and site)" }]));
  const t = env.speed.tml;
  $("#speed-note").textContent = `Terraria-Lite runs about ${Math.round(1290000 / 986).toLocaleString("en-US")} times faster than one headless tModLoader process on one thread. Matching one Terraria-Lite training run with real Terraria would take about ${t.cores_to_match_lite_training} cores and ${t.ram_gb_to_match} GB of RAM, before the client-side player logic and observation extraction that the headless measurement leaves out.`;

  // ---- hard ----
  const names = rl.achievements;
  const gen = byId["v8-generic-g9998"], sh = byId["v8-shaped-g9998"];
  const lunaAll = llm.attempts.filter((a) => a.model.startsWith("openai/gpt-6-luna"));
  const lunaRates = Object.fromEntries(names.map((n) => [n, lunaAll.filter((a) => a.achievements.includes(n)).length / lunaAll.length]));
  const order = [...names].sort((a, b) => (gen.rates[b] - gen.rates[a]) || (sh.rates[b] - sh.rates[a]) || (six.rates[b] - six.rates[a]));
  const hrows = [
    { label: "PPO generic, 2B (test)", cells: order.map((n) => gen.rates[n]) },
    { label: "PPO + shaping, 2B (test)", cells: order.map((n) => sh.rates[n]) },
    { label: "PPO + shaping, 6B, 1 run (val.)", cells: order.map((n) => six.rates[n]) },
    { label: `GPT-6 Luna, ${lunaAll.length} attempts (v7)`, cells: order.map((n) => lunaRates[n]) },
  ];
  $("#hard-heat").append(heatmap(hrows, order.map((n) => ({ label: n, icon: achIcon(n) })), { fmt: (v) => `${Math.round(100 * v)}` }));

  // ---- open-ended ----
  clips($("#clips"), env.skills);

  // ---- pareto ----
  $("#rate").textContent = `${fmt.usd(costs.gpu.usd_per_gpu_hour)} per ${costs.gpu.name.split(" (")[0]} GPU-hour, an assumption dated ${costs.gpu.date}`;
  const shapes = { rl: "circle", shaped: "diamond", llm: "square", human: "triangle", baseline: "circle" };
  const draw = (basis) => {
    const pts = rows.filter((r) => (r.version === "v7" || r.version === "v8") && r.value != null).map((r) => {
      const isRL = r.kind === "rl" || r.kind === "shaped";
      const x = isRL ? (basis === "train" ? r.trainUsd : r.epUsd) : r.epUsd;
      return {
        x: x || null, y: r.value, label: r.agent, color: `--${r.kind === "baseline" ? "base" : r.kind}`, shape: shapes[r.kind], sample: r.placeholder,
        tip: `<b>${r.agent}</b> (${r.version})<br>${fmt.n(r.value)}/32 ${r.stat}${r.ci ? ` ${fmt.ci(r.ci)}` : ""}<br>${x ? fmt.usd(x) : "no cost"} ${isRL && basis === "train" ? "training per seed (estimated)" : "per episode"}${r.placeholder ? "<br><i>sample data</i>" : ""}`,
        short: r.placeholder ? null : r.short,
      };
    }).filter((p) => p.x);
    $("#pareto-chart").replaceChildren();
    scatter($("#pareto-chart"), pts, { xLog: true, xDomain: basis === "train" ? [0.01, 100] : [1e-5, 100], yDomain: [0, 32], xLabel: "US dollars (log scale)", yLabel: "score /32", xFmt: (v) => fmt.usd(v), frontier: true, labels: true, label: "Score against cost" });
  };
  draw("train");
  for (const b of $$("#pareto .seg button")) b.addEventListener("click", () => {
    $$("#pareto .seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); draw(b.dataset.basis);
  });
  $("#pareto-legend").replaceChildren(legend([
    { color: "--rl", label: "RL, generic" }, { color: "--shaped", label: "RL with disclosed priors" }, { color: "--llm", label: "LLM" },
    { color: "--human", label: "Human", sample: true }, { color: "--base", label: "Baseline", sample: true }, { color: "--muted", label: "hollow, dashed: sample data", sample: true }]));

  // ---- calibration ----
  const pub = cal.published["Craftax-1B"];
  const ours = Object.fromEntries(cal.ours.rows.map((r) => [r.algo, r]));
  bars($("#calib-chart"), [
    ...pub.filter((p) => ["PPO", "PPO-RNN", "PPO-LSTM"].includes(p.algo)).flatMap((p) => [
      { label: `${p.algo}, published`, value: p.pct, color: "--base" },
      ...(ours[p.algo] ? [{ label: `${p.algo}, ours`, value: ours[p.algo].pct, lo: ours[p.algo].ci[0], hi: ours[p.algo].ci[1], dots: ours[p.algo].seed_pcts, color: "--rl" }] : []),
    ]),
    { label: "PPO with Terraria-Lite settings, ours", value: ours["PPO, Terraria-Lite settings"].pct, lo: ours["PPO, Terraria-Lite settings"].ci[0], hi: ours["PPO, Terraria-Lite settings"].ci[1], dots: ours["PPO, Terraria-Lite settings"].seed_pcts, color: "--shaped" },
  ], { domain: [0, 25], fmt: (v) => `${v.toFixed(1)}%`, xLabel: "Craftax-1B reward, % of maximum (226)", label: "Craftax calibration" });

  // ---- next ----
  $("#next-list").replaceChildren(...hist.in_progress.map((p) => el("li", {}, el("b", {}, p.what), `: ${p.detail} `, el("span", { class: "note" }, `(${p.source})`))));
})().catch((e) => fail($("#main"), e));
