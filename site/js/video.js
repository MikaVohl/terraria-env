// Run recordings from the official-Terraria campaigns. The files live in site/media/
// (gitignored; site/tools/fetch_videos.py copies, trims and encodes them), the
// metadata in data/videos.json. Every video timeline is game time: real-time runs
// are cut to the evaluation window, paused runs also lose every model-call freeze,
// so a video second is a game second and milestone times can be used as seek points.
import { el, $$ } from "./common.js";

export const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;

/* v: a data/videos.json row. opts: {start (video s), chapters: [{t (video s), game (game s, shown), label}], title, sub} */
export function videoPlayer(v, { start = 0, chapters = [], title, sub } = {}) {
  const video = el("video", {
    controls: "", preload: "none", playsinline: "", muted: "", poster: v.poster,
    src: start ? `${v.src}#t=${start}` : v.src,
    "aria-label": `Recording of run ${v.run}${title ? `: ${title}` : ""}`,
  });
  const err = el("p", { class: "note vid-err", hidden: true },
    "Video file not found. Run python3 site/tools/fetch_videos.py to copy and encode it from the run directory.");
  video.addEventListener("error", () => { err.hidden = false; }, true);

  const rates = el("div", { class: "seg vid-rate", role: "group", "aria-label": `Playback speed, ${v.run}` },
    [1, 2, 4, 8].map((r) => el("button", { type: "button", "aria-pressed": String(r === 1), onclick: (e) => {
      video.playbackRate = r;
      $$("button", e.currentTarget.parentNode).forEach((b) => b.setAttribute("aria-pressed", String(b === e.currentTarget)));
    } }, `${r}x`)));

  const chap = chapters.length ? el("div", { class: "unlocks vid-chapters", role: "group", "aria-label": `Jump to a moment, ${v.run}` },
    chapters.map((c) => el("button", { type: "button", title: `Seek to game time ${mmss(c.game ?? c.t)}`, onclick: () => { video.currentTime = Math.max(0, c.t - 2); video.play().catch(() => {}); } },
      el("span", { class: "mono" }, mmss(c.game ?? c.t)), " ", c.label))) : null;

  const len = v.clock === "paused"
    ? `${mmss(v.trimmed_s)} of game time; the raw recording is ${mmss(v.raw_s)} wall time, ${v.freezes} model-call freezes cut`
    : `${mmss(v.trimmed_s)}, real time (raw recording ${mmss(v.raw_s)} including the game launch)`;
  return el("figure", { class: "vid" },
    video, err,
    el("figcaption", {},
      title ? el("b", {}, title) : null,
      sub ? el("span", { class: "vid-sub" }, sub) : null,
      el("span", { class: "vid-len" }, `Run ${v.run}. ${len}.`)),
    rates, chap);
}
