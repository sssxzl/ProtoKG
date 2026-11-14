# -*- coding: utf-8 -*-
"""LLM 调用诊断记录（★ M1-③：只观测，不改语义）。

★ 目的：让**每次** LLM 调用与解析失败都可追溯，并能解释产出数量变化。
★ 约束：
  · **不改变** Prompt / 温度 / 调用预算 / 重试策略 / 抽取语义
  · **不增加**自动 JSON 修复行为（本轮只记录失败）
  · 诊断产物独立落盘，**不改变**既有正式 Fact / Seed 内容
  · ★ **诊断日志本身写入失败时，不得使原本成功的抽取任务变成失败**
  · ★ 不记录 API Key 等敏感信息；原始响应只存**哈希 + 安全诊断片段**
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

#: ★ 诊断目录（★ **不入 Git**：由 .gitignore 的 ``/derived/diagnostics/`` 排除）
DIAG_DIR = pathlib.Path("derived") / "diagnostics" / "llm_calls"

#: ★ 原始响应诊断片段的最大长度（★ 只截前 N 字符 ⇒ 不落整份响应）
RAW_HEAD_CHARS = 400

#: ★ 错误阶段取值
STAGE_REQUEST = "request"
STAGE_RESPONSE = "model_response"
STAGE_JSON_PARSE = "json_parse"
STAGE_SCHEMA = "schema_validation"
STAGE_MAPPING = "mapping"
STAGE_NONE = None


def sha256_text(text: str) -> str:
    """文本 SHA-256（★ 用于原始响应指纹）。"""
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _safe_head(text: Optional[str]) -> Optional[str]:
    """原始响应的**安全诊断片段**（★ 截断 + 去控制字符）。"""
    if text is None:
        return None
    _t = str(text)
    _t = "".join(ch if ch.isprintable() or ch in "\n\t" else "�" for ch in _t)
    if len(_t) > RAW_HEAD_CHARS:
        _t = _t[:RAW_HEAD_CHARS] + "…[truncated]"
    return _t


@dataclass
class LLMCallRecord:
    """★ 单次 LLM 调用的结构化记录（★ 字段名与验收要求一一对应）。"""

    run_id: str
    protocol: str
    document: Optional[str] = None
    entry_type: Optional[str] = None            # "document" / "paragraph"
    chunk_id: Optional[str] = None
    source_span: Optional[str] = None
    chunk_hash: Optional[str] = None
    model: Optional[str] = None
    prompt_digest: Optional[str] = None
    parser_version: Optional[str] = None
    cache_hit: Optional[bool] = None
    cache_key: Optional[str] = None
    attempt: Optional[int] = None               # ★ 重试序号（1 起）
    request_index: Optional[int] = None         # ★ 本次运行的请求序号
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    finish_reason: Optional[str] = None
    error_stage: Optional[str] = None
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    raw_response_sha256: Optional[str] = None
    raw_response_head: Optional[str] = None
    outcome: str = "success"                    # success/failed/retry_recovered/abandoned
    blocks_without_candidate: Optional[int] = None
    elapsed_s: Optional[float] = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


@dataclass
class LLMDiagnostics:
    """★ 一次运行的诊断收集器（★ 写盘失败不影响主流程）。"""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    protocol: str = ""
    entry_type: str = ""
    out_dir: pathlib.Path = field(default=DIAG_DIR)
    records: list = field(default_factory=list)
    input_blocks: int = 0        # ★ 输入块数（★ 由 _extract_blocks 回填）
    _seq: int = 0
    _write_errors: list = field(default_factory=list)

    # ---------------- 记录 ----------------
    def new_record(self, **kw) -> LLMCallRecord:
        self._seq += 1
        kw.setdefault("run_id", self.run_id)
        kw.setdefault("protocol", self.protocol)
        kw.setdefault("entry_type", self.entry_type)
        kw.setdefault("request_index", self._seq)
        _r = LLMCallRecord(**kw)
        self.records.append(_r)
        return _r

    # ---------------- 落盘（★ 失败不影响主流程）----------------
    def flush(self) -> Optional[str]:
        """把记录写到受保护的本地诊断目录（★ 失败 ⇒ 返回 None，不抛异常）。"""
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            _p = self.out_dir / f"{self.run_id}.jsonl"
            with _p.open("w", encoding="utf-8") as f:
                for _r in self.records:
                    f.write(json.dumps(_r.to_dict(), ensure_ascii=False) + "\n")
            _s = self.out_dir / f"{self.run_id}_summary.json"
            _s.write_text(json.dumps(self.summary(), ensure_ascii=False, indent=2),
                          encoding="utf-8")
            return str(_p)
        except Exception as exc:                # noqa: BLE001
            # ★ **诊断写入失败不得使抽取失败** ⇒ 只记录，不抛
            try:
                self._write_errors.append(f"{type(exc).__name__}: {exc}")
            except Exception:                   # noqa: BLE001
                pass
            return None

    # ---------------- 汇总 ----------------
    def summary(self) -> dict:
        """★ 按协议与运行批次汇总（★ 验收要求的六段计数）。"""
        c = {
            "input_blocks": self.input_blocks,
            "llm_calls": 0, "cache_hits": 0,
            "parse_ok": 0, "parse_failed": 0, "mapped_candidates": 0,
        }
        stages = {}
        outcomes = {}
        finish_reasons = {}
        for _r in self.records:
            # ★ 「mapping」是**产物映射阶段**的记录 ⇒ **不是一次 LLM 调用**
            if _r.error_stage == STAGE_MAPPING:
                continue
            c["llm_calls"] += 1
            if _r.cache_hit:
                c["cache_hits"] += 1
            if _r.error_stage == STAGE_JSON_PARSE:
                c["parse_failed"] += 1
            elif _r.outcome == "success" and _r.error_stage != STAGE_MAPPING:
                c["parse_ok"] += 1
            if _r.error_stage:
                stages[_r.error_stage] = stages.get(_r.error_stage, 0) + 1
            outcomes[_r.outcome] = outcomes.get(_r.outcome, 0) + 1
            if _r.finish_reason:
                finish_reasons[_r.finish_reason] = finish_reasons.get(_r.finish_reason, 0) + 1
        # ★ 「映射候选数」= 产物映射阶段记录里的丢弃数（★ 口径见报告）
        c["mapped_candidates"] = sum(
            (_r.blocks_without_candidate or 0) for _r in self.records
            if _r.error_stage == STAGE_MAPPING)
        return {
            "run_id": self.run_id,
            "protocol": self.protocol,
            "entry_type": self.entry_type,
            "ts_start": min((_r.ts for _r in self.records), default=None),
            "ts_end": max((_r.ts for _r in self.records), default=None),
            "counters": c,
            "error_stages": stages,
            "outcomes": outcomes,
            "finish_reasons": finish_reasons,
            "write_errors": list(self._write_errors),
        }


def summarize_runs(diag_dir: pathlib.Path = DIAG_DIR) -> dict:
    """★ 汇总一个目录下的所有运行（★ 按协议 + 运行批次）。"""
    out = {}
    if not diag_dir.is_dir():
        return out
    for _s in sorted(diag_dir.glob("*_summary.json")):
        try:
            _d = json.loads(_s.read_text(encoding="utf-8"))
        except Exception:                       # noqa: BLE001
            continue
        out[_s.name.replace("_summary.json", "")] = {
            "protocol": _d.get("protocol"),
            "entry_type": _d.get("entry_type"),
            "counters": _d.get("counters"),
            "error_stages": _d.get("error_stages"),
            "outcomes": _d.get("outcomes"),
            "finish_reasons": _d.get("finish_reasons"),
        }
    return out


__all__ = [
    "DIAG_DIR", "LLMCallRecord", "LLMDiagnostics", "sha256_text",
    "summarize_runs",
    "STAGE_REQUEST", "STAGE_RESPONSE", "STAGE_JSON_PARSE",
    "STAGE_SCHEMA", "STAGE_MAPPING",
]
