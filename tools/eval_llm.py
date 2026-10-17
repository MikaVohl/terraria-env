"""Plan/run/verify a budgeted symbolic agent evaluation against an explicit game.

No network or secret access unless run + --allow-api + provider=openrouter.
"""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("plan", "run", "verify"), default="plan")
    parser.add_argument("--environment-root", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--allow-api", action="store_true")
    parser.add_argument("--ssh-key-source", help="Explicit SSH login whose Hermes OpenRouter key is read into memory only")
    args = parser.parse_args()
    root = args.environment_root.resolve()
    libs = [root / "python/terraria_lite" / ("libterraria." + ext) for ext in ("dylib", "so", "dll")]
    library = next((p for p in libs if p.is_file()), None)
    if library is None:
        parser.error("Build the chosen environment library before evaluating")
    os.environ["TERRARIA_LITE_LIB"] = str(library)
    from terraria_lite.llm_bench import config, provenance, run, verify
    if args.mode == "verify":
        if not args.out or args.allow_api or args.ssh_key_source:
            parser.error("Verify requires --out and never permits API/credential access")
        print(json.dumps(verify(args.out, root), indent=2))
        return
    if not args.config:
        parser.error("Plan/run requires --config")
    c = config(json.loads(args.config.read_text()))
    if args.mode == "plan":
        if args.allow_api or args.ssh_key_source:
            parser.error("Planning never permits API/credential access")
        print(json.dumps({"config": c, "provenance": provenance(root),
                          "episodes": len(c["seeds"])*c["replicates"], "api_calls": 0}, indent=2))
        return
    if not args.out:
        parser.error("Run requires a fresh --out directory")
    key, source = None, None
    if args.ssh_key_source:
        if not args.allow_api or c["provider"] != "openrouter":
            parser.error("SSH credentials require an explicitly enabled OpenRouter run")
        from terraria_lite.llm_providers import hermes_key
        key, source = hermes_key(args.ssh_key_source)
        print("OpenRouter credential loaded into memory; value suppressed", flush=True)
    summary = run(c, root, args.out, allow_api=args.allow_api, key=key, credential_source=source)
    print(json.dumps({k:v for k,v in summary.items() if k != "episodes"}, indent=2))
    if summary["complete"]:
        print(json.dumps(verify(args.out, root), indent=2))
    else:
        raise SystemExit("Incomplete evaluation preserved; do not silently retry")


if __name__ == "__main__":
    main()
