// Shared page chrome and helpers: navigation, theme, DOM builder, number
// formats, data loading, Terraria icons, the "sample data" marker, tooltips
// and sortable tables. No framework; every page is a module importing this.

export const PAGES = [
  ["index.html", "Overview"],
  ["lite.html", "Terraria-Lite"],
  ["terraria.html", "Official Terraria"],
  ["rl.html", "Bitter lesson"],
  ["environment.html", "Environment"],
  ["failures.html", "Failures"],
  ["history.html", "History"],
  ["method.html", "Method"],
  ["submit.html", "Submit"],
  ["replay.html", "Replays"],
];

/* el("a", {href, class}, child, "text", [more]) */
export function el(tag, attrs = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k === "text") n.textContent = v;
    else if (k.startsWith("on") && typeof v === "function") n.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(n.style, v);
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) n.append(k instanceof Node ? k : String(k));
  return n;
}
export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];

/* ---- chrome ---- */
export function chrome() {
  const here = location.pathname.split("/").pop() || "index.html";
  const top = el("header", { class: "topbar" },
    el("div", { class: "in" },
      el("a", { class: "brand", href: "index.html" }, el("img", { class: "px", src: icon("Item_1"), alt: "" }), el("span", {}, "Terraria-Lite")),
      el("nav", { class: "nav", "aria-label": "Site" },
        PAGES.map(([href, label]) => el("a", { href, "aria-current": href === here ? "page" : null }, label))),
      el("button", { class: "theme-btn", type: "button", id: "theme-btn", "aria-label": "Switch colour theme" }, "Theme")));
  document.body.prepend(el("a", { class: "skip", href: "#main" }, "Skip to content"), top);
  const btn = $("#theme-btn");
  const label = () => { btn.textContent = isDark() ? "Light" : "Dark"; };
  btn.addEventListener("click", () => {
    const next = isDark() ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch { /* private mode */ }
    label();
    document.dispatchEvent(new CustomEvent("themechange"));
  });
  label();
  const foot = el("footer", { class: "site" }, el("div", { class: "wrap" },
    el("div", {}, "Local site for the Terraria-Lite project. Data: ", el("code", {}, "site/data/*.json"),
      ". Entries marked ", sampleBadge(), " are placeholders that show the layout, not results."),
    el("div", {}, "Terraria art is read from a local game install and is not redistributed. Terraria is a trademark of Re-Logic.")));
  document.body.append(foot);
}
export function isDark() {
  const t = document.documentElement.dataset.theme;
  return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
}
// Apply the stored theme as early as possible (module scripts run after parse; pages also inline this).
try { const t = localStorage.getItem("theme"); if (t) document.documentElement.dataset.theme = t; } catch { /* ignore */ }

export function sampleBadge(text = "sample data") {
  return el("span", { class: "sample", title: "Placeholder: illustrates the layout; not a measured result" }, text);
}

