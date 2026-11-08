import { chrome, el, $, data, sampleBadge, table, fail } from "../common.js";

chrome();

const STATUS = {
  v10: { short: "release candidate", cite: "Nothing final yet. Until the freeze (DECISIONS.md Gate 1), label any v10 number as a release-candidate result with the commit hash." },
  v9: { short: "superseded by v10", cite: "\"Terraria-Lite v9\" with the commit hash. The v9 PPO pilots and the LLM campaign on this site ran on it." },
  v8: { short: "development preview", cite: "\"Terraria-Lite v8 (ore 300, trees 200)\" with the knobs and the library's native_sha256. The RL results on this site use these knobs." },
  v7: { short: "frozen", cite: "\"Terraria-Lite v7\". The LLM studies and the browser replays (the wasm build is byte-identical to v7)." },
};

/* Flatten a JSON Schema into rows {path, type, required, description}. */
function fields(node, prefix = "", required = []) {
  const out = [];
  for (const [k, v] of Object.entries(node.properties || {})) {
    const path = prefix ? `${prefix}.${k}` : k;
    const type = v.const != null ? `"${v.const}"` : v.enum ? v.enum.map((x) => `"${x}"`).join(" | ")
      : v.type === "array" ? `array of ${v.items?.type || "any"}` : v.type || "any";
    const extra = [v.pattern ? `pattern ${v.pattern}` : null, v.minimum != null ? `minimum ${v.minimum}` : null, v.minItems ? `at least ${v.minItems}` : null].filter(Boolean).join("; ");
    out.push({ path, type, required: required.includes(k), description: [v.description, extra].filter(Boolean).join(". ") });
    if (v.type === "object" && v.properties) out.push(...fields(v, path, v.required || []));
    if (v.type === "array" && v.items?.properties) out.push(...fields(v.items, `${path}[]`, v.items.required || []));
  }
  return out;
}

(async () => {
  const [lite, schema] = await data("lite", "submission.schema");

  // ---- versions ----
  $("#versions-table").append(table([
    { key: "label", label: "Version", render: (r) => el("b", {}, r.label) },
    { key: "short", label: "Status", render: (r) => el("div", {}, STATUS[r.id].short, r.placeholder_only ? [" ", sampleBadge("no results yet")] : null) },
    { key: "ach", label: "Achievements", cls: "r", render: (r) => `${r.achievements}${r.unit === "%" ? " (weighted)" : ""}` },
    { key: "status", label: "Details" },
    { key: "cite", label: "What to cite", render: (r) => STATUS[r.id].cite },
  ], lite.versions, { caption: "Environment versions" }));

  // ---- schema ----
  $("#schema-version").textContent = schema.properties.schema_version.const;
  $("#schema-src").textContent = JSON.stringify(schema, null, 2);
  $("#fields").append(table([
    { key: "path", label: "Field", render: (r) => el("code", {}, r.path) },
    { key: "type", label: "Type", render: (r) => el("span", { class: "mono", style: { fontSize: "13px" } }, r.type) },
    { key: "required", label: "Required", cls: "c", render: (r) => (r.required ? "yes" : "") },
    { key: "description", label: "Meaning" },
  ], fields(schema, "", schema.required), { caption: "Results file fields" }));
})().catch((e) => fail($("#main"), e));
