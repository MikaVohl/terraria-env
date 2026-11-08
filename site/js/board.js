// Turns leaderboard entries (data/lite.json) into uniform rows, filling real
// numbers from the generated files: rl:final/<key>, rl:run/<id>, llm:<study>/<harness>.
import { data } from "./common.js";

export async function loadLite() {
  const [lite, rl, llm, costs] = await data("lite", "rl", "llm", "costs");
  const rows = lite.entries.map((e) => resolve(e, { rl, llm, costs }));
  return { lite, rl, llm, costs, rows };
}

export function llmGroup(llm, study, harness) {
  return llm.attempts.filter((a) => a.study === study && a.harness === harness);
}

function resolve(e, { rl, llm, costs }) {
  const rate = costs.gpu.usd_per_gpu_hour;
  const row = {
    id: e.id, version: e.version, kind: e.kind, agent: e.agent, short: e.short || e.agent, sub: e.sub, prior: e.prior,
    placeholder: !!e.placeholder, verified: e.verified || false, notes: e.notes, source: e.source,
    value: e.score?.value ?? null, ci: e.score?.ci ?? null, stat: e.score?.stat || "mean",
    seeds: e.seeds ?? null, worlds: e.worlds ?? null, split: e.split || null,
    steps: e.budget?.env_steps ?? null, actions: e.budget?.actions ?? null,
    gpuHours: e.cost?.gpu_hours ?? null, epUsd: e.cost?.per_episode_usd ?? null,
    wallHours: e.wall_hours ?? null, crafter: e.crafter ?? null, deaths: e.deaths ?? null,
    costEstimated: e.cost?.gpu_hours != null, rateIsSample: costs.gpu.placeholder,
  };
  if (row.gpuHours != null) row.trainUsd = row.gpuHours * rate;
  if (!e.ref) return row;
  const [src, key] = e.ref.split(":");
  if (src === "rl" && key.startsWith("final/")) {
    const f = rl.final[key.slice(6)];
    const test = f.test.episodes ? f.test : null;
    Object.assign(row, {
      value: f.test_iqm, ci: f.test_ci, stat: "IQM", seeds: f.scores.length, worlds: 128, split: "test",
      valIqm: f.iqm, valCi: f.ci, seedScores: f.test_scores, steps: f.steps, gpuHours: f.hours, trainUsd: f.hours * rate,
      wallHours: f.hours, crafter: f.test_crafter, deaths: f.deaths, actions: 3000,
      rates: rateMap(test ? test.hits : f.validation.hits, test ? test.episodes : f.validation.episodes, rl.achievements),
      firstUnlock: f.first_unlock_median, progress: f.progress, progressGrid: f.progress_grid,
      costEstimated: true, source: `${rl._source.split(" via ")[0]} (final configuration ${key.slice(6)})`,
      runs: f.runs,
    });
    row.epUsd = costs.rl_inference.usd_per_episode;
  } else if (src === "rl" && key.startsWith("run/")) {
    const id = key.slice(4), r = rl.runs.find((x) => x.id === id);
    const b = rl.best_run.id === id ? rl.best_run : null;
    Object.assign(row, {
      value: r.score, ci: null, stat: "mean", seeds: 1, worlds: 128, split: "validation", steps: r.steps,
      gpuHours: r.hours, trainUsd: r.hours * rate, wallHours: r.hours, crafter: r.crafter_score, deaths: r.deaths, actions: 3000,
      rates: b ? rateMap(b.validation.hits, b.validation.episodes, rl.achievements) : null,
      firstUnlock: b?.first_unlock_median, progress: b?.progress, progressGrid: b?.progress_grid,
      costEstimated: true, source: `experiments/eg15/${id}`, runs: [id],
    });
    row.epUsd = costs.rl_inference.usd_per_episode;
  } else if (src === "llm") {
    const [study, harness] = key.split("/");
    const at = llmGroup(llm, study, harness);
    const scores = at.map((a) => a.score);
    const names = llm.attempts.length ? [...new Set(llm.attempts.flatMap((a) => a.achievements))] : [];
    const rates = {};
    for (const a of at) for (const n of a.achievements) rates[n] = (rates[n] || 0) + 1 / at.length;
    const fu = {};
    for (const n of names) {
      const v = at.map((a) => a.first_unlock[n]).filter((x) => x != null).sort((p, q) => p - q);
      if (v.length) fu[n] = v.length % 2 ? v[(v.length - 1) / 2] : (v[v.length / 2 - 1] + v[v.length / 2]) / 2;
    }
    Object.assign(row, {
      value: mean(scores), ci: scores.length > 1 ? [Math.min(...scores), Math.max(...scores)] : null, ciIsRange: true, stat: "mean",
      seeds: 1, worlds: at.length, split: "public dev", actions: Math.round(mean(at.map((a) => a.steps))),
      epUsd: mean(at.map((a) => a.actual_cost_usd)), totalUsd: at.reduce((p, a) => p + a.actual_cost_usd, 0),
      wallHours: mean(at.map((a) => a.elapsed_seconds)) / 3600, deaths: at.filter((a) => a.died).length / at.length,
      crafter: crafterFromRates(rates, 32), rates, firstUnlock: fu, attempts: at, seedScores: scores,
      illegal: at.reduce((p, a) => p + a.illegal_attempts, 0) / at.reduce((p, a) => p + a.steps, 0),
      source: at[0]?.source.split("/").slice(0, 2).join("/"), costEstimated: false,
    });
  }
  return row;
}

const mean = (v) => (v.length ? v.reduce((a, b) => a + b, 0) / v.length : null);
function rateMap(hits, episodes, names) {
  const out = {};
  for (const n of names) out[n] = (hits[n] || 0) / episodes;
  return out;
}
/* Crafter score: exp(mean(ln(1 + s_i))) - 1 over n achievements, s_i in percent. */
export function crafterFromRates(rates, n) {
  let acc = 0;
  for (const v of Object.values(rates)) acc += Math.log1p(100 * v);
  return Math.exp(acc / n) - 1;
}

/* Cumulative achievements over steps for one LLM attempt (step chart points). */
export function attemptProgress(a) {
  const steps = Object.values(a.first_unlock).sort((p, q) => p - q);
  const pts = [[0, 0]];
  steps.forEach((s, i) => pts.push([s, i + 1]));
  pts.push([a.steps, steps.length]);
  return pts;
}