/* ---- data ---- */
const cache = new Map();
export function getJSON(path) {
  if (!cache.has(path)) cache.set(path, fetch(path).then((r) => { if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`); return r.json(); }));
  return cache.get(path);
}
export async function data(...names) { return Promise.all(names.map((n) => getJSON(`data/${n}.json`))); }

/* ---- formats ---- */
export const fmt = {
  n(x, d = 2) { return x == null || Number.isNaN(x) ? "n/a" : Number(x).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }); },
  int(x) { return x == null ? "n/a" : Math.round(x).toLocaleString("en-US"); },
  pct(x, d = 0) { return x == null ? "n/a" : `${(100 * x).toFixed(d)}%`; },
  usd(x) {
    if (x == null) return "n/a";
    if (x === 0) return "$0";
    if (x < 0.01) return `$${x.toPrecision(1)}`;
    if (x < 10) return `$${x.toFixed(2)}`;
    return `$${Math.round(x).toLocaleString("en-US")}`;
  },
  steps(x) {
    if (x == null) return "n/a";
    if (x >= 2 ** 30 * 0.95) return `${+(x / 2 ** 30).toFixed(x % 2 ** 30 ? 2 : 0)}B`;
    if (x >= 2 ** 20 * 0.95) return `${+(x / 2 ** 20).toFixed(0)}M`;
    return x.toLocaleString("en-US");
  },
  hours(h) {
    if (h == null) return "n/a";
    if (h < 1 / 60) return `${Math.round(h * 3600)} s`;
    if (h < 1) return `${Math.round(h * 60)} min`;
    return `${h.toFixed(h < 10 ? 1 : 0)} h`;
  },
  rate(x) { // steps per second
    if (x >= 1e6) return `${+(x / 1e6).toFixed(2)}M`;
    if (x >= 1e3) return `${+(x / 1e3).toFixed(x >= 1e5 ? 0 : 1)}k`;
    return `${Math.round(x)}`;
  },
  ci(ci, d = 2) { return ci && ci[0] != null ? `[${fmt.n(ci[0], d)}, ${fmt.n(ci[1], d)}]` : ""; },
};

/* ---- Terraria icons (local ExtractedTextures through the viz symlink) ---- */
export const icon = (name) => `viz/textures/${name}.png`;
export const ACH_ICON = {
  "collect wood": "Item_9", "collect stone": "Item_3", "place block": "Item_2", "craft workbench": "Item_36",
  "craft furnace": "Item_33", "craft anvil": "Item_35", "place torch": "Item_8", "place platform": "Item_94",
  "collect copper": "Item_12", "collect iron": "Item_11", "collect silver": "Item_14", "collect gold": "Item_13",
  "smelt copper": "Item_20", "smelt iron": "Item_22", "smelt silver": "Item_21", "smelt gold": "Item_19",
  "defeat Blue Slime": "Item_23", "defeat Cave Bat": { sheet: "NPC_49", fw: 44, fh: 32 }, "open chest": "Item_48", "craft wooden sword": "Item_24",
  "craft metal sword": "Item_4", "craft wood breastplate": "Item_728", "craft iron chainmail": "Item_81",
  "heal with food or potion": "Item_28", "use life crystal": "Item_29", "double jump": "Item_53",
  "descend deep": "Item_18", "return to surface": "Item_50", "explore 30 columns": "Item_393", "climb rope": "Item_965",
  "craft iron pickaxe": "Item_1", "craft gold pickaxe": "Item_3521",
  // v9 additions
  "reach the caverns": "Item_18", "defeat Zombie": "Item_216", "defeat Demon Eye": "Item_38", "survive a night": "Item_17",
  "defeat Skeleton": "Item_154", "collect lens": "Item_38", "craft Suspicious Looking Eye": "Item_43",
  "summon the Eye of Cthulhu": "Item_43", "defeat the Eye of Cthulhu": "Item_56",
};
export function achIcon(name, cls = "ico") {
  const f = ACH_ICON[name];
  if (!f) return el("span", { class: cls });
  if (typeof f === "string") return el("img", { class: `${cls} px`, src: icon(f), alt: "", loading: "lazy" });
  // first frame of a sprite sheet, as a background crop
  return el("span", { class: `${cls} px`, "aria-hidden": "true", style: {
    display: "inline-block", backgroundImage: `url(${icon(f.sheet)})`, backgroundRepeat: "no-repeat",
    backgroundSize: "100% auto", backgroundPosition: "0 0", aspectRatio: `${f.fw} / ${f.fh}`, height: "auto" } });
}

/* ---- tooltip ---- */
let tipEl;
export function tip(evt, html) {
  if (!tipEl) { tipEl = el("div", { class: "tip", role: "tooltip" }); document.body.append(tipEl); }
  if (html == null) { tipEl.style.display = "none"; return; }
  tipEl.innerHTML = html;
  tipEl.style.display = "block";
  const r = tipEl.getBoundingClientRect();
  let x = evt.clientX + 14, y = evt.clientY + 14;
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - 14;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - 14;
  tipEl.style.left = `${Math.max(4, x)}px`; tipEl.style.top = `${Math.max(4, y)}px`;
}
/* Attach a tooltip to an element for mouse and keyboard focus. */
export function withTip(node, html) {
  node.addEventListener("mousemove", (e) => tip(e, html));
  node.addEventListener("mouseleave", (e) => tip(e, null));
  node.addEventListener("focus", () => { const r = node.getBoundingClientRect(); tip({ clientX: r.right, clientY: r.top }, html); });
  node.addEventListener("blur", (e) => tip(e, null));
  return node;
}
export const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ---- sortable table ----
   cols: [{key, label, cls, sort: (row) => value, render: (row) => Node|string, title}]
   rows: array of objects (row.placeholder marks sample rows). */
export function table(cols, rows, { sortKey, desc = true, caption } = {}) {
  const wrap = el("div", { class: "table-wrap" });
  const t = el("table", {});
  if (caption) t.append(el("caption", { class: "visually-hidden" }, caption));
  const head = el("tr", {});
  const tbody = el("tbody", {});
  let state = { key: sortKey, desc };
  const draw = () => {
    const c = cols.find((x) => x.key === state.key);
    const sorted = c && c.sort ? [...rows].sort((a, b) => {
      const va = c.sort(a), vb = c.sort(b);
      if (va == null && vb == null) return 0; if (va == null) return 1; if (vb == null) return -1;
      return (va < vb ? -1 : va > vb ? 1 : 0) * (state.desc ? -1 : 1);
    }) : rows;
    tbody.replaceChildren(...sorted.map((r) => el("tr", { class: r.placeholder ? "is-sample" : null },
      cols.map((c2) => el("td", { class: c2.cls }, c2.render ? c2.render(r) : r[c2.key])))));
    for (const th of head.children) th.setAttribute("aria-sort", th.dataset.key === state.key ? (state.desc ? "descending" : "ascending") : "none");
  };
  for (const c of cols) {
    const th = el("th", { class: c.cls, scope: "col", "data-key": c.key, title: c.title });
    if (c.sort) th.append(el("button", { class: "sort", type: "button", onclick: () => { state = { key: c.key, desc: state.key === c.key ? !state.desc : true }; draw(); } }, c.label));
    else th.append(c.label);
    head.append(th);
  }
  t.append(el("thead", {}, head), tbody);
  wrap.append(t);
  draw();
  return wrap;
}

/* CI cell: value, interval text and a small interval bar on [lo, hi] of the given domain. */
export function ciCell(v, ci, domain, d = 2) {
  const [a, b] = domain, pos = (x) => `${(100 * (x - a)) / (b - a)}%`;
  const bar = el("div", { class: "ci-bar", "aria-hidden": "true" });
  if (ci && ci[0] != null) bar.append(el("i", { style: { left: pos(ci[0]), width: `${(100 * (ci[1] - ci[0])) / (b - a)}%` } }));
  if (v != null) bar.append(el("b", { style: { left: pos(v) } }));
  return el("div", { class: "ci-cell" }, el("span", { class: "num" }, el("b", {}, fmt.n(v, d)), " ", el("span", { class: "muted" }, fmt.ci(ci, d))), bar);
}

export function kindBadge(kind) {
  const label = { rl: "RL", llm: "LLM", human: "Human", baseline: "Baseline", shaped: "RL + priors" }[kind] || kind;
  return el("span", { class: `kind ${kind}` }, label);
}

export function fail(where, err) {
  console.error(err);
  where.append(el("p", { class: "check-bad" }, `Could not load: ${err.message}`));
}
