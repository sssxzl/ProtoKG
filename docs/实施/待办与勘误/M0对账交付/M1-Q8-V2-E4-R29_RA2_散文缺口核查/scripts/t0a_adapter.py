# -*- coding: utf-8 -*-
"""T0-A 隔离适配器：显式非思考模式 + 载荷自检（不进入生产路径）。

只被 T0-A 隔离运行脚本使用；`core/llm.py` 一行不改。
"""
from __future__ import annotations

import json
import urllib.request

BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-flash"
TEMPERATURE = 0.1
MAX_TOKENS = 4000
RESPONSE_FORMAT = {"type": "json_object"}
THINKING = {"type": "disabled"}


class PayloadError(RuntimeError):
    pass


def build_payload(system: str, user: str, *, model: str = MODEL,
                  max_tokens: int = MAX_TOKENS,
                  temperature: float = TEMPERATURE) -> dict:
    """构造请求体。thinking 放**顶层**（等价于 SDK 的 extra_body）。"""
    return {
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": dict(RESPONSE_FORMAT),
        "thinking": dict(THINKING),
    }


def assert_payload_ok(payload: dict, *, expect_max_tokens: int = MAX_TOKENS) -> None:
    """发请求前的硬校验；任一不符即抛 PayloadError（在网络发出前终止）。"""
    if payload.get("model") != MODEL:
        raise PayloadError(f"model 不符：{payload.get('model')}")
    th = payload.get("thinking")
    if not isinstance(th, dict) or th.get("type") != "disabled":
        raise PayloadError(f"thinking 未显式关闭：{th}")
    if int(payload.get("max_tokens", -1)) != expect_max_tokens:
        raise PayloadError(f"max_tokens 不符：{payload.get('max_tokens')}")
    rf = payload.get("response_format")
    if not isinstance(rf, dict) or rf.get("type") != "json_object":
        raise PayloadError(f"response_format 不符：{rf}")
    if abs(float(payload.get("temperature", -1)) - TEMPERATURE) > 1e-9:
        raise PayloadError(f"temperature 不符：{payload.get('temperature')}")


class T0AClient:
    """最小 HTTP 客户端；只实现 chat_json，不带重试。"""

    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = MODEL
        self.last_error = None

    def chat_json(self, *, system: str, user: str, temperature: float = TEMPERATURE,
                  max_tokens: int = MAX_TOKENS) -> dict:
        payload = build_payload(system, user, max_tokens=max_tokens,
                                temperature=temperature)
        assert_payload_ok(payload, expect_max_tokens=max_tokens)
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:   # noqa: S310
            raw = r.read().decode("utf-8")
        data = json.loads(raw)
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        self.last_call_meta = {
            "finish_reason": choice.get("finish_reason"),
            "input_tokens": (data.get("usage") or {}).get("prompt_tokens"),
            "output_tokens": (data.get("usage") or {}).get("completion_tokens"),
        }
        try:
            return json.loads(content) if content.strip() else {}
        except ValueError as exc:
            raise ValueError(f"JSONDecodeError: {exc}") from exc
