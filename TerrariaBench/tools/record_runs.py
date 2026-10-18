"""Record the whole desktop for every run that starts, into <run>/desktop.mp4. Passive and unattended.

Uses live_panel.active_run() to find the run whose owned game is alive; starts record_desktop.py
for it and stops when the run writes result.json or its game exits.
"""
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from live_panel import active_run  # noqa: E402
from terrariabench.linux_control import desktop_environment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def main():
    fps = sys.argv[1] if len(sys.argv) > 1 else "15"
    current = recorder = None
    while True:
        run = active_run()
        if recorder and (run != current or (current / "result.json").exists()):
            recorder.send_signal(2)  # SIGINT: finalize the MP4
            recorder.wait(timeout=60)
            # Start each video on a clean desktop (Omarchy shell IPC; harmless if unavailable).
            subprocess.run(["qs", "ipc", "-n", "-p", "/usr/share/omarchy/shell", "call", "notifications", "dismissAll"],
                           env=desktop_environment(), capture_output=True, timeout=5)
            print(f"stopped {current}", flush=True)
            recorder = current = None
        if run and recorder is None and not (run / "desktop.mp4").exists():
            current = run
            recorder = subprocess.Popen([str(ROOT / ".venv/bin/python"), str(ROOT / "tools/record_desktop.py"),
                                         str(run / "desktop.mp4"), "--fps", fps, "--until-file", str(run / "result.json")])
            print(f"recording {run}", flush=True)
        time.sleep(1)


if __name__ == "__main__":
    main()
