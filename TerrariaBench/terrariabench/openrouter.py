"""Narrow OpenRouter vision adapter with explicit accounting and no retries."""
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import shlex
import urllib.error
import urllib.request

BASE = "https://openrouter.ai/api/v1"


def hermes_key(path=None):
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key
    path = Path(path) if path else Path.home() / ".hermes/.env"
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:].lstrip()
        name, equal, value = line.partition("=")
        if equal and name.strip() == "OPENROUTER_API_KEY":
            values = shlex.split(value, comments=True)
            if len(values) == 1 and values[0] and not values[0].startswith("$"):
                return values[0]
    raise RuntimeError("No literal OPENROUTER_API_KEY in Hermes .env; no secrets were logged")


def request(path, *, key=None, payload=None, timeout=60):
    headers = {"Content-Type": "application/json", "X-OpenRouter-Title": "TerrariaBench development smoke"}
    if key:
        headers["Authorization"] = "Bearer " + key
    req = urllib.request.Request(BASE + path, headers=headers,
                                 data=json.dumps(payload).encode() if payload is not None else None)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        # Never persist error bodies/headers that could echo credentials.
        raise RuntimeError(f"OpenRouter HTTP {error.code}; no automatic retry") from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        raise RuntimeError("OpenRouter transport/JSON failure; charge uncertain; no retry") from None
    if not isinstance(result, dict) or "error" in result:
        raise RuntimeError("OpenRouter returned an error; charge uncertain; no retry")
    return result


def model_metadata(model_id):
    data = request("/models")["data"]
    model = next((m for m in data if m["id"] == model_id), None)
    if not model or "image" not in model.get("architecture", {}).get("input_modalities", []):
        raise ValueError("requested model is missing or has no image input")
    if not {"response_format", "max_tokens"} <= set(model.get("supported_parameters", [])):
        raise ValueError("model lacks required request controls")
    return {k: model.get(k) for k in ("id", "canonical_slug", "created", "pricing", "architecture", "supported_parameters")}


class Budget:
    def __init__(self, usd, pricing, input_ceiling=32768, output_ceiling=2048):
        self.limit = self.decimal(usd)
        self.input_rate = max(self.decimal(pricing["prompt"]), self.decimal(pricing.get("image", "0")))
        self.output_rate = max(self.decimal(pricing["completion"]), self.decimal(pricing.get("internal_reasoning", "0")))
        self.request_rate = self.decimal(pricing.get("request", "0"))
        self.input_ceiling, self.output_ceiling = input_ceiling, output_ceiling
        self.spent = Decimal(0)
        self.pending = Decimal(0)
        self.tokens = 0

    @staticmethod
    def decimal(value):
        try:
            number = Decimal(str(value))
        except InvalidOperation:
            raise ValueError("invalid price/cost") from None
        if not number.is_finite() or number < 0:
            raise ValueError("invalid price/cost")
        return number

    @property
    def reservation(self):
        return self.input_rate * self.input_ceiling + self.output_rate * self.output_ceiling + self.request_rate

    def reserve(self):
        if self.pending or self.spent + self.reservation > self.limit:
            raise RuntimeError("dollar reservation limit reached")
        self.pending = self.reservation

    def reconcile(self, usage):
        if not isinstance(usage, dict) or usage.get("cost") is None:
            raise RuntimeError("missing usage/cost; reservation remains uncertain")
        prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
        if any(type(n) is not int or n < 0 for n in (prompt, completion)):
            raise RuntimeError("missing/invalid token usage")
        cost = self.decimal(usage["cost"])
        reserved = self.pending
        self.spent += cost
        self.pending = Decimal(0)
        self.tokens += prompt + completion
        if prompt > self.input_ceiling or completion > self.output_ceiling or cost > reserved:
            raise RuntimeError("accounting assumption exceeded; stop before another call")
        if self.spent > self.limit:
            raise RuntimeError("reported cost exceeds run ceiling")

    def summary(self):
        return {"usd_limit": str(self.limit), "reported_usd": str(self.spent),
                "uncertain_reserved_usd": str(self.pending), "tokens": self.tokens,
                "reservation_per_call_usd": str(self.reservation)}
