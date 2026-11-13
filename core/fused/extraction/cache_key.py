# -*- coding: utf-8 -*-
"""core/fused/extraction/cache_key.py —— **缓存键的版本化**（第一批）。

★ 对应改进计划 §6：

  | 项 | 内容 |
  |---|---|
  | 缓存键 | 提示版本 + **模型标识** + **推理配置**（温度 / 输出预算）+
    **解析器版本** + **Schema 版本** + **校验器版本** + 输入指纹 |
  | 模型快照 | ★ 记录供应商返回的**实际模型版本** ⇒ 规避「模型别名指向的底层版本变化」 |

★ ★ **两条结论要分开写**（★ 文档措辞纪律）
  ① **缓存命中时产物可复现**（可保证）
  ② **重新调用同一模型能否再次生成逐字节相同的结果**（**不一定成立**）
  ⇒ ⇒ 不得把①说成②。
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

#: ★ **解析器版本**（形态切分 + 各通道的规则版本）
#:   ⇒ 解析规则变更 ⇒ 缓存自动失效（避免用旧结果冒充新结果）
PARSER_VERSION: str = "rfc-parser-v1"

#: ★ **Schema 版本**（中间表示的字段结构）
SCHEMA_VERSION: str = "rfc-norm-schema-v1"

#: ★ **校验器版本**（证据过滤 / 语义校验规则的版本）
VERIFIER_VERSION: str = "normative-verifier-v1"

#: 默认推理配置（★ 进缓存键 ⇒ 推理配置变化 ⇒ 缓存失效）
DEFAULT_TEMPERATURE: float = 0.1
DEFAULT_MAX_TOKENS: int = 16000


def _env(*names: str, default: str = "") -> str:
    for _n in names:
        _v = os.environ.get(_n)
        if _v:
            return str(_v)
    return default


def model_identity() -> str:
    """**模型标识**（★ 进缓存键）。

    读取优先级：``LLM_MODEL`` → ``DEEPSEEK_MODEL`` → 构造参数默认值。
    """
    return _env("LLM_MODEL", "DEEPSEEK_MODEL", default="deepseek-chat")


def inference_config(temperature: Optional[float] = None,
                     max_tokens: Optional[int] = None) -> dict:
    """**推理配置**（★ 进缓存键）。"""
    return {
        "temperature": (DEFAULT_TEMPERATURE if temperature is None
                        else float(temperature)),
        "max_tokens": (DEFAULT_MAX_TOKENS if max_tokens is None
                       else int(max_tokens)),
    }


def cache_key(*, prompt_version: str, input_fingerprint: str,
              temperature: Optional[float] = None,
              max_tokens: Optional[int] = None,
              model: Optional[str] = None,
              model_snapshot: Optional[str] = None,
              prompt_digest: str = "",
              parser_version: str = PARSER_VERSION,
              schema_version: str = SCHEMA_VERSION,
              verifier_version: str = VERIFIER_VERSION) -> str:
    """计算**版本化的缓存键**。

    ★ 任一要素变化 ⇒ 键变化 ⇒ **旧缓存自动失效**（不会用旧结果冒充新结果）。
    ★ `model_snapshot` 为**供应商返回的实际模型版本**（若有）⇒ 与 `model` 标识
      一起进键 ⇒ ⇒ 规避「别名指向的底层版本变化」。
    """
    _parts = {
        "prompt_version": str(prompt_version),
        # ★ prompt **内容**指纹（★ 改 prompt ⇒ 键变 ⇒ 旧缓存自动失效）
        "prompt_digest": str(prompt_digest or ""),
        "model": str(model or model_identity()),
        "model_snapshot": str(model_snapshot or ""),
        "inference": inference_config(temperature, max_tokens),
        "parser_version": str(parser_version),
        "schema_version": str(schema_version),
        "verifier_version": str(verifier_version),
        "input": str(input_fingerprint),
    }
    _raw = json.dumps(_parts, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))
    return hashlib.sha256(_raw.encode("utf-8")).hexdigest()


def fingerprint_texts(*texts: str) -> str:
    """对多段文本做**输入指纹**（★ 顺序敏感 ⇒ 段落顺序变化 ⇒ 键变化）。"""
    _h = hashlib.sha256()
    for _t in texts:
        _h.update(hashlib.sha256((_t or "").encode("utf-8")).digest())
    return _h.hexdigest()


def key_manifest(key: str) -> dict:
    """把缓存键的**构成要素**记录下来（★ 可审计 ⇒ 「可复现」的可解释性）。"""
    return {
        "key": key,
        "parser_version": PARSER_VERSION,
        "schema_version": SCHEMA_VERSION,
        "verifier_version": VERIFIER_VERSION,
        "model": model_identity(),
        "note": ("★ 「缓存命中时产物可复现」可保证；"
                 "★ 「重新调用同一模型能否逐字节相同」**不一定成立**"),
    }


__all__ = [
    "PARSER_VERSION", "SCHEMA_VERSION", "VERIFIER_VERSION",
    "DEFAULT_TEMPERATURE", "DEFAULT_MAX_TOKENS",
    "model_identity", "inference_config", "cache_key", "fingerprint_texts",
    "key_manifest",
]
