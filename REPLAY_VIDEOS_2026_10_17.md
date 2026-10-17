# Same-seed illustrative agent videos — October17,2026

Two separate **58.9-second H.264 MP4s**,1472×1248 at30fps, with matching pacing:

- `experiments/agent-videos-20261017-a/Luna_same_seed.mp4`
- `experiments/agent-videos-20261017-a/PPO_same_seed.mp4`

Both use frozen v7 on public seed31,000,010. Luna replays its existing first
long development episode (20 achievements, dies at2478 actions; $0.408 reported
episode API cost). PPO uses the completed standard equal/.999 spatial policy,
training seed801 at16,777,216 transitions. One new sampled rollout, sampler12345,
no best-of:15 achievements,3,000 actions, alive with100 health. This is an
illustration, **not a matched-prior benchmark or a policy-selection result**.
No training, extra model calls, reserved-world access or frozen-source edits.

Pacing is identical for both:60 game actions per video second, slowed to15 near
either episode's furnace/anvil/initial smelting unlocks and deaths. There is a
1.5-second opening and3-second ending. A terminated episode freezes while the
shared action timeline continues to3,000. API inference latency is omitted and
explicitly labeled. All actions remain in their original order; no cuts,
trajectory manipulation or synthesized gameplay frames.

`tools/replay_video.c` is a rendering-only POSIX/SDL adapter, compiled against
the snapshot's **unmodified** core, original-texture renderer and replay parser.
It streams RGB frames directly into ffmpeg; no screen recording or massive
intermediate frame directory. It does not change the playable UI or simulator.
Header/footer captions identify method, prior knowledge/training, seed, action
counter, health, score, termination and the illustrative nature of the clip.

`tools/export_agent_videos.py` records the single PPO episode, derives a common
presentation schedule, builds the adapter and encodes both files. Its output
manifest preserves policy/tape/native/renderer/schedule/video hashes and actual
outcomes. Both tapes first passed the original native headless verifier; adapter
final-state records match those native states. Both MP4s fully decode without
errors, have1767 frames and matching dimensions/durations. Representative frames
from each video were visually inspected. Unrelated active studies are unchanged.

Reproduce into a **new** output directory (requires SDL2, ffmpeg and local
Terraria extracted art):

```sh
.venv/bin/python tools/export_agent_videos.py \
  --environment-root experiments/v7-reward-20261017.sGYPqq/variants/v7 \
  --policy experiments/v7-reward-20261017.sGYPqq/runs/v7-equal-g999-801/step-16777216.pt \
  --llm-tape experiments/llm-luna-20261017.amwt1tz8/run/world-31000010-rep-0/actions.tape \
  --llm-result experiments/llm-luna-20261017.amwt1tz8/run/world-31000010-rep-0/result.json \
  --out experiments/agent-videos-new
```

The existing video's source copies are preserved alongside its manifest. Native
replay determinism is verified; encoder/container metadata may differ on export.
