// Zoom: the observation. State vs observation, the one-hot window, the status
// vector as inventory slots and advancement badges. Values are the real
// Obs row for the current replay step.
import { $, el, htmlH3, fitCanvas, icon, clamp, fmt, iconCanvas } from "./ui.js";
import { drawPlayerIcon } from "./terraria.js";

const SCALARS = ["health", "tool tier", "facing", "jump left", "fall", "depth", "across", "time", "max health",
  "weapon", "armor", "attack cd", "heal cd", "hurt cd", "air jump", "mine cd", "safe time"];

export class ObsZoom {
  constructor(S, lab) {
    this.S = S; this.lab = lab; const core = S.core2, K = core.L;
    this.K = K;
    const root = $("#zoom-obs");
    this.strip = el("canvas", { class: "vecstrip" });
    this.mini = el("canvas", { style: { width: "512px", height: "384px", imageRendering: "pixelated" } });
    this.win = el("canvas", { style: { width: "396px", height: "324px" } });
    this.onehot = el("canvas", { style: { width: "100%", height: "360px" } });
    this.gauges = el("div", { class: "gauges" });
    this.selEl = el("div", { class: "slots", style: { gridTemplateColumns: "repeat(10, 40px)" } });
    this.invEl = el("div", { class: "slots", style: { gridTemplateColumns: "repeat(17, 40px)" } });
    this.achEl = el("div", { class: "advs" });
    this.entCanvas = el("canvas", { style: { width: "352px", height: "288px" } });
    this.budget = el("div", { class: "legend" });
    this.subs = [
      el("div", { class: "sub row" }, el("div", {}, el("div", { class: "cap" }, "state · the whole world (Env)"), this.mini), el("div", { style: { flex: 1 } }, this.budget)),
      el("div", { class: "sub row" }, el("div", {}, el("div", { class: "cap" }, "observation window · 11×9"), this.win), el("div", { style: { flex: 1, minWidth: 0 } }, el("div", { class: "cap" }, "one-hot tiles: 24 kinds × 99 cells, + light"), this.onehot)),
      el("div", { class: "sub" }, el("div", { class: "cap" }, "status · scalars [0–16] · selected block [17–26]"), el("div", { class: "row" }, this.gauges, this.selEl), el("div", { class: "cap", style: { marginTop: "6px" } }, "inventory [27–59] · value = √(count / 999)"), this.invEl),
      el("div", { class: "sub row" }, el("div", {}, el("div", { class: "cap" }, "achievements [60–91]"), this.achEl), el("div", {}, el("div", { class: "cap" }, "creatures [92–487] · 4 per cell"), this.entCanvas)),
    ];
    root.append(htmlH3("c-obs", "OBSERVATION o<sub>t</sub> · 2,963 numbers"), this.strip, ...this.subs);
    this.gaugeEls = SCALARS.map((n) => { const u = el("u"); const d = el("div", { class: "gauge" }, n, el("i", {}, u)); this.gauges.append(d); return u; });
    const slot = (img, title) => { const c = iconCanvas(img); const u = el("u"), b = el("b"); const d = el("div", { class: "slot", title }, c, b, el("i", {}, u)); return { d, u, b }; };
    this.sel = core.placeables.map((it) => { const s = slot(S.items[it], core.itemNames[it]); this.selEl.append(s.d); return s; });
    this.inv = core.itemNames.map((n, i) => { const s = slot(S.items[i], n); this.invEl.append(s.d); return s; });
    this.ach = core.achNames.map((n, i) => { const c = iconCanvas(S.achIcons[i]); const d = el("div", { class: "adv", title: n }, c); this.achEl.append(d); return d; });
    this.tip = el("div", { class: "tip" }); document.body.append(this.tip);
    this.strip.addEventListener("mousemove", (e) => this.hoverStrip(e));
    this.strip.addEventListener("mouseleave", () => (this.tip.style.display = "none"));
    this.segments();
  }

