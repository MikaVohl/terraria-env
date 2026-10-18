"""Controlled, cost-accounted diagnostic experiments; independent of reference runs."""
import argparse
import base64
import copy
from decimal import Decimal
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import signal
import time

from .linux_control import GameControl, launch, validate_actions, stop_owned_game
from .openrouter import RETRY_POLICY, Budget, ProviderError, hermes_key, request, retry_delay
from .reference_live import ACTION_SCHEMA
from .reference_scoring import checkpoint_view, reference_score

ROOT = Path(__file__).resolve().parents[1]
SYSTEM = "You control a live Terraria game using the documented interface. Screenshots and tool results are observations. Follow the task, use normal gameplay, and recover from errors."
VARIANTS = {
    'tools': {}, 'paused': {'clock':'paused'}, 'peaceful': {'pve':False},
    'checkpoints': {'checkpoints':True}, 'specific': {'goal':'workbench'},
    'guided': {'goal':'workbench','guide':True}, 'inventory': {'inventory':True},
    'json': {'scaffold':'json'}, 'notes': {'scaffold':'json','history':'notes4'},
    'long-hold': {'hold_ms':8000}, 'motor': {'hold_ms':8000,'motor':True},
    'normalized': {'coordinates':'normalized1000'},
}
DEFAULT = {'clock':'realtime','pve':True,'checkpoints':False,'goal':'open',
           'guide':False,'inventory':False,'scaffold':'tools','history':'full',
           'hold_ms':2000,'motor':False,'scenario':'fresh','reasoning':'medium'}


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2)+'\n')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Ledger:
    """Lock the ledger before reserving; unknown transport charges remain reserved."""
    def __init__(self, root, limit=None):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.path=self.root/'ledger.json'
        if not self.path.exists():
            if limit is None: raise ValueError('campaign requires an explicit cap')
            with self.path.open('x') as s:
                json.dump({'limit_usd':str(limit),'spent_usd':'0','pending':{},'calls':[]},s)
    def change(self, run, reserve=None, charge=None, cancel=False):
        with self.path.open('r+') as s:
            fcntl.flock(s,fcntl.LOCK_EX)
            data=json.load(s)
            spent=Decimal(data['spent_usd'])
            if reserve is not None:
                pending=sum((Decimal(v) for v in data['pending'].values()),Decimal(0))
                if run in data['pending'] or spent+pending+reserve>Decimal(data['limit_usd']):
                    raise RuntimeError('campaign_reservation_limit')
                data['pending'][run]=str(reserve)
            if charge is not None:
                if run not in data['pending']: raise ValueError('charge without reservation')
                data['pending'].pop(run)
                data['spent_usd']=str(spent+charge)
                data['calls'].append({'run':run,'usd':str(charge),'unix':time.time()})
            if cancel: data['pending'].pop(run,None)
            s.seek(0);json.dump(data,s,indent=2);s.truncate();s.flush();os.fsync(s.fileno())
            return data


class ProcessClock:
    def __init__(self,pid,enabled,journal):
        self.pid=pid;self.enabled=enabled;self.paused=False;self.journal=Path(journal)
        self.paused_since=None;self.paused_seconds=0
    def set(self,paused):
        if not self.enabled or paused==self.paused:return
        os.killpg(self.pid,signal.SIGSTOP if paused else signal.SIGCONT)
        stamp=time.time()
        if paused:self.paused_since=stamp
        else:self.paused_seconds+=stamp-self.paused_since
        self.paused=paused
        with self.journal.open('a') as s:s.write(json.dumps({'paused':paused,'unix':stamp})+'\n')
    def total(self):
        return self.paused_seconds+(time.time()-self.paused_since if self.paused else 0)


def target_ready(events):
    """First heartbeat proving the armed target exists and is alive, else None."""
    for e in events:
        t=e.get('target') or {}
        if e.get('event')=='heartbeat' and t.get('slot',-1)>=0 and t.get('active') and t.get('life',0)>0:
            return e
    return None


