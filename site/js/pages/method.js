import { chrome, el, $, data, fmt, achIcon, sampleBadge, table, fail } from "../common.js";
import { bars, legend } from "../charts.js";

chrome();

(async () => {
  const [env, rl, costs, cal] = await data("environment", "rl", "costs", "calibration");

  // ---- v9 tiers ----
  const v9 = env.achievements_v9;
  $("#v9-n").textContent = v9.tiers.reduce((s, t) => s + t.items.length, 0);
  $("#v9-max").textContent = v9.max;
  $("#v9-tiers").replaceChildren(...v9.tiers.flatMap((t) => [
    el("h4", {}, `${t.name}: weight ${t.weight}, ${t.items.length} achievements, ${t.weight * t.items.length} points`),
    el("ul", { class: "ach-list" }, t.items.map((n) => el("li", {}, achIcon(n), n))),
  ]), el("p", { class: "note" }, `Dropped from v8: ${v9.dropped_from_v8.join(", ")}. Source: ${v9._source}.`));

  // ---- IQM example (real) ----
  const order = ["generic_g9998", "shaped_g9998", "o3t2_standard", "v8_default"];
  const color = { v8_default: "--base", o3t2_standard: "--rl", generic_g9998: "--rl", shaped_g9998: "--shaped" };
  bars($("#iqm-chart"), order.map((k) => {
    const f = rl.final[k];
    return { label: f.name, value: f.test_iqm, lo: f.test_ci[0], hi: f.test_ci[1], dots: f.test_scores, color: color[k] };
  }), { domain: [24, 29], fmt: (v) => v.toFixed(2), xLabel: "test score out of 32 (IQM, 5 seeds)", label: "v8 final configurations, test IQM" });
  $("#iqm-legend").append(legend([{ color: "--base", label: "v8 default knobs" }, { color: "--rl", label: "generic RL" }, { color: "--shaped", label: "RL with disclosed priors (recipe shaping)" }]));
  const pi = rl.p_improve;
  const short = { generic_g9998: "generic, gamma .9998", shaped_g9998: "shaped, gamma .9998", o3t2_standard: "ore 3x + trees 2x", v8_default: "v8 default" };
  $("#pimp").append(table([
    { key: "name", label: "P(row beats column)", render: (r) => el("b", {}, rl.final[r.k].name) },
    ...order.map((c) => ({ key: c, label: short[c], cls: "r", title: rl.final[c].name,
      render: (r) => (r.k === c ? el("span", { class: "muted" }, "-") : el("span", { class: "num" }, pi[r.k][c].toFixed(2))) })),
  ], order.map((k) => ({ k })), { caption: "Probability of improvement between v8 final configurations" }));

  // ---- cost model ----
  const g = costs.gpu, c = costs.cpu, inf = costs.rl_inference;
  const ph = (p) => (p ? sampleBadge("placeholder") : el("span", { class: "verified" }, "listed price"));
  $("#cost-table").append(table([
    { key: "what", label: "Item", render: (r) => el("div", {}, el("span", { class: "agent-name" }, r.what), el("span", { class: "agent-sub" }, r.sub)) },
    { key: "rate", label: "Rate", cls: "r", render: (r) => el("span", { class: "num" }, r.rate) },
    { key: "date", label: "Date", render: (r) => el("span", { class: "num" }, r.date || "") },
    { key: "status", label: "Status", render: (r) => ph(r.placeholder) },
  ], [
    { what: "GPU rental", sub: `${g.name}. ${g.basis}`, rate: `${fmt.usd(g.usd_per_gpu_hour)} per GPU-hour`, date: g.date, placeholder: g.placeholder },
    { what: "CPU core", sub: c.name, rate: `${fmt.usd(c.usd_per_core_hour)} per core-hour`, date: c.date, placeholder: c.placeholder },
    ...costs.api.map((a) => ({ what: `API: ${a.model}`, sub: a.source, rate: `$${a.usd_per_mtok_input.toFixed(2)} in, $${a.usd_per_mtok_output.toFixed(2)} out per million tokens`, date: a.date, placeholder: false })),
    { what: "RL inference per episode", sub: inf._note, rate: fmt.usd(inf.usd_per_episode), date: null, placeholder: inf.placeholder },
  ], { caption: "Cost model" }));
  $("#cost-note").textContent = `RL training cost = GPU-hours x ${fmt.usd(g.usd_per_gpu_hour)}. Example: a 2B-step v8 run on one GPU takes about ${fmt.hours(rl.final.generic_g9998.hours)} (generic final configuration, mean over seeds), so about ${fmt.usd(rl.final.generic_g9998.hours * g.usd_per_gpu_hour)} per seed at the placeholder rate. Source: data/costs.json, data/rl.json.`;

  // ---- calibration ----
  $("#cal-src").href = cal.published_source;
  const pubTable = (key) => table([
    { key: "algo", label: `${key}, algorithm` },
    { key: "pct", label: "% of max", cls: "r", render: (r) => el("span", { class: "num" }, r.pct.toFixed(1)) },
  ], cal.published[key], { caption: `Published ${key} scoreboard` });
  $("#pub-1b").append(pubTable("Craftax-1B"));
  $("#pub-1m").append(pubTable("Craftax-1M"));
  $("#ours-note").textContent = cal.ours._note;
  const ours = cal.ours.rows;
  const pub = Object.fromEntries(cal.published["Craftax-1B"].map((p) => [p.algo, p.pct]));
  bars($("#calib-chart"), [
    ...cal.published["Craftax-1B"].map((p) => ({ label: `${p.algo}, published`, value: p.pct, color: "--base" })),
    ...ours.map((r) => ({ label: `${r.algo}, ours`, value: r.pct, lo: r.ci[0], hi: r.ci[1], dots: r.seed_pcts, color: r.algo.includes("Terraria") ? "--shaped" : "--rl",
      tip: `<b>${r.algo}, ours</b><br>${r.pct.toFixed(1)}%, seeds ${r.seed_pcts.map((x) => x.toFixed(1)).join(", ")} (bar: range over ${r.seeds} seeds)<br>${r.hw}, ${fmt.hours(r.wall_hours)} wall clock${pub[r.algo] != null ? `<br>published: ${pub[r.algo].toFixed(1)}%` : ""}` })),
  ], { domain: [0, 25], fmt: (v) => `${v.toFixed(1)}%`, xLabel: "Craftax-1B reward, % of maximum (226)", label: "Craftax calibration" });
  $("#calib-legend").append(legend([{ color: "--base", label: "published (Craftax README)" }, { color: "--rl", label: "our rerun of the official baseline" }, { color: "--shaped", label: "our PPO with Terraria-Lite settings" }]));
  const sm = cal.smoke;
  $("#smoke-text").textContent = `${sm.note} The upstream Craftax_Baselines ppo.py ran on ${sm.env} at commit ${sm.upstream_commit.slice(0, 12)}. Source: ${sm._source}.`;
  const facts = [
    ["Environment", sm.env, ""],
    ["Steps", fmt.int(sm.steps), `${sm.envs} parallel envs`],
    ["Device", sm.device, `${sm.wall_seconds.toFixed(1)} s wall clock`],
    ["Final episode return", sm.final_episode_return.toFixed(2), "training metric, Craftax-Classic"],
  ];
  $("#smoke-facts").replaceChildren(...facts.map(([k, v, s]) => el("div", {}, el("dt", {}, k), el("dd", {}, v, " ", el("small", {}, s)))));
})().catch((e) => fail($("#main"), e));