  segments() {
    const K = this.K, cells = K.VIEW_W * K.VIEW_H, kinds = K.TILE_COUNT + 1;
    this.seg = [
      { n: cells * kinds, c: "#6aa8ff", label: "tiles one-hot" }, { n: cells, c: "#f3c63c", label: "light" },
      { n: 17, c: "#e9e6e1", label: "scalars" }, { n: K.PLACEABLE_COUNT, c: "#c39bff", label: "selected" },
      { n: K.ITEM_COUNT, c: "#6fd39b", label: "inventory" }, { n: K.ACH_COUNT, c: "#ffd84a", label: "achievements" },
      { n: cells * 4, c: "#ef7b5f", label: "creatures" },
    ];
    this.total = this.seg.reduce((a, s) => a + s.n, 0);
  }

  /* flat float vector, as the network sees it */
  vector() {
    const K = this.K, o = this.lab.obs, cells = K.VIEW_W * K.VIEW_H, kinds = K.TILE_COUNT + 1;
    const v = new Float32Array(this.total);
    for (let k = 0; k < cells; k++) { v[k * kinds + o.tile[k]] = 1; v[cells * kinds + k] = o.light[k] / 15; }
    v.set(o.status, cells * kinds + cells);
    return v;
  }
  describe(i) {
    const K = this.K, cells = K.VIEW_W * K.VIEW_H, kinds = K.TILE_COUNT + 1, core = this.S.core2;
    if (i < cells * kinds) return `cell ${Math.floor(i / kinds)} is ${core.tileNames[i % kinds]}?`;
    i -= cells * kinds; if (i < cells) return `light of cell ${i}`;
    i -= cells; if (i < 17) return `status: ${SCALARS[i]}`;
    i -= 17; if (i < K.PLACEABLE_COUNT) return `selected: ${core.itemNames[core.placeables[i]]}`;
    i -= K.PLACEABLE_COUNT; if (i < K.ITEM_COUNT) return `inventory: ${core.itemNames[i]}`;
    i -= K.ITEM_COUNT; if (i < K.ACH_COUNT) return `achieved: ${core.achNames[i]}`;
    i -= K.ACH_COUNT; return `cell ${Math.floor(i / 4)}: ${["slime", "bat", "creature hp", "phase"][i % 4]}`;
  }
  hoverStrip(e) {
    const r = this.strip.getBoundingClientRect(), i = Math.floor(((e.clientX - r.left) / r.width) * this.total);
    const v = this.vec ? this.vec[i] : 0;
    this.tip.textContent = `[${i}] ${this.describe(i)} = ${v.toFixed(3)}`;
    Object.assign(this.tip.style, { display: "block", left: e.clientX + 12 + "px", top: e.clientY + 12 + "px" });
  }

