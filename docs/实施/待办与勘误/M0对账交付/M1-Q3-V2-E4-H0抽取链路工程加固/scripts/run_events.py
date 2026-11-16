# -*- coding: utf-8 -*-
"""★ H0 §四 P0：★ **运行事件记录与统计不可覆盖**（★ 影子层，★ 不改生产）。

★ 三个必须区分的概念：
  · ★ ``actual_llm_request`` —— ★ 真正发出的 HTTP 请求（★ 计入预算与费用）
  · ★ ``cache_hit``           —— ★ 命中缓存，★ **零请求、零 token、零费用**
  · ★ ``local_replay``        —— ★ 离线重放，★ **零请求、零 token、零费用**

★ 设计要点：
  1. ★ 每次运行唯一 ``run_id``；★ 每次实际请求唯一 ``request_attempt_id``
  2. ★ **追加式**事件记录（★ 永不覆盖）
  3. ★ **每次运行汇总由事件记录重新计算**（★ 不从可覆盖的 stats 读取）
  4. ★ 重试与首次请求**分别**记录
  5. ★ **一个请求处理多个块** ⇒ 请求数与块数**独立统计**
  6. ★ 解析失败后重试**保留首次失败证据**
  7. ★ 缺失的历史 token 数据标 **unavailable**（★ **不得估算后写成真实值**）
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import time
import uuid

ACTUAL = "actual_llm_request"
CACHE = "cache_hit"
REPLAY = "local_replay"

PRICE_IN = 0.15 / 1e6      # ★ USD / token（★ 闲时价，★ deepseek-flash）
PRICE_OUT = 0.60 / 1e6


class RunEventLog:
    """★ 追加式运行事件日志（★ 不可覆盖）。"""

    def __init__(self, out_dir, run_id: str = None, *, protocol: str = "",
                 entry_type: str = ""):
        self.out_dir = pathlib.Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.protocol = protocol
        self.entry_type = entry_type
        self.path = self.out_dir / f"{self.run_id}.events.jsonl"
        # ★ 追加模式打开（★ 永不覆盖已有事件）
        self._fh = self.path.open("a", encoding="utf-8")
        self._seq = 0

    # ---------- 写入 ----------
    def record(self, event_kind: str, **kw) -> str:
        """★ 追加一条事件（★ 返回 request_attempt_id）。"""
        self._seq += 1
        _rid = kw.pop("request_attempt_id", None) or \
            f"{self.run_id}-a{self._seq:04d}"
        _ev = {
            "run_id": self.run_id,
            "event_kind": event_kind,
            "request_attempt_id": _rid,
            "event_seq": self._seq,
            "ts": time.time(),
            "protocol": kw.pop("protocol", self.protocol),
            "entry_type": kw.pop("entry_type", self.entry_type),
            **kw}
        self._fh.write(json.dumps(_ev, ensure_ascii=False) + "\n")
        self._fh.flush()
        return _rid

    def record_actual(self, **kw) -> str:
        """★ 记录一次**真实** LLM 请求（★ 计入预算）。"""
        return self.record(ACTUAL, **kw)

    def record_cache_hit(self, **kw) -> str:
        return self.record(CACHE, **kw)

    def record_replay(self, **kw) -> str:
        return self.record(REPLAY, **kw)

    def record_failure(self, *, attempt_of: str = None, error_stage: str = "",
                       error_type: str = "", error_message: str = "",
                       **kw) -> str:
        """★ 记录失败（★ **保留首次失败证据**；★ 重试单独记一条 actual）。"""
        return self.record("llm_failure", attempt_of=attempt_of,
                           error_stage=error_stage, error_type=error_type,
                           error_message=str(error_message)[:400], **kw)

    def close(self):
        try:
            self._fh.close()
        except Exception:
            pass

    # ---------- 由事件重算汇总 ----------
    def events(self):
        if not self.path.is_file():
            return []
        return [json.loads(l) for l in
                self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def summarize(self) -> dict:
        """★ **由事件记录重新计算**汇总（★ 绝不使用可覆盖的 stats）。"""
        _evs = self.events()
        _actual = [e for e in _evs if e["event_kind"] == ACTUAL]
        _cache = [e for e in _evs if e["event_kind"] == CACHE]
        _replay = [e for e in _evs if e["event_kind"] == REPLAY]
        _fail = [e for e in _evs if e["event_kind"] == "llm_failure"]
        _retries = [e for e in _actual if e.get("is_retry")]
        _blocks = set()
        for e in _evs:          # ★ ★ 含失败事件（★ 失败涉及的块也要计入）
            for _b in (e.get("block_ids") or []):
                _blocks.add(_b)
        _tin = sum(int(e.get("input_tokens") or 0) for e in _actual)
        _tout = sum(int(e.get("output_tokens") or 0) for e in _actual)
        return {
            "★ run_id": self.run_id,
            "★ actual_llm_request": len(_actual),
            "★ cache_hit": len(_cache),
            "★ local_replay": len(_replay),
            "★ failure_events": len(_fail),
            "★ retry_requests": len(_retries),
            "★ 首请求数": len(_actual) - len(_retries),
            "★ 涉及块数（★ 与请求数独立）": len(_blocks),
            "★ input_tokens（★ 仅真实请求）": _tin,
            "★ output_tokens（★ 仅真实请求）": _tout,
            "★ token 合计（★ 仅真实请求）": _tin + _tout,
            "★ 估算费用 USD（★ 仅真实请求）": round(
                _tin * PRICE_IN + _tout * PRICE_OUT, 8),
            "★ ★ 不可覆盖性": "★ 汇总由追加式事件重算 ⇒ ★ 后续复核【无法覆盖】首次统计",
            "★ 事件文件": str(self.path),
        }


def summarize_file(path, *, run_id=None) -> dict:
    """★ 从**已有**事件文件重算汇总（★ 用于历史复核）。"""
    _p = pathlib.Path(path)
    if not _p.is_file():
        return {"★ 状态": "★ unavailable（★ 事件文件不存在）",
                "★ 结论": "★ **不可独立复算**"}
    _evs = [json.loads(l) for l in _p.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    _actual = [e for e in _evs if e["event_kind"] == ACTUAL]
    _cache = [e for e in _evs if e["event_kind"] == CACHE]
    _replay = [e for e in _evs if e["event_kind"] == REPLAY]
    _fail = [e for e in _evs if e["event_kind"] == "llm_failure"]
    _retries = [e for e in _actual if e.get("is_retry")]
    _blocks = set()
    for e in _evs:          # ★ ★ 含失败事件（★ 失败涉及的块也要计入）
        for _b in (e.get("block_ids") or []):
            _blocks.add(_b)
    _tin = sum(int(e.get("input_tokens") or 0) for e in _actual)
    _tout = sum(int(e.get("output_tokens") or 0) for e in _actual)
    return {
        "★ run_id": run_id or (_evs[0]["run_id"] if _evs else None),
        "★ actual_llm_request": len(_actual),
        "★ cache_hit": len(_cache),
        "★ local_replay": len(_replay),
        "★ failure_events": len(_fail),
        "★ retry_requests": len(_retries),
        "★ 首请求数": len(_actual) - len(_retries),
        "★ 涉及块数": len(_blocks),
        "★ input_tokens": _tin, "★ output_tokens": _tout,
        "★ token 合计": _tin + _tout,
        "★ 估算费用 USD": round(_tin * PRICE_IN + _tout * PRICE_OUT, 8),
        "★ 事件文件": str(_p),
        "★ 事件文件 SHA256": hashlib.sha256(_p.read_bytes()).hexdigest(),
    }


__all__ = ["ACTUAL", "CACHE", "REPLAY", "RunEventLog", "summarize_file"]
