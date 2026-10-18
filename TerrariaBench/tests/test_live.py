import io
import os
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

from terrariabench.linux_control import validate_actions
from terrariabench.openrouter import Budget, ProviderError, hermes_key, request, retry_delay
from terrariabench.live import pixel_actions


class LiveContractTests(unittest.TestCase):
    def test_normalized_coordinates_map_without_strategy(self):
        actions = [{"x": 500, "y": 500, "mouse": "left", "ms": 200}]
        self.assertEqual(pixel_actions(actions, "normalized1000"), [{"x": 640, "y": 360, "mouse": "left", "ms": 200}])
        self.assertEqual(actions[0]["x"], 500)
        self.assertEqual(pixel_actions([{"x": 1000, "y": 1000}], "normalized1000"), [{"x": 1279, "y": 719}])
        for value in (-1, 1001, True, 0.5):
            with self.assertRaises(ValueError):
                pixel_actions([{"x": value, "y": 1}], "normalized1000")

    def test_rejects_unsafe_batches_atomically(self):
        for bad in (
            [], [{"keys": ["a"]}, {"keys": ["super"]}], [{"command": "shell"}],
            [{"x": 1280, "y": 0}], [{"x": 0}], [{"ms": True}],
            [{"ms": 1001}], [{"keys": ["a", "a"]}], [{"mouse": "unknown"}],
        ):
            with self.subTest(batch=bad), self.assertRaises(ValueError):
                validate_actions(bad)
        self.assertEqual(validate_actions([{"keys": ["d", "space"], "mouse": "left", "x": 4, "y": 5, "ms": 1000}])[0]["ms"], 1000)

    def test_reservation_precedes_call_and_is_reconciled(self):
        budget = Budget(1, {"prompt": ".000001", "completion": ".000005"})
        budget.reserve()
        with self.assertRaises(RuntimeError):
            budget.reserve()
        budget.reconcile({"prompt_tokens": 500, "completion_tokens": 100, "cost": .001})
        self.assertEqual(str(budget.spent), "0.001")
        self.assertEqual(budget.tokens, 600)
        budget.reserve()

    def test_missing_usage_preserves_uncertain_charge(self):
        budget = Budget(1, {"prompt": ".000001", "completion": ".000005"})
        budget.reserve()
        with self.assertRaises(RuntimeError):
            budget.reconcile({"prompt_tokens": 5, "completion_tokens": 3})
        self.assertGreater(budget.pending, 0)
        with self.assertRaises(RuntimeError):
            budget.reserve()

    def test_rejects_over_budget_and_excess_usage(self):
        budget = Budget(.001, {"prompt": ".000001", "completion": ".000005"})
        with self.assertRaises(RuntimeError):
            budget.reserve()
        budget = Budget(1, {"prompt": ".000001", "completion": ".000005"})
        budget.reserve()
        with self.assertRaises(RuntimeError):
            budget.reconcile({"prompt_tokens": 50000, "completion_tokens": 0, "cost": .05})

    def test_nonfinite_prices_and_costs_rejected(self):
        for value in ("NaN", "Infinity", "-1", None):
            with self.assertRaises(ValueError):
                Budget(1, {"prompt": value, "completion": "0"})

    def test_provider_failures_classify_retryability(self):
        class TruncatedBody(io.BytesIO):
            def read(self, *args):
                raise ssl.SSLError("bad record mac")
        cases = [
            (TruncatedBody(), True),  # case 27 escaped as a raw SSLError
            (urllib.error.HTTPError("u", 429, "rate", {"Retry-After": "7"}, None), True),
            (urllib.error.HTTPError("u", 400, "bad", {}, None), False),
            (io.BytesIO(b'{"error": {"code": 502}}'), True),
            (io.BytesIO(b'{"error": {"code": 402}}'), False),
            (io.BytesIO(b"not json"), True),
        ]
        for outcome, retryable in cases:
            def urlopen(*args, **kwargs):
                if isinstance(outcome, Exception):
                    raise outcome
                return outcome
            with self.subTest(outcome=outcome), patch("urllib.request.urlopen", urlopen):
                with self.assertRaises(ProviderError) as caught:
                    request("/chat/completions", payload={})
                self.assertEqual(caught.exception.retryable, retryable)
        error = ProviderError("x", retryable=True, retry_after=7.0)
        self.assertEqual(retry_delay(error, 0), 7.0)
        self.assertEqual(retry_delay(ProviderError("x", retryable=True, retry_after=900), 0), 30.0)
        self.assertEqual(retry_delay(ProviderError("x", retryable=True), 2), 8.0)

    def test_abandoned_attempts_stay_counted_against_the_cap(self):
        budget = Budget(".0025", {"prompt": "0", "completion": "0", "request": ".001"})
        budget.reserve()
        budget.abandon()
        budget.reserve()
        budget.abandon()
        self.assertEqual(budget.summary()["uncertain_reserved_usd"], "0.002")
        with self.assertRaises(RuntimeError):
            budget.reserve()

    def test_loads_only_literal_hermes_key_without_shell_execution(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            path = Path(root) / ".env"
            path.write_text('OTHER=ignored\nexport OPENROUTER_API_KEY="fake-key-for-test" # comment\n')
            self.assertEqual(hermes_key(path), "fake-key-for-test")
            path.write_text('OPENROUTER_API_KEY=$(touch /not/executed)\n')
            with self.assertRaises(RuntimeError):
                hermes_key(path)


if __name__ == "__main__":
    unittest.main()
