"""Multi-provider LLM client with structured output support.

Picks a provider based on `settings.llm_provider`:
  - "azure_openai"  → Azure OpenAI (chat completions)
  - "ollama"        → Local Ollama (/api/chat)
  - "anthropic"     → Anthropic Messages API
  - "google"        → Google Gemini generateContent

Every provider exposes the same async surface:
    await llm.complete(messages, *, schema=None, max_tokens=...)
returning either {"text": str} or a dict matching the JSON schema.
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class LlmError(RuntimeError):
    pass


def _strip_fence(text: str) -> str:
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[1] if "\n" in s else s[3:]
        if s.endswith("```"):
            s = s[: -3]
    return s.strip()


def _parse_structured(raw: str, schema: dict | None) -> Any:
    if schema is None:
        return {"text": raw}
    try:
        return json.loads(_strip_fence(raw))
    except json.JSONDecodeError as exc:
        raise LlmError(f"LLM did not return valid JSON: {exc}\nRaw: {raw[:500]}")


class _AzureOpenAI:
    name = "azure_openai"

    def __init__(self) -> None:
        if not (settings.azure_openai_endpoint and settings.azure_openai_api_key and settings.azure_openai_deployment):
            raise LlmError("Azure OpenAI not configured")

    async def complete(self, messages: list[dict], *, schema: dict | None = None, max_tokens: int = 800) -> Any:
        url = (
            f"{settings.azure_openai_endpoint.rstrip('/')}/openai/deployments/"
            f"{settings.azure_openai_deployment}/chat/completions"
            f"?api-version={settings.azure_openai_api_version}"
        )
        body: dict[str, Any] = {"messages": messages, "max_tokens": max_tokens, "temperature": 0.2}
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": schema, "strict": False},
            }
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=body, headers={"api-key": settings.azure_openai_api_key})
            if resp.status_code >= 400:
                raise LlmError(f"Azure OpenAI {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
        raw = data["choices"][0]["message"]["content"] or ""
        return _parse_structured(raw, schema)


class _Ollama:
    name = "ollama"

    def __init__(self) -> None:
        if not settings.ollama_base_url:
            raise LlmError("Ollama base URL not configured")

    async def complete(self, messages: list[dict], *, schema: dict | None = None, max_tokens: int = 800) -> Any:
        url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"
        body: dict[str, Any] = {
            "model": settings.ollama_model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.2, "num_predict": max_tokens},
        }
        if schema is not None:
            body["format"] = "json"
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(url, json=body)
            if resp.status_code >= 400:
                raise LlmError(f"Ollama {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
        raw = data.get("message", {}).get("content") or ""
        return _parse_structured(raw, schema)


class _Anthropic:
    name = "anthropic"

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise LlmError("Anthropic API key not configured")

    async def complete(self, messages: list[dict], *, schema: dict | None = None, max_tokens: int = 800) -> Any:
        system_msgs = [m["content"] for m in messages if m["role"] == "system"]
        non_system = [m for m in messages if m["role"] != "system"]
        body: dict[str, Any] = {
            "model": settings.anthropic_model,
            "max_tokens": max_tokens,
            "temperature": 0.2,
            "messages": non_system,
        }
        if system_msgs:
            sys_text = "\n\n".join(system_msgs)
            if schema is not None:
                sys_text += (
                    "\n\nReturn ONLY valid JSON matching this schema, no prose, no code fence:\n"
                    + json.dumps(schema)
                )
            body["system"] = sys_text
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                json=body,
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            if resp.status_code >= 400:
                raise LlmError(f"Anthropic {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
        parts = data.get("content", [])
        raw = "".join(p.get("text", "") for p in parts if p.get("type") == "text")
        return _parse_structured(raw, schema)


class _Google:
    name = "google"

    def __init__(self) -> None:
        if not settings.google_api_key:
            raise LlmError("Google API key not configured")

    async def complete(self, messages: list[dict], *, schema: dict | None = None, max_tokens: int = 800) -> Any:
        contents: list[dict] = []
        system_instr = None
        for m in messages:
            if m["role"] == "system":
                system_instr = m["content"] if not system_instr else system_instr + "\n\n" + m["content"]
            else:
                role = "user" if m["role"] == "user" else "model"
                contents.append({"role": role, "parts": [{"text": m["content"]}]})
        body: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {"temperature": 0.2, "maxOutputTokens": max_tokens},
        }
        if system_instr:
            body["systemInstruction"] = {"parts": [{"text": system_instr}]}
        if schema is not None:
            body["generationConfig"]["responseMimeType"] = "application/json"
            body["generationConfig"]["responseSchema"] = schema
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.google_model}:generateContent?key={settings.google_api_key}"
        )
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(url, json=body)
            if resp.status_code >= 400:
                raise LlmError(f"Google {resp.status_code}: {resp.text[:500]}")
            data = resp.json()
        try:
            raw = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raise LlmError(f"Google response missing text: {json.dumps(data)[:500]}")
        return _parse_structured(raw, schema)


_PROVIDERS = {
    "azure_openai": _AzureOpenAI,
    "ollama": _Ollama,
    "anthropic": _Anthropic,
    "google": _Google,
}


_client_cache: dict[str, Any] = {}


def get_llm() -> Any:
    provider = settings.llm_provider
    if provider not in _PROVIDERS:
        raise LlmError(
            f"Unknown LLM provider '{provider}'. Set LLM_PROVIDER to one of: {list(_PROVIDERS)}"
        )
    if provider not in _client_cache:
        _client_cache[provider] = _PROVIDERS[provider]()
    return _client_cache[provider]


def is_configured() -> bool:
    try:
        get_llm()
        return True
    except LlmError:
        return False


async def complete(messages: list[dict], *, schema: dict | None = None, max_tokens: int = 800) -> Any:
    return await get_llm().complete(messages, schema=schema, max_tokens=max_tokens)
