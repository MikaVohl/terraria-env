"""Recompute diagnostic artifact consistency and produce an exploratory scorecard."""
import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
import html
import json
import math
from pathlib import Path
import struct
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from terrariabench.linux_control import validate_actions
from terrariabench.experiments import metrics, pixel_actions


def audit(root):
    manifest=json.loads((root/'manifest.json').read_text());result=json.loads((root/'result.json').read_text())
    config=manifest['config'];assert config==result['config']
    outputs=[json.loads(s) for s in (root/'tool-results.jsonl').read_text().splitlines()] if (root/'tool-results.jsonl').exists() else []
    by_id={o.get('call_id'):o for o in outputs if o.get('call_id')}
    json_steps={o['step']:o for o in outputs if o['name']=='json'}
    expected=[];cost=Decimal(0);tokens=0;images=set();prior=[];prior_response=None
    responses=sorted(root.glob('response-*.json'))
    for i,path in enumerate(responses):
        response=json.loads(path.read_text());req=json.loads((root/f'request-{i:03d}.json').read_text())
        assert response['model']==manifest['model']['id']
        cost+=Decimal(str(response['usage']['cost']));tokens+=response['usage']['prompt_tokens']+response['usage']['completion_tokens']
        msgs=req['messages'];assert msgs[0]['content']==manifest['system_prompt'];assert msgs[1]['content']==manifest['task_prompt']
        if config['history']=='full':
            assert msgs[:len(prior)]==prior
            if prior_response is not None:assert msgs[len(prior)]==prior_response
        prior=msgs;prior_response=response['choices'][0]['message']
        for msg in msgs:
            if isinstance(msg.get('content'),list):
                for part in msg['content']:
                    if part.get('type')=='image_url':
                        im=part['image_url'];data=(root/im['artifact']).read_bytes()
                        assert hashlib.sha256(data).hexdigest()==im['sha256']
                        assert struct.unpack('>II',data[16:24])==(1024,1024)
                        images.add(im['artifact'])
        if config['scaffold']=='json':
            o=json_steps.get(i)
            if o and 'dispatched_commands' in o['result']:
                body=json.loads(prior_response['content']);expected.extend(pixel_actions(body['actions'],config))
        else:
            assert req['tools']==manifest['tools']
            assert {t['function']['name'] for t in req['tools']}=={'look','act'}|({'inventory'} if config['inventory'] else set())|({'checkpoints'} if config['checkpoints'] else set())|({'use_item'} if config['motor'] else set())
            for call in prior_response.get('tool_calls',[]):
                o=by_id.get(call['id'])
                if not o or 'dispatched_commands' not in o['result']:continue
                params=json.loads(call['function']['arguments'])
                if call['function']['name']=='act':expected.extend(pixel_actions(params['actions'],config))
                elif call['function']['name']=='use_item':expected.extend(pixel_actions([{'keys':[str(params['slot']%10)],'ms':50},{'x':params['x'],'y':params['y'],'mouse':'left','ms':params['ms']}],config))
    receipts=[json.loads(s) for s in (root/'inputs.jsonl').read_text().splitlines()] if (root/'inputs.jsonl').exists() else []
    assert expected==[r['action'] for r in receipts]
    for action in expected:validate_actions([action],width=1024,height=1024,max_hold_ms=config['hold_ms'])
    assert all(r['actor']=='agent' for r in receipts)
    assert cost==Decimal(result['accounting']['reported_usd']);assert tokens==result['accounting']['tokens']
    for relative,sha in manifest['source_hashes'].items():assert hashlib.sha256((root/'source'/relative).read_bytes()).hexdigest()==sha
    events=json.loads((root/'evaluation-events.json').read_text())
    assert events and events[0]['scenario']==config['scenario']
    assert events[0]['pve_enabled']==config['pve'];assert events[0]['trusted_setup']==(config['scenario']!='fresh')
    assert not any(e.get('event')=='calibration_probe' for e in events)
    source_events=[]
    for p in (root/'telemetry').glob('*.jsonl'):source_events.extend(json.loads(s) for s in p.read_text().splitlines())
    assert events==source_events
    # Start tick is a runner measurement, not independently attested.
    start_tick=max(e['game_updates'] for e in events)-result['metrics']['game_updates_during_agent']
    recomputed=metrics(events,receipts,start_tick)
    # Python releases differ in floating-point sum accumulation.
    assert math.isclose(recomputed['input_hold_seconds'],result['metrics']['input_hold_seconds'],abs_tol=1e-8)
    recomputed['input_hold_seconds']=result['metrics']['input_hold_seconds']
    assert recomputed==result['metrics']
    if not config['pve']:assert all(e['hostile_npcs_active']==0 for e in events if e['event']=='heartbeat')
    complete=len(responses)==result['calls'] and not Decimal(result['accounting']['uncertain_reserved_usd'])
    out={'artifact_checks_passed':True,'all_calls_accounted':complete,'responses':len(responses),'commands':len(receipts),'images_verified':len(images),'source_files_verified':len(manifest['source_hashes']),'official_eligible':False}
    (root/'audit.json').write_text(json.dumps(out,indent=2)+'\n');return out


