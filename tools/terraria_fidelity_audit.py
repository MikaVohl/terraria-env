"""Read core constants from a local Terraria assembly (optional dnfile/dncil).

uv run --no-project --with dnfile --with dncil python tools/terraria_fidelity_audit.py
No assets or proprietary code are written or redistributed.
"""
import argparse
from pathlib import Path
import dnfile
from dncil.cil.body import CilMethodBody
from dncil.cil.body.reader import CilMethodBodyReaderBytes


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--assembly",type=Path,default=Path.home()/"Library/Application Support/Steam/steamapps/common/Terraria/Terraria.app/Contents/Resources/Terraria.exe")
    a=p.parse_args(); pe=dnfile.dnPE(str(a.assembly))
    fields=pe.net.mdtables.Field.rows
    def field_name(operand):
        token=getattr(operand,"value",0)
        return str(fields[(token&0xffffff)-1].Name) if token>>24==4 else ""
    def integer(instruction):
        name=instruction.opcode.name
        if name.startswith("ldc.i4.") and name[7:] in [str(i) for i in range(9)]: return int(name[7:])
        if name in ("ldc.i4","ldc.i4.s"): return instruction.operand
        return None
    for cls in pe.net.mdtables.TypeDef.rows:
        if str(cls.TypeName) not in ("Main","Player"): continue
        for index in cls.MethodList:
            method=index.row
            if not method.Rva: continue
            try: body=CilMethodBody(CilMethodBodyReaderBytes(pe.get_data(method.Rva,2000000)))
            except Exception: continue
            ins=body.instructions
            for i,x in enumerate(ins):
                name=field_name(x.operand)
                if name in ("tileSolid","tileSolidTop","tileBlockLight") and x.opcode.name=="ldsfld" and i+3<len(ins):
                    tile,value=integer(ins[i+1]),integer(ins[i+2])
                    if tile in (5,16,17,18,19,21,30) and value is not None and ins[i+3].opcode.name.startswith("stelem"):
                        print(f"{cls.TypeName}.{method.Name}: {name}[{tile}]={value}")
                if name in ("width","height") and str(cls.TypeName)=="Player" and x.opcode.name=="stfld" and i>0:
                    value=integer(ins[i-1])
                    if value is not None: print(f"Player.{method.Name}: {name}={value}")


if __name__=="__main__": main()
