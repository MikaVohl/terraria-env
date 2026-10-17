import json
from pathlib import Path
import re
import unittest

from terrariabench.linux_control import validate_actions
from terrariabench.reference_live import TOOLS
from terrariabench.reference_scoring import REFERENCE_LEVELS, checkpoint_view, reference_score, score_published_result


class ReferenceTests(unittest.TestCase):
    def test_wood_score_matches_published_example(self):
        events = [{"milestone": m, "category": "progress", "agent_driven": True}
                  for m in ("wood_1", "wood_10", "wood_25", "wood_100")]
        result = reference_score(events + [{"milestone": "held_axe", "category": "non_scoring"}])
        self.assertEqual(result["agency_score"], 4)
        self.assertEqual(result["level_counts"], {"1": 2, "2": 2, "3": 0, "4": 0, "5": 0})
        self.assertEqual(reference_score(events, direct_tile_control=True)["agency_score"], 0)

    def test_inherited_idle_diagnostics_and_duplicate_facts_do_not_score(self):
        events = [{"event": "start", "baseline": ["wood_25"]},
                  {"milestone": "wood_25", "agent_driven": True},
                  {"milestone": "wood_10", "agent_driven": False},
                  {"milestone": "wood_1", "agent_driven": True},
                  {"milestone": "wood_1", "agent_driven": True}]
        self.assertEqual(reference_score(events)["agency_score"], 1)

    def test_action_backing_and_checkpoint_visibility(self):
        events = [{"event": "checkpoint", "milestone": "wood_1", "unix_seconds": 2, "category": "progress"},
                  {"event": "heartbeat", "inventory": ["private"], "position": [1, 2]}]
        self.assertEqual(reference_score(events, actions=[])["agency_score"], 0)
        self.assertEqual(reference_score(events, actions=[{"actor": "agent", "started_unix": 1}])["agency_score"], 1)
        view = checkpoint_view(events)
        self.assertEqual(len(view), 1)
        self.assertNotIn("inventory", str(view))
        self.assertNotIn("position", str(view))

    def test_reference_viewport_bounds_are_separate_from_legacy_smoke(self):
        action = [{"x": 1023, "y": 1023, "ms": 2000}]
        validate_actions(action, width=1024, height=1024, max_hold_ms=2000)
        with self.assertRaises(ValueError):
            validate_actions(action)
        with self.assertRaises(ValueError):
            validate_actions([{"x": 1024, "y": 0}], width=1024, height=1024)

    def test_reference_tools_have_no_gameplay_helpers(self):
        self.assertEqual({t["function"]["name"] for t in TOOLS}, {"look", "act", "checkpoints"})

    def test_reference_mod_catalog_agrees(self):
        root = Path(__file__).resolve().parents[1]
        source = (root/"mod/TerrariaBenchObserver/ReferenceMode.cs").read_text().split("return new Dictionary<string, bool> {")[1]
        self.assertEqual(set(re.findall(r'\["([a-z_0-9]+)"\]', source)), set(REFERENCE_LEVELS))

    def test_all_archived_published_scores(self):
        path = Path(__file__).resolve().parents[1]/"reference/evidence.json"
        if not path.exists():
            self.skipTest("public evidence snapshot not fetched")
        runs = json.loads(path.read_text())["published_runs"]
        self.assertEqual(len(runs), 7)
        for run in runs:
            metrics = {k: run[k] for k in ("scoring_checkpoints", "direct_tile_control_used", "stalled")}
            with self.subTest(model=run["model"]):
                self.assertEqual(score_published_result({"score_metrics": metrics})["agency_score"], run["expected_agency_score"])