def analyze(root):
    root=Path(root);rows=[]
    for path in sorted(root.glob('*/result.json')):
        result=json.loads(path.read_text());config=result['config'];m=result['metrics'];sc=m['public_subset_score']
        try:aud=audit(path.parent);status='pass' if aud['all_calls_accounted'] else 'partial'
        except Exception as e:status='FAIL: '+type(e).__name__+': '+str(e)
        inv=m['inventory_stack_maxima'];milestones=sc['milestones']
        traces=[json.loads(s) for s in (path.parent/'tool-results.jsonl').read_text().splitlines()] if (path.parent/'tool-results.jsonl').exists() else []
        tool_counts=Counter(t['name'] for t in traces)
        replies=[json.loads(p.read_text()) for p in path.parent.glob('response-*.json')]
        row={'run':path.parent.name,'model':result['model'],'scenario':config['scenario'],'clock':config['clock'],'scaffold':config['scaffold'],
             'history':config['history'],'goal':config['goal'],'guide':config['guide'],'pve':config['pve'],'inventory_access':config['inventory'],
             'checkpoint_access':config['checkpoints'],'hold_ms':config['hold_ms'],'motor':config['motor'],
             'coordinates':config.get('coordinates','pixels'),
             'calls':result['calls'],'commands':result['commands'],'frames':result['frames'],'invalid':result['invalid_outputs'],
             'usd':result['accounting']['reported_usd'],'uncertain_usd':result['accounting']['uncertain_reserved_usd'],
             'wood_max':inv.get('Wood',0),'workbench':'workbench_1' in milestones,'torch_max':inv.get('Torch',0),'furnace':'furnace_1' in milestones,
             'families':';'.join(m['progress_families']),'deaths':m['deaths'],'damage_received':m['damage_received'],
             'target_killed':m['target_killed'],'target_player_damage':m['player_damage_to_target'],
             'max_hostiles':m['max_hostile_npcs'],'sim_seconds':round(m['game_updates_during_agent']/60,2),
             'wall_seconds':round(result['agent_wall_seconds'],2),'inference_seconds':round(result['inference_seconds'],2),
             'tool_counts':json.dumps(dict(tool_counts),sort_keys=True),
             'max_prompt_tokens':max((r['usage']['prompt_tokens'] for r in replies),default=0),
             'length_truncations':sum(r['choices'][0].get('finish_reason')=='length' for r in replies),
             'stop':result['stop_reason'],'audit':status}
        rows.append(row)
    if not rows:return
    with (root/'summary.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    (root/'summary.json').write_text(json.dumps(rows,indent=2)+'\n')
    columns=['run','wood_max','workbench','torch_max','furnace','target_killed','target_player_damage','damage_received','calls','commands','invalid','usd','sim_seconds','audit']
    body=''.join('<tr>'+''.join('<td>'+('<a href="'+r['run']+'/index.html">'+r['run']+'</a>' if k=='run' else html.escape(str(r[k])))+'</td>' for k in columns)+'</tr>' for r in rows)
    ledger=json.loads((root/'ledger.json').read_text())
    page='<!doctype html><meta charset="utf-8"><title>Terraria diagnostic experiments</title><style>body{background:#111a17;color:#edf4ef;font:14px system-ui;margin:28px}table{border-collapse:collapse}td,th{padding:7px;border:1px solid #35493c}a{color:#a5dfbd}th{position:sticky;top:0;background:#263d30}</style><h1>Exploratory Terraria experiments</h1><p>One development world; initial screening is mostly single attempts. Conditions differ in control opportunities, simulation exposure and reasoning settings. No statistical model ranking or full-game claim.</p><p>New campaign reported cost: $'+ledger['spent_usd']+'; unresolved reservations: '+html.escape(json.dumps(ledger['pending']))+'</p><table><tr>'+''.join('<th>'+k+'</th>' for k in columns)+'</tr>'+body+'</table>'
    (root/'index.html').write_text(page)
    print(json.dumps({'runs':len(rows),'audit_failures':[r['run'] for r in rows if r['audit'].startswith('FAIL')],'ledger_spent_usd':ledger['spent_usd'],'pending':ledger['pending']}))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);analyze(p.parse_args().root)
