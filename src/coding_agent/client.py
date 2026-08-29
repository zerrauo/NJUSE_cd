"""Minimal OpenAI-compatible client; no agent SDK is used here."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import Settings


class ModelClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        payload = json.dumps({
            "model": self.settings.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.2,
        }).encode("utf-8")
        request = Request(
            f"{self.settings.base_url}/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {self.settings.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"模型 API 返回 HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"无法连接模型 API: {exc.reason}") from exc
        except TimeoutError as exc:
            raise RuntimeError("模型 API 请求超时") from exc

        try:
            return data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"模型响应格式异常: {str(data)[:500]}") from exc

