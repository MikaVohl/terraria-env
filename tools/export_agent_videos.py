"""Two same-seed MP4 replays; no API calls, no training or best-of sampling."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment-root',type=Path,required=True)
    parser.add_argument('--policy',type=Path,required=True)
    parser.add_argument('--llm-tape',type=Path,required=True)
    parser.add_argument('--llm-result',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    envroot=args.environment_root.resolve();out=args.out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    os.environ['TERRARIA_LITE_LIB']=str(envroot/'python/terraria_lite/libterraria.dylib')
    sys.path.insert(0,str(envroot/'python'))
    import numpy as np
    import torch
    from terraria_lite import SPEC,TerrariaLite
    from terraria_lite.watch import _load,rollout,write_tape
    result=json.loads(args.llm_result.read_text());seed=result['seed']
    assert SPEC.version==7 and seed==31000010
    torch.set_num_threads(1);torch.manual_seed(12345);np.random.seed(12345)
    action_fn,kind=_load(args.policy)
    actions,info,died=rollout(action_fn,seed,False,3000)
    write_tape(out/'PPO.tape',seed,3000,'PPO sampled,16.8M transitions; first single rollout',actions)
    shutil.copy2(args.llm_tape,out/'Luna.tape')
    records={'Luna':{'info':result['native_info'],'source':str(args.llm_tape.resolve())},
             'PPO':{'info':info,'died':died,'checkpoint':str(args.policy.resolve()),'sampling_seed':12345,'best_of':1}}
    slow=set()
    for name in records:
        verified=subprocess.check_output([str(envroot/'terraria-px'),'--watch',str(out/(name+'.tape')),'--verify'],text=True)
        native=json.loads(verified.splitlines()[-1]);expected=records[name]['info']
        assert native['steps']==expected['steps'] and native['health']==expected['health'] and native['achievement_mask']==expected['achievement_mask']
        tape=(out/(name+'.tape')).read_text().splitlines();marker=next(i for i,x in enumerate(tape) if x.startswith('actions '));aa=list(map(int,tape[marker+1:]))
        env=TerrariaLite(max_steps=3000);env.reset(seed=seed);previous=0;first={}
        for a in aa:
            _,_,term,trunc,state=env.step(a)
            gained=state['achievement_mask']&~previous;previous=state['achievement_mask']
            for i,ach in enumerate(SPEC.achievement_names):
                if gained>>i&1:
                    first[ach]=state['steps']
                    if ach in ('craft furnace','craft anvil','smelt copper','smelt iron'):
                        slow.update(range(max(0,state['steps']-15),min(3000,state['steps']+25)))
        env.close();records[name]['first_achievement_steps']=first
        if expected['health']==0:slow.update(range(max(0,expected['steps']-25),min(3000,expected['steps']+10)))
    # Identical global action-time mapping in both exports. Natural death freezes
    # only that pane; the common action timeline continues to3000.
    schedule=[0]*45;position=0.0
    while position<3000:
        position=min(3000,position+(.5 if int(position) in slow else 2.0))
        schedule.append(int(position))
    schedule += [3000]*90
    (out/'schedule.txt').write_text(''.join(f'{s}\n' for s in schedule))
    repo=Path(__file__).resolve().parents[1]
    cflags=subprocess.check_output(['sdl2-config','--cflags'],text=True).split()
    libs=subprocess.check_output(['sdl2-config','--libs'],text=True).split()
    cmd=['cc','-std=c11','-O2','-Wno-unused-function','-Wno-unused-const-variable',
         '-I'+str(envroot/'include'),'-I'+str(envroot/'src'),'-I'+str(envroot/'third_party'),*cflags,
         '-DVIDEO_RENDER_SOURCE="'+str(envroot/'src/px_render.c')+'"',
         '-DVIDEO_MAIN_SOURCE="'+str(envroot/'src/px_main.c')+'"',str(repo/'tools/replay_video.c'),
         *[str(envroot/'src'/f) for f in ('sim.c','worldgen.c','light.c','obs.c')],'-o',str(out/'replay-video'),'-lm',*libs]
    subprocess.run(cmd,check=True)
    shutil.copy2(repo/'tools/replay_video.c',out/'replay_video.c')
    shutil.copy2(__file__,out/'export_agent_videos.py')
    for name in records:
        title='LUNA | HIGH REASONING' if name=='Luna' else 'PPO | TRAINED FROM SCRATCH'
        subtitle='Public recipes + notes | existing recorded episode | $0.408 API cost' if name=='Luna' else '16.8M training transitions | frozen v7 policy | one sampled rollout'
        video=out/(name+'_same_seed.mp4')
        render_env={**os.environ,'SDL_VIDEODRIVER':'dummy','SDL_RENDER_DRIVER':'software'}
        with (out/(name+'-render.log')).open('x') as log:
            render=subprocess.Popen([str(out/'replay-video'),str(out/(name+'.tape')),str(out/'schedule.txt'),title,subtitle],stdout=subprocess.PIPE,stderr=log,env=render_env)
            try:
                encode=subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-n','-f','rawvideo','-pixel_format','rgb24','-video_size','736x624','-framerate','30','-i','pipe:0','-vf','scale=1472:1248:flags=neighbor','-c:v','libx264','-preset','fast','-crf','18','-threads','2','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],stdin=render.stdout)
                render.stdout.close();rc=render.wait()
                assert encode.returncode==0 and rc==0,(name,rc,encode.returncode)
            finally:
                if render.poll() is None:render.terminate();render.wait()
        final_line=next(s for s in (out/(name+'-render.log')).read_text().splitlines() if s.startswith('VIDEO_FINAL '))
        final=json.loads(final_line.split(' ',1)[1]);expected=records[name]['info']
        assert all(final[k]==expected[k] for k in ('steps','health','achievement_mask'))
        assert final['frames']==len(schedule)
        records[name]['video_sha256']=sha(video)
        records[name]['video']=str(video)
        records[name]['tape_sha256']=sha(out/(name+'.tape'))
    manifest={'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'seed':seed,'environment_version':SPEC.version,
              'api_calls':0,'training_runs':0,'records':records,'duration_seconds':len(schedule)/30,
              'pacing':'Identical action timeline.60 actions/s normally;15 actions/s near crafting milestones and deaths;1.5s opening,3s ending. Episode state freezes after termination.',
              'native_library_sha256':sha(envroot/'python/terraria_lite/libterraria.dylib'),
              'checkpoint_sha256':sha(args.policy),'schedule_sha256':sha(out/'schedule.txt'),
              'renderer_sources':{str(p.relative_to(envroot)):sha(p) for folder in ('src','include') for p in (envroot/folder).glob('*') if p.suffix in ('.c','.h')},
              'illustrative_only':True}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