RENDER_SETTLE_SECONDS=.25  # >=15 rendered frames at 60 FPS after the ready heartbeat


def tool(name,description,properties=None,required=None):
    p={'type':'object','properties':properties or {},'additionalProperties':False}
    if required:p['required']=required
    return {'type':'function','function':{'name':name,'description':description,'parameters':p}}


def tools_for(config):
    schema=copy.deepcopy(ACTION_SCHEMA)
    schema['items']['properties']['ms']['maximum']=config['hold_ms']
    normalized=config.get('coordinates')=='normalized1000'
    if normalized:
        for axis in ('x','y'):schema['items']['properties'][axis]['maximum']=1000
    tools=[tool('look','Capture the current 1024x1024 screenshot.'),
           tool('act','Send normal keyboard/mouse actions in '+('normalized 0..1000 coordinates.' if normalized else 'screenshot pixels.'),{'actions':schema},['actions'])]
    if config['checkpoints']:tools.append(tool('checkpoints','Read public checkpoint events.'))
    if config['inventory']:tools.append(tool('inventory','Privileged diagnostic: read current inventory slots, item names/counts and HP.'))
    if config['motor']:
        tools.append(tool('use_item','Open-loop motor macro: select a hotbar slot and hold left mouse at your supplied coordinate. No targeting or state feedback.',
                          {'slot':{'type':'integer','minimum':1,'maximum':10},'x':{'type':'integer','minimum':0,'maximum':1023},
                           'y':{'type':'integer','minimum':0,'maximum':1023},'ms':{'type':'integer','minimum':20,'maximum':8000}},['slot','x','y','ms']))
    return tools


def prompt_for(c):
    if c['scenario']=='crafting':
        goal='This is a prepared crafting diagnostic. You start with 50 wood, 50 stone and 5 gel in addition to starter tools. Create a workbench, at least 10 torches, and a furnace through normal inventory crafting. Starting resources are inherited and do not score. Continue improving your base afterward.'
    elif c['scenario']=='slime':
        goal='This is a prepared combat diagnostic. A blue slime starts nearby and the Guide was removed during setup. Defeat the slime using your starter equipment, avoid damage, and recover if necessary. Afterward continue progressing.'
    elif c['goal']=='workbench':
        goal='Starting fresh, collect at least 25 wood and make a workbench through normal gameplay. Afterward continue progressing toward the Wall of Flesh.'
    else:goal='Starting with a fresh character and world, make as much genuine Terraria progress as possible toward defeating the Wall of Flesh.'
    text=goal+'\nThe window is 1024x1024. Coordinates are pixels 0..1023 on both axes. Actions may combine keys, mouse (left/right/middle), x,y, and ms. A/D move, space jumps, esc toggles inventory, number keys select hotbar slots. Keys/buttons release after every action. Batches contain 1..16 actions and execute without intermediate feedback. Max hold is '+str(c['hold_ms'])+' ms. Continue until the harness budget ends; do not stop after your first milestone.\n'
    text+=('The entire game process pauses while the model thinks. It runs during action and observation windows.\n' if c['clock']=='paused' else 'The game continues running while you think.\n')
    text+=('Normal hostile mobs and damage are enabled.\n' if c['pve'] else 'Hostile NPCs/projectiles are suppressed in this diagnostic; no loot or defeat credit is granted.\n')
    if c['guide']:text+='Shared guide for this condition: hotbar 1 is sword, 2 pickaxe, 3 axe. Select the axe and hold left mouse at the base of a nearby tree; approach dropped wood to collect it. A workbench needs 10 wood. Esc opens inventory; use the crafting panel on the left. A torch recipe uses wood and gel; a furnace needs 20 stone, 4 wood and 3 torches. Place crafting stations nearby when needed.\n'
    if c['scaffold']=='json':text+='Every response must be a JSON object with exactly notes (your memory/plan, at most 2000 characters) and actions (1..16 action objects). Example: {"notes":"Inspect the result next","actions":[{"keys":["d"],"ms":100}]}. A fresh screenshot follows each response. No tool calls.\n'
    else:
        text+='Use look to observe and act to send actions. Request observations whenever needed.\n'
        if c['inventory']:text+='The inventory tool is available in this privileged-observation condition.\n'
        if c['checkpoints']:text+='You may read public checkpoints with the checkpoints tool.\n'
        if c['motor']:text+='The use_item macro selects the requested slot and holds the mouse; you must choose coordinates and timing yourself.\n'
    if c.get('coordinates')=='normalized1000':
        text=text.replace('Coordinates are pixels 0..1023 on both axes.',
                          'Output NORMALIZED coordinates 0..1000 on BOTH axes: left/top=0, right/bottom=1000, center=500,500. Do NOT output pixel coordinates. The controller linearly maps these coordinates to screenshot pixels, without aiming or perception assistance.')
    return text


