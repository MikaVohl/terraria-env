# LLM agent evaluation harness

Initial implementation: October17, 2026. **Development harness, not a public
leaderboard.** See [research/design review](LLM_BENCHMARK_RESEARCH_2026_10.md)
and [first authorized live smoke](LLM_SMOKE_2026_10_17.md).

The separately authorized [Luna harness comparison](LUNA_HARNESS_PROTOCOL_2026_10_17.md)
uses v0.2 with optional compact observation packets and generic interruption
after a paid illegal-action tick. These are explicit scaffold settings, not
gameplay changes. Earlier v0.1 run snapshots/replays remain intact.

The game, action budget and scorer are shared with RL. The agent sees only the
symbolic local view/status/entities/legal mask plus public rules and recipes.
No full-map oracle, strategic action mask, navigation controller or generated
code execution. Model memory/history and batching are explicit scaffold choices.

## Offline checks

From `/Users/mikavohl/Projects/terraria-lite`:

```sh
PYTHONPATH=python .venv/bin/python tools/llm_protocol_selftest.py
PYTHONPATH=python .venv/bin/python tools/llm_harness_selftest.py
PYTHONPATH=python .venv/bin/python tools/llm_harness_selftest.py \
  --environment-root experiments/v7-reward-20261017.sGYPqq/variants/v7
```

These tests use synthetic provider responses and tiny public diagnostic worlds.
They never read credentials, use SSH or call a model API. They test observation
parity, inventory decoding, malformed and illegal actions, boundaries, schemas,
accounting, exclusive outputs, error handling and deterministic transcript/tape
verification. Nothing changes the active PPO snapshots or consumes their splits.

## Plan and run an offline baseline

```sh
PYTHONPATH=python .venv/bin/python tools/eval_llm.py \
  --mode plan --environment-root experiments/v7-reward-20261017.sGYPqq/variants/v7 \
  --config benchmarks/llm/smoke.json

PYTHONPATH=python .venv/bin/python tools/eval_llm.py \
  --mode run --environment-root experiments/v7-reward-20261017.sGYPqq/variants/v7 \
  --config benchmarks/llm/smoke.json --out experiments/my-llm-offline-smoke
```

`plan` does not read credentials, reset worlds or contact any provider. `run`
requires a new output directory. The offline random baseline selects uniformly
from the legal mask; `noop` is also available. A full run has one claim and
separate history/notes per world/replicate. Interrupted or failed runs are
preserved, not automatically resumed/retried.

## OpenRouter API tests

The historical first smoke config requested **`openai/gpt-6.1-sol` with high reasoning**,
one public development world, up to16 API calls and16 listed primitive actions
per call, with a **$2 total guard**. The game itself still has a3,000-action
deadline, but this smoke cannot execute more than256 primitive actions. It is
not a full-budget model evaluation. It finished before the user changed the
preferred model to Luna; its actual reported cost was $0.2821147.

**The preferred development model is now `openai/gpt-6-luna`, high reasoning.**
`benchmarks/llm/openrouter-luna-high-dev.json` declares three fresh public worlds,
up to3,000 primitive actions and256 calls per world, and a shared **$2 guard**.
It stops earlier on death or any configured budget. With at most16 primitive
actions per response,256 calls permit a full episode only if the model submits
sufficiently long lists. The cost guard can also truncate later worlds; do not
interpret a budget stop as a full-action-budget score. See the
[Luna launch record](LLM_LUNA_2026_10_17.md).

Review/edit a copy of that config before any later run. Model ID, budgets,
history, reasoning and pricing ceilings are part
of the evaluation contract. Pricing provenance is dated; recheck current rates
before later runs. No implicit provider/model fallback, tools or web search.

To use a key already available in the process environment:

```sh
PYTHONPATH=python .venv/bin/python tools/eval_llm.py \
  --mode run --environment-root experiments/v7-reward-20261017.sGYPqq/variants/v7 \
  --config benchmarks/llm/openrouter-luna-high-dev.json \
  --out experiments/my-luna-high-dev --allow-api
```

Alternatively append `--ssh-key-source mika@omarchy` to read only an OpenRouter
key from that login's Hermes configuration. Tailscale may require user approval.
The key is captured in process memory; do not put it in command arguments,
configuration JSON or repository files. Authorization headers are never logged.
Model-visible game state is sent to the explicitly selected OpenRouter service.

The request includes `reasoning.effort=high`, excludes returned private reasoning,
requests structured JSON and requires provider parameter support. Input, output,
reasoning-token details and actual cost are retained when the service supplies
them. Missing usage, model mismatch or a transport error stops the run. A timed
out request might still be charged; there are no automatic retries.

The local dollar guard reserves charges using UTF8 input-size and output-token
bounds at declared conservative price ceilings. Accounted cost is deliberately
different from actual provider-reported cost and may be much larger. This guard
is not a provider billing guarantee; use a separately limited key/account for
strict monetary exposure. Unknown charges remain labeled as uncertain.

## Outputs and replay

Each run saves:

- `manifest.json`: exact model/scaffold/budget settings, game/native/harness
  hashes, track, prior-knowledge policy and credential **source**, never its value.
- `world-*/claim.json`: exclusive attempt identity.
- `world-*/events.jsonl`: hash-chained request/response/action/reward/state events.
- `world-*/result.json`: per-attempt score, achievement times, budget/failure
  reason, costs, tokens, invalid requests and native final state.
- `world-*/actions.tape`: native-viewer replay when at least one action executed.
- `summary.json`: complete/incomplete denominator, world-cluster bootstrap
  interval when possible, all achievement rates and secondary coverage metric.

Provider logs can contain game observations and model-authored notes. They do
not contain SSH/key values or private reasoning text. Keep raw logs local unless
deliberately reviewing them for publication. Claims are local overwrite guards,
not a claim of independently administered secret testing.

Replay without model calls:

```sh
PYTHONPATH=python .venv/bin/python tools/eval_llm.py \
  --mode verify --environment-root experiments/v7-reward-20261017.sGYPqq/variants/v7 \
  --out experiments/my-luna-high-dev

experiments/v7-reward-20261017.sGYPqq/variants/v7/terraria-px \
  --watch experiments/my-luna-high-dev/world-31000010-rep-0/actions.tape
```

Verification requires the original harness and engine hashes. For durable runs,
copy the Python package and CLI into an immutable implementation snapshot before
running, as done for the first live smoke. The final report contains the command
using that snapshot so later development cannot invalidate verification.

## Interpretation and current limits

Primary score is mean unweighted achievements/32. Always report the primitive
action, API-call, token, time and dollar limits beside it. A `call_budget` result
is not a full3,000-action completion. One world has no meaningful generalization
interval. Repeated attempts are not best-of selection and bootstrap units are
worlds. Infrastructural errors produce an incomplete aggregate, not an inflated
mean over successful requests. Game failure/death is different from API failure.

Primitive and bounded-open-loop tracks have different observation cadence; do
not pool them. Public recipes and pretrained knowledge mean this is not equal
training-data comparison with scratch PPO. Current implementation does not yet
provide pixels, sandboxed program agents, private leaderboard administration,
human-normalized scores, automatic model summaries, direct Anthropic/OpenAI SDK
clients or an Inspect exporter. OpenRouter is the initial API backend; the small
provider boundary can be extended without changing the game/scorer contract.