  draw(sub) {
    const S = this.S, K = this.K, lab = this.lab, e = lab.replay.view, core = S.core2, o = lab.obs;
    this.subs.forEach((d, i) => d.classList.toggle("on", i === sub));
    this.vec = this.vector();
    { // vector strip
      const { g, w, h } = fitCanvas(this.strip);
      g.clearRect(0, 0, w, h);
      let x0 = 0;
      const segActive = [[0], [0, 1], [2, 3, 4], [5, 6]][sub] ?? [];
      this.seg.forEach((s, si) => {
        const sw = (s.n / this.total) * w, on = segActive.includes(si);
        g.fillStyle = on ? s.c : "#2a2a32"; g.globalAlpha = 0.18; g.fillRect(x0, 12, sw, h - 26); g.globalAlpha = 1;
        g.fillStyle = s.c; g.globalAlpha = on ? 1 : 0.35;
        for (let i = 0; i < s.n; i++) {
          const v = this.vec[this.seg.slice(0, si).reduce((a, q) => a + q.n, 0) + i];
          if (v) { const bh = clamp(Math.abs(v)) * (h - 26); g.fillRect(x0 + (i / s.n) * sw, h - 14 - bh, Math.max(1, sw / s.n), bh); }
        }
        g.globalAlpha = 1; g.fillStyle = on ? s.c : "#6b6b74"; g.font = "10px ui-monospace, Menlo, monospace";
        if (sw > 40) g.fillText(`${s.label} ${s.n}`, x0 + 2, 9);
        x0 += sw;
      });
      g.fillStyle = "#8b8b94"; g.fillText("0", 0, h - 2); g.textAlign = "right"; g.fillText(String(this.total - 1), w, h - 2); g.textAlign = "left";
    }
    if (sub === 0) { // whole world, one pixel per tile, observation window
      const { g, w, h } = fitCanvas(this.mini);
      const img = new ImageData(K.WORLD_W, K.WORLD_H), m = core.u8(), d = img.data;
      for (let y = 0; y < K.WORLD_H; y++) for (let x = 0; x < K.WORLD_W; x++) {
        const t = m[e.p + K.TILES + y * K.WORLD_W + x], c = t ? S.art.tileRGB[t] : (y > e.surface(x) + 1 ? [42, 31, 24] : [110, 160, 235]);
        const j = (y * K.WORLD_W + x) * 4; d[j] = c[0]; d[j + 1] = c[1]; d[j + 2] = c[2]; d[j + 3] = 255;
      }
      const tmp = new OffscreenCanvas(K.WORLD_W, K.WORLD_H); tmp.getContext("2d").putImageData(img, 0, 0);
      g.imageSmoothingEnabled = false; g.drawImage(tmp, 0, 0, w, h);
      const sx = w / K.WORLD_W, sy = h / K.WORLD_H;
      const bx = (e.px - (K.VIEW_W >> 1)) * sx, by = (e.py - (K.VIEW_H >> 1)) * sy;
      g.fillStyle = "rgba(106,168,255,.18)"; g.fillRect(bx, by, K.VIEW_W * sx, K.VIEW_H * sy);
      g.strokeStyle = "#6aa8ff"; g.lineWidth = 3; g.strokeRect(bx, by, K.VIEW_W * sx, K.VIEW_H * sy);
      g.fillStyle = "#6aa8ff"; g.font = "bold 12px ui-monospace, Menlo, monospace"; g.fillText("what the agent sees", Math.min(bx, w - 150), by > 20 ? by - 6 : by + K.VIEW_H * sy + 14);
      g.fillStyle = "#fff"; g.fillRect(e.px * sx, (e.py - 2) * sy, 2 * sx, 3 * sy);
      const wh = K.WORLD_W * K.WORLD_H;
      const fields = [["tiles[96][128]", wh], ["light[96][128]", wh], ["terrain_light", wh], ["object_part", wh],
        ["sky_cutoff, surface", K.PX - K.SKY_CUTOFF], ["mobs[8], chests[10]", K.ACH - K.MOBS], ["player, inventory, RNG, msg…", 0]];
      fields[6][1] = K.ENV_BYTES - fields.slice(0, 6).reduce((a, f) => a + f[1], 0);
      this.budget.innerHTML = `<p><b>state</b>: <b class="c-env">${fmt(K.ENV_BYTES)}</b> bytes, everything the simulator knows</p>` +
        fields.map(([n, b]) => `<div style="display:flex;gap:8px;align-items:center"><span style="display:inline-block;width:${Math.max(2, b / 60)}px;height:8px;background:#6fd39b"></span>${n} <span class="muted">${fmt(b)} B</span></div>`).join("") +
        `<p style="margin-top:14px"><b>observation</b>: <b class="c-obs">${fmt(this.total)}</b> floats, the blue box, with unlit cells blanked out</p>` +
        `<p class="muted">It knows where it is (depth = ${o.status[5].toFixed(2)}, across = ${o.status[6].toFixed(2)} are two status numbers) but nothing outside the box: not the ore 30 tiles away, not the cave below the next wall.</p>`;
    }
    if (sub === 1) {
      const { g, w, h } = fitCanvas(this.win), cs = w / K.VIEW_W;
      g.clearRect(0, 0, w, h);
      for (let k = 0; k < K.VIEW_W * K.VIEW_H; k++) {
        const x = (k % K.VIEW_W) * cs, y = Math.floor(k / K.VIEW_W) * cs, t = o.tile[k];
        if (t === K.TILE_COUNT) { g.fillStyle = "#050507"; g.fillRect(x, y, cs, cs); g.fillStyle = "#3a3a44"; g.font = `${cs * 0.6}px ui-monospace`; g.fillText("?", x + cs * 0.3, y + cs * 0.75); }
        else if (t === 0) { g.fillStyle = "#1c2a44"; g.fillRect(x, y, cs, cs); }
        else g.drawImage(S.art.tileIcon(t), x, y, cs, cs);
        g.fillStyle = `rgba(0,0,0,${0.7 * (1 - o.light[k] / 15)})`; g.fillRect(x, y, cs, cs);
        g.strokeStyle = "rgba(255,255,255,.06)"; g.strokeRect(x, y, cs, cs);
      }
      // player body
      const cx = (K.VIEW_W >> 1) * cs, cy = (K.VIEW_H >> 1) * cs;
      drawPlayerIcon(g, S.art, cx, cy - 2 * cs, cs);
      const oh = fitCanvas(this.onehot), G = oh.g, kinds = K.TILE_COUNT + 1, rh = (oh.h - 20) / kinds, cw = (oh.w - 22) / (K.VIEW_W * K.VIEW_H);
      G.clearRect(0, 0, oh.w, oh.h);
      for (let t = 0; t < kinds; t++) {
        if (t < K.TILE_COUNT && t) G.drawImage(S.art.tileIcon(t), 2, t * rh, rh - 1, rh - 1);
        else { G.fillStyle = t ? "#050507" : "#1c2a44"; G.fillRect(2, t * rh, rh - 1, rh - 1); }
      }
      for (let k = 0; k < K.VIEW_W * K.VIEW_H; k++) {
        G.fillStyle = "#16161b"; G.fillRect(22 + k * cw, 0, cw - 0.5, kinds * rh);
        G.fillStyle = "#6aa8ff"; G.fillRect(22 + k * cw, o.tile[k] * rh, Math.max(1, cw - 0.5), rh - 0.5);
        G.fillStyle = `rgba(243,198,60,${o.light[k] / 15})`; G.fillRect(22 + k * cw, kinds * rh + 6, Math.max(1, cw - 0.5), 12);
      }
      G.fillStyle = "#8b8b94"; G.font = "9px ui-monospace"; G.fillText("light", 22, kinds * rh + 4);
    }
    if (sub === 2 || sub === 3) {
      this.gaugeEls.forEach((u, i) => (u.style.width = clamp(o.status[i]) * 100 + "%"));
      this.sel.forEach((s, i) => { const v = o.status[K.OBS_SEL0 + i]; s.u.style.width = v * 100 + "%"; s.b.textContent = v ? "1" : ""; s.d.classList.toggle("sel", !!v); });
      this.inv.forEach((s, i) => { const v = o.status[K.OBS_INV0 + i], n = e.inv(i); s.u.style.width = clamp(v) * 100 + "%"; s.b.textContent = n || ""; s.d.classList.toggle("zero", !n); s.d.title = `${core.itemNames[i]}: ${n} → √(${n}/999) = ${v.toFixed(3)}`; });
      this.ach.forEach((d, i) => d.classList.toggle("got", o.status[K.OBS_ACH0 + i] > 0));
      const { g, w, h } = fitCanvas(this.entCanvas), cs = w / K.VIEW_W;
      g.clearRect(0, 0, w, h);
      for (let k = 0; k < K.VIEW_W * K.VIEW_H; k++) {
        const x = (k % K.VIEW_W) * cs, y = Math.floor(k / K.VIEW_W) * cs, b = K.OBS_ENTITY0 + k * 4;
        const t = o.tile[k];
        g.globalAlpha = 0.3;
        if (t && t < K.TILE_COUNT) g.drawImage(S.art.tileIcon(t), x, y, cs, cs); else { g.fillStyle = t ? "#050507" : "#1c2a44"; g.fillRect(x, y, cs, cs); }
        g.globalAlpha = 1;
        if (o.status[b]) icon(g, S.art.slimeIcon, x, y, cs);
        if (o.status[b + 1]) icon(g, S.art.batIcon, x, y, cs);
        if (o.status[b + 2]) { g.fillStyle = "#e8314f"; g.fillRect(x + 1, y + cs - 3, (cs - 2) * o.status[b + 2], 2); }
      }
      let any = false; for (let k = 0; k < K.VIEW_W * K.VIEW_H * 4; k++) if (o.status[K.OBS_ENTITY0 + k]) { any = true; break; }
      g.fillStyle = "#e9e6e1"; g.font = "11px ui-monospace, Menlo, monospace";
      g.fillText(any ? "" : "no creatures in view: all 396 entries are 0", 6, h - 8);
    }
  }
}