def pixel_actions(actions,config):
    if config.get('coordinates')!='normalized1000':
        return validate_actions(actions,width=1024,height=1024,max_hold_ms=config['hold_ms'])
    validate_actions(actions,width=1001,height=1001,max_hold_ms=config['hold_ms'])
    converted=[]
    for action in actions:
        action=dict(action)
        for axis in ('x','y'):
            if axis in action:action[axis]=round(action[axis]*1023/1000)
        converted.append(action)
    return validate_actions(converted,width=1024,height=1024,max_hold_ms=config['hold_ms'])


def metrics(events,receipts,start_tick):
    hb=[e for e in events if e.get('event')=='heartbeat']
    maxima={}
    for e in hb:
        for item in e['inventory']:
            maxima[item.get('name',str(item['type']))]=max(maxima.get(item.get('name',str(item['type'])),0),item['stack'])
    targets=[e.get('target',{}) for e in hb]
    score=reference_score(events,actions=receipts)
    return {'public_subset_score':score,'inventory_stack_maxima':maxima,
            'progress_families':sorted(set('wood' if m.startswith('wood_') else m for m in score['milestones'])),
            'deaths':sum(e.get('event')=='death' for e in events),
            'minimum_hp':min((e['life'] for e in hb),default=None),
            'damage_received':max((e.get('damage_received',0) for e in hb),default=0),
            'hits_received':max((e.get('hits_received',0) for e in hb),default=0),
            'max_hostile_npcs':max((e['hostile_npcs_active'] for e in hb),default=0),
            'hostile_observed_heartbeats':sum(e['hostile_npcs_active']>0 for e in hb),
            'target_killed':any(e.get('killed',False) for e in targets),
            'player_damage_to_target':max((e.get('player_damage',0) for e in targets),default=0),
            'game_updates_during_agent':max((e.get('game_updates',0) for e in events),default=start_tick)-start_tick,
            'input_hold_seconds':sum(r['action'].get('ms',100)/1000 for r in receipts),
            'journal_closed':any(e.get('event')=='end' for e in events)}


def snapshot_inputs(root,fixture):
    """Copy the immutable fixture and harness source into a new run; return their hashes."""
    shutil.copytree(fixture,root/'tml',ignore=shutil.ignore_patterns('Logs','*.log','*.bak'))
    for folder in ('terrariabench','mod','configs','prompts'):
        shutil.copytree(ROOT/folder,root/'source'/folder,ignore=shutil.ignore_patterns('__pycache__'))
    return ({str(p.relative_to(root/'source')):digest(p) for p in (root/'source').rglob('*') if p.is_file()},
            {str(p.relative_to(fixture)):digest(p) for p in fixture.rglob('*') if p.is_file()})


def model_pricing(model):
    """Worst-case per-token pricing across a model's documented overrides."""
    pricing=copy.deepcopy(model['pricing'])
    for override in pricing.get('overrides',[]):
        for k in ('prompt','completion','internal_reasoning','image','request'):
            if k in override:pricing[k]=str(max(Decimal(pricing.get(k,'0')),Decimal(override[k])))
    return pricing


