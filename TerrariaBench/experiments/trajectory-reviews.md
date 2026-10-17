# Manual development trajectory reviews

These observations describe specific archived sequences, not population-level
failure rates or claims about a model's internal reasoning. Screenshot hashes
refer to ignored raw artifacts retained on Omarchy and synchronized locally.

## 20-haiku-tools-crafting: recipe selection followed by wrong craft target

Starting stock is 50 wood, 50 stone and 5 gel. Frame 00008 shows the workbench
recipe at approximately (40,694), beneath the currently selected torch recipe.
Response 008 clicks (40,694). Frame 00009 shows that the workbench is now the
selected recipe, at approximately (40,606), with the 10-wood requirement visible.
Response 009 instead clicks (40,518). Frame 00010 shows the torch selected again;
the three resource stacks remain 50/50/5. No bench/torch/furnace checkpoint was
recorded during the completed attempt.

This sequence verifies a successful recipe-selection input followed by a
visually misplaced follow-up click. It supports investigating dynamic UI
grounding and selection/crafting semantics. It does not by itself establish
whether memory, visual recognition, instruction following or another component
caused the follow-up choice.

| Raw screenshot | SHA-256 |
|---|---|
| `20-haiku-tools-crafting/frames/00008.png` | `e7cc6e199d3939ca9247166c5e6a97e0ffa73e85d2dd43711cb82d9733a432b3` |
| `20-haiku-tools-crafting/frames/00009.png` | `6c8c73ad1f414ee5d33b4babb1c00ccfa860ceec988c58f79e4f5e70732a255a` |
| `20-haiku-tools-crafting/frames/00010.png` | `f8bd32c33f378c5e354a11c2d33789a49e65077c0dec5bb992862de34c79f4fb` |

Raw paths are relative to `runs/diagnostic-campaign-01`. API response and input
receipt archives preserve the exact commands. No additional model call or
operator input was introduced during this review.

## 15-haiku-motor-fresh: offered macro was not used

The declared `use_item` macro was available, but the completed tool journal
contains 12 `act` and 12 `look` calls and no `use_item` calls. Executed primitive
holds reached five seconds. This is an availability/adoption observation, not
a direct evaluation of executing that macro; zero wood cannot establish that
the macro itself was ineffective. The simpler long-hold attempt used eight
commands above two seconds (maximum four seconds) and obtained a workbench.

## 25-gemini-tools-slime: in-game menu stopped world exposure

This externally real-time attempt ended in Settings → Cursor. The input journal
shows Esc, a click near Settings at (900,975), then two menu clicks at (350,510)
and (350,515). The final screenshot shows the Cursor settings panel, not combat.
The attempt ran for 87.7 agent wall seconds but recorded 62 nominal simulation
seconds. Heartbeats were one second apart before stopping in the menu; no
external process pause was enabled. This supports attributing the shortened
world exposure to the menu state rather than to the declared paused variant.

Future protocols should explicitly decide whether agents may use in-game pause
menus, and observe menu state. Here the action remains a legitimate recorded
game input and the combat outcome remains unsuccessful. A real-time condition
label describes the external scheduler, not a guarantee of continuous gameplay.
