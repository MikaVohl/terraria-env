"""Artifact-only report/portable patches for the v6/v7 previews and pilots."""
import difflib,hashlib,json,statistics
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STUDY=ROOT/'experiments/core-next-20261012.DAW09u'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    p=read(STUDY/'pilot-protocol.json');status=read(STUDY/'pilot-status.json')
    assert sha(STUDY/'pilot-runner.py')==p['runner_sha256']
    for v,manifest in p['sources'].items():
        assert all(sha(STUDY/v/rel)==h for rel,h in manifest.items()),'Frozen pilot source changed'
        changes=[]
        paths={str(f.relative_to(STUDY/v)) for folder in ('include','src') for f in (STUDY/v/folder).iterdir() if f.suffix in ('.c','.h')}
        paths.update(['Makefile','tools/core_contract_test.c','tools/object_selftest.c'])
        for rel in sorted(paths):
            old=(ROOT/rel).read_text() if (ROOT/rel).exists() else ''
            new=(STUDY/v/rel).read_text()
            changes.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+rel if old else '/dev/null',tofile='b/'+rel))
        (ROOT/f'CORE_{v.upper()}.patch').write_text(''.join(changes))
    rows=[]
    for v,method,seed in p['runs']:
        d=STUDY/f'runs/{v}/{method}-{seed}'
        if not (d/'curve.json').exists():continue
        curve=read(d/'curve.json');last=curve[-1];e=last['evaluation']
        row={'version':v,'method':method,'seed':seed,'steps':last['steps'],'score':e['mean_achievements'],'death_rate':e['death_rate'],'bench':e['hits'].get('craft workbench',0),'stone':e['hits'].get('collect stone',0),'furnace':e['hits'].get('craft furnace',0),'anvil':e['hits'].get('craft anvil',0),'curve_sha256':sha(d/'curve.json')}
        assert sorted(x['seed'] for x in e['records'])==list(range(13000001,13000033))
        assert statistics.mean(x['achievements'] for x in e['records'])==e['mean_achievements']
        if (d/'summary.json').exists():row['summary']=read(d/'summary.json');assert row['summary']['steps']==p['steps_per_run']
        if (d/'crafting.json').exists():
            c=read(d/'crafting.json');assert c['mean_achievements']==e['mean_achievements'] and c['checkpoint_sha256']==sha(d/f"step-{p['steps_per_run']}.pt")
            assert c['seed_range']==p['validation_seeds'] and c['environment_version']==int(v[1:])
            assert c['probe_sha256']==sha(STUDY/f'probe-{v}.dylib')
            h=c['gate_steps_before_first_furnace_stone_sufficient'];den=sum(h)
            row['crafting']={'opportunity_worlds':c['opportunity_episodes'],'missing_both_fraction':sum(n for i,n in enumerate(h) if not i&1 and not i&8)/den if den else None,'counters':c['counters'],'wood_sinks':c['wood_consumed_by_action'],'sha256':sha(d/'crafting.json')}
        rows.append(row)
    complete=status['stage']=='complete'
    if complete:
        assert len(rows)==6 and all(r['steps']==p['steps_per_run'] and 'summary' in r and 'crafting' in r for r in rows)
        assert sum(r['summary']['steps'] for r in rows)==25165824
        assert not list(STUDY.glob('**/*claim.json')),'Pilot should not consume tests'
    control_root=ROOT/'experiments/core-controls-20261012.u3HE5B'
    controls=None
    if (control_root/'pilot-status.json').exists():
        control_status=read(control_root/'pilot-status.json');cp=read(control_root/'pilot-protocol.json')
        assert sha(control_root/'control-runner.py')==cp['runner_sha256']
        assert cp['sources']==p['sources']
        assert all(all(sha(control_root/v/rel)==h for rel,h in manifest.items()) for v,manifest in cp['sources'].items())
        cr=[]
        for v,m,s in cp['runs']:
            d=control_root/f'runs/{v}/{m}-{s}'
            if not (d/'curve.json').exists():continue
            last=read(d/'curve.json')[-1];e=last['evaluation']
            assert sorted(x['seed'] for x in e['records'])==list(range(13000001,13000033))
            assert statistics.mean(x['achievements'] for x in e['records'])==e['mean_achievements']
            r={'version':v,'method':m,'seed':s,'steps':last['steps'],'score':e['mean_achievements'],'death_rate':e['death_rate'],'bench':e['hits'].get('craft workbench',0),'stone':e['hits'].get('collect stone',0),'furnace':e['hits'].get('craft furnace',0),'anvil':e['hits'].get('craft anvil',0)}
            if (d/'summary.json').exists():r['summary']=read(d/'summary.json')
            if (d/'crafting.json').exists():
                c=read(d/'crafting.json');assert c['mean_achievements']==e['mean_achievements'] and c['checkpoint_sha256']==sha(d/'step-4194304.pt')
                assert c['probe_sha256']==sha(control_root/f'probe-{v}.dylib')
                r['crafting']={k:z for k,z in c.items() if k!='records'}
            cr.append(r)
        control_complete=control_status['stage']=='complete'
        if control_complete:
            assert len(cr)==4 and all(r['steps']==4194304 and 'summary' in r and 'crafting' in r for r in cr)
            assert sum(r['summary']['steps'] for r in cr)==16777216 and not list(control_root.glob('**/*claim.json'))
        controls={'complete':control_complete,'status':control_status,'protocol':cp,'runs':cr}
    calibrations={str(f.parent.relative_to(STUDY)):read(f) for f in (STUDY/'calibration').glob('*/summary.json')}
    result={'complete':complete and bool(controls and controls['complete']),'initial_pilot_complete':complete,'status':status,'protocol':p,'source_hashes_verified':True,'reserved_tests_consumed':False,'runs':rows,'controls':controls,'calibrations':calibrations,'calibration_transitions_excluded':sum(x['steps'] for x in calibrations.values()),'simulator':read(STUDY/'simulator-v5-v7-optimized.json'),'learner_cpu':read(STUDY/'learner-cpu.json')}
    (ROOT/'CORE_NEXT_2026_10.json').write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Core/interface/replay pilot results — 2026-10-12','','Status: **'+('complete and artifact-audited' if complete else 'running; partial checkpoints only')+'**. See [implementation and protocol](CORE_NEXT_2026_10.md).','','| Version/method | Seed | Transitions | Final/latest score /32 | Death | Bench / stone / furnace / anvil worlds out of 32 |','| --- | ---: | ---: | ---: | ---: | --- |']
    for r in rows:lines.append(f"| {r['version']}/{r['method']} | {r['seed']} | {r['steps']:,} | {r['score']:.3f} | {r['death_rate']:.1%} | {r['bench']} / {r['stone']} / {r['furnace']} / {r['anvil']} |")
    if complete:
        lines += ['','Six fresh 4M-ending runs total **25,165,824 main transitions**. Validation 13,000,001–13,000,032 only; all reserved test worlds remain unused. Two seeds are exploratory, not a non-inferiority or architecture proof. PPO evaluation is categorical, Q evaluation greedy.','']
        for v,m in [('v6','ppo'),('v7','ppo'),('v7','replay')]:
            rs=[r for r in rows if r['version']==v and r['method']==m]
            lines.append(f"{v}/{m}: mean {statistics.mean(r['score'] for r in rs):.3f}/32; furnace {sum(r['furnace'] for r in rs)}/64; mean wall {statistics.mean(r['summary']['wall_seconds_including_validation'] for r in rs):.1f}s.")
        lines+=['','All final-policy diagnostics reproduce their corresponding final validation means. See numeric evidence for source hashes, resource sinks, legal furnace opportunities and action-weighted joint prerequisites. Main v4/default policies are unchanged. No additional experiment or reserved evaluation is implied by this report.']
        lines+=['','Initial interpretation: direct selection increases conditional carried-bench selection (6.6%→36.6% for seed601, 11.4%→40.2% for seed602), but neither PPO seed collects stone. No stone-sufficient furnace opportunities occur in any of the six policies. The interface intervention did not solve progression in this small-budget pilot. Replay reaches stone in 13/64 worlds but scores lower with higher mortality; it is not a demonstrated improvement, nor a verdict against experience reuse/world models. Cross-method world seed streams also differ (PPO seed×10M, replay seed), so retain this as an exploratory package comparison.']
    if controls:
        lines+=['','## Follow-on mining-reliable package control','','Status: **'+('complete' if controls['complete'] else 'running; partial checkpoints only')+'**. Chosen after inspecting the first pilot, not a preregistered confirmation. Same frozen game/learner bytes; targets128/lambda.99/entropy.03 versus earlier MLP512/lambda.95/entropy.01 is a package contrast. V6/v7 within targets compares the interface separately. Four additional fresh4M trials (16,777,216 transitions), no reserved evaluation.','','| Version/package | Seed | Transitions | Score /32 | Bench / stone / furnace / anvil worlds out of 32 |','| --- | ---: | ---: | ---: | --- |']
        for r in controls['runs']:lines.append(f"| {r['version']}/{r['method']} | {r['seed']} | {r['steps']:,} | {r['score']:.3f} | {r['bench']} / {r['stone']} / {r['furnace']} / {r['anvil']} |")
        if controls['complete']:
            lines+=['','Total new main training across both stages: **41,943,040 transitions, 10 full runs**. All final diagnostic scores and frozen hashes match; no defaults promoted or tests consumed.',
                '', 'Control interpretation: targets reach stone in63/64 v6 worlds and64/64 v7 worlds, but craft zero benches/furnaces. Means are15.281 versus15.266/32 (paired score changes +.344/−.375). The interface alone does not address production of the first workshop station. Wood is below4 on >99.9% of stone-sufficient pre-furnace actions in every control policy, and a nearby bench is absent100%; those are overlapping descriptive fractions, not isolated causes.','',
                'Next agent research should address prerequisite discovery/resource allocation with general representations and experience reuse/predictive learning, using the mining-reliable control. Do not scale a surface-bound4M-ending policy by extending an annealed-to-zero checkpoint. A new32M schedule is a different fresh-budget experiment; no such run was launched here. Uniform Double DQN’s poor pilot is not a verdict against replay or Dreamer. Tool/ore correctness fixes are useful independently of an immediate score gain.']
    else:lines+=['','Do not interpret unequal-step rows as final comparisons or pool checkpoints as independent seeds.']
    (ROOT/'CORE_NEXT_RESULTS_2026_10.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'complete':complete,'rows':rows},indent=2))

if __name__=='__main__':main()
