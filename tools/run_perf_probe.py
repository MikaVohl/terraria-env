"""Build isolated prototypes and run a bounded, sequential performance sweep."""
import json
import os
from pathlib import Path
import subprocess
import sys

out=Path(sys.argv[1]).resolve()
out.mkdir(parents=True,exist_ok=False)
common=['cc','-std=c11','-O2','-g','-fPIC','-Iinclude','-Isrc']
subprocess.run(common+['-Dlight_recompute=light_reference','-c','src/light.c','-o',str(out/'light-ref.o')],check=True)
for lib in ['reference','cached']:
    subprocess.run(common+['-shared']+(['-DPROBE_CACHE'] if lib=='cached' else [])+
        ['src/sim.c','src/worldgen.c','src/obs.c','src/capi.c','tools/perf_probe.c',str(out/'light-ref.o'),'-o',str(out/(lib+'.dylib'))],check=True)
jobs=[]
for workers in [1,4]:jobs.append(('cached',['--mode','check','--workers',str(workers)]))
for lib in ['reference','cached']:
    for n in [16,64,256]:
        for batch in [False,True]:
            jobs.append((lib,['--mode','vector','--envs',str(n),'--steps','32768']+(['--batch'] if batch else [])))
    for n in [16,256]:
        for w in [2,4]:jobs.append((lib,['--mode','vector','--envs',str(n),'--steps','32768','--batch','--workers',str(w)]))
for threads in [1,2,4,6,8]:
    jobs.append(('reference',['--mode','train','--threads',str(threads)]))
for lib in ['reference','cached']:
    for w in [1,4]:jobs.append((lib,['--mode','train','--batch','--workers',str(w),'--threads','2']))
for device in ['cpu','mps']:
    for n in [16,64,256]:
        jobs.append(('cached',['--mode','train','--batch','--workers','4','--threads','2','--envs',str(n),'--device',device]))
with (out/'results.jsonl').open('w',buffering=1) as f:
    for lib,args in jobs:
        env={**os.environ,'TERRARIA_LITE_LIB':str(out/(lib+'.dylib'))}
        try:
            r=subprocess.run([sys.executable,'tools/perf_probe.py',*args],env=env,capture_output=True,text=True,timeout=180)
            row={'library':lib,'args':args,'returncode':r.returncode,'stdout':r.stdout,'stderr':r.stderr}
            if r.returncode==0:row['measurement']=json.loads(r.stdout.splitlines()[-1])
        except subprocess.TimeoutExpired:
            row={'library':lib,'args':args,'error':'timeout after 180 seconds'}
        f.write(json.dumps(row)+'\n');print(json.dumps(row),flush=True)
