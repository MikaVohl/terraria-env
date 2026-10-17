# Building a Terraria agent benchmark: research and decisions

Research date: **October 17, 2026**. This is a benchmark-design review, not a
claim of model superiority or a completed leaderboard. Papers, official policies,
release-specific methodology and implementation documentation were consulted.
The implementations below borrow ideas, not upstream code or benchmark scores.

## What established evaluations actually measure

### ARC-AGI-1/2: fixed tasks, explicit attempts, transparent inference resources

ARC's official testing policy describes model configurations that specify the
model, reasoning and token limits, and publication of outputs, duration and cost.
Its reference runner separates provider calls, saved submissions and scoring;
the README distinguishes attempts from transport retries and notes that hidden
SDK retries can complicate accounting. ARC-AGI-2's original announcement allows
two answers per task. This is not equivalent to taking the best of many game
episodes. [Testing policy](https://arcprize.org/policy),
[reference runner](https://github.com/arcprize/arc-agi-benchmarking),
[ARC-AGI-2 announcement](https://arcprize.org/blog/announcing-arc-agi-2-and-arc-prize-2025).

**Our decision:** freeze exact model/reasoning, prompt, budgets and sources;
save every attempt, never select a flattering trajectory as the aggregate.
No hidden retries or automatic recovery of ambiguously charged calls. Our
graded outcome is game progression, not exact-match puzzle answers.

### ARC-AGI-3: interactive action efficiency, calibrated against humans

ARC-AGI-3 adds interactive exploration and action-efficiency measurement.
Current official methodology distinguishes environment actions from internal
reasoning/tool operations. Its relative-human-action score uses a measured upper
median human baseline, nonlinear per-level efficiency and normalized aggregation.
That calibration cannot be invented from a single impressive AI replay.
[Scoring methodology](https://github.com/arcprize/docs/blob/main/methodology.mdx),
[benchmarking harness](https://github.com/arcprize/docs/blob/main/benchmarking-agent.mdx).

**Our decision:** count primitive actions separately from API calls, inference
tokens and latency. Defer human-normalized scores until controlled lockstep human
trials exist. Known Terraria recipes and instructions are intentionally allowed:
we measure proficiency in a known game, not ARC-style discovery from minimal
priors. Random worlds do not make the rules themselves novel.

### Factorio Learning Environment: the interface and scaffold are part of the task

FLE agents generate Python programs against an API and observe program output.
The documented v0.3.0 lab-play protocol gives fixed resources and throughput
targets, allows64 program steps, supplies API/recipe/pattern documentation and
reports Pass@8. Its baseline retains conversation history and invokes model
summarization as context fills. This differs materially from open-play, where
agents start from little and must progress on randomized maps.
[FLE v0.3.0](https://jackhopkins.github.io/factorio-learning-environment/versions/0.3.0.html),
[paper](https://arxiv.org/html/2503.09617v1),
[implementation](https://github.com/JackHopkins/factorio-learning-environment).

**Our decision:** public recipes are appropriate, but resource gifts, pathfinding
helpers, bulk crafting and generated-code execution would define different
tracks. Neither64 program calls nor Pass@8 can be compared directly with our
3,000 primitive actions and mean achievements. Factorio references here mean the
published FLE protocol: similarly named CPU benchmarks or unverified
"FactorioBench" discussions are not sources of agent-evaluation numbers.

### Craftax: separate game contracts, observation modalities and learning budgets

Craftax's paper separates Classic/full environments and1M/1B training budgets,
uses symbolic observations for its benchmark and compares multiple training
seeds. Full Craftax's difficulty-weighted achievements and health-change rewards
are not identical to our equal-weight game score. Large-scale scratch RL and a
pretrained API model have different prior knowledge and compute accounting.
[Paper, interface/evaluation/appendix](https://arxiv.org/html/2402.16801v2),
[official code](https://github.com/MichaelTMatthews/Craftax).

**Our decision:** pin v4/v7 separately and keep model comparisons within one
game/interface contract. Use the existing unweighted32-achievement evaluator.
Do not present a provider's reasoning-token budget as equivalent to RL training
transitions. The current PPO reward study is independent and remains frozen.

### Crafter: achievement breadth matters beyond average return

Crafter's official protocol reports individual achievement success rates and a
geometric-mean coverage score rather than only environment reward. Its README
also distinguishes externally informed agents from its bounded-interaction RL
category. Recorder code stores transitions and achievement/inventory telemetry.
[Evaluation rules](https://github.com/danijar/crafter#evaluation),
[recorder implementation](https://github.com/danijar/crafter/blob/main/crafter/recorder.py).

**Our decision:** mean unweighted achievements remains primary, but all32 rates,
first-unlock action counts, deaths and a clearly labeled Crafter-style coverage
statistic are retained. Do not rename our32-achievement result a Crafter score
or treat shaped training return as evaluation success.

### BALROG: compare models and scaffolds separately

BALROG's paper distinguishes new models from new agentic strategies. Its simple
baseline gives game rules and available actions, conditions decisions on chat
history, and uses16 observations in the reported baseline. Text and visual
interfaces are explicit options, and implementation settings expose history,
model generation parameters, saved trajectories and local/API backends.
[Paper, zero-shot protocol](https://arxiv.org/html/2411.13543v1),
[evaluation documentation](https://github.com/balrog-ai/BALROG/blob/main/docs/evaluation.md).

**Our decision:** declare history length and model-authored memory rather than
quietly adding a planner or hand-written summary. Start symbolic-only; visual
input is a later separate track. A better model with the same scaffold and a
better scaffold with the same model are different experiments.

### Reliability and reproducible infrastructure

The original tau-bench reports Pass^k reliability across repeated trials, not
just best-of-k success; its repository now explicitly warns that the original
task data are outdated. We borrow the reliability question, not those tasks.
[Historical reference](https://github.com/sierra-research/tau-bench).

Inspect documents structured evaluation logs and a distinct agent interface;
its log design also addresses repeated-message storage growth. WebArena's
canonical implementation emphasizes explicit configurations, isolated initial
state and reproducible evaluation rather than demonstrations on mutable sites.
[Inspect logs](https://inspect.aisi.org.uk/eval-logs.html),
[Inspect agents](https://inspect.aisi.org.uk/agents.html),
[WebArena](https://github.com/web-arena-x/webarena).

**Our decision:** preserve all attempts/errors and separate infrastructure failure
from agent failure. Reset model notes/history between episodes. Bootstrap world
means, not individual calls or correlated repeated samples. Keep a thin game
runner now rather than install a heavyweight framework into the active PPO
environment; future Inspect/BALROG adapters can wrap the same session contract.

## Proposed Terraria benchmark contract

### Primary task and information

Earn distinct achievements within3,000 primitive actions on randomized worlds,
with fixed recipes/items/achievements for each version. Count achievements
directly from the deterministic simulator, not an LLM judge. Death ends the
episode; no undo, reset, resource gifts or save-state search inside an attempt.
The world advances only when a primitive action executes. API latency is measured
but does not move enemies while the model thinks.

The model gets the RL local tile/light/entity observation, public inventory and
status, earned achievements and legal-action mask, plus human-readable public
rules/recipes. No full map, hidden ore, chest contents, station coordinates or
white-box crafting observer enters model input. Numeric inventory encoding is
**sqrt(count/999)**; decoding must square it. The old prototype's linear decode
was wrong and is corrected in the new protocol. Both raw status and decoded
inventory are tested against the RL observation.

### Two explicitly labeled interfaces

- **symbolic-primitive:** one primitive action per model decision. Most direct
  comparison with RL's observation cadence, but potentially3,000 API calls.
- **symbolic-open-loop:** up to16 explicitly listed primitive actions per call.
  Every action still costs a tick, with no intermediate feedback or conditional
  execution. This is cost-saving action batching, not "mine until successful"
  or "craft the next tool" automation. Report it separately.

Malformed output costs one noop; batch validation is atomic, so a partly invalid
list does not execute its valid prefix. Known illegal actions remain attempted
actions. Model notes are length-limited and reset each episode. No arbitrary
Python, shell commands or filesystem tools are exposed to the model.

### Budgets and reporting

Freeze maximum primitive actions, model calls, output tokens per call, total
provider tokens, input bytes, wall time, history, notes and total run dollars.
Record requested and returned model IDs, reasoning effort, provider, finish
reason, reported usage (including reasoning where supplied), latency and cost.
No silent model fallback. A transport failure may have incurred a charge; stop
and preserve the attempt rather than retrying invisibly.

The dollar guard reserves conservative input-size/output-token charges using
operator-declared price ceilings before each request. This is local accounting,
not an absolute billing guarantee. Record actual provider-reported cost separately
from conservative accounted cost; provider account caps remain the final billing
safety net. Missing usage or exceeded accounting assumptions stop the run.

Primary reporting: mean achievements/32 across declared worlds/replicates,
per-achievement coverage, deaths, first-unlock timing, actual primitive actions,
call/token/cost/latency budgets, invalid outputs and stop reasons. Resource-budget
stops retain attained progress but are not3,000-action completions. Infrastructure
errors make the aggregate incomplete, not a silently dropped denominator.
No pass@k or "best seed" as the default headline.

Public development worlds use a separate31M range. The old consumed PPO tests,
the active17M validation split and unused19M reserved tests are guarded. A local
numeric seed list is **not a secret held-out benchmark**. Formal private testing
needs independent administration, frozen submissions and budget/split ownership.

### Reproducibility and next gates

Every run stores source/native-library hashes, exact configuration and public
rules, append-only hash-chained request/response/action events, per-attempt
claims and native-viewer tapes. Independent verification replays all primitive
actions and checks each observed state/reward, final state and tape contents.
Hash chains detect accidental modification; they are not cryptographic proof
against an evaluator who can rewrite the whole artifact set.

Before a leaderboard: expand to a frozen multiworld suite with repeated model
samples; establish controls at matching interfaces/budgets; collect lockstep
human runs; define private-test administration; audit failure and budget handling;
then measure performance versus cost. The first live smoke is plumbing evidence,
not a comparison with16M PPO or an estimate of general model capability.

## API implementation sources

The user subsequently authorized using a Hermes OpenRouter credential on their
SSH host for **GPT-6.1 Sol at high reasoning**. The model ID is verified against
OpenRouter's live public catalog, not substituted with another alias. The key is
read into process memory over SSH, never printed, stored locally or placed in
request logs. The first smoke uses a $2 total guard and at most16 model calls.

Official OpenAI documentation confirms the requested model and reasoning levels;
OpenRouter documents its reasoning and token/structured-output parameters. These
contracts guided the adapter and offline mocks, not any unverified speed claims.
[GPT-6.1 Sol](https://developers.openai.com/api/docs/models/gpt-6.1-sol),
[OpenRouter reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens),
[OpenRouter parameters](https://openrouter.ai/docs/api_reference/parameters),
[live model catalog](https://openrouter.ai/api/v1/models).

After that smoke finished, the user chose **Luna instead of Sol** for future
work. The [Luna batch](LLM_LUNA_2026_10_17.md) uses exact
`openai/gpt-6-luna`, high reasoning, three public development worlds and the
same $2 total guard, with higher action/call allowances. Official
[Luna documentation](https://developers.openai.com/api/docs/models/gpt-6-luna)
and the live catalog were checked before launch. This is a cost-conscious
development choice, not yet evidence that Luna is equally capable.
