"""OpenAI-compatible client for the gateway's Unified route (GPT-5.6 Luna/Terra/Sol, GPT-6 Luna/Astra).

Same local 0600 config as gateway.py (~/.config/terrariabench/gateway.json); the Unified base URL is
`unified_base_url` if present, else the Anthropic `base_url` with `/anthropic` replaced by `/Unified/v1`.
Two request shapes, both not streamed so every response carries the gateway's `X-Token-Usage-Cost` header
(also `usage.total_cost`), which accounting uses; the list-price estimate is kept alongside:
  responses()  /v1/responses: function tools with reasoning (the tool loop). Chat completions reject
               function tools unless reasoning_effort is "none". Reasoning items are kept encrypted in the
               history (store=false, include reasoning.encrypted_content) like Anthropic thinking blocks.
  chat()       /v1/chat/completions without tools (planner/executor JSON replies).
The key is never written to artifacts or errors.
"""
import http.client
import json
import urllib.error
import urllib.request

from . import gateway
from .openrouter import RETRYABLE_HTTP, ProviderError

# USD/token list prices fitted on 2026-11-08 from the gateway's own X-Token-Usage-Cost on two probes per
# model (2,110 prompt + 4 output tokens; 17 prompt + 602 output tokens), rounded up. Used only for the
# per-call reservation and the list-price cross-check; reported cost comes from the header.
# gpt-6-luna: fitted 2026-11-10 the same way (2,110 prompt + 5 output = $0.000181; 13 + 661 = $0.000226).
# gpt-6-astra: fitted 2026-11-10 by tools/terrabot/probe_price.py (2,114 prompt + 4 output = $0.0180999; 14 + 584 =
# $0.0199512 -> $8.50/M in, $33.96/M out, rounded up to $34). /models lists $6.80/M list input, but the header bills
# input at the cache-creation rate ($8.50/M).
MODELS = {
    "gpt-5.6-luna": {"price": {"input": 0.18e-6, "output": 0.82e-6}},
    "gpt-5.6-terra": {"price": {"input": 1.8e-6, "output": 8.2e-6}},
    "gpt-5.6-sol": {"price": {"input": 3.4e-6, "output": 13.6e-6}},
    # Chat completions report the deployment as gpt-6-luna-2026-09-22; Responses as dvue-aoai-006-gpt-6-luna.
    "gpt-6-luna": {"price": {"input": 0.09e-6, "output": 0.35e-6}, "deployment": "gpt-6-luna-2026-09-22"},
    "gpt-6-astra": {"price": {"input": 8.5e-6, "output": 34.0e-6}, "deployment": "gpt-6-astra-2026-09-03"},
}
REASONING = ("none", "low", "medium", "high")
MAX_COMPLETION_TOKENS = 16384
CHAT_KEYS = ("role", "content", "tool_calls", "tool_call_id", "name")


def base_url():
    c = gateway.config()
    return c.get("unified_base_url") or c["base_url"].replace("/anthropic", "/Unified/v1")


def convert(messages):
    """Shared chat history -> OpenAI chat messages (drops harness/provider-private fields)."""
    out = []
    for m in messages:
        msg = {k: m[k] for k in CHAT_KEYS if m.get(k) is not None}
        msg.setdefault("content", "")
        if msg["role"] == "assistant" and not msg.get("tool_calls"):
            msg.pop("tool_calls", None)
        out.append(msg)
    return out


def responses_body(model, reasoning, messages, tools, max_tokens=MAX_COMPLETION_TOKENS, tool_choice="auto"):
    """Shared chat history -> Responses API request. The system message becomes `instructions`; assistant turns
    replay their raw output items (reasoning, function calls, text); tool results become function_call_output."""
    items = []
    for m in messages[1:]:
        if m["role"] == "assistant":
            items.extend(m["responses_output"])
        elif m["role"] == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": m["content"]})
        elif isinstance(m["content"], str):
            items.append({"role": "user", "content": [{"type": "input_text", "text": m["content"]}]})
        else:
            items.append({"role": "user", "content": [
                {"type": "input_text", "text": p["text"]} if p["type"] == "text" else
                {"type": "input_image", "image_url": p["image_url"]["url"]} for p in m["content"]]})
    return {"model": model, "instructions": messages[0]["content"], "input": items, "store": False,
            "include": ["reasoning.encrypted_content"], "reasoning": {"effort": reasoning, "summary": "auto"},
            "tools": [{"type": "function", "name": t["function"]["name"], "description": t["function"]["description"],
                       "parameters": t["function"]["parameters"]} for t in tools],
            "tool_choice": tool_choice, "max_output_tokens": max_tokens}


