"""Audit local original art without copying or redistributing Terraria assets."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
from terraria_lite.rules import player_knowledge


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--textures",type=Path,default=Path.home()/"Library/Application Support/Steam/steamapps/common/Terraria/ExtractedTextures")
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    source=(root/"src/px_render.c").read_text()
    names=set(re.findall(r'"((?:Tiles_|Tree_|Player_|NPC_|Armor/)[A-Za-z0-9_/]+)"',source))
    rules=player_knowledge()
    names.update(f"Item_{i['terraria_id']}" for i in rules["items"]+rules["starting_equipment"])
    picks=re.search(r"static const int ids\[4\]=\{([^}]+)\}",source)
    names.update(f"Item_{int(i)}" for i in picks[1].split(","))
    assets=[]
    for name in sorted(names):
        path=a.textures/f"{name}.png"; data=path.read_bytes()
        assert data[:8]==b"\x89PNG\r\n\x1a\n" and data[12:16]==b"IHDR",path
        width,height=struct.unpack(">II",data[16:24])
        assets.append({"name":name,"width":width,"height":height,
                       "sha256":hashlib.sha256(data).hexdigest()})
    dimensions={r["name"]:(r["width"],r["height"]) for r in assets}
    assert dimensions["NPC_1"]==(32,52) and dimensions["NPC_49"]==(44,160)
    assert dimensions["Tiles_5"][0]>=20 and dimensions["Tiles_5"][1]>=64
    assembly=a.textures.parent/"Terraria.exe"
    if not assembly.exists(): assembly=a.textures.parent/"Terraria.app/Contents/Resources/Terraria.exe"
    result={"environment_version":rules["environment_version"],"textures":str(a.textures),
            "renderer_sha256":hashlib.sha256(source.encode()).hexdigest(),
            "assets":assets,"original_assembly_sha256":hashlib.sha256(assembly.read_bytes()).hexdigest() if assembly.exists() else None,
            "blue_slime_verified_local_il":{"SetDefaults_alpha":175,"SetDefaults_color_rgba":[0,80,255,100],
                "GetAlpha_daylight_rgba":[80,80,80,80],"GetColor_overlay_rgba":[0,80,255,100]},
            "note":"Hashes audit originals, not pixel equivalence of the simplified SDL renderer. IL constants were manually inspected; this script does not re-decompile them."}
    a.out.write_text(json.dumps(result,indent=2)+"\n")
    print(f"Audited {len(assets)} original PNGs; slime/bat sheet dimensions and forest trunk crops valid")


if __name__=="__main__": main()
