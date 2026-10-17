"""Isolated versioned core/batch timing with recorded raw samples and hashes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--roots",nargs="+",type=Path,required=True)
    a=p.parse_args(); rows=[]
    harness=Path(__file__).resolve().parent/"core_benchmark.c"
    for root in a.roots:
        root=root.resolve(); env=os.environ.copy();env["PYTHONPATH"]=str(root/"python");env.pop("TERRARIA_LITE_LIB",None)
        with tempfile.TemporaryDirectory(prefix="terraria-core-") as directory:
            binary=Path(directory)/"core"
            subprocess.run(["cc","-std=c11","-O2",f"-I{root/'include'}",f"-I{root/'src'}",str(harness),
                *[str(root/"src"/n) for n in ["sim.c","worldgen.c","light.c","obs.c"]],"-lm","-o",str(binary)],check=True)
            core=json.loads(subprocess.check_output([str(binary)],text=True))
        batch=json.loads(subprocess.check_output([sys.executable,str(harness.parent/"v2_benchmark.py"),
                "--steps","262144","--envs","64","--workers","4"],env=env,text=True))
        assert core["environment_version"]==batch["environment_version"]
        rows.append({"root":str(root),"core":core,"batch":batch,
            "core_source_sha256":{str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest()
                for f in [*root.glob("src/*.c"),*root.glob("include/*.h"),*root.glob("python/terraria_lite/libterraria.*")]}})
    result={"hardware":"Apple M5 Pro, 48 GiB, macOS","context":"No training jobs active; active desktop; three repeats, same harness/seed protocol. Cross-version workload differences are not exact optimization speedups.","measurements":rows}
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    for row in rows:print(f"{Path(row['root']).name}: v{row['core']['environment_version']} core={row['core']['median_sps']:,.0f}/s batch={row['batch']['median_sps']:,.0f}/s")


if __name__=="__main__": main()
