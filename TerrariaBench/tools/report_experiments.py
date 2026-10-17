"""Render the complete diagnostic scorecard and the separately selected repeats."""
import argparse
from collections import defaultdict
from decimal import Decimal
import json
from pathlib import Path
from statistics import median


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('records',type=Path)
    a=p.parse_args();rows=json.loads((a.records/'summary.json').read_text())
    budget=json.loads((a.records/'budget-snapshot.json').read_text())
    pending=sum((Decimal(v) for v in budget['pending'].values()),Decimal(0))
    reported=Decimal(budget['spent_usd'])+Decimal(budget['prior_session_reported_usd'])
    out=['# Terraria diagnostic campaign results','',
         f'Snapshot: **{len(rows)} completed game attempts**, plus nine static-image probe calls. '
         'This is adaptive development on one world, not a model leaderboard or a complete-game evaluation.','',
         f'Session reported API charges: **${reported:.6f}**; unresolved reservations: **${pending:.6f}**. '
         f'Combined accounted exposure: **${reported+pending:.6f}** against the $3 session cap. '
         'The ledger snapshot may include an active attempt; reservations are retained until reconciled.','',
         'Raw records, conditions and stop reasons are in [summary.csv](summary.csv). '
         'Per-attempt manifests record prompts, tools, model metadata, source and fixture hashes. '
         'Artifact checks verify internal consistency against retained raw logs; they do not independently validate the grader.','',
         '## Selected repeated contrasts','',
         'The repeat plan was selected after initial screening signals. Each cell has three planned new attempts, '
         'shuffled within three blocks. Initial/pilot attempts are excluded from this table. '
         'These remain small development samples, with unpinned encounter RNG. Outcome rates and distributions '
         'use fully accounted attempts; attempt counts and costs retain interrupted attempts.','',
         '| Model / condition | Accounted / recorded / planned | ≥25 wood | Workbench | Deaths (runs) | Wood maximum, median [range] | Median calls / frames | Reported cost |',
         '|---|---:|---:|---:|---:|---|---|---:|']
    groups=defaultdict(list)
    for r in rows:
        if r['run'].startswith('R'):
            groups[(r['model'].split('/')[1],r['run'].split('-')[2])].append(r)
    for (model,condition),rs in sorted(groups.items()):
        cost=sum((Decimal(r['usd']) for r in rs),Decimal(0))
        good=[r for r in rs if r['audit'].startswith('pass')];n=len(good)
        if not good:
            out.append(f'| {model} / {condition} | 0/{len(rs)}/3 | — | — | — | — | — | ${cost:.5f} |')
            continue
        wood=[r['wood_max'] for r in good]
        out.append(f'| {model} / {condition} | {n}/{len(rs)}/3 | {sum(v>=25 for v in wood)}/{n} | '
                   f'{sum(r["workbench"] for r in good)}/{n} | {sum(r["deaths"]>0 for r in good)}/{n} | '
                   f'{median(wood):g} [{min(wood)}, {max(wood)}] | '
                   f'{median(r["calls"] for r in good):g} / {median(r["frames"] for r in good):g} | ${cost:.5f} |')
    if not groups:out+=['','Repeats have not completed yet.']
    for scenario,title in [('fresh','All fresh-world attempts'),('crafting','Prepared crafting'),('slime','Prepared combat')]:
        out+=['',f'## {title}','']
        if scenario=='crafting':
            out+=['Starting 50 wood, 50 stone and 5 gel are inherited setup. Wood maxima include inherited stock; '
                  'wood checkpoints are excluded from progress. Workbench/torch/furnace columns measure newly observed possession, '
                  'not independent proof of the crafting operation.','']
        elif scenario=='slime':
            out+=['Guide removed; one designated blue slime is armed after window setup, while natural background mobs remain enabled. Only damage to that target is attributed. The initial rendered frame may precede '
                  'the spawn. Target death and attributed player damage are distinct; the original operator positive '
                  'control verified one hit, but not the kill detector. These attempts do not establish a clean clock effect.','']
        out+=['| Attempt | Wood max | Bench | Torches max / furnace | Target damage / killed | Damage received / deaths | Calls / frames | Cost | Audit |',
              '|---|---:|---|---|---|---|---|---:|---|']
        for r in rows:
            if r['scenario']!=scenario:continue
            target=f'{r["target_player_damage"]} / {"yes" if r["target_killed"] else "no"}' if scenario=='slime' else 'n/a'
            out.append(f'| [{r["run"]}]({r["run"]}/result.json) | {r["wood_max"]} | '
                       f'{"yes" if r["workbench"] else "no"} | {r["torch_max"]} / {"yes" if r["furnace"] else "no"} | '
                       f'{target} | '
                       f'{r["damage_received"]} / {r["deaths"]} | {r["calls"]} / {r["frames"]} | '
                       f'${Decimal(r["usd"]):.5f} | {r["audit"]} |')
    out+=['','## Interpretation boundaries','',
          '- Equal API calls do not mean equal action/observation opportunities. Stop limits include nominal observer updates; '
          'inference and cleanup can cross the simulation threshold. This is not an exact fixed-tick API.',
          '- PvE is enabled except the explicitly labeled peaceful ablation. Natural hostile encounters differ. '
          'Received damage is not evidence of successful combat; natural loot may come from the Guide.',
          '- A partial audit marks an unaccounted provider response/charge, not a model failure. '
          'Completed unsuccessful agent trajectories are retained.',
          '- A qualified `pass_with_inert_tail` requires an exact exported journal prefix followed only by '
          'heartbeats with identical observed state and advancing timestamps/ticks. Raw data and original '
          'result stay unchanged. Future runs wait for process termination before export.',
          '- Named native coding-agent frameworks, learned motor policies, new world seeds, bosses and post-Hardmode progression were not evaluated.',
          '- See [interpretation rules](../../interpretation.md), [selection plan](../../repeats-01.json) '
          'and [research rationale](../../design-rationale.md).','']
    (a.records/'REPORT.md').write_text('\n'.join(out))
    print(json.dumps({'report':str(a.records/'REPORT.md'),'runs':len(rows),'repeat_cells':len(groups)}))


if __name__=='__main__':main()
