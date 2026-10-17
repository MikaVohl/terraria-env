# Final-policy crafting diagnostics — 2026-10-12

Reporting-only analysis of all 30 saved final-policy validation rollouts. No new neural evaluations. Full joint 16-code histograms, wood sinks and event records remain in each run’s `crafting.json`; per-policy derived metrics and hashes are in [the audit](FOOTPRINT_LEARNING_2026_10.audit.json).

Missing fractions condition on pre-first-furnace actions with at least 20 stone. Wood means at least 4, torches at least 3, station means a nearby workbench. These are overlapping action-weighted descriptions, not independent seeds or causal attribution. Bench selection conditions on inventory ownership, not on placement-space availability. Acquired wood includes recoveries; sinks count actual consumed units, not unique resource supply.

| Policy | Score /32 | Opportunity worlds /128 | Furnace worlds /128 | Missing wood / station / both | Bench selected while owned | Wood acquired / platform sink per world |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| v4/memory-501 | 18.547 | 5 | 5 | 93.3% / 97.3% / 90.6% | 2.3% | 35.6 / 8.2 |
| v4/memory-502 | 18.391 | 2 | 2 | 93.4% / 97.5% / 91.0% | 4.7% | 42.5 / 9.7 |
| v4/memory-503 | 17.344 | 0 | 0 | 99.6% / 100.0% / 99.6% | n/a | 17.3 / 12.3 |
| v4/memory-504 | 17.172 | 0 | 0 | 99.5% / 100.0% / 99.5% | n/a | 16.0 / 10.4 |
| v4/memory-505 | 17.344 | 0 | 0 | 98.0% / 99.1% / 97.2% | 1.7% | 20.6 / 11.2 |
| v4/mlp-501 | 16.961 | 29 | 29 | 88.2% / 89.1% / 77.8% | 11.9% | 52.8 / 1.8 |
| v4/mlp-502 | 19.633 | 13 | 13 | 86.7% / 98.0% / 84.7% | 17.9% | 56.1 / 2.2 |
| v4/mlp-503 | 10.969 | 0 | 0 | n/a / n/a / n/a | 21.9% | 61.2 / 12.2 |
| v4/mlp-504 | 10.984 | 0 | 0 | n/a / n/a / n/a | 23.4% | 74.5 / 9.1 |
| v4/mlp-505 | 10.391 | 0 | 0 | n/a / n/a / n/a | 18.4% | 38.4 / 2.4 |
| v4/targets-501 | 18.539 | 3 | 3 | 93.9% / 98.6% / 92.5% | 4.8% | 39.0 / 11.5 |
| v4/targets-502 | 17.477 | 2 | 2 | 89.9% / 98.5% / 88.4% | 0.6% | 29.7 / 9.7 |
| v4/targets-503 | 17.680 | 3 | 2 | 97.9% / 99.0% / 96.8% | 9.6% | 38.4 / 5.9 |
| v4/targets-504 | 17.648 | 0 | 0 | 97.9% / 99.9% / 97.8% | 10.6% | 43.9 / 8.7 |
| v4/targets-505 | 17.055 | 0 | 0 | 99.7% / 100.0% / 99.7% | n/a | 17.4 / 11.9 |
| v5/memory-501 | 16.969 | 0 | 0 | 99.9% / 99.9% / 99.9% | 1.1% | 15.8 / 9.7 |
| v5/memory-502 | 16.969 | 0 | 0 | 99.9% / 100.0% / 99.9% | n/a | 16.5 / 11.1 |
| v5/memory-503 | 17.227 | 0 | 0 | 99.4% / 100.0% / 99.4% | n/a | 16.0 / 10.5 |
| v5/memory-504 | 16.859 | 0 | 0 | 97.8% / 99.8% / 97.6% | 2.5% | 17.4 / 9.5 |
| v5/memory-505 | 17.203 | 0 | 0 | 99.9% / 100.0% / 99.9% | n/a | 16.3 / 10.4 |
| v5/mlp-501 | 23.555 | 120 | 106 | 24.9% / 98.6% / 23.7% | 3.3% | 70.7 / 1.8 |
| v5/mlp-502 | 19.266 | 18 | 16 | 81.5% / 98.1% / 79.6% | 26.0% | 47.9 / 4.5 |
| v5/mlp-503 | 21.867 | 126 | 126 | 46.7% / 96.9% / 43.7% | 14.4% | 70.2 / 9.2 |
| v5/mlp-504 | 10.953 | 0 | 0 | n/a / n/a / n/a | 38.5% | 64.4 / 16.4 |
| v5/mlp-505 | 10.938 | 0 | 0 | n/a / n/a / n/a | 25.8% | 60.1 / 11.5 |
| v5/targets-501 | 17.258 | 0 | 0 | 97.6% / 99.8% / 97.4% | 2.6% | 18.8 / 12.3 |
| v5/targets-502 | 17.016 | 0 | 0 | 99.6% / 99.9% / 99.5% | 1.5% | 15.8 / 8.7 |
| v5/targets-503 | 16.758 | 0 | 0 | 99.7% / 99.9% / 99.6% | 1.5% | 15.4 / 9.6 |
| v5/targets-504 | 17.109 | 0 | 0 | 99.8% / 100.0% / 99.8% | n/a | 14.8 / 10.7 |
| v5/targets-505 | 17.219 | 0 | 0 | 99.9% / 100.0% / 99.9% | n/a | 16.2 / 11.7 |

Interpretation: the v5 targets/memory packages reach zero furnace opportunities across all five seeds each. They acquire roughly 16 wood/world, spend roughly 10 on platforms and 2.5–2.7 on torches, and almost never craft benches. On v4, the same packages acquire more wood and craft more benches, but still almost never coordinate all four furnace prerequisites. The successful v5 MLP seeds demonstrate that the enlarged-object game supports workshop progression; the two late MLP seeds remain near 11/32 with no furnaces. Missing furnace opportunity is not the same as inability to learn the furnace action.

Bench space is available during more than 98% of owned-bench actions in every aggregate package/version group. This weakens a simple “cannot place the larger bench anywhere” explanation, but does not exclude harder placement during rare strategically useful moments. V5 MLP has more opportunities without more aggregate bench-selection frequency. Inventory friction, wood retention/reacquisition, station positioning and sparse long-term credit remain candidate intervention targets—not proven individual causes.

These observations do not isolate object size, world generation, interaction reach, architecture, entropy or trace settings. No resource supply, recipe, mask, reward or controller was changed. See [the study report](FOOTPRINT_LEARNING_2026_10.md) for the five-independent-seed comparisons.
