"""Development session: start a TerraBot game (test mode, no recording) and keep it up until <run>/STOP exists.
Ad-hoc scripts connect with TB_SOCKET=<run>/agent.sock. Never used for scored runs.

    python tools/terrabot/dev_session.py --fixture runs/terrabot-fixtures/tb-41100101 --run runs/terrabot-dev-01
"""
import argparse
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from session import Session  # noqa: E402

p = argparse.ArgumentParser()
p.add_argument("--fixture", required=True)
p.add_argument("--run", required=True)
p.add_argument("--display", default=":15")
p.add_argument("--output", default="HEADLESS-24")
a = p.parse_args()
s = Session(a.run, a.fixture, display=a.display, output=a.output, test_mode=True, record=False,
            manifest={"agent_kind": "dev", "purpose": "interactive development"}).start()
try:
    while not (s.run / "STOP").exists():
        time.sleep(1)
finally:
    s.stop({"kind": "dev"})
