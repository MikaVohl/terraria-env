import copy
import re
import tempfile
import unittest
from pathlib import Path

from terrariabench.__main__ import demo
from terrariabench.catalog import CATALOG_VERSION, MILESTONES
from terrariabench.scoring import JournalError, read_journal, score


def journal():
    base = {"schema": 1, "run_id": "test", "source": "TerrariaBenchObserver"}
    return [base | entry for entry in [
        {"event": "session_start", "tick": 0, "elapsed_seconds": 0,
         "catalog": CATALOG_VERSION, "baseline": [], "synthetic": True},
        {"event": "checkpoint", "tick": 60, "elapsed_seconds": 1, "milestone": "wood_25"},
        {"event": "session_end", "tick": 120, "elapsed_seconds": 2},
    ]]


class ScoringTests(unittest.TestCase):
    def test_demo_round_trip_and_never_official(self):
        with tempfile.TemporaryDirectory() as root:
            result = demo(root)
            self.assertEqual(result["progress_count"], 2)
            self.assertEqual(result["deaths"], 1)
            self.assertFalse(result["official_eligible"])
            self.assertTrue(result["synthetic"])
            self.assertEqual(score(read_journal(Path(root) / "events.jsonl")), result)
            with self.assertRaises(FileExistsError):
                demo(root)

    def test_inherited_boss_cannot_be_counted(self):
        data = journal()
        data[0]["baseline"] = ["moon_lord"]
        data[1]["milestone"] = "moon_lord"
        with self.assertRaises(JournalError):
            score(data)

    def test_rejects_corrupt_or_spoofed_journals(self):
        mutations = [
            (1, "milestone", "invented"), (1, "source", "agent"),
            (1, "run_id", "other"), (1, "elapsed_seconds", float("nan")),
            (1, "tick", True), (1, "tick", -1),
            (2, "elapsed_seconds", 0), (0, "catalog", "other"),
            (0, "baseline", ["invented"]), (0, "synthetic", None),
            (1, "schema", True),
        ]
        for index, key, value in mutations:
            with self.subTest(key=key, value=value):
                data = journal()
                data[index][key] = value
                with self.assertRaises(JournalError):
                    score(data)

    def test_duplicate_and_post_end_events_rejected(self):
        data = journal()
        with self.assertRaises(JournalError):
            score(data[:2] + [copy.deepcopy(data[1])] + data[2:])
        with self.assertRaises(JournalError):
            score(data + [data[-1]])

    def test_truncated_run_keeps_progress_and_is_open(self):
        result = score(journal()[:-1])
        self.assertEqual(result["progress_count"], 1)
        self.assertFalse(result["journal_closed"])

    def test_moon_lord_is_distinct_from_other_progress(self):
        data = journal()
        data[1]["milestone"] = "moon_lord"
        self.assertTrue(score(data)["moon_lord_observed"])
        self.assertFalse(score(journal())["moon_lord_observed"])

    def test_heartbeat_updates_time_without_credit(self):
        data = journal()
        heartbeat = data[1] | {"event": "heartbeat", "tick": 100, "elapsed_seconds": 1.5}
        result = score(data[:2] + [heartbeat])
        self.assertEqual(result["progress_count"], 1)
        self.assertEqual(result["game_updates"], 100)
        self.assertEqual(result["elapsed_seconds"], 1.5)

    def test_mod_and_python_catalog_agree(self):
        source = Path(__file__).resolve().parents[1] / "mod/TerrariaBenchObserver/Observer.cs"
        facts = source.read_text().split("return new Dictionary<string, bool> {")[1]
        self.assertEqual(set(re.findall(r'\["([a-z_0-9]+)"\]', facts)), set(MILESTONES))

    def test_malformed_json_and_nonobjects(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "events.jsonl"
            for content in ("{broken\n", "[]\n", "null\n"):
                path.write_text(content)
                with self.assertRaises(JournalError):
                    read_journal(path)


if __name__ == "__main__":
    unittest.main()
