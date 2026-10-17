"""Unpaid operator input/hit/kill positive control, never a model benchmark run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from terrariabench.experiments import dump
from terrariabench.linux_control import GameControl, launch


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--fixture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();root=a.output.resolve()
    if root.exists() or root.is_relative_to(a.fixture.resolve()):raise ValueError('new output outside fixture required')
    for proc in Path('/proc').glob('[0-9]*/cmdline'):
        try:argv=proc.read_bytes().split(b'\0')
        except (OSError,PermissionError):continue
        if len(argv)>1 and argv[0].endswith(b'/dotnet') and argv[1]==b'tModLoader.dll':
            raise RuntimeError('graphical worker is busy; do not overlap calibration')
    root.mkdir(parents=True)
    shutil.copytree(a.fixture,root/'tml',ignore=shutil.ignore_patterns('Logs','*.log','*.bak'))
    dump(root/'manifest.json',{'kind':'operator_calibration','model_run':False,
         'description':'Stationary alternating shortsword clicks through real OS inputs; private telemetry only checks completion.',
         'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         'fixture_hashes':{str(f.relative_to(a.fixture)):hashlib.sha256(f.read_bytes()).hexdigest() for f in a.fixture.rglob('*') if f.is_file()}})
    pid=game=None
    def events():
        return [json.loads(s) for f in (root/'telemetry').glob('*.jsonl') for s in f.read_text().splitlines()]
    try:
        pid=launch(root/'tml',root/'client.log',root/'telemetry',skipselect=True,width=1024,height=1024,
             config_updates={'UIScale':.9,'ResetDefaultUIScale':False,'Zoom':1.0},
             extra_env={'TERRARIABENCH_PROFILE':'reference-reconstructed-v1','TERRARIABENCH_PVE':'enabled',
                        'TERRARIABENCH_REFERENCE_STARTER_PREFIXES':'plain','TERRARIABENCH_SCENARIO':'slime',
                        'TERRARIABENCH_SCENARIO_ARM':str(root/'scenario-armed'),'TERRARIABENCH_CHECKPOINT_CHAT':'disabled'})
        deadline=time.monotonic()+100
        while not any(e['event']=='heartbeat' for e in events()):
            if time.monotonic()>deadline:raise TimeoutError('startup')
            time.sleep(.2)
        game=GameControl(pid,root/'inputs.jsonl',width=1024,height=1024,max_hold_ms=2000);game.setup_window()
        (root/'scenario-armed').write_text(str(time.time()))
        while not any(e.get('target',{}).get('slot',-1)>=0 for e in events()):
            if time.monotonic()>deadline:raise TimeoutError('scenario readiness')
            time.sleep(.1)
        game.capture(root/'initial.png')
        game.act([{'keys':['1'],'ms':50}],actor='operator_calibration')
        deadline=time.monotonic()+100;step=0
        while time.monotonic()<deadline:
            if any(e.get('target',{}).get('killed',False) for e in events()):break
            x=550 if step%2==0 else 475
            game.act([{'x':x,'y':522,'mouse':'left','ms':160},{'ms':100}],actor='operator_calibration')
            step+=1
            if step%20==0:game.capture(root/f'frame-{step:03d}.png')
        game.capture(root/'final.png')
    finally:
        if game:game.close()
        if pid:
            time.sleep(1.05)
            cmd=Path(f'/proc/{pid}/cmdline')
            if cmd.exists() and str(root/'tml').encode() in cmd.read_bytes():os.killpg(pid,signal.SIGTERM)
        ev=events();targets=[e['target'] for e in ev if 'target' in e]
        killed=any(t['killed'] for t in targets)
        damage=max((t['player_damage'] for t in targets),default=0)
        receipts=[json.loads(s) for s in (root/'inputs.jsonl').read_text().splitlines()] if (root/'inputs.jsonl').exists() else []
        dump(root/'evaluation-events.json',ev)
        result={'kind':'operator_calibration','model_run':False,'target_killed':killed,
                'player_damage':damage,'commands':len(receipts),
                'all_inputs_operator_labeled':bool(receipts) and all(r['actor']=='operator_calibration' for r in receipts),
                'validation_passed':killed and damage>0,'api_cost_usd':'0'}
        dump(root/'result.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':main()
