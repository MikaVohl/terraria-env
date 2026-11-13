// Zoom: the plateau. Per-achievement success of the final checkpoint on 128
// validation episodes (from viz/data/run.json).
import { $, el, fitCanvas, icon } from "./ui.js";

export class OutroZoom {
  constructor(S) {
    this.S = S;
    this.canvas = el("canvas", { style: { width: "100%", flex: "1 1 auto", minHeight: 0 } });
    $("#zoom-outro").append(el("h3", {}, "WHERE THE TRAINED AGENT STOPS · share of 128 validation episodes earning each achievement"), this.canvas);
  }
  draw() {
    const S = this.S, names = S.core2.achNames, ck = S.run.checkpoints[S.run.checkpoints.length - 1], eps = ck.episodes || 128;
    const { g, w, h } = fitCanvas(this.canvas);
    g.clearRect(0, 0, w, h);
    const rows = names.map((n, i) => ({ n, i, f: (ck.hits?.[n] ?? 0) / eps })).sort((a, b) => b.f - a.f);
    const rh = Math.min(24, (h - 10) / rows.length);
    g.font = "12px ui-monospace, Menlo, monospace";
    rows.forEach((r, k) => {
      const y = 4 + k * rh;
      icon(g, S.achIcons[r.i], 0, y + 2, rh - 4, r.f ? 1 : 0.5);
      g.fillStyle = r.f ? "#e9e6e1" : "#ff8a70"; g.fillText(r.n, rh + 4, y + rh * 0.7);
      g.fillStyle = "#1f1f25"; g.fillRect(260, y + 3, w - 330, rh - 6);
      g.fillStyle = r.f >= 0.5 ? "#f3c63c" : r.f > 0 ? "#b58a2a" : "#ff6a4a";
      g.fillRect(260, y + 3, Math.max(r.f ? 2 : 0, (w - 330) * r.f), rh - 6);
      g.fillStyle = r.f ? "#8b8b94" : "#ff8a70"; g.fillText(r.f ? `${(r.f * 100).toFixed(0)}%` : "never", w - 60, y + rh * 0.7);
    });
  }
}
