import { chrome, el, $, data, fmt, achIcon, table, fail } from "../common.js";
import { bars, heatmap } from "../charts.js";
import { boot, drawWorld, whileVisible } from "../sim.js";

chrome();

(async () => {
  const [env, rl] = await data("environment", "rl");
  const f = env.facts;

  $("#iface").replaceChildren(...[
    ["World", `${f.world_v8} (v8); ${f.world_v9} in v9`],
    ["View", f.view],
    ["Actions", `${f.actions} discrete, masked by physical legality`],
    ["Episode", `${fmt.int(f.episode_v8)} steps (v8); ${fmt.int(f.episode_v9)} in v9`],
    ["Achievements", `${f.achievements_v8} (v8); ${f.achievements_v9} in four tiers (v9)`],
    ["State", `${fmt.int(f.env_bytes)} bytes per world, copied in one memcpy`],
    ["Training reward", f.reward],
  ].map(([k, v]) => el("div", {}, el("dt", {}, k), el("dd", { style: { fontSize: "15px", fontWeight: 400 } }, v))));

  // ---- world gallery (real simulator) ----
  const grid = $("#world-grid");
  const cells = env.gallery_seeds.map((seed) => {
    const c = el("canvas", { class: "px", width: 512, height: 384, role: "img", "aria-label": `Whole world generated from seed ${seed}` });
    grid.append(el("figure", { class: "clip" }, c, el("figcaption", { class: "note" }, `Seed ${seed.toLocaleString("en-US")}`)));
    return { seed, c };
  });
  boot().then((S) => {
    const e = S.core.env();
    for (const { seed, c } of cells) {
      c.style.aspectRatio = `${S.K.WORLD_W} / ${S.K.WORLD_H}`;
      whileVisible(c, (v) => { if (v && !c.dataset.done) { e.reset(seed); drawWorld(S, c, e); c.dataset.done = "1"; } });
    }
  }).catch((err) => grid.append(el("p", { class: "check-bad" }, `World renders need the viz build and local textures: ${err.message}`)));

  // ---- achievements ----
  const tierOf = {};
  for (const t of env.achievements_v9.tiers) for (const n of t.items) tierOf[n] = `${t.name} (x${t.weight})`;
  const gen = rl.final.generic_g9998, sh = rl.final.shaped_g9998;
  const rate = (f2, n) => (f2.test.hits[n] || 0) / f2.test.episodes;
  const rows = rl.achievements.map((n, i) => ({ n, i, g: rate(gen, n), s: rate(sh, n), t: tierOf[n] || (env.achievements_v9.dropped_from_v8.includes(n) ? "not scored in v9" : "renamed in v9") }));
  $("#ach-table").append(table([
    { key: "i", label: "Bit", cls: "r", sort: (r) => r.i, render: (r) => el("span", { class: "num muted" }, r.i) },
    { key: "n", label: "Achievement", sort: (r) => r.n, render: (r) => el("span", {}, achIcon(r.n), " ", r.n) },
    { key: "g", label: "Generic PPO, test", cls: "r", sort: (r) => r.g, render: (r) => el("span", { class: "num" }, fmt.pct(r.g, r.g > 0 && r.g < 0.01 ? 1 : 0)) },
    { key: "s", label: "Shaped PPO, test", cls: "r", sort: (r) => r.s, render: (r) => el("span", { class: "num" }, fmt.pct(r.s, r.s > 0 && r.s < 0.01 ? 1 : 0)) },
    { key: "t", label: "v9 tier", sort: (r) => r.t, render: (r) => el("span", { class: "note" }, r.t) },
  ], rows, { sortKey: "g", caption: "v8 achievements with success rates and v9 tiers" }));

  const v9 = env.achievements_v9;
  $("#v9-intro").textContent = `38 achievements; the headline score is the sum of the weights unlocked, as a percentage of the maximum ${v9.max} (13 x 1 + 12 x 3 + 8 x 5 + 5 x 8). Dropped from v8: ${v9.dropped_from_v8.join(", ")}.`;
  $("#v9-tiers").replaceChildren(...v9.tiers.map((t) => el("div", {},
    el("h3", {}, `${t.name}, weight ${t.weight} (${t.items.length} achievements, ${t.items.length * t.weight} of ${v9.max} points)`),
    el("ul", { class: "ach-list" }, t.items.map((n) => el("li", {}, achIcon(n), n))))));

  // ---- human ----
  const h = env.human;
  $("#controls").textContent = h.controls;
  $("#concessions").replaceChildren(...h.concessions.map((c) => el("li", {}, c)));
  const counts = {};
  for (const s of h.scores) { const b = `${Math.floor(s / 4) * 4} to ${Math.floor(s / 4) * 4 + 3}`; counts[b] = (counts[b] || 0) + 1; }
  bars($("#human-chart"), Object.entries(counts).map(([b, n]) => ({ label: `${b} achievements`, value: n, color: "--human", sample: true })),
    { domain: [0, Math.max(...Object.values(counts)) + 1], fmt: (v) => `${v}`, tickFmt: (t) => `${t}`, xLabel: "players (sample data)", labelW: 150, label: "Sample human score histogram" });

  // ---- speed ----
  const sp = env.speed;
  $("#speed-table").append(table([
    { key: "name", label: "Setup", render: (r) => el("span", {}, el("b", {}, r.name), el("span", { class: "agent-sub" }, r.hw)) },
    { key: "sps", label: "Actions per second", cls: "r", sort: (r) => r.sps, render: (r) => el("span", { class: "num" }, fmt.int(r.sps), r.derived ? el("span", { class: "agent-sub" }, "derived") : "") },
    { key: "kind", label: "Measured by", render: (r) => el("span", { class: "note" }, r.kind === "published" ? "published (Craftax)" : "us") },
    { key: "src", label: "Source", render: (r) => el("code", { style: { whiteSpace: "normal" } }, r.source) },
  ], sp.rows, { sortKey: "sps", caption: "Speed measurements" }));
  const t = sp.tml;
  $("#tml-note").textContent = `Real Terraria per tick: ${t.per_tick_us.world} microseconds for the world alone, ${t.per_tick_us.player} with a player, ${t.per_tick_us.player_mining} with a mining player. Startup takes ${t.startup_s} s and generating a small world ${t.worldgen_s} s; each process holds ${t.rss_mib[0]} to ${t.rss_mib[1]} MiB. Not simulated in that measurement: ${t.not_simulated}.`;
})().catch((e) => fail($("#main"), e));
