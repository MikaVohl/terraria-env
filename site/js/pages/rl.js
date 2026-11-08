import { chrome, el, $, data, fmt, esc, kindBadge, sampleBadge, table, ciCell, fail } from "../common.js";
import { bars, scatter, lines, heatmap, legend } from "../charts.js";

chrome();

/* Arm family of a run, from its shaping knobs (see site/tools/export_data.py). */
const FAMILY = {
  generic: { label: "Generic: no shaping (novelty, uniform mix)", color: "--rl", kind: "rl" },
  standard: { label: "Mean recipe potential (standard arm)", color: "--gold", kind: "shaped" },
  frontier: { label: "Frontier recipe potential (shaped arm)", color: "--shaped", kind: "shaped" },
};
const family = (r) => (r.potential === 0 ? "generic" : r.potential_mode === "mean" ? "standard" : "frontier");

const FINAL = {
  v8_default: { short: "v8 default supply, standard", color: "--base" },
  o3t2_standard: { short: "Ore 3x + trees 2x, standard", color: "--gold" },
  generic_g9998: { short: "Generic, gamma .9998", color: "--rl" },
  shaped_g9998: { short: "Shaped, gamma .9998", color: "--shaped" },
};

const signed = (v, d = 2) => `${v >= 0 ? "+" : ""}${v.toFixed(d)}`;
const mean = (v) => v.reduce((a, b) => a + b, 0) / v.length;
const B = 2 ** 30;

