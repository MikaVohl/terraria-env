"""Print the iterate_ppo.py argv of an explore_screen arm (PACKAGE + layout + arm flags), one per line.

    python perf/v10/arm_argv.py v10_shaped_g9999 gpu
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import explore_screen as es  # noqa: E402

arm, layout = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "gpu")
print("\n".join([*es.PACKAGE, *es.LAYOUTS[layout], *es.ARMS[arm]]))
