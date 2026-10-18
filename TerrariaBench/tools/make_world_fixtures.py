"""Generate held-out small Classic world fixtures with the dedicated server.

Each fixture copies the base fixture (player, config, observer mod) and swaps in a
newly generated world. The server is asked to exit as soon as it reports start, so
the saved world has only seconds of unattended simulation and no player has entered.
Evil and spawn come from the seed; they are read back and recorded, not chosen.
"""
import argparse
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from terrariabench.worldfile import read_header  # noqa: E402

TML = Path.home() / ".local/share/Steam/steamapps/common/tModLoader"


def generate(seed, save_dir, log_path, port):
    world = save_dir / "Worlds/TBworld.wld"
    args = ["bash", "LaunchUtils/ScriptCaller.sh", "-server", "-tmlsavedirectory", str(save_dir),
            "-world", str(world), "-autocreate", "1", "-seed", str(seed), "-worldname", "TBworld",
            "-difficulty", "0", "-port", str(port), "-maxplayers", "1", "-password", secrets.token_hex(12)]
    started = time.monotonic()
    with log_path.open("w") as log:
        proc = subprocess.Popen(args, cwd=TML, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, start_new_session=True)
        ready_at = None
        for line in proc.stdout:
            log.write(line)
            if ready_at is None and "Server started" in line:
                ready_at = time.monotonic()
                proc.stdin.write("exit\n")
                proc.stdin.flush()
            if time.monotonic() - started > 600:
                proc.kill()
                raise RuntimeError(f"world generation timed out for seed {seed}")
        proc.wait()
    if ready_at is None or not world.exists():
        raise RuntimeError(f"server did not produce a world for seed {seed}; see {log_path}")
    return world, {"generation_seconds": ready_at - started, "server_exit_code": proc.returncode}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base", type=Path, required=True)
    p.add_argument("--out-root", type=Path, required=True)
    p.add_argument("--prefix", required=True)
    p.add_argument("seeds", nargs="+", type=int)
    args = p.parse_args()
    for index, seed in enumerate(args.seeds):
        target = args.out_root / f"{args.prefix}-{seed}"
        if target.exists():
            raise SystemExit(f"refusing to overwrite {target}")
        with tempfile.TemporaryDirectory(prefix="tbgen-") as tmp:
            save = Path(tmp)
            shutil.copytree(args.base / "Mods", save / "Mods")
            (save / "Worlds").mkdir()
            world, gen = generate(seed, save, save / "server.log", 7790 + index)
            header = read_header(world)
            if header["seed"] != str(seed) or (header["width_tiles"], header["height_tiles"]) != (4200, 1200) \
                    or header["game_mode"] != 0 or header["special_seed_flags"]:
                raise RuntimeError(f"unexpected generated world for seed {seed}: {header}")
            shutil.copytree(args.base, target, ignore=shutil.ignore_patterns("Worlds", "fixture.json"))
            (target / "Worlds").mkdir()
            for suffix in (".wld", ".twld"):
                shutil.copy2(world.with_suffix(suffix), target / "Worlds" / ("TBworld" + suffix))
            shutil.copy2(save / "server.log", target / "generation.log")
        fixture = {"seed": str(seed), "size": "small", "difficulty": "classic", "evil": header["evil"],
                   "created_via": "tModLoader dedicated server -autocreate; exit requested at server start",
                   "player_from_base_fixture": str(args.base), "entered_before_freeze": False,
                   "held_out": True, "world_header": header, "generation": gen}
        (target / "fixture.json").write_text(json.dumps(fixture, indent=2) + "\n")
        print(json.dumps({"fixture": str(target), "evil": header["evil"], "spawn_tile": header["spawn_tile"]}), flush=True)


if __name__ == "__main__":
    main()
