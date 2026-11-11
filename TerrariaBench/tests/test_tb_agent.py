"""Offline tests of the TerraBot agent loop helpers: reply parsing, ledger accounting, API reference rendering."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/terrabot"))
import agent  # noqa: E402


class ReplyParsing(unittest.TestCase):
    REPLY = """Plan: chop trees.
<notes>wood first</notes>
<file path="lib/util.py">```python
def f():
    return 1
```</file>
<program timeout="120" screenshot="yes">
import tb
print(tb.me().x)
</program>"""

    def test_program_files_notes(self):
        progs = agent.PROGRAM_RE.findall(self.REPLY)
        self.assertEqual(len(progs), 1)
        attrs, code = progs[0]
        self.assertIn('timeout="120"', attrs)
        self.assertIn("print(tb.me().x)", agent.strip_fence(code))
        files = agent.FILE_RE.findall(self.REPLY)
        self.assertEqual(files[0][0], "lib/util.py")
        self.assertEqual(agent.strip_fence(files[0][1]), "def f():\n    return 1")
        self.assertEqual(agent.NOTES_RE.search(self.REPLY).group(1), "wood first")

    def test_trim_keeps_head_and_tail(self):
        t = agent.trim("a" * 100 + "b" * 100, 60)
        self.assertTrue(t.startswith("a") and t.endswith("b") and "cut" in t)


class Ledger(unittest.TestCase):
    def test_open_reservations_count_as_spent(self):
        with tempfile.TemporaryDirectory() as d:
            agent.LEDGER = Path(d) / "ledger.jsonl"
            agent.ledger_write({"kind": "reserve", "call": "a", "usd": 0.5})
            agent.ledger_write({"kind": "settle", "call": "a", "usd": 0.1})
            agent.ledger_write({"kind": "reserve", "call": "b", "usd": 0.7})
            self.assertAlmostEqual(agent.ledger_spent(), 0.8)

    def test_budget_refuses_before_calling(self):
        with tempfile.TemporaryDirectory() as d:
            agent.LEDGER = Path(d) / "ledger.jsonl"
            agent.ledger_write({"kind": "settle", "call": "x", "usd": 9.99})
            m = agent.Model.__new__(agent.Model)
            m.model, m.run_name, m.run_cap, m.ledger_cap, m.spent, m.calls = "claude-opus-5-5", "t", 5, 10, 0, 0
            with self.assertRaises(agent.BudgetStop):
                m.call("system", [{"role": "user", "content": [{"type": "text", "text": "hi"}]}])
            self.assertEqual(len(agent.LEDGER.read_text().splitlines()), 1)


class Reference(unittest.TestCase):
    def test_api_reference_lists_public_functions(self):
        ref = agent.api_reference()
        for name in ("tb.me(", "tb.goto(", "tb.craft(", "tb.tiles(", "Pathfinder capabilities"):
            self.assertIn(name, ref)
        self.assertNotIn("truth_", ref)


if __name__ == "__main__":
    unittest.main()
