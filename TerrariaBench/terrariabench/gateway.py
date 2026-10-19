"""Anthropic Messages client for an internal Anthropic-compatible gateway, shaped like omp's requests.

The endpoint, the subscription-key header name and the key live outside the repository in
~/.config/terrariabench/gateway.json (mode 0600): {"base_url": ..., "key_header": ..., "key": ...}.
Headers and body fields mirror omp 18.1.16's anthropic-messages requests (captured against a
local echo listener), including SSE streaming and omp's per-model reasoning mappings. The key is
never written to artifacts or errors.
"""
import http.client
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
import uuid
import zlib

from .openrouter import RETRYABLE_HTTP, ProviderError

CONFIG_FILE = Path.home() / ".config/terrariabench/gateway.json"
OMP_VERSION = "18.1.16"
CONTEXT_MANAGEMENT = {"edits": [{"type": "clear_thinking_20251015", "keep": "all"}]}
# Per-model omp 18.1.16 request shapes (`--thinking <level>`, captured against a local echo
# listener) and OpenRouter-listed USD/token prices. Streamed responses carry no
# X-Token-Usage-Cost header, so these list prices back the accounting.
MODELS = {
    "claude-haiku-5-5": {
        "price": {"input": 0.10e-6, "output": 0.50e-6, "cache_read": 0.01e-6, "cache_write": 0.125e-6},
        "max_tokens": 64000,
        "betas": "effort-2025-11-24,context-management-2025-06-27,interleaved-thinking-2025-05-14",
        "reasoning": {"medium": {"thinking": {"type": "enabled", "budget_tokens": 8192, "display": "summarized"}}}},
    **{model: {"price": price, "max_tokens": 128000,
               "betas": "effort-2025-11-24,context-management-2025-06-27",
               "reasoning": {level: {"thinking": {"type": "adaptive", "display": "summarized"},
                                     "output_config": {"effort": level}} for level in ("low", "medium")}}
       for model, price in (
           ("claude-sonnet-5-5", {"input": 2.0e-6, "output": 10.0e-6, "cache_read": 0.10e-6, "cache_write": 2.5e-6}),
           ("claude-opus-5-5", {"input": 4.0e-6, "output": 20.0e-6, "cache_read": 0.20e-6, "cache_write": 5.0e-6}))},
}
RETRYABLE_STREAM_ERRORS = frozenset({"overloaded_error", "api_error", "rate_limit_error", "timeout_error"})


def config():
    """Endpoint, key-header name and key from the local 0600 config file (never committed)."""
    if CONFIG_FILE.stat().st_mode & 0o077:
        raise RuntimeError(f"{CONFIG_FILE} must not be group/world readable")
    return json.loads(CONFIG_FILE.read_text())


def load_key():
    key = config().get("key")
    if not key:
        raise RuntimeError("No gateway key in the local config file; no secrets were logged")
    return key


def session_id():
    return str(uuid.uuid7() if hasattr(uuid, "uuid7") else uuid.uuid4())


def headers(key, session, model):
    return {"Accept": "text/event-stream", "Accept-Encoding": "gzip, deflate",
            "Authorization": "Bearer N/A", "Content-Type": "application/json",
            config()["key_header"]: key, "User-Agent": f"omp/{OMP_VERSION}",
            "X-Claude-Code-Session-Id": session, "anthropic-beta": MODELS[model]["betas"],
            "anthropic-dangerous-direct-browser-access": "true",
            "anthropic-version": "2023-06-01", "x-app": "cli"}


def body(model, reasoning, system, messages, tools, session):
    spec = MODELS[model]
    return {"model": model, "messages": messages,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "tools": tools, "metadata": {"user_id": json.dumps({"session_id": session}, separators=(",", ":"))},
            "max_tokens": spec["max_tokens"], **spec["reasoning"][reasoning],
            "context_management": CONTEXT_MANAGEMENT, "stream": True}


def convert(messages, tools):
    """Chat-format history (system, user, assistant+tool_calls, tool, image user) -> Anthropic."""
    out = []

    def add(role, blocks):
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": list(blocks)})

    for m in messages[1:]:
        if m["role"] == "assistant":
            add("assistant", m["anthropic_content"])
        elif m["role"] == "tool":
            add("user", [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}])
        elif isinstance(m["content"], str):
            add("user", [{"type": "text", "text": m["content"]}])
        else:
            blocks = []
            for part in m["content"]:
                if part["type"] == "text":
                    blocks.append({"type": "text", "text": part["text"]})
                else:
                    head, data = part["image_url"]["url"].split(",", 1)
                    blocks.append({"type": "image", "source": {"type": "base64",
                                   "media_type": head[5:].split(";")[0], "data": data}})
            add("user", blocks)
    # omp marks the newest user turn for prompt caching.
    last = out[-1]["content"][-1]
    out[-1]["content"][-1] = {**last, "cache_control": {"type": "ephemeral"}}
    return out, [{"name": t["function"]["name"], "description": t["function"]["description"],
                  "input_schema": t["function"]["parameters"]} for t in tools]