def _post(path, payload, key, timeout):
    c = gateway.config()
    req = urllib.request.Request(base_url() + path, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", c["key_header"]: key})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.headers.get("X-Token-Usage-Cost"), json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            retry_after = float(error.headers.get("Retry-After")) if error.headers else None
        except (TypeError, ValueError):
            retry_after = None
        raise ProviderError(f"unified HTTP {error.code}; charge uncertain",
                            retryable=error.code in RETRYABLE_HTTP | {529}, retry_after=retry_after) from None
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise ProviderError("unified read timeout; charge uncertain", retryable=True) from None
        raise ProviderError(f"unified connection failure (URLError/{type(error.reason).__name__}); not sent",
                            retryable=True, sent=False) from None
    except (OSError, http.client.HTTPException, json.JSONDecodeError) as error:
        raise ProviderError(f"unified transport/JSON failure ({type(error).__name__}); charge uncertain",
                            retryable=True) from None


def responses(payload, *, key, timeout=90):
    """One Responses API request, normalized to the shared chat-completion shape (raw output items kept)."""
    header, data = _post("/responses", payload, key, timeout)
    if not isinstance(data, dict) or data.get("status") not in ("completed", "incomplete") or "output" not in data:
        raise ProviderError("unified response not completed; charge uncertain", retryable=True)
    output = data["output"]
    usage = data.get("usage") or {}
    prompt, completion = usage.get("input_tokens") or 0, usage.get("output_tokens") or 0
    calls = [{"id": o["call_id"], "type": "function", "function": {"name": o["name"], "arguments": o.get("arguments") or "{}"}}
             for o in output if o.get("type") == "function_call"]
    text = "\n".join(c.get("text", "") for o in output if o.get("type") == "message" for c in o.get("content") or []
                     if c.get("type") == "output_text")
    summary = "\n".join(s.get("text", "") for o in output if o.get("type") == "reasoning" for s in o.get("summary") or [])
    finish = "tool_calls" if calls else (data.get("incomplete_details") or {}).get("reason") or "stop"
    return _normalized(data.get("id"), data.get("model") or "", payload["model"], finish,
                       {"role": "assistant", "content": text or None, "reasoning": summary or None, "tool_calls": calls,
                        "responses_output": output},
                       prompt, completion, (usage.get("input_tokens_details") or {}).get("cached_tokens") or 0,
                       (usage.get("output_tokens_details") or {}).get("reasoning_tokens"),
                       header if header is not None else usage.get("total_cost"), header is not None)


def body(model, reasoning, messages, tools=None, max_tokens=MAX_COMPLETION_TOKENS):
    """Chat-completions request. Function tools are only accepted with reasoning_effort "none"."""
    payload = {"model": model, "messages": convert(messages), "max_completion_tokens": max_tokens,
               "reasoning_effort": reasoning}
    if tools:
        payload.update(tools=tools, tool_choice="auto")
    return payload


def chat(payload, *, key, timeout=90):
    """One chat-completions request (no function tools), normalized to the shared shape."""
    header, data = _post("/chat/completions", payload, key, timeout)
    if not isinstance(data, dict) or not data.get("choices"):
        raise ProviderError("unified response without choices; charge uncertain", retryable=True)
    usage = data.get("usage") or {}
    message = data["choices"][0].get("message") or {}
    return _normalized(data.get("id"), data.get("model") or "", payload["model"], data["choices"][0].get("finish_reason"),
                       {"role": "assistant", "content": message.get("content"), "reasoning": None,
                        "tool_calls": message.get("tool_calls") or []},
                       usage.get("prompt_tokens") or 0, usage.get("completion_tokens") or 0,
                       (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0,
                       (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                       header if header is not None else usage.get("total_cost"), header is not None)


def _normalized(rid, returned, model, finish, message, prompt, output, cached, reasoning_tokens, reported, from_header):
    price = MODELS[model]["price"]
    listed = price["input"] * prompt + price["output"] * output  # cache discounts ignored: upper bound
    # Deployments report e.g. "gpt-5.6-luna-2026-07-09" or "dvue-aoai-001-gpt-5.6-luna".
    return {"id": rid, "model": model if model in returned else returned, "model_version": returned,
            "choices": [{"finish_reason": finish, "message": message}],
            "usage": {"prompt_tokens": prompt, "completion_tokens": output, "cached_tokens": cached,
                      "reasoning_tokens": reasoning_tokens,
                      "cost": f"{float(reported):.10f}" if reported is not None else f"{listed:.10f}",
                      "cost_source": "gateway_header" if from_header else
                                     "usage_total_cost" if reported is not None else "list_price",
                      "list_price_cost": f"{listed:.10f}"}}
