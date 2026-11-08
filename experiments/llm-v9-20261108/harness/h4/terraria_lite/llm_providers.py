"""Small provider boundary. No SDK retries, model substitution or credential logs."""
import json
import os
import re
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler

from terraria_lite.llm_protocol import canonical


class ProviderError(RuntimeError):
    """An ambiguous request must never be automatically retried."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ProviderError("Provider redirect refused; no credential forwarding")


def post_json(payload, key, timeout):
    request = Request("https://openrouter.ai/api/v1/chat/completions",
                      canonical(payload).encode(), headers={"Authorization": "Bearer " + key,
                      "Content-Type": "application/json", "X-Title": "Terraria Lite Development Evaluation"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            data = response.read(4_194_305)
        if len(data) > 4_194_304:
            raise ProviderError("Provider response exceeded size limit")
        return json.loads(data)
    except HTTPError as error:
        raise ProviderError(f"Provider HTTP {error.code}; no retry; charge status may be unknown") from None
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise ProviderError(f"Provider transport/JSON failure ({type(error).__name__}); no retry") from None


def hermes_key(destination):
    """Read only Hermes credential files over explicitly selected SSH connection.

    Secret travels over encrypted SSH into this process's memory; never an argv,
    local file, printed value, transcript field or child training environment.
    """
    if not re.fullmatch(r"[A-Za-z0-9_.@-]+", destination):
        raise ValueError("Invalid SSH destination")
    script = r'''
import json, pathlib, re, shlex
base=pathlib.Path.home()
for candidate in (base/'.hermes/.env',base/'.hermes/config.yaml',base/'.config/hermes/.env',base/'.config/hermes/config.yaml'):
    if not candidate.is_file(): continue
    text=candidate.read_text()
    for line in text.splitlines():
        match=re.match(r'\s*(?:export\s+)?(OPENROUTER_API_KEY|openrouter_api_key|api_key)\s*[=:]\s*(.*?)\s*$',line)
        if not match: continue
        field,raw=match.groups()
        try: parts=shlex.split(raw,comments=True)
        except ValueError: continue
        value=parts[0] if len(parts)==1 else ''
        if value.startswith('sk-or-') and len(value)>24:
            print(json.dumps({'key':value,'source':str(candidate),'field':field})); raise SystemExit(0)
raise SystemExit('No OpenRouter key found in scoped Hermes configuration files')
'''
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", destination,
                             "python3 -"], input=script, capture_output=True, text=True, timeout=45)
    if result.returncode:
        # Do not propagate remote config text or command outputs into logs.
        raise ProviderError(f"Hermes SSH key retrieval failed (exit {result.returncode}); verify SSH approval/login")
    try:
        record = json.loads(result.stdout)
        secret = record.pop("key")
        if not secret.startswith("sk-or-"):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ProviderError("Hermes returned an invalid credential record; output suppressed") from None
    return secret, {"method": "scoped SSH read, memory only", "host": destination, **record}


class OpenRouter:
    def __init__(self, config, key=None, transport=post_json):
        self.config, self.transport = config, transport
        self._key = key  # never serialized

    def payload(self, messages, schema):
        result = {"model": self.config["model"], "messages": messages,
                  "max_tokens": self.config["max_output_tokens"],
                  "provider": {"require_parameters": True, "allow_fallbacks": False}}
        if self.config["reasoning_effort"] != "none":
            result["reasoning"] = {"effort": self.config["reasoning_effort"], "exclude": True}
        if self.config["structured_output"]:
            result["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "terraria_actions", "strict": True, "schema": schema}}
        return result

    def call(self, payload, timeout):
        key = self._key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ProviderError("OPENROUTER_API_KEY missing; no request sent")
        raw = self.transport(payload, key, timeout)
        if raw.get("error"):
            raise ProviderError("Provider returned an error object; charge status may be unknown")
        requested, actual = self.config["model"], raw.get("model", "")
        if actual != requested and not re.fullmatch(re.escape(requested) + r"-\d{4}-\d{2}-\d{2}", actual):
            raise ProviderError("Provider returned a different model; no substitution accepted")
        choices = raw.get("choices", [])
        if len(choices) != 1:
            raise ProviderError("Expected exactly one model completion")
        choice, usage = choices[0], raw.get("usage")
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                                             for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
            raise ProviderError("Missing/invalid provider token accounting; stop rather than undercount")
        if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
            raise ProviderError("Inconsistent provider token totals")
        message = choice.get("message", {})
        content = message.get("content") or ""
        if not isinstance(content, str):
            raise ProviderError("Non-text provider content")
        # Exclude private reasoning and authorization headers from our log format.
        return {"text": content, "id": raw.get("id"), "model": actual,
                "provider": raw.get("provider"), "finish_reason": choice.get("finish_reason"),
                "usage": usage}


def decisions_post(payload, key, timeout):
    request = Request("https://openrouter.ai/api/alpha/decisions", canonical(payload).encode(),
                      headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                               "X-Title": "Terraria Lite Development Evaluation"})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            data = response.read(4_194_305)
        if len(data) > 4_194_304:
            raise ProviderError("Provider response exceeded size limit")
        return json.loads(data)
    except HTTPError as error:
        raise ProviderError(f"Provider HTTP {error.code}; no retry; charge status may be unknown") from None
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise ProviderError(f"Provider transport/JSON failure ({type(error).__name__}); no retry") from None


class OpenRouterDecisions:
    """TypeSafe Jev through OpenRouter's Decisions API: one 'choice' over the currently legal actions.

    State = system text + the newest user turn (no history). Options are read from the text
    observation's 'Legal now:' line, so the choice set is exactly the action mask. Jev writes no notes.
    """

    def __init__(self, config, key=None, transport=decisions_post):
        self.config, self.transport = config, transport
        self._key = key

    def payload(self, messages, schema):
        user = messages[-1]["content"]
        line = next(l for l in user.splitlines() if l.startswith("Legal now: "))
        options = [o.strip() for o in re.split(r",\s(?![^\[]*\])", line[len("Legal now: "):].rstrip("."))]
        criteria = {re.sub(r"\s*\[.*\]$", "", o): ("Do: " + o) for o in options}
        if self.config.get("action_set") == "macro":
            criteria.update({m: f"Macro: {m} (multi-tick, stops early when blocked or on an event)" for m in
                             ("walk left 8", "walk right 8", "dig left 6", "dig right 6", "dig down 6", "stairs up-left 4", "stairs up-right 4")})
        # The machine-readable rules JSON duplicates the guide/action list; Jev's state keeps the text parts only.
        system = messages[0]["content"].split("PUBLIC RULES (machine-readable):", 1)[0]
        return {"model": self.config["model"],
                "state": [system, "Current observation:\n" + user],
                "questions": {"action": {"type": "choice", "criteria": criteria,
                                         "instructions": "Choose the single primitive action that best advances earning more weighted achievements "
                                                         "right now, following the guide's progression, while staying alive."}}}

    def call(self, payload, timeout):
        key = self._key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise ProviderError("OPENROUTER_API_KEY missing; no request sent")
        raw = self.transport(payload, key, timeout)
        if raw.get("error"):
            raise ProviderError("Provider returned an error object; charge status may be unknown")
        actual = raw.get("model") or self.config["model"]
        if not actual.startswith(self.config["model"]):
            raise ProviderError("Provider returned a different model; no substitution accepted")
        answer = (raw.get("answers") or {}).get("action") or {}
        choice = answer.get("choice")
        usage = raw.get("usage") or {}
        prompt, completion = usage.get("input_tokens"), usage.get("output_tokens") or 0
        if type(prompt) is not int or type(completion) is not int:
            raise ProviderError("Missing/invalid provider token accounting; stop rather than undercount")
        text = canonical({"plan": f"confidence {answer.get('confidence')}", "actions": [choice] if isinstance(choice, str) else []})
        return {"text": text, "id": raw.get("id"), "model": actual, "provider": "openrouter-decisions", "finish_reason": "stop",
                "usage": {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt+completion,
                          "cost": _reported(usage.get("cost"))}}


GATEWAY_CONFIG = os.path.expanduser("~/.config/terrariabench/gateway.json")
GATEWAY_ROOT = "https://llm-api.amd.com:18443"
ANTHROPIC_BETAS = "effort-2025-11-24,context-management-2025-06-27,interleaved-thinking-2025-05-14"
HAIKU_BUDGETS = {"low": 1024, "medium": 4096, "high": 8192}


def gateway_credentials():
    """Key header and key from the local 0600 gateway file; memory only, never logged."""
    if os.stat(GATEWAY_CONFIG).st_mode & 0o077:
        raise ProviderError("Gateway credential file must not be group/world readable")
    with open(GATEWAY_CONFIG) as f:
        record = json.load(f)
    if not record.get("key") or not record.get("key_header"):
        raise ProviderError("Gateway credential file lacks key/header; nothing sent")
    return record["key_header"], record["key"], {"method": "local 0600 file, memory only", "path": GATEWAY_CONFIG}


def gateway_post(url, payload, header, key, timeout):
    request = Request(url, canonical(payload).encode(), headers={header: key, "Content-Type": "application/json",
                      "anthropic-version": "2023-06-01", "anthropic-beta": ANTHROPIC_BETAS})
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            cost = response.headers.get("X-Token-Usage-Cost")
            data = response.read(4_194_305)
        if len(data) > 4_194_304:
            raise ProviderError("Provider response exceeded size limit")
        return json.loads(data), cost
    except HTTPError as error:
        raise ProviderError(f"Gateway HTTP {error.code}; no retry; charge status may be unknown") from None
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise ProviderError(f"Gateway transport/JSON failure ({type(error).__name__}); no retry") from None


def _reported(cost):
    try:
        value = float(cost)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


class AnthropicGateway:
    """Anthropic Messages route. Prompt caching: system block + newest user turn (rolling prefix)."""

    def __init__(self, config, credentials=None, transport=gateway_post):
        self.config, self.transport = config, transport
        self._header, self._key = (credentials or (None, None))[:2]

    def payload(self, messages, schema):
        system = messages[0]["content"]
        turns = [{"role": m["role"], "content": [{"type": "text", "text": m["content"]}]} for m in messages[1:]]
        turns[-1]["content"][-1]["cache_control"] = {"type": "ephemeral"}
        result = {"model": self.config["model"], "max_tokens": self.config["max_output_tokens"],
                  "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                  "messages": turns}
        effort = self.config["reasoning_effort"]
        if effort != "none":
            if "haiku" in self.config["model"]:
                result["thinking"] = {"type": "enabled", "budget_tokens": HAIKU_BUDGETS[effort]}
            else:
                result["thinking"] = {"type": "adaptive"}
                result["output_config"] = {"effort": effort}
        return result

    def call(self, payload, timeout):
        if not self._key:
            raise ProviderError("Gateway key missing; no request sent")
        raw, cost = self.transport(GATEWAY_ROOT + "/anthropic/v1/messages", payload, self._header, self._key, timeout)
        if raw.get("type") == "error" or raw.get("error"):
            raise ProviderError("Gateway returned an error object; charge status may be unknown")
        requested, actual = self.config["model"], raw.get("model", "")
        if actual != requested and not re.fullmatch(re.escape(requested) + r"-\d{8}", actual):
            raise ProviderError("Provider returned a different model; no substitution accepted")
        usage = raw.get("usage") or {}
        fresh, write, read, output = (usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "output_tokens"))
        if any(type(v) is not int or v < 0 for v in (fresh, write, read, output)):
            raise ProviderError("Missing/invalid provider token accounting; stop rather than undercount")
        blocks = raw.get("content") or []
        text = "\n".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        stop = raw.get("stop_reason")
        return {"text": text, "id": raw.get("id"), "model": actual, "provider": "amd-gateway-anthropic",
                "finish_reason": "stop" if stop in ("end_turn", "stop_sequence") else stop,
                "usage": {"prompt_tokens": fresh+write+read, "completion_tokens": output, "total_tokens": fresh+write+read+output,
                          "fresh_input_tokens": fresh, "cache_write_tokens": write, "cache_read_tokens": read,
                          "cost": _reported(cost)}}


class OpenAIGateway:
    """OpenAI-compatible Unified route (chat completions, automatic prefix caching)."""

    def __init__(self, config, credentials=None, transport=gateway_post):
        self.config, self.transport = config, transport
        self._header, self._key = (credentials or (None, None))[:2]

    def payload(self, messages, schema):
        result = {"model": self.config["model"], "messages": messages,
                  "max_completion_tokens": self.config["max_output_tokens"]}
        if self.config["reasoning_effort"] != "none":
            result["reasoning_effort"] = self.config["reasoning_effort"]
        if self.config["structured_output"]:
            result["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "terraria_actions", "strict": True, "schema": schema}}
        return result

    def call(self, payload, timeout):
        if not self._key:
            raise ProviderError("Gateway key missing; no request sent")
        raw, cost = self.transport(GATEWAY_ROOT + "/Unified/v1/chat/completions", payload, self._header, self._key, timeout)
        if raw.get("error"):
            raise ProviderError("Gateway returned an error object; charge status may be unknown")
        requested, actual = self.config["model"], raw.get("model", "")
        if actual != requested and not re.fullmatch(re.escape(requested) + r"-\d{4}-\d{2}-\d{2}", actual):
            raise ProviderError("Provider returned a different model; no substitution accepted")
        choices = raw.get("choices", [])
        if len(choices) != 1:
            raise ProviderError("Expected exactly one model completion")
        usage = raw.get("usage")
        if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0
                                             for k in ("prompt_tokens", "completion_tokens", "total_tokens")):
            raise ProviderError("Missing/invalid provider token accounting; stop rather than undercount")
        cached = (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
        reasoning = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
        content = choices[0].get("message", {}).get("content") or ""
        if not isinstance(content, str):
            raise ProviderError("Non-text provider content")
        reported = _reported(cost)
        if reported is None:
            reported = _reported(usage.get("total_cost"))
        return {"text": content, "id": raw.get("id"), "model": actual, "provider": "amd-gateway-unified",
                "finish_reason": choices[0].get("finish_reason"),
                "usage": {"prompt_tokens": usage["prompt_tokens"], "completion_tokens": usage["completion_tokens"],
                          "total_tokens": usage["total_tokens"], "cache_read_tokens": cached,
                          "reasoning_tokens": reasoning, "cost": reported}}
