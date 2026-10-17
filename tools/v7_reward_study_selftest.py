"""Pure protocol/statistics regression checks; never train or evaluate policies."""
from pathlib import Path
import tempfile
from unittest.mock import patch

import v7_reward_study as study


def main():
    assert len(study.CELLS) == len(study.SEEDS) == 5
    assert study.STEPS * 25 == 419430400
    interval = study.interval([-2, -1, 0, 1, 2])
    assert interval["mean"] == 0
    assert abs(interval["interval"][1] - 2.7764451051977987 / 2**.5) < 1e-10
    wide = study.interval([-2, -1, 0, 1, 2], .99375)
    assert wide["interval"][1] > interval["interval"][1]
    values = dict(zip(study.CELLS, [10, 12, 15, 16, 21]))
    assert study.contrasts(values) == {"v7_equal_minus_v4": 2, "discount_main_effect": 4,
                                       "weight_main_effect": 5, "interaction": 2}
    with tempfile.TemporaryDirectory(prefix="terraria-v7-study-test-") as directory:
        root = Path(directory)
        study.write(root / "guard.json", {"fixture": True}, exclusive=True)
        try:
            study.write(root / "guard.json", {"fixture": False}, exclusive=True)
        except FileExistsError:
            pass
        else:
            raise AssertionError("Exclusive study guard overwritten")
        study.write(root / "study-protocol.json", {})
        study.write(root / "started.json", {"fixture": True})
        with patch.object(study, "verify_sources"), patch.object(study.subprocess, "Popen") as launch:
            try:
                study.run(root)
            except FileExistsError:
                pass
            else:
                raise AssertionError("A started study was relaunched")
            launch.assert_not_called()
        command = study.command(root, "v7-difficulty-g1", 801)
        assert command[command.index("--validation-seed-start")+1] == "17000001"
        assert command[command.index("--test-seed-start")+1] == "19000001"
        assert command[command.index("--steps")+1] == "16777216"
        assert command[command.index("--achievement-reward")+1] == "difficulty"
    print("Study tests passed: factorial contrasts, df4 intervals, adjusted bounds, exclusive guards and fresh validation commands; no experiments run")


if __name__ == "__main__":
    main()
