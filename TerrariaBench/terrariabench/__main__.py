import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path

from .catalog import CATALOG_VERSION
from .scoring import JournalError, read_journal, score


def doctor(steam_common):
    root = Path(steam_common).expanduser()
    tml = root / "tModLoader"
    dll = tml / "tModLoader.dll"
    return {
        "terraria_found": (root / "Terraria").is_dir(),
        "tmodloader_found": dll.is_file(),
        "tmodloader_path": str(tml),
        "tmodloader_sha256": hashlib.sha256(dll.read_bytes()).hexdigest() if dll.is_file() else None,
        "python": sys.version.split()[0],
        "development_runner_present": True,
        "official_runner_ready": False,
        "next_gate": "Audit full-game event attribution, stability and multiworld evaluation.",
    }


def demo(destination):
    """Generate explicit synthetic data; never launch a game or call a model."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    journal = destination / "events.jsonl"
    run_id = "synthetic-" + uuid.uuid4().hex
    common = {"schema": 1, "source": "TerrariaBenchObserver", "run_id": run_id}
    events = [
        {"event": "session_start", "tick": 0, "elapsed_seconds": 0,
         "catalog": CATALOG_VERSION, "baseline": [], "synthetic": True},
        {"event": "checkpoint", "tick": 600, "elapsed_seconds": 10, "milestone": "wood_25"},
        {"event": "checkpoint", "tick": 900, "elapsed_seconds": 15, "milestone": "possess_workbench"},
        {"event": "death", "tick": 1200, "elapsed_seconds": 20},
        {"event": "session_end", "tick": 1800, "elapsed_seconds": 30},
    ]
    # Exclusive creation protects existing results from accidental replacement.
    with journal.open("x") as stream:
        for event in events:
            stream.write(json.dumps(common | event) + "\n")
    result = score(read_journal(journal))
    (destination / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        from .reference_live import main as reference_main
        sys.argv = [sys.argv[0]] + sys.argv[2:]
        reference_main()
        return
    parser = argparse.ArgumentParser(description="TerrariaBench tools. Use 'run --help' for the reconstructed-reference baseline.")
    commands = parser.add_subparsers(dest="command", required=True)
    inspect = commands.add_parser("doctor", help="Read-only local installation check")
    steam = Path.home() / ("Library/Application Support/Steam/steamapps/common" if sys.platform == "darwin" else ".local/share/Steam/steamapps/common")
    inspect.add_argument("--steam-common", default=str(steam))
    example = commands.add_parser("demo", help="Generate and score a SYNTHETIC journal")
    example.add_argument("--output", type=Path, required=True)
    evaluate = commands.add_parser("score", help="Validate and score observer JSONL")
    evaluate.add_argument("journal", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "doctor":
            result = doctor(args.steam_common)
        elif args.command == "demo":
            result = demo(args.output)
        else:
            result = score(read_journal(args.journal))
    except (OSError, JournalError) as error:
        parser.exit(2, f"terrariabench: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
