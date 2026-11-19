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
MAX_TOKENS = 8000          # R29-RA2 r2：4000 → 8000（输出容量修正）
RESPONSE_FORMAT = {"type": "json_object"}
THINKING = {"type": "disabled"}


class PayloadError(RuntimeError):
    pass


class EmptyContent(ValueError):
    pass


class SchemaError(ValueError):
    pass


class FinishReasonError(RuntimeError):
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


def assert_payload_ok(payload: dict) -> None:
    """发请求前的硬校验；任一不符即抛 PayloadError（在网络发出前终止）。"""
    if payload.get("model") != MODEL:
        raise PayloadError(f"model 不符：{payload.get('model')}")
    th = payload.get("thinking")
    if not isinstance(th, dict) or th.get("type") != "disabled":
        raise PayloadError(f"thinking 未显式关闭：{th}")
    if int(payload.get("max_tokens", -1)) != MAX_TOKENS:
        raise PayloadError(f"max_tokens 不符：{payload.get('max_tokens')}")
    rf = payload.get("response_format")
    if not isinstance(rf, dict) or rf.get("type") != "json_object":
        raise PayloadError(f"response_format 不符：{rf}")
    if abs(float(payload.get("temperature", -1)) - TEMPERATURE) > 1e-9:
        raise PayloadError(f"temperature 不符：{payload.get('temperature')}")


ALLOWED_FINISH = {"stop"}


def validate_items(content: str, meta: dict, required: tuple[str, ...]) -> dict:
    """通用条目校验：只要求 items 元素含指定字段（用于第二阶段）。"""
    fr = (meta or {}).get("finish_reason")
    if fr not in ALLOWED_FINISH:
        raise FinishReasonError(f"finish_reason={fr!r} 不接受（仅允许 stop）")
    text = (content or "").strip()
    if not text:
        raise EmptyContent("响应内容为空或纯空白")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"JSONDecodeError: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise SchemaError("缺少 items 数组")
    for it in data["items"]:
        if not isinstance(it, dict):
            raise SchemaError("items 元素不是对象")
        for k in required:
            if k not in it:
                raise SchemaError(f"条目缺少字段 {k}")
    return data


def validate_response(content: str, meta: dict) -> dict:
    """把「响应内容 + finish_reason」合成一次校验；不通过即抛，绝不返回空 dict。

    · 空 / 纯空格 ⇒ EmptyContent
    · 非法 JSON ⇒ JSONDecodeError
    · 结构不符 ⇒ SchemaError
    · finish_reason 非 stop（含 length / 缺失 / 未知）⇒ FinishReasonError
    """
    fr = (meta or {}).get("finish_reason")
    if fr not in ALLOWED_FINISH:
        raise FinishReasonError(f"finish_reason={fr!r} 不接受（仅允许 stop）")
    text = (content or "").strip()
    if not text:
        raise EmptyContent("响应内容为空或纯空白")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ValueError(f"JSONDecodeError: {exc}") from exc
    if not isinstance(data, dict):
        raise SchemaError(f"顶层不是对象：{type(data).__name__}")
    items = data.get("items")
    if not isinstance(items, list):
        raise SchemaError("缺少 items 数组")
    for it in items:
        if not isinstance(it, dict):
            raise SchemaError("items 元素不是对象")
        for k in ("doc", "entity", "meaning"):
            if k not in it:
                raise SchemaError(f"条目缺少字段 {k}")
    return data


class T0AClient:
    """最小 HTTP 客户端；只实现 chat_json，不带重试。"""

    def __init__(self, api_key: str, base_url: str = BASE_URL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = MODEL
        self.last_error = None

    def chat_json_for(self, *, system: str, user: str,
                      required: tuple[str, ...] = ("id", "status"),
                      temperature: float = TEMPERATURE,
                      max_tokens: int = MAX_TOKENS) -> dict:
        """第二阶段用：返回通用条目结构，不套用抽取 Schema。"""
        if int(max_tokens) != MAX_TOKENS:
            raise PayloadError(f"固定 max_tokens={MAX_TOKENS}，收到 {max_tokens}")
        payload = build_payload(system, user, max_tokens=MAX_TOKENS,
                                temperature=temperature)
        assert_payload_ok(payload)
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=180) as r:  # noqa: S310
            raw = r.read().decode("utf-8")
        data = json.loads(raw)
        ch = (data.get("choices") or [{}])[0]
        content = (ch.get("message") or {}).get("content") or ""
        self.last_call_meta = {"finish_reason": ch.get("finish_reason"),
                               "input_tokens": (data.get("usage") or {}).get("prompt_tokens"),
                               "output_tokens": (data.get("usage") or {}).get("completion_tokens")}
        return validate_items(content, self.last_call_meta, required)

    def chat_json(self, *, system: str, user: str, temperature: float = TEMPERATURE,
                  max_tokens: int = MAX_TOKENS) -> dict:
        if int(max_tokens) != MAX_TOKENS:
            raise PayloadError(f"T0-A 固定 max_tokens={MAX_TOKENS}，收到 {max_tokens}")
        payload = build_payload(system, user, max_tokens=MAX_TOKENS,
                                temperature=temperature)
        assert_payload_ok(payload)
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
        return validate_response(content, self.last_call_meta)
