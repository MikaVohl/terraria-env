# Why these diagnostic contrasts

This campaign studies complete agent configurations: model, observations,
instructions, memory, action interface and timing. A change to any of these can
change the measured capability. Model-only rankings require those choices to be
fixed; system comparisons require them to be disclosed.

The following are our design proposals, informed by established benchmarks:

| Evidence | Terraria implication | Current status |
|---|---|---|
| [Crafter](https://arxiv.org/abs/2109.06780) evaluates semantically meaningful achievements across resource discovery and crafting. | Report an achievement profile; several wood thresholds should not dominate distinct crafting, exploration and combat abilities. | Raw checkpoint vector plus progress families; no final aggregate chosen. |
| [VideoGameBench](https://arxiv.org/abs/2505.18134) includes real-time play and a Lite setting that pauses during inference. | Separate reasoning/control capability with paused inference from latency-sensitive real-time deployment. | Both clocks tested; process freezing verified, exact stepping unavailable. |
| [OSWorld](https://arxiv.org/abs/2404.07972) combines environment setup with execution-based evaluation. | Freeze task fixtures and privately verify resulting state; a model's claim of crafting is insufficient. Validate graders independently. | Copied saves, input receipts and private telemetry; combat kill calibration still incomplete. |
| [MineDojo](https://arxiv.org/abs/2206.08853) supports diverse open-ended tasks and multimodal knowledge resources. | Use prepared diagnostic tasks alongside fresh campaigns, and make available knowledge an explicit experimental variable. | Crafting/combat fixtures and guide ablation; no large knowledge-base condition tested. |
| [Procgen](https://arxiv.org/abs/1912.01588) studies sample efficiency and generalization over procedurally generated environments. | Freeze development worlds, then evaluate selected conditions on unseen world seeds. | Only one development world so far; repeated attempts are not a generalization test. |

These sources motivate contrasts rather than supply a Terraria protocol. In
particular, our raw keyboard/mouse controls, observation scheduling and budgets
are our own experimental choices, not reproductions of their implementations.

The sweep already exposes several measurement questions. Coordinate conventions
need a declared contract. API-call counts can buy different numbers of action
and observation opportunities. Prepared encounters need a ready/render barrier.
Inventory possession needs to be distinguished from proven recipe execution,
and hostile loot alone does not prove an agent kill. We should settle these
before using longer campaigns to draw comparative conclusions.

The present 16-call trials diagnose early interaction. The original reference's
Wall-of-Flesh goal ends at entry to Hardmode; a complete-game benchmark must
separately define progression through the later bosses and Moon Lord. Neither
boss competence nor complete-game success is established by this campaign.