def _events(response):
    decoder = zlib.decompressobj(16 + zlib.MAX_WBITS) if response.headers.get("Content-Encoding") == "gzip" else \
        zlib.decompressobj() if response.headers.get("Content-Encoding") == "deflate" else None
    pending, data = b"", []
    while chunk := response.read1(65536):
        pending += decoder.decompress(chunk) if decoder else chunk
        *lines, pending = pending.split(b"\n")
        for line in lines:
            line = line.rstrip(b"\r")
            if line.startswith(b"data:"):
                data.append(line[5:].strip())
            elif not line and data:
                yield json.loads(b"\n".join(data))
                data = []
    if data:
        yield json.loads(b"\n".join(data))


def messages(payload, *, key, session, timeout=90, base=None):
    """One streamed request. Returns (assembled Anthropic message, gateway response metadata)."""
    req = urllib.request.Request((base or config()["base_url"]) + "/v1/messages", data=json.dumps(payload).encode(),
                                 headers=headers(key, session, payload["model"]), method="POST")
    message, blocks, partial = None, {}, {}
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            gateway = {k: response.headers.get(k) for k in
                       ("X-Token-Usage-Cost", "x-ms-region", "Request-Id", "apim-request-id", "x-ratelimit-remaining-tokens")}
            for event in _events(response):
                kind = event.get("type")
                if kind == "message_start":
                    message = event["message"]
                elif kind == "content_block_start":
                    blocks[event["index"]] = dict(event["content_block"])
                elif kind == "content_block_delta":
                    block, delta = blocks[event["index"]], event["delta"]
                    if delta["type"] == "text_delta":
                        block["text"] = block.get("text", "") + delta["text"]
                    elif delta["type"] == "thinking_delta":
                        block["thinking"] = block.get("thinking", "") + delta["thinking"]
                    elif delta["type"] == "signature_delta":
                        block["signature"] = block.get("signature", "") + delta["signature"]
                    elif delta["type"] == "input_json_delta":
                        partial[event["index"]] = partial.get(event["index"], "") + delta["partial_json"]
                elif kind == "message_delta":
                    message.update({k: v for k, v in event["delta"].items() if v is not None})
                    message["usage"] = {**message.get("usage", {}), **(event.get("usage") or {})}
                elif kind == "error":
                    error = event.get("error") or {}
                    raise ProviderError(f"gateway stream error {error.get('type')}; charge uncertain",
                                        retryable=error.get("type") in RETRYABLE_STREAM_ERRORS)
            gateway["X-Token-Usage-Cost"] = gateway["X-Token-Usage-Cost"] or response.headers.get("X-Token-Usage-Cost")
    except urllib.error.HTTPError as error:
        try:
            retry_after = float(error.headers.get("Retry-After")) if error.headers else None
        except (TypeError, ValueError):
            retry_after = None
        raise ProviderError(f"gateway HTTP {error.code}; charge uncertain",
                            retryable=error.code in RETRYABLE_HTTP | {529}, retry_after=retry_after) from None
    except urllib.error.URLError as error:
        # urllib raises URLError only while connecting/sending (DNS, refused, TLS, connect timeout):
        # the gateway never received a complete request, so no charge is possible.
        raise ProviderError(f"gateway connection failure (URLError/{type(error.reason).__name__}); not sent",
                            retryable=True, sent=False) from None
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as error:
        raise ProviderError(f"gateway transport/JSON failure ({type(error).__name__}); charge uncertain",
                            retryable=True) from None
    if message is None or message.get("stop_reason") is None:
        raise ProviderError("gateway stream ended before message_stop; charge uncertain", retryable=True)
    for index, raw in partial.items():
        try:
            blocks[index]["input"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            blocks[index]["input"], blocks[index]["unparsed_input"] = {}, raw
    message["content"] = [blocks[i] for i in sorted(blocks)]
    return message, gateway


def normalize(message, gateway, model):
    """Chat-completion shape for the shared loop, live panel and report; raw blocks preserved."""
    content = message["content"]
    calls = [{"id": b["id"], "type": "function", "function": {
        "name": b["name"], "arguments": b.pop("unparsed_input", None) or json.dumps(b["input"])}}
        for b in content if b["type"] == "tool_use"]
    usage = message.get("usage", {})
    fresh, write, read = (usage.get(k) or 0 for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    output = usage.get("output_tokens") or 0
    price = MODELS[model]["price"]
    listed = (price["input"] * fresh + price["cache_write"] * write + price["cache_read"] * read
              + price["output"] * output)
    header = gateway.get("X-Token-Usage-Cost")
    return {"id": message.get("id"), "model": message.get("model"),
            "choices": [{"finish_reason": message.get("stop_reason"), "message": {
                "role": "assistant",
                "content": "\n".join(b["text"] for b in content if b["type"] == "text") or None,
                "reasoning": "\n".join(b.get("thinking", "") for b in content if b["type"] == "thinking") or None,
                "tool_calls": calls, "anthropic_content": content}}],
            "usage": {"prompt_tokens": fresh + write + read, "completion_tokens": output,
                      "cost": header if header is not None else f"{listed:.10f}",
                      "cost_source": "gateway_header" if header is not None else "list_price",
                      "list_price_cost": f"{listed:.10f}", "anthropic": usage},
            "gateway": {k: v for k, v in gateway.items() if v is not None}}
