"""One chat transport for both providers.

Anthropic and OpenAI differ in three places that matter here: the endpoint, the
auth header, and whether JSON mode is a request parameter or a prompt
instruction. Everything else is the same call, so it is one function rather than
three near copies spread across the synthesiser, the expander and the eval judge.

No SDK. Both APIs are a single POST with a JSON body, and a dependency that has
to be installed before the demo runs is a dependency that can fail before the
demo runs.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request

from . import config

FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.M)


class LLMError(RuntimeError):
    pass


def api_key(provider: str) -> str:
    env = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}[provider]
    key = os.environ.get(env)
    if not key:
        raise LLMError(f"{env} is not set")
    return key


def chat(system: str, user: str, *, provider: str | None = None, model: str | None = None,
         max_tokens: int = 2000, json_mode: bool = True, timeout: int = 120) -> str:
    """Send one turn, return the text. Raises LLMError with the provider's own message."""
    provider = provider or config.LLM_PROVIDER
    model = model or config.model_for(provider)
    key = api_key(provider)

    if provider == "anthropic":
        url = f"{config.ANTHROPIC_BASE.rstrip('/')}/v1/messages"
        body = {"model": model, "max_tokens": max_tokens, "temperature": 0,
                "system": system, "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01",
                   "content-type": "application/json"}
    elif provider == "openai":
        url = f"{config.OPENAI_BASE.rstrip('/')}/v1/chat/completions"
        body = {"model": model, "max_completion_tokens": max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if json_mode:
            # Native JSON mode. The word "json" must appear in the prompt or the
            # API rejects the request, which the synthesis schema block satisfies.
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    else:
        raise LLMError(f"provider {provider!r} has no chat transport")

    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        # Surfaced rather than swallowed: "model not found" and "insufficient
        # quota" are the two most common first run failures, and both are
        # diagnosable from the provider's own words.
        raise LLMError(f"{provider} {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise LLMError(f"{provider} unreachable: {exc.reason}") from exc

    if provider == "anthropic":
        return "".join(b.get("text", "") for b in payload.get("content", []))
    choices = payload.get("choices") or []
    if not choices:
        raise LLMError(f"openai returned no choices: {str(payload)[:200]}")
    return choices[0].get("message", {}).get("content") or ""


def parse_json(text: str) -> dict | list:
    """Tolerant extraction: a model that wraps JSON in prose still parses."""
    cleaned = FENCE.sub("", (text or "").strip())
    for opener, closer in (("{", "}"), ("[", "]")):
        start, end = cleaned.find(opener), cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"no JSON in model output: {(text or '')[:200]!r}")
