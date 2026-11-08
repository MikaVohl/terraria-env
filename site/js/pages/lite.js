import { chrome, el, $, $$, fmt, achIcon, kindBadge, sampleBadge, table, ciCell, fail } from "../common.js";
import { scatter, lines, heatmap, legend } from "../charts.js";
import { loadLite, attemptProgress } from "../board.js";

chrome();

const KINDS = [["rl", "RL, generic"], ["shaped", "RL with disclosed priors"], ["llm", "LLM"], ["human", "Human"], ["baseline", "Baseline"]];
const COLOR = { rl: "--rl", shaped: "--shaped", llm: "--llm", human: "--human", baseline: "--base" };
const SHAPE = { rl: "circle", shaped: "diamond", llm: "square", human: "triangle", baseline: "circle" };
const VIZ_RUN = "eg15-envopt2b-v8-20261101/build-v8-g0/pot_e1024_max2-2001"; // the policy viz plays

(async () => {
  const { lite, rl, llm, costs, rows } = await loadLite();
  const params = new URLSearchParams(location.search);
  const state = { version: params.get("v") || "v8", kinds: new Set(KINDS.map((k) => k[0])), sample: true, axis: "usd" };
  const ver = (id) => lite.versions.find((v) => v.id === id);

  // ---- contract ----
  const c = lite.contract;
  $("#contract-facts").replaceChildren(...[
    ["Observation", c.observation], ["Actions", c.actions], ["Horizon", c.horizon], ["Score (v7, v8)", c.score_v8], ["Score (v9)", c.score_v9],
  ].map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", { style: { fontSize: "15px", fontWeight: 400 } }, v))));
  $("#contract-llm").textContent = `${c.summary} LLM harness rules: ${c.llm_rules}`;

  // ---- version tabs and filters ----
  const tabs = $("#version-tabs");
  for (const v of lite.versions) {
    tabs.append(el("button", { type: "button", role: "tab", "aria-selected": String(v.id === state.version), "data-v": v.id,
      onclick: () => { state.version = v.id; history.replaceState(null, "", `?v=${v.id}`); renderAll(); } }, v.label));
  }
  const f = $("#filters");
  for (const [k, label] of KINDS) {
    const cb = el("input", { type: "checkbox", checked: true, onchange: (e) => { e.target.checked ? state.kinds.add(k) : state.kinds.delete(k); renderBoard(); } });
    f.append(el("label", {}, cb, kindBadge(k), " ", label));
  }
  f.append(el("label", {}, el("input", { type: "checkbox", checked: true, onchange: (e) => { state.sample = e.target.checked; renderAll(); } }), "show sample data"));
  for (const b of $$("#cost-axis button")) b.addEventListener("click", () => {
    $$("#cost-axis button").forEach((x) => x.setAttribute("aria-pressed", String(x === b))); state.axis = b.dataset.axis; renderCost();
  });

  const visible = () => rows.filter((r) => r.version === state.version && (state.sample || !r.placeholder));

  function renderBoard() {
    const v = ver(state.version);
    $$("#version-tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.v === state.version)));
    $("#version-status").replaceChildren(v.status, " ", v.placeholder_only ? sampleBadge("all entries are sample data") : "");
    const list = visible().filter((r) => state.kinds.has(r.kind));
    let rank = 0;
    const ranked = [...list].sort((a, b) => (b.value ?? -1) - (a.value ?? -1)).map((r) => ({ ...r, rank: r.placeholder ? null : ++rank }));
    const unit = v.unit === "%" ? "%" : "/32";
    const cols = [
      { key: "rank", label: "#", cls: "r", sort: (r) => (r.rank == null ? null : -r.rank), render: (r) => (r.rank ?? "") },
      { key: "agent", label: "Agent", cls: "col-agent", sort: (r) => r.agent, render: (r) => el("div", {},
        el("span", { class: "agent-name" }, r.agent), " ", r.placeholder ? sampleBadge() : "",
        el("span", { class: "agent-sub" }, r.sub), r.notes ? el("span", { class: "agent-sub" }, r.notes) : "") },
      { key: "kind", label: "Kind", sort: (r) => r.kind, render: (r) => kindBadge(r.kind) },
      { key: "prior", label: "Prior knowledge", cls: "col-prior", sort: (r) => r.prior, render: (r) => el("span", { class: "note" }, r.prior) },
      { key: "value", label: `Score ${unit}`, sort: (r) => r.value, title: "IQM over training seeds with a bootstrap 95% CI for RL; mean and range over worlds for LLM attempts",
        render: (r) => el("div", {}, ciCell(r.value, r.ci, v.domain, unit === "%" ? 1 : 2),
          el("span", { class: "agent-sub" }, `${r.stat}${r.ci ? (r.ciIsRange ? ", range over worlds" : ", 95% CI") : ""}`)) },
      { key: "n", label: "Seeds x worlds", sort: (r) => (r.seeds || 0) * (r.worlds || 0), render: (r) => el("span", { class: "num" }, `${r.seeds ?? "?"} x ${r.worlds ?? "?"}`, el("span", { class: "agent-sub" }, r.split || "")) },
      { key: "budget", label: "Budget", sort: (r) => r.steps ?? r.actions, render: (r) => el("span", { class: "num" },
        r.steps ? `${fmt.steps(r.steps)} steps` : "", r.steps ? el("span", { class: "agent-sub" }, "training, per seed") : "",
        !r.steps && r.actions ? `${fmt.int(r.actions)} actions` : "", !r.steps && r.actions ? el("span", { class: "agent-sub" }, "per episode") : "") },
      { key: "cost", label: "Cost", cls: "r", sort: (r) => r.trainUsd ?? r.epUsd, title: "RL: training GPU-hours per seed times the assumed rate. LLM: provider-reported cost per episode.",
        render: (r) => el("span", { class: "num" },
          r.trainUsd != null ? fmt.usd(r.trainUsd) : r.epUsd != null ? fmt.usd(r.epUsd) : "n/a",
          el("span", { class: "agent-sub" }, r.trainUsd != null ? "per seed, estimated" : r.epUsd != null ? "per episode" : "")) },
      { key: "wall", label: "Time", cls: "r", sort: (r) => r.wallHours, render: (r) => el("span", { class: "num" }, r.wallHours != null ? fmt.hours(r.wallHours) : "n/a",
        el("span", { class: "agent-sub" }, r.steps ? "per seed" : r.wallHours != null ? "per episode" : "")) },
      { key: "crafter", label: "Crafter", cls: "r", sort: (r) => r.crafter, title: "Crafter geometric-mean score over all achievement rates (%)", render: (r) => el("span", { class: "num" }, r.crafter != null ? fmt.n(r.crafter, 1) : "n/a") },
      { key: "deaths", label: "Deaths", cls: "r", sort: (r) => r.deaths, render: (r) => el("span", { class: "num" }, r.deaths != null ? fmt.pct(r.deaths) : "n/a") },
      { key: "verified", label: "Verified", sort: (r) => (r.verified ? 1 : 0), render: verifiedCell },
    ];
    $("#board-table").replaceChildren(table(cols, ranked, { sortKey: "value", caption: `Terraria-Lite ${v.label} leaderboard` }));
    $("#board-note").textContent = state.version === "v7"
      ? "LLM entries are development studies on public worlds with few worlds each and dollar guards that stopped some episodes early; their interval is the range over worlds, not a confidence interval. They use pretrained knowledge and the public recipes, so they are not an equal-prior comparison with PPO trained from scratch."
      : state.version === "v8"
        ? `RL scores are the IQM over 5 training seeds on the 128 reserved test worlds (25,000,001 to 25,000,128), evaluated once. Training cost uses ${fmt.usd(costs.gpu.usd_per_gpu_hour)} per GPU-hour, an assumption, not a quote. No LLM has been run on v8 yet.`
        : "v9 pilots are queued; every row is sample data showing the planned columns (percent of the weighted maximum, budgets of 250M, 1B and 4B steps).";
  }

  function verifiedCell(r) {
    if (r.verified === "replay") {
      const id = r.attempts?.[0]?.id;
      return el("span", {}, el("span", { class: r.placeholder ? "unverified" : "verified" }, "replay"), " ",
        id ? el("a", { href: `replay.html?id=${encodeURIComponent(id)}` }, "watch") : "");
    }
    if (r.verified === "checkpoint") {
      const viz = r.runs?.includes(VIZ_RUN);
      return el("span", {}, el("span", { class: r.placeholder ? "unverified" : "verified", title: "Checkpoint, protocol and per-episode evaluation records are preserved; evaluation uses fixed worlds and a fixed sampler seed (54321), so it can be rerun exactly" }, "checkpoint"),
        viz ? el("span", {}, " ", el("a", { href: "viz/index.html#agent" }, "watch")) : "");
    }
    return el("span", { class: "unverified" }, "no");
  }

  function renderCost() {
    const v = ver(state.version);
    const pts = visible().filter((r) => r.value != null).map((r) => {
      const isRL = r.kind === "rl" || r.kind === "shaped";
      const x = state.axis === "usd" ? (isRL ? r.trainUsd : r.epUsd) : r.wallHours;
      return {
        x: x || null, y: r.value, label: r.agent, color: COLOR[r.kind], shape: SHAPE[r.kind], sample: r.placeholder,
        short: r.placeholder ? null : r.short,
        ylo: r.ci?.[0], yhi: r.ci?.[1],
        tip: `<b>${r.agent}</b><br>${fmt.n(r.value)}${v.unit} (${r.stat})${r.ci ? ` ${fmt.ci(r.ci)}` : ""}<br>${state.axis === "usd" ? `${fmt.usd(x)} ${isRL ? "training per seed, estimated" : "per episode"}` : `${fmt.hours(x)} ${isRL ? "training per seed" : "per episode"}`}${r.placeholder ? "<br><i>sample data</i>" : ""}`,
      };
    }).filter((p) => p.x);
    const xd = state.axis === "usd" ? [0.01, 100] : [0.01, 100];
    scatter($("#cost-chart"), pts, { xLog: true, xDomain: xd, yDomain: v.domain, frontier: true, labels: true,
      xLabel: state.axis === "usd" ? "US dollars (log scale)" : "wall-clock hours (log scale)", yLabel: v.unit === "%" ? "% of weighted max" : "achievements /32",
      xFmt: state.axis === "usd" ? (t) => fmt.usd(t) : (t) => fmt.hours(t), label: "Score against cost" });
    $("#cost-legend").replaceChildren(legend(KINDS.map(([k, l]) => ({ color: COLOR[k], label: l })).concat([{ color: "--muted", label: "sample data", sample: true }])));
  }

  function renderAch() {
    const v = ver(state.version);
    if (state.version === "v9") {
      const tr = lite.v9_tier_rates;
      $("#ach-intro").replaceChildren("v9 groups its 38 achievements into four tiers weighted 1, 3, 5 and 8. Cells: mean fraction of a tier's achievements unlocked per episode. ", sampleBadge());
      const byId = Object.fromEntries(rows.map((r) => [r.id, r]));
      $("#ach-heat").replaceChildren(heatmap(tr.agents.map((a) => ({ label: byId[a.id]?.agent || a.id, sample: true, cells: a.rates })),
        tr.tiers.map((t) => ({ label: t, icon: el("span", { style: { fontSize: "12px", fontWeight: 600, whiteSpace: "nowrap", padding: "0 6px" } }, t) })), { fmt: (x) => `${Math.round(100 * x)}%` }));
      return;
    }
    const withRates = visible().filter((r) => r.rates);
    const names = rl.achievements;
    const avg = (n) => withRates.reduce((p, r) => p + (r.rates[n] || 0), 0) / Math.max(1, withRates.length);
    const order = [...names].sort((a, b) => avg(b) - avg(a));
    $("#ach-intro").textContent = `All ${names.length} achievements, sorted by mean success across the entries shown (percent of episodes). ` +
      (state.version === "v8" ? "RL rows use the reserved test worlds (5 seeds x 128 worlds) except the single 6B run (validation worlds)." : "LLM rows pool their few development worlds, so one world moves a cell by 33 to 100 points.");
    $("#ach-heat").replaceChildren(heatmap(withRates.map((r) => ({ label: shortName(r), cells: order.map((n) => r.rates[n] ?? 0) })),
      order.map((n) => ({ label: n, icon: achIcon(n) })), { fmt: (x) => `${Math.round(100 * x)}` }));
  }

  function renderProgress() {
    const series = [], leg = [];
    const vis = visible();
    if (state.version === "v9") {
      $("#progress-intro").replaceChildren("No v9 episodes exist yet. This view will show mean achievements unlocked by each step for every entry once the pilots report. ", sampleBadge());
      $("#progress-chart").replaceChildren(); $("#progress-legend").replaceChildren(); $("#first-heat").replaceChildren(); $("#first-intro").textContent = "";
      return;
    }
    const ppo = vis.filter((r) => r.progress);
    const palette = ["--rl", "--shaped", "--bc", "--human", "--gold"];
    ppo.forEach((r, i) => {
      const col = r.kind === "rl" ? "--rl" : palette[(i % (palette.length - 1)) + 1];
      series.push({ label: shortName(r), color: col, points: r.progressGrid.map((s, j) => [s, r.progress[j]]), width: 2.5 });
      leg.push({ color: col, label: `${shortName(r)} (mean over ${r.id === "v8-best-run" ? "128" : "640"} episodes)`, line: true });
    });
    const llmRows = vis.filter((r) => r.attempts);
    for (const r of llmRows) for (const a of r.attempts) {
      series.push({ label: `${a.model.split(" ")[0].replace("openai/", "")} ${a.harness}, world ${a.world} (${a.status})`, color: "--llm", points: attemptProgress(a), step: true, width: 1.4, opacity: 0.75 });
    }
    if (llmRows.length) leg.push({ color: "--llm", label: "LLM attempts, one line per world (ends at death or budget stop)", line: true });
    $("#progress-intro").textContent = state.version === "v8"
      ? "Mean number of achievements unlocked by each step of the 3,000-step episode (validation worlds, all seeds pooled). The shape shows when progress happens: fast early unlocks, then a long slope toward the hard tier."
      : "Achievements unlocked by each step. PPO: mean over 640 validation episodes. LLM: one step line per attempt, ending where the attempt ended (death, dollar guard or call cap); a line that stops early is not a 3,000-step result.";
    lines($("#progress-chart"), series, { xDomain: [0, 3000], yDomain: [0, 32], xLabel: "environment step", yLabel: "achievements unlocked", label: "Cumulative achievements over an episode" });
    $("#progress-legend").replaceChildren(legend(leg));

    const fu = vis.filter((r) => r.firstUnlock && Object.keys(r.firstUnlock).length);
    const names = rl.achievements;
    const med = (n) => { const v = fu.map((r) => r.firstUnlock[n]).filter((x) => x != null).sort((a, b) => a - b); return v.length ? v[Math.floor(v.length / 2)] : 1e9; };
    const order = [...names].sort((a, b) => med(a) - med(b));
    $("#first-intro").textContent = "Median step of the first unlock, over the episodes that unlocked it; empty cells were never unlocked. Stronger colour means earlier. This is the TerrariaBench milestone heatmap, in environment steps.";
    $("#first-heat").replaceChildren(heatmap(fu.map((r) => ({ label: shortName(r), cells: order.map((n) => r.firstUnlock[n] ?? null) })),
      order.map((n) => ({ label: n, icon: achIcon(n) })), { fmt: (s) => (s >= 1000 ? `${(s / 1000).toFixed(1)}k` : `${Math.round(s)}`), scale: (s) => 1 - Math.min(1, s / 3000) }));
  }

  function renderDist() {
    const sec = $("#dist");
    sec.hidden = state.version !== "v8";
    if (sec.hidden) return;
    const keys = [["generic_g9998", "--rl"], ["shaped_g9998", "--shaped"], ["o3t2_standard", "--bc"]];
    const series = keys.map(([k, col]) => {
      const f = rl.final[k], tot = Object.values(f.score_hist).reduce((a, b) => a + b, 0);
      const pts = Array.from({ length: 33 }, (_, n) => [n, (f.score_hist[String(n)] || 0) / tot]).filter((p) => p[0] >= 14);
      return { label: f.name, color: col, points: pts, width: 2.2 };
    });
    lines($("#dist-chart"), series, { xDomain: [14, 32], yDomain: [0, 0.6], xLabel: "achievements unlocked in the episode", yLabel: "fraction of episodes", yFmt: (t) => `${Math.round(100 * t)}%`, label: "Distribution of achievements per episode" });
    $("#dist-legend").replaceChildren(legend(series.map((s) => ({ color: s.color, label: s.label, line: true }))));
  }

  function renderAll() { renderBoard(); renderCost(); renderAch(); renderProgress(); renderDist(); }
  renderAll();
})().catch((e) => fail($("#main"), e));

function shortName(r) { return r.short; }
