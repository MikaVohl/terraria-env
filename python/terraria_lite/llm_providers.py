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
                  "reasoning": {"effort": self.config["reasoning_effort"], "exclude": True},
                  "provider": {"require_parameters": True, "allow_fallbacks": False},
                  "response_format": {"type": "json_schema", "json_schema": {
                      "name": "terraria_actions", "strict": True, "schema": schema}}}
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
