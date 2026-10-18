# Final queued-trial concurrency amendment — October17,2026

At **6:14p.m. Edmonton**, the user's explicit request, "can you run the queued
one in parallel?", authorized a **concurrency-only amendment** to the ongoing
[v7 reward study](V7_REWARD_PROTOCOL_2026_10_17.md). All25 main trials and the
419,430,400-transition retained comparison remain unchanged.

## What changed, and what did not

The original immutable supervisor limits dispatch to three workers. Starting a
fourth independently without coordinating it would eventually make the original
dispatcher attempt the same run or fail its fresh-directory guard. Therefore:

- The exact original dispatcher PID99218 was validated and **suspended**, not
  its three training children. Its source, launch/protocol/start records and
  study artifacts remain intact.
- Three running trials keep their original PIDs/start identities, learner
  processes and optimizer/RNG/environment state: v4-equal-g999-805 PID25123,
  v7-equal-g999-805 PID25143 and v7-equal-g1-805 PID25148. None was restarted,
  resumed from a checkpoint, signaled or warm-started.
- A fresh, hashed coordinator PID27793 starts **only** the last untouched trial,
  v7-difficulty-g999-805 PID27801, from scratch using the original frozen command,
  configuration/environment and16M schedule. Four main trials now overlap.
- Once these trials finish, the new coordinator invokes the original frozen
  crafting diagnostic commands/order and original report implementation. It
  never invokes the old dispatcher again or trains a replacement. It then
  removes the suspended dispatcher, after no live main worker remains.
- Gameplay, learner and reward bytes, seeds, validation, checkpoint intervals,
  LR/entropy/trace settings, masks, objectives, selection/test rules and original
  study-protocol bytes **do not change**. Reserved worlds remain unused.

This is a disclosed orchestration amendment, not an unmodified execution of
the original three-worker concurrency plan. Final overlap wall times have
different contention: do not interpret run-time differences as intrinsic
method/algorithm throughput or silently pool them with three-worker timings.

## Provenance and monitoring

- Fresh coordinator snapshot:
  `experiments/v7-parallel-finish-20261017.mj7w51sy/coordinator.py`.
- New launch time:2026-10-18T00:14:23.642239UTC (October17,6:14p.m. Edmonton).
- Coordinator SHA256:
  `40920da39caa6f6dbf99766100b0be93251b2085e6b08d39a7ddb8601286e09c`.
- New root preserves `launch.json`, `started.json`, `status-before.json`,
  `amendment.json`, `last-trial-launch.json`, `runner.log` and live `status.json`.
- Original study `parallel-amendment.json` points to that root. Original study
  `status.json` now explicitly identifies the new coordinator and amendment;
  the previous status is preserved, not relabeled as new execution evidence.
- All original gameplay/learner/probe hashes were verified before handoff and
  again before the extra dispatch. Frozen directories/files were not patched.
- Read-only planning validated the exact adopted PIDs and untouched queued
  destination before any signal; live inspection confirmed all four expected
  processes with unchanged original worker starts and no remaining queue.
- Only PID99218 is suspended; it remains stopped until the handoff finishes,
  so it cannot duplicate the newly launched run. Failure preserves artifacts,
  stops only validated active trial identities, and never automatically retries.

The completion monitor must follow **PID27793 and the amendment-root log**, not
mistake historical PID99218's intentional stopped state for training failure.
Full25-run artifact/contrast/crafting auditing remains required. Main v4/game
and policy defaults, earlier studies, LLM experiments and unrelated work are
unchanged. No additional trials, paid API calls or new reserved tests authorized.