def read_events(root):
    paths=list((root/'telemetry').glob('*.jsonl'))
    return [json.loads(s) for s in paths[0].read_text().splitlines()] if len(paths)==1 else []


def start_game(root,config,max_hold_ms,extra_env=None):
    """Launch the owned client, wait for telemetry, place the window and arm the scenario.

    Returns (pid, GameControl, scenario_ready). The combat barrier guarantees the first
    observation follows a heartbeat showing the live designated target."""
    env={'TERRARIABENCH_PROFILE':'reference-reconstructed-v1','TERRARIABENCH_PVE':'enabled' if config['pve'] else 'disabled',
         'TERRARIABENCH_REFERENCE_STARTER_PREFIXES':'plain','TERRARIABENCH_SCENARIO':config['scenario'],
         'TERRARIABENCH_SCENARIO_ARM':str(root/'scenario-armed'),
         'TERRARIABENCH_CHECKPOINT_CHAT':'enabled' if config.get('checkpoints') else 'disabled'}|(extra_env or {})
    pid=launch(root/'tml',root/'client.log',root/'telemetry',skipselect=True,width=1024,height=1024,
               config_updates={'UIScale':.9,'ResetDefaultUIScale':False,'Zoom':1.0},extra_env=env)
    dump(root/'game.json',{'pid':pid})
    game=None
    try:
        deadline=time.monotonic()+100
        while not read_events(root):
            if time.monotonic()>deadline or not Path(f'/proc/{pid}').exists():raise RuntimeError('startup_timeout')
            time.sleep(.5)
        game=GameControl(pid,root/'inputs.jsonl',width=1024,height=1024,max_hold_ms=max_hold_ms);game.setup_window()
        while not any(e['event']=='heartbeat' for e in read_events(root)):
            if time.monotonic()>deadline:raise RuntimeError('heartbeat_timeout')
            time.sleep(.1)
        scenario_ready=None
        armed=time.monotonic();(root/'scenario-armed').write_text(str(time.time()))
        if config['scenario']=='slime':
            # Barrier: never show the agent a first frame captured before the target exists.
            while (ready:=target_ready(read_events(root))) is None:
                if time.monotonic()-armed>5:raise RuntimeError('scenario_ready_timeout')
                time.sleep(.05)
            time.sleep(RENDER_SETTLE_SECONDS)
            scenario_ready={'ready_heartbeat_game_updates':ready['game_updates'],'target':ready['target'],
                            'arm_to_ready_wall_seconds':time.monotonic()-armed,'render_settle_seconds':RENDER_SETTLE_SECONDS}
    except BaseException:
        # The caller never receives the pid on failure; never leave an orphaned client behind.
        stop_game(root,pid,game)
        raise
    return pid,game,scenario_ready


def stop_game(root,pid,game):
    if game:game.close()
    # Finish a heartbeat before terminating; exclude this observation tail from claims of exact stepping.
    if pid and Path(f'/proc/{pid}').exists():
        time.sleep(1.05)
        dump(root/'termination.json',stop_owned_game(pid,root/'tml'))