(async () => {
  const [rl, lite, costs, hist, llm] = await data("rl", "lite", "costs", "history", "llm");
  const rate = costs.gpu.usd_per_gpu_hour;
  const runById = Object.fromEntries(rl.runs.map((r) => [r.id, r]));
  const F = rl.final;
  const abl = (dim, re) => rl.ablations.find((t) => t.dimension === dim && (!re || re.test(t.title)));
  const setting = (t, label) => t.settings.find((s) => s.label === label);
  const refOf = (t) => setting(t, t.reference);
  const best = rl.best_run, bestRun = runById[best.id];

  // ---- TL;DR ----
  const sup2 = abl("supply", /2B/), sup512 = abl("supply", /512M/);
  const supGain = setting(sup2, "ore 3x + trees 2x");
  const supGain512 = setting(sup512, "ore 3x + trees 2x");
  const discG = abl("discount", /generic/), discS = abl("discount", /shaped/);
  const dG = setting(discG, "gamma 0.9998"), dS = setting(discS, "gamma 0.9998");
  const cap = abl("capacity"), capRef = refOf(cap);
  const wide = setting(cap, "hidden 1024, lr 1e-4"), lstm = setting(cap, "LSTM 256");
  const world = abl("world"), view = abl("view"), ge = abl("exploration");
  const worldWorst = Math.min(...world.settings.map((s) => s.delta));
  const viewDeltas = view.settings.filter((s) => s !== refOf(view)).map((s) => s.delta);
  const geGen = setting(ge, "generic arm + Go-Explore"), geGenRef = refOf(ge);
  const geSh = setting(ge, "best shaped arm + Go-Explore"), geShRef = setting(ge, "best shaped arm");
  const long = rl.runs.filter((r) => r.steps > 2 * B && r.world === "128x96" && r.view === "11x9" && r.gamma >= 0.9998);
  const longSh = long.filter((r) => family(r) !== "generic"), longGen = long.filter((r) => family(r) === "generic");
  const pickSh = longSh.filter((r) => r["craft iron pickaxe"] > 0);
  const pickAny = rl.runs.filter((r) => r["craft iron pickaxe"] > 0);
  const pSG = rl.p_improve.shaped_g9998.generic_g9998;
  const liteE = Object.fromEntries(lite.entries.map((e) => [e.id, e]));
  const v9g = liteE["v9-generic-1b"], v9s = liteE["v9-shaped-1b"], v10g = liteE["v10-generic-1b"], v10s = liteE["v10-shaped-1b"];
  const bv = best.validation, bvh = bv.hits;

  $("#tldr-list").replaceChildren(
    el("li", {}, el("b", {}, "A fair world first. "), `Raising ore supply 3x and tree supply 2x moved the standard arm by ${signed(supGain.delta)} at 2B steps (validation mean, 5 seeds each; ${signed(supGain512.delta)} at 512M), test IQM ${fmt.n(F.v8_default.test_iqm)} to ${fmt.n(F.o3t2_standard.test_iqm)}. Returns to the surface went from ${fmt.n(refOf(sup2).surface, 1)} to ${fmt.n(supGain.surface, 1)} of 128 worlds. No network or memory change came close.`),
    el("li", {}, el("b", {}, "A longer horizon was the largest single hyperparameter gain. "), `Raising the discount from gamma .999 to .9998 added ${signed(dG.delta)} for the generic arm and ${signed(dS.delta)} for the shaped arm (2B steps).`),
    el("li", {}, el("b", {}, "Architecture did about nothing. "), `Hidden width 1024 instead of 128: ${signed(wide.delta)}; an LSTM with 256 units: ${signed(lstm.delta)} at ${fmt.n(lstm.hours / capRef.hours, 1)}x the wall-clock time (${fmt.hours(lstm.hours)} against ${fmt.hours(capRef.hours)}).`),
    el("li", {}, el("b", {}, "Shaping ties on the mean but unlocks the iron pickaxe. "), `Generic and shaped arms reach test IQM ${fmt.n(F.generic_g9998.test_iqm)} and ${fmt.n(F.shaped_g9998.test_iqm)}; P(shaped beats generic) is ${fmt.n(pSG)}. Only ${pickAny.length} of ${rl.runs.length} runs ever crafted an iron pickaxe, all shaped and all at ${fmt.steps(Math.min(...pickAny.map((r) => r.steps)))} steps or more: ${pickSh.length} of ${longSh.length} shaped runs at 4B to 6B steps, none of the ${longGen.length} generic runs at 4B.`),
    el("li", {}, el("b", {}, `One 6B-step shaped run reaches ${fmt.n(best.score)}/32 `), `with an iron pickaxe in ${bvh["craft iron pickaxe"]} of ${bv.episodes} validation worlds and a climb back to the surface in ${bvh["return to surface"]} (one seed, selected as the best run).`),
    el("li", {}, el("b", {}, "The bitter lesson holds on the mean, not at the hardest step. "), `Counting the later 6B-step runs as well (generic arm at gamma .9999, five seeds; four more shaped seeds), the shaped arm crafted an iron pickaxe in 5 of 15 runs and the generic arm in 0 of 9 (DECISIONS.md C4). On the newer versions the two arms stay close at 1B steps: v9 ${fmt.n(mean(v9g.seed_scores), 1)}% generic against ${fmt.n(mean(v9s.seed_scores), 1)}% shaped (mean of 5 seeds), v10 ${fmt.n(v10g.score.value, 1)}% against ${fmt.n(v10s.score.value, 1)}% (mean of 3 seeds), validation worlds.`),
    el("li", {}, el("b", {}, "Things that hurt or did not help. "), `Worlds 256 tiles wide cost up to ${fmt.n(-worldWorst, 1)} points; a 21x15 view lowered the score in every setting tried (${signed(Math.max(...viewDeltas))} to ${signed(Math.min(...viewDeltas))}); Go-Explore restarts changed the generic arm by ${signed(geGen.mean - geGenRef.mean)} and the shaped arm by ${signed(geSh.mean - geShRef.mean)}.`),
  );

  // ---- facts ----
  const totalH = rl.runs.reduce((a, r) => a + r.hours, 0);
  $("#facts").replaceChildren(...[
    ["PPO runs", fmt.int(rl.runs.length), `${Object.keys(rl.studies).length} studies, 512M to 6B steps`],
    ["GPU-hours, all runs", fmt.int(totalH), `about ${fmt.usd(totalH * rate)} at the assumed rate`],
    ["Best test IQM (5 seeds)", fmt.n(Math.max(F.generic_g9998.test_iqm, F.shaped_g9998.test_iqm)), "of 32, 2B steps"],
    ["Best single run", fmt.n(best.score), `of 32, ${fmt.steps(best.steps)} steps, validation`],
  ].map(([k, v, s]) => el("div", {}, el("dt", {}, k), el("dd", {}, v, " ", el("small", {}, s)))));

  // ---- final configurations ----
  $("#rate").textContent = `${fmt.usd(rate)} per GPU-hour (${costs.gpu.name.split(" (")[0]}, a placeholder dated ${costs.gpu.date})`;
  const bc = lite.entries.find((e) => e.id === "v8-bc-shaped");
  const finalRows = Object.entries(F).map(([k, f]) => ({
    key: k, name: f.name, short: FINAL[k].short, kind: FAMILY[family(runById[f.runs[0]])].kind, steps: f.steps,
    val: f.iqm, valCi: f.ci, test: f.test_iqm, testCi: f.test_ci, seeds: f.scores.length, crafter: f.test_crafter,
    deaths: f.deaths, hours: f.hours, cost: f.hours * rate,
  }));
  finalRows.push({
    key: bc.id, name: bc.agent, short: "PPO + BC + shaping", sub: bc.sub, kind: bc.kind, placeholder: true, steps: bc.budget.env_steps,
    val: null, valCi: null, test: bc.score.value, testCi: bc.score.ci, seeds: bc.seeds, crafter: bc.crafter,
    deaths: bc.deaths, hours: bc.cost.gpu_hours, cost: bc.cost.gpu_hours * rate,
  });
  const dom = [25, 30.5];
  $("#final-table").append(table([
    { key: "name", label: "Configuration", render: (r) => el("div", {}, el("div", { class: "agent-name" }, r.name, " ", kindBadge(r.kind), r.placeholder ? [" ", sampleBadge()] : null), r.sub ? el("div", { class: "agent-sub" }, r.sub) : null) },
    { key: "steps", label: "Steps", cls: "r", sort: (r) => r.steps, render: (r) => fmt.steps(r.steps) },
    { key: "val", label: "Validation IQM", sort: (r) => r.val, render: (r) => (r.val == null ? el("span", { class: "muted" }, "n/a") : ciCell(r.val, r.valCi, dom)) },
    { key: "test", label: "Test IQM", sort: (r) => r.test, render: (r) => ciCell(r.test, r.testCi, dom) },
    { key: "seeds", label: "Seeds", cls: "r" },
    { key: "crafter", label: "Crafter score", cls: "r", sort: (r) => r.crafter, render: (r) => fmt.n(r.crafter, 1), title: "Geometric mean of per-achievement success rates, test worlds" },
    { key: "deaths", label: "Deaths", cls: "r", sort: (r) => r.deaths, render: (r) => fmt.pct(r.deaths, 1), title: "Share of validation episodes that end in death" },
    { key: "hours", label: "GPU-h per seed", cls: "r", sort: (r) => r.hours, render: (r) => fmt.n(r.hours, 2) },
    { key: "cost", label: "Training cost per seed (est.)", cls: "r", sort: (r) => r.cost, render: (r) => fmt.usd(r.cost) },
  ], finalRows, { sortKey: "test", caption: "Final v8 PPO configurations" }));
  $("#final-note").replaceChildren(
    "The standard arm uses a mean recipe potential (coefficient 3), so it is a shaped arm too. The hatched row is ", sampleBadge(),
    ": it shows where the behaviour-cloning arm will appear and is not a result. Costs are estimates because the GPU rate is a placeholder.");

  // ---- probability of improvement ----
  const keys = Object.keys(F);
  $("#pi").append(heatmap(
    keys.map((a) => ({ label: FINAL[a].short, cells: keys.map((b) => (a === b ? null : rl.p_improve[a][b])) })),
    keys.map((b) => ({ label: FINAL[b].short, icon: el("span", { class: "pi-col" }, FINAL[b].short) })),
    { fmt: (v) => fmt.n(v, 2), corner: "row beats column" }));
  $("#pi-note").textContent = `Generic against shaped: ${fmt.n(rl.p_improve.generic_g9998.shaped_g9998)}, shaped against generic: ${fmt.n(pSG)}. With 5 seeds a side, neither arm is reliably better on the mean. Both beat the standard arms in every seed pair.`;

  // ---- ablation explorer ----
  const SHORT = (t) => ({
    supply: `Supply ${(t.title.match(/at (\S+)/) || [])[1] || ""}`.trim(),
    shaping: "Shaping", discount: /generic/.test(t.title) ? "Discount, generic" : "Discount, shaped",
    capacity: "Capacity", world: "World size", view: "View size", budget: "Budget", exploration: "Go-Explore",
  }[t.dimension] || t.title);
  const hard = (label, key) => ({ label, get: (s) => s[key], run: (r) => r[{ anvil: "craft anvil", breastplate: "craft wood breastplate", surface: "return to surface", iron_pick: "craft iron pickaxe" }[key]], fmt: (v) => fmt.n(v, v % 1 ? 1 : 0), domain: () => [0, 128], count: true });
  const METRICS = {
    score: { label: "Score (achievements of 32)", get: (s) => s.mean, run: (r) => r.score, fmt: (v) => v.toFixed(2) },
    delta: { label: "Change against the reference", get: (s) => s.delta, run: (r, ref) => r.score - ref.mean, fmt: (v) => signed(v) },
    anvil: hard("Anvil crafted (worlds of 128)", "anvil"),
    breastplate: hard("Wood breastplate crafted (worlds of 128)", "breastplate"),
    surface: hard("Returned to surface (worlds of 128)", "surface"),
    iron_pick: hard("Iron pickaxe crafted (worlds of 128)", "iron_pick"),
    deaths: { label: "Deaths (share of episodes)", get: (s) => s.deaths, run: (r) => r.deaths, fmt: (v) => fmt.pct(v, 1), domain: (vs) => [0, Math.max(...vs) * 1.15 || 0.1] },
    hours: { label: "Wall-clock hours per run", get: (s) => s.hours, run: (r) => r.hours, fmt: (v) => `${v.toFixed(2)} h`, domain: (vs) => [0, Math.max(...vs) * 1.1] },
  };
  const sel = $("#ab-metric");
  for (const [k, m] of Object.entries(METRICS)) sel.append(el("option", { value: k }, m.label));
  const state = { t: 0, m: "score" };
  const tabs = rl.ablations.map((t, i) => el("button", { type: "button", "aria-pressed": String(i === 0), onclick: () => { state.t = i; drawAb(); } }, SHORT(t)));
  $("#ab-tables").replaceChildren(...tabs);
  sel.addEventListener("change", () => { state.m = sel.value; drawAb(); });
  const abLegend = legend(Object.values(FAMILY).map((f) => ({ color: f.color, label: f.label })));
  $("#ab-chart").after(abLegend);

  function drawAb() {
    tabs.forEach((b, i) => b.setAttribute("aria-pressed", String(i === state.t)));
    const t = rl.ablations[state.t], m = METRICS[state.m], ref = refOf(t);
    const rows = t.settings.map((s) => {
      const rs = s.runs.map((id) => runById[id]);
      const v = m.get(s), dots = rs.map((r) => m.run(r, ref));
      const fam = FAMILY[family(rs[0])];
      return {
        label: s.label, value: v, dots: dots.length > 1 ? dots : [], color: fam.color,
        tip: `<b>${esc(s.label)}</b>${s === ref ? " (reference)" : ""}<br>${esc(m.label)}: ${m.fmt(v)}<br>${rs.length} seed${rs.length > 1 ? "s" : ""}: ${rs.map((r) => `${r.seed}: ${m.fmt(m.run(r, ref))}`).join(", ")}<br>${esc(fam.label)}`,
      };
    });
    const vals = rows.flatMap((r) => [r.value, ...r.dots]);
    let domain;
    if (state.m === "score") domain = [Math.floor(Math.min(...vals) - 0.3), Math.min(32, Math.ceil(Math.max(...vals) + 0.3))];
    else if (state.m === "delta") { const p = 0.15 * (Math.max(0, ...vals) - Math.min(0, ...vals) || 1); domain = [Math.min(0, ...vals) - p, Math.max(0, ...vals) + p]; }
    else domain = m.domain(vals);
    $("#ab-title").textContent = t.title;
    bars($("#ab-chart"), rows, {
      domain, fmt: m.fmt, tickFmt: (x) => (state.m === "deaths" ? fmt.pct(x, 0) : state.m === "delta" ? signed(x, 1) : x),
      xLabel: m.label, ref: state.m === "delta" ? 0 : m.get(ref), refLabel: "reference", label: `${t.title}: ${m.label}`,
    });
    $("#ab-caption").textContent = caption(t, m, ref, domain);
    $("#ab-runs-sum").textContent = `Runs in this table (${new Set(t.settings.flatMap((s) => s.runs)).size})`;
    $("#ab-runs").replaceChildren(...t.settings.map((s) => el("li", {},
      el("b", {}, s.label), s === ref ? " (reference)" : "", `: mean ${fmt.n(s.mean)}, sd ${fmt.n(s.sd)}, ${s.runs.length} seed${s.runs.length > 1 ? "s" : ""}`,
      el("ul", {}, s.runs.map((id) => el("li", {}, el("code", {}, id), ` score ${fmt.n(runById[id].score)}, ${fmt.steps(runById[id].steps)} steps, ${fmt.hours(runById[id].hours)}`))))));
  }

  function caption(t, m, ref, domain) {
    const others = t.settings.filter((s) => s !== ref);
    const hi = others.reduce((a, s) => (m.get(s) > m.get(a) ? s : a)), lo = others.reduce((a, s) => (m.get(s) < m.get(a) ? s : a));
    const parts = [`Reference: ${ref.label}, ${m.fmt(m.get(ref))} (${ref.runs.length} seed${ref.runs.length > 1 ? "s" : ""}).`];
    if (others.every((s) => m.get(s) === 0) && m.get(ref) === 0) parts.push("No run in this table did this at all.");
    else if (hi === lo) parts.push(`${hi.label}: ${m.fmt(m.get(hi))}.`);
    else parts.push(`Highest: ${hi.label}, ${m.fmt(m.get(hi))}. Lowest: ${lo.label}, ${m.fmt(m.get(lo))}.`);
    if (state.m === "score" || state.m === "delta") parts.push(`The reference seeds spread with sd ${fmt.n(ref.sd)}, so smaller changes are within seed noise.`);
    if (state.m === "score") parts.push(`The axis starts at ${domain[0]}, not 0.`);
    if (state.m === "iron_pick") parts.push("Iron pickaxes only appear in shaped runs of 4B to 6B steps; see the longer runs below.");
    const single = t.settings.filter((s) => s.runs.length === 1).length;
    if (single) parts.push(`${single} setting${single > 1 ? "s have" : " has"} a single seed; read ${single > 1 ? "them" : "it"} as indicative.`);
    return parts.join(" ");
  }
  drawAb();

  // ---- learning curves: final configurations ----
  const curve = (id) => rl.curves[id].map((p) => [p[0], p[1]]);
  const meanCurve = (ids) => {
    const cs = ids.map(curve), xs = cs[0].map((p) => p[0]).filter((x) => cs.every((c) => c.some((p) => p[0] === x)));
    return xs.map((x) => [x, mean(cs.map((c) => c.find((p) => p[0] === x)[1]))]);
  };
  const fSeries = [];
  for (const [k, f] of Object.entries(F)) {
    for (const id of f.runs) fSeries.push({ color: FINAL[k].color, points: curve(id), width: 1, opacity: 0.35, quiet: true });
    const mc = meanCurve(f.runs);
    fSeries.push({ label: FINAL[k].short, short: FINAL[k].short, color: FINAL[k].color, points: mc, width: 3,
      tip: `<b>${esc(f.name)}</b><br>mean of ${f.runs.length} seeds at ${fmt.n(mc[mc.length - 1][0], 2)}B: ${fmt.n(mc[mc.length - 1][1])}<br>validation IQM ${fmt.n(f.iqm)}, test IQM ${fmt.n(f.test_iqm)}` });
  }
  lines($("#curve-final"), fSeries, { xLabel: "environment steps (billions)", yLabel: "validation score (of 32)", xFmt: (x) => `${x}B`, label: "Learning curves of the four final configurations", rightPad: 16 });
  $("#curve-final-legend").replaceChildren(legend(Object.entries(FINAL).map(([k, v]) => ({ color: v.color, label: `${v.short} (${F[k].runs.length} seeds)`, line: true }))));
  const at = (k, x) => meanCurve(F[k].runs).find((p) => p[0] === x)?.[1];
  $("#curve-final-cap").textContent = `At 1B steps the generic arm averages ${fmt.n(at("generic_g9998", 1))} and the shaped arm ${fmt.n(at("shaped_g9998", 1))}; at 2B, ${fmt.n(at("generic_g9998", 2))} and ${fmt.n(at("shaped_g9998", 2))}. At 2B the two standard configurations are ${fmt.n(at("generic_g9998", 2) - at("o3t2_standard", 2), 1)} (ore 3x + trees 2x) and ${fmt.n(at("generic_g9998", 2) - at("v8_default", 2), 1)} (default supply) points below the generic arm.`;

  // ---- learning curves: long runs ----
  const lSeries = long.map((r) => {
    const fam = FAMILY[family(r)], ip = r["craft iron pickaxe"];
    return {
      label: `${r.variant}, ${r.arm}, seed ${r.seed}`, color: fam.color, points: curve(r.id), width: ip > 0 ? 3 : 1.4, opacity: ip > 0 ? 1 : 0.6,
      dash: family(r) === "generic" ? "5 3" : null,
      tip: `<b>${esc(r.arm)}</b><br>${esc(r.variant)}, seed ${r.seed}, ${fmt.steps(r.steps)} steps<br>final ${fmt.n(r.score)}; iron pickaxe in ${ip} of 128 worlds; return to surface in ${r["return to surface"]}`,
    };
  });
  lines($("#curve-long"), lSeries, { xLabel: "environment steps (billions)", yLabel: "validation score (of 32)", xFmt: (x) => `${x}B`, vlines: [{ x: 2, label: "2B" }], label: "Learning curves of runs longer than 2B steps" });
  $("#curve-long-legend").replaceChildren(legend([
    { color: "--shaped", label: `Shaped arms, log inventory (${longSh.length} runs)`, line: true },
    { color: "--rl", label: `Generic arm (${longGen.length} runs)`, line: true, dash: true }]));
  const genLongMax = Math.max(...longGen.map((r) => r.score));
  $("#long-text").textContent = `Every run longer than 2B steps on the fair world (ore 3x + trees 2x, 128x96, 11x9 view) with gamma .9998 or .9999. Thick lines are the ${pickSh.length} runs that craft an iron pickaxe, all shaped. The best generic run ends at ${fmt.n(genLongMax)} with no iron pickaxe; the 6B shaped run ends at ${fmt.n(bestRun.score)}.`;
  $("#curve-long-cap").textContent = `Iron pickaxe worlds (of 128) for the shaped runs: ${longSh.map((r) => `seed ${r.seed} at ${fmt.steps(r.steps)}, gamma ${r.gamma}: ${r["craft iron pickaxe"]}`).join("; ")}. Generic runs: ${longGen.map((r) => r["craft iron pickaxe"]).join(", ")}. The same configuration finds the pickaxe in some seeds and not in others.`;

  // ---- all runs scatter ----
  const shapeOf = (r) => (r.world !== "128x96" ? "triangle" : r.view !== "11x9" ? "square" : "circle");
  scatter($("#all-runs"), rl.runs.map((r) => ({
    x: r.hours, y: r.score, color: FAMILY[family(r)].color, shape: shapeOf(r), r: r.steps > 2 * B ? 5.5 : 4,
    label: `${r.variant}, ${r.arm}, seed ${r.seed}`,
    tip: `<b>${esc(r.variant)}</b><br>${esc(r.arm)}<br>seed ${r.seed}, ${fmt.steps(r.steps)} steps, ${fmt.hours(r.hours)}<br>score ${fmt.n(r.score)}${r.test_score != null ? `, test ${fmt.n(r.test_score)}` : ""}<br>iron pickaxe ${r["craft iron pickaxe"]}/128, surface ${r["return to surface"]}/128<br><span class="mono">${esc(r.study)}</span>`,
  })), { xDomain: [0, Math.ceil(Math.max(...rl.runs.map((r) => r.hours)))], xLabel: "wall-clock training hours", yLabel: "final validation score (of 32)", xFmt: (x) => `${x} h`, label: "All PPO runs: score against hours" });
  $("#all-runs-legend").replaceChildren(legend(Object.values(FAMILY).map((f) => ({ color: f.color, label: `${f.label} (${rl.runs.filter((r) => FAMILY[family(r)] === f).length})` }))));
  const nBig = rl.runs.filter((r) => r.world !== "128x96").length, nView = rl.runs.filter((r) => r.world === "128x96" && r.view !== "11x9").length;
  $("#all-runs-cap").textContent = `All ${rl.runs.length} v8 runs. Circles: default 128x96 world and 11x9 view; squares: 21x15 view (${nView} runs); triangles: 256x96 world (${nBig} runs). Large marks are runs longer than 2B steps; the clusters near 0.5, 2 and 4 hours are the 512M, 2B and 4B budgets. Hover or focus a point for its configuration.`;

  // ---- costs ----
  const inf = costs.rl_inference.usd_per_episode;
  const luna = llm.attempts.filter((a) => a.study === "luna-batch");
  const lunaUsd = mean(luna.map((a) => a.actual_cost_usd));
  const sumH = (ids) => ids.reduce((a, id) => a + runById[id].hours, 0);
  const costRows = [
    ...Object.entries(F).map(([k, f]) => ({ name: f.name, steps: f.steps, hours: f.hours, seeds: f.runs.length, total: sumH(f.runs) })),
    { name: "Best single run (shaped, gamma .9998)", steps: bestRun.steps, hours: bestRun.hours, seeds: 1, total: bestRun.hours },
    { name: `All ${rl.runs.length} v8 runs`, steps: null, hours: totalH / rl.runs.length, seeds: rl.runs.length, total: totalH },
    { name: bc.agent, placeholder: true, steps: bc.budget.env_steps, hours: bc.cost.gpu_hours, seeds: bc.seeds, total: bc.cost.gpu_hours * bc.seeds },
  ];
  $("#cost-table").append(table([
    { key: "name", label: "Configuration", render: (r) => el("span", {}, r.name, r.placeholder ? [" ", sampleBadge()] : null) },
    { key: "steps", label: "Steps per seed", cls: "r", sort: (r) => r.steps, render: (r) => (r.steps ? fmt.steps(r.steps) : "512M to 6B") },
    { key: "hours", label: "GPU-h per seed", cls: "r", sort: (r) => r.hours, render: (r) => fmt.n(r.hours, 2) },
    { key: "train", label: "Training per seed (est.)", cls: "r", sort: (r) => r.hours, render: (r) => fmt.usd(r.hours * rate) },
    { key: "seeds", label: "Seeds or runs", cls: "r" },
    { key: "total", label: "Total GPU-h", cls: "r", sort: (r) => r.total, render: (r) => fmt.n(r.total, 1) },
    { key: "totalUsd", label: "Total training (est.)", cls: "r", sort: (r) => r.total, render: (r) => fmt.usd(r.total * rate) },
    { key: "inf", label: "Inference per episode (est.)", cls: "r", render: () => fmt.usd(inf) },
    { key: "eval", label: "128-world evaluation (est.)", cls: "r", render: () => fmt.usd(128 * inf) },
  ], costRows, { caption: "Estimated training and inference cost" }));
  const genSeed = F.generic_g9998.hours * rate;
  $("#cost-text").textContent = `RL pays once for training and almost nothing per episode. Training cost is wall-clock GPU-hours times ${fmt.usd(rate)} per GPU-hour, a placeholder rate until a dated quote is pinned. At that rate one 2B-step seed of the generic arm costs about ${fmt.usd(genSeed)}, roughly ${Math.round(genSeed / lunaUsd)} GPT-6 Luna episodes (mean actual cost ${fmt.usd(lunaUsd)} over the ${luna.length} batch episodes). Inference is ${fmt.usd(inf)} per 3,000-step episode, an order-of-magnitude estimate that has not been measured.`;
  $("#cost-note").replaceChildren(costs.gpu.basis, " Inference: ", costs.rl_inference._note, " The hatched row is ", sampleBadge(), ".");

  // ---- in progress ----
  $("#progress-list").replaceChildren(...hist.in_progress.filter((p) => /^v10/.test(p.what)).map((p) =>
    el("li", {}, el("b", {}, p.what), `: ${p.detail} `, el("span", { class: "note" }, "(", el("code", {}, p.source), ")"))));
})().catch((e) => fail($("#main"), e));