def run(args):
    config=DEFAULT|VARIANTS[args.variant]
    config.update(scenario=args.scenario,reasoning=args.reasoning)
    if args.clock:config['clock']=args.clock
    if args.goal:config['goal']=args.goal
    if args.guide:config['guide']=True
    if args.calls<1 or args.calls>256 or not 0<args.usd<=1 or not 1<=args.seconds<=1800:raise ValueError('invalid experiment bounds')
    root=args.output.resolve();fixture=args.fixture.resolve()
    if root.exists() or root.is_relative_to(fixture):raise ValueError('new output outside fixture required')
    if config['scenario']=='slime' and not config['pve']:raise ValueError('combat task requires enemies')
    ledger=Ledger(args.campaign)
    catalog=request('/models')['data'];model=next(m for m in catalog if m['id']==args.model)
    if 'image' not in model['architecture']['input_modalities']:raise ValueError('vision model required')
    required={'max_tokens', 'tools' if config['scaffold']=='tools' else 'response_format'}
    if not required<=set(model['supported_parameters']):raise ValueError('unsupported request controls')
    budget=Budget(args.usd,model_pricing(model),input_ceiling=65536,output_ceiling=4096)
    key=hermes_key();root.mkdir(parents=True)
    source_hashes,fixture_hashes=snapshot_inputs(root,fixture)
    task=prompt_for(config);tools=tools_for(config)
    manifest={'protocol':'diagnostic-v1','config':config,'task_prompt':task,'system_prompt':SYSTEM,
              'tools':tools,'model':model,'reservation_pricing':model_pricing(model),
              'limits':{'calls':args.calls,'wall_seconds':args.seconds,'simulation_seconds':args.sim_seconds,'usd':args.usd},
              'source_hashes':source_hashes,'fixture_hashes':fixture_hashes,
              'retry_policy':RETRY_POLICY,'official_eligible':False,'started_unix':time.time()}
    dump(root/'manifest.json',manifest)
    history=[{'role':'system','content':SYSTEM},{'role':'user','content':task}]
    images={};frame_count=calls=invalid=retries=0;notes='';recent=[];latencies=[];start_tick=0
    pid=game=clock=None;stop='startup';started=time.monotonic();agent_started=None;scenario_ready=None
    def events():return read_events(root)
    def observe():
        nonlocal frame_count
        clock.set(False)
        if config['clock']=='paused':time.sleep(.08)
        p=root/'frames'/f'{frame_count:05d}.png';meta=game.capture(p);frame_count+=1
        clock.set(True)
        url='data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()
        images[url]={'artifact':str(p.relative_to(root)),'sha256':digest(p),'capture':meta}
        return {'role':'user','content':[{'type':'text','text':'Current game screenshot:'},{'type':'image_url','image_url':{'url':url}}]}
    def archive(payload):
        result=copy.deepcopy(payload)
        for msg in result['messages']:
            if isinstance(msg.get('content'),list):
                for part in msg['content']:
                    if part.get('type')=='image_url':part['image_url']=images[part['image_url']['url']]
        return result
    def dispatch(actions):
        actions=pixel_actions(actions,config)
        projected=sum(a.get('ms',100)/1000+.15 for a in actions)+.5
        if agent_started and time.monotonic()-agent_started+projected>args.seconds:
            raise TimeoutError('wall_limit_before_batch')
        ticks=max((e['game_updates'] for e in events()),default=start_tick)-start_tick
        if ticks+projected*60>args.sim_seconds*60:
            raise TimeoutError('simulation_limit_before_batch')
        clock.set(False)
        if config['clock']=='paused':time.sleep(.04)
        try:return game.act(actions)
        finally:
            if config['clock']=='paused':time.sleep(.08)
            clock.set(True)
    try:
        pid,game,scenario_ready=start_game(root,config,config['hold_ms'])
        clock=ProcessClock(pid,config['clock']=='paused',root/'clock.jsonl')
        history.append(observe());agent_started=time.monotonic()
        start_tick=max(e['game_updates'] for e in events());stop='call_limit'
        for step in range(args.calls):
            elapsed=time.monotonic()-agent_started
            tick=max(e['game_updates'] for e in events())-start_tick
            if elapsed>=args.seconds or tick>=args.sim_seconds*60:stop='wall_or_simulation_limit';break
            if config['scaffold']=='json' and config['history']=='notes4':
                payload_messages=history[:2]+[{'role':'user','content':json.dumps({'notes':notes,'last_action_results':recent[-4:]})},history[-1]]
            else:payload_messages=history
            payload={'model':args.model,'messages':payload_messages,'max_tokens':4096,'stream':False,
                     'reasoning':{'effort':config['reasoning']},'provider':{'allow_fallbacks':False,'require_parameters':True}}
            if config['scaffold']=='tools':payload.update(tools=tools,tool_choice='auto')
            else:payload['response_format']={'type':'json_object'}
            dump(root/f'request-{step:03d}.json',archive(payload))
            calls+=1;attempt=0
            while True:
                budget.reserve();charge_key=f'{root.name}#{step:03d}.{attempt}'
                try:ledger.change(charge_key,reserve=budget.reservation)
                except Exception:
                    budget.pending=Decimal(0);raise
                t0=time.monotonic()
                try:
                    response=request('/chat/completions',key=key,payload=payload,timeout=min(90,max(1,args.seconds-(time.monotonic()-agent_started))))
                    break
                except ProviderError as error:
                    budget.abandon();dump(root/'accounting.json',budget.summary())
                    wait=retry_delay(error,attempt)
                    retry=(error.retryable and attempt<RETRY_POLICY['max_retries_per_call'] and retries<RETRY_POLICY['max_retries_per_run']
                           and time.monotonic()-agent_started+wait<args.seconds)
                    with (root/'provider-failures.jsonl').open('a') as s:
                        s.write(json.dumps({'step':step,'attempt':attempt,'error':str(error),'retryable':error.retryable,'will_retry':retry,
                                            'wait_seconds':wait,'attempt_seconds':time.monotonic()-t0,'uncertain_usd':str(budget.reservation),'unix':time.time()})+'\n')
                    if not retry:raise
                    retries+=1;attempt+=1;time.sleep(wait)
            latency=time.monotonic()-t0;latencies.append(latency)
            dump(root/f'response-{step:03d}.json',response)
            usage=response.get('usage')
            # Reconcile both journals even when usage exceeds a local assumption.
            try:budget.reconcile(usage)
            finally:
                if usage and usage.get('cost') is not None:ledger.change(charge_key,charge=Budget.decimal(usage['cost']))
                dump(root/'accounting.json',budget.summary())
            if response.get('model')!=args.model:raise RuntimeError('returned_model_mismatch')
            message=response['choices'][0]['message'];history.append(copy.deepcopy(message))
            if response['choices'][0].get('finish_reason')=='length':invalid+=1
            if config['scaffold']=='json':
                try:
                    body=json.loads(message.get('content') or '')
                    if set(body)!={'notes','actions'} or not isinstance(body['notes'],str) or len(body['notes'])>2000:raise ValueError('expected notes and actions; notes max 2000 characters')
                    receipts=dispatch(body['actions']);notes=body['notes']
                    outcome={'dispatched_commands':len(receipts),'actions':body['actions']}
                except (ValueError,TypeError,KeyError) as error:
                    invalid+=1;outcome={'error':str(error),'nothing_dispatched':True}
                recent.append(outcome);history.append({'role':'user','content':json.dumps(outcome)});history.append(observe())
                with (root/'tool-results.jsonl').open('a') as s:s.write(json.dumps({'step':step,'name':'json','result':outcome})+'\n')
            else:
                toolcalls=message.get('tool_calls') or []
                if not toolcalls:stop='agent_stopped_without_tool';break
                next_images=[]
                for call in toolcalls:
                    name=call['function']['name']
                    try:
                        p=json.loads(call['function']['arguments'])
                        if not isinstance(p,dict):raise ValueError('arguments must be object')
                        if name=='act' and set(p)=={'actions'}:
                            receipts=dispatch(p['actions']);outcome={'dispatched_commands':len(receipts)}
                        elif name=='look' and not p:next_images.append(observe());outcome={'image_follows':True}
                        elif name=='checkpoints' and config['checkpoints'] and not p:outcome={'events':checkpoint_view(events())}
                        elif name=='inventory' and config['inventory'] and not p:
                            heartbeat=[e for e in events() if e['event']=='heartbeat']
                            e=heartbeat[-1];outcome={k:e[k] for k in ('inventory','life','dead','game_updates')}
                        elif name=='use_item' and config['motor'] and set(p)=={'slot','x','y','ms'}:
                            if type(p['slot']) is not int or not 1<=p['slot']<=10:raise ValueError('invalid slot')
                            actions=[{'keys':[str(p['slot']%10)],'ms':50},{'x':p['x'],'y':p['y'],'mouse':'left','ms':p['ms']}]
                            receipts=dispatch(actions);outcome={'dispatched_commands':len(receipts),'macro':'select_then_hold_no_feedback'}
                        else:raise ValueError('unknown tool or arguments')
                    except (ValueError,TypeError,KeyError) as error:invalid+=1;outcome={'error':str(error),'nothing_dispatched':True}
                    history.append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(outcome)})
                    with (root/'tool-results.jsonl').open('a') as s:s.write(json.dumps({'step':step,'call_id':call['id'],'name':name,'result':outcome,'unix':time.time()})+'\n')
                history.extend(next_images)
            if invalid>=3:stop='invalid_output_limit';break
            print(json.dumps({'run':root.name,'call':calls,'usd':str(budget.spent),'latency':round(latency,2)}),flush=True)
        clock.set(False);time.sleep(.15);game.capture(root/'final.png')
    except Exception as error:
        stop=type(error).__name__+': '+str(error).replace(key,'[redacted]')
    finally:
        agent_seconds=time.monotonic()-agent_started if agent_started else 0
        frozen_seconds=clock.total() if clock else 0
        if clock:clock.set(False)
        stop_game(root,pid,game)
        ev=events();receipts=[json.loads(s) for s in (root/'inputs.jsonl').read_text().splitlines()] if (root/'inputs.jsonl').exists() else []
        dump(root/'evaluation-events.json',ev);dump(root/'accounting.json',budget.summary())
        result={'run':root.name,'config':config,'model':args.model,'stop_reason':stop,'calls':calls,'provider_retries':retries,
                'scenario_ready':scenario_ready,'commands':len(receipts),
                'frames':frame_count,'invalid_outputs':invalid,'agent_wall_seconds':agent_seconds,'paused_seconds':frozen_seconds,
                'inference_seconds':sum(latencies),'latencies':latencies,'accounting':budget.summary(),'metrics':metrics(ev,receipts,start_tick),
                'official_eligible':False,'exact_simulation_stepper':False,'observation_and_cleanup_windows_advance_game':True}
        dump(root/'result.json',result)
        frames=''.join(f'<a href="frames/{p.name}"><img width="420" src="frames/{p.name}" loading="lazy"></a>' for p in sorted((root/'frames').glob('*.png')))
        responses=''.join('<details><summary>'+p.name+'</summary><pre>'+html.escape(p.read_text())+'</pre></details>' for p in sorted(root.glob('response-*.json')))
        (root/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>'+root.name+'</title><style>body{background:#141a18;color:#eee;font:15px system-ui;margin:30px}pre{white-space:pre-wrap;overflow-wrap:anywhere}img{margin:5px}</style><h1>'+root.name+'</h1><pre>'+html.escape(json.dumps(result,indent=2))+'</pre>'+frames+responses)
        print(json.dumps(result),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--campaign',type=Path,required=True);p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--model',required=True)
    p.add_argument('--variant',choices=VARIANTS,default='tools');p.add_argument('--scenario',choices=['fresh','crafting','slime'],default='fresh')
    p.add_argument('--clock',choices=['realtime','paused']);p.add_argument('--goal',choices=['open','workbench'])
    p.add_argument('--guide',action='store_true');p.add_argument('--reasoning',choices=['none','low','medium','high'],default='medium')
    p.add_argument('--calls',type=int,default=16);p.add_argument('--seconds',type=int,default=300);p.add_argument('--sim-seconds',type=int,default=120)
    p.add_argument('--usd',type=float,default=.35)
    run(p.parse_args())

if __name__=='__main__':main()
