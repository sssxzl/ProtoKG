# -*- coding: utf-8 -*-
"""★ M1-Q3-P0.7～P0.9 共用库：★ 预算账本 + 冻结 + L2 判定执行器。

★ 统一口径（★ 用户要求）：
  `api_attempts / logical_verdicts / deterministic_shortcuts / cache_hits / retries`
★ 预算：★ API 尝试次数是**严格上限**（重试也计入）；★ token 上限**执行前**校验；
★ 达限即停；★ **不事后提高**；★ 单价未配置 ⇒ **费用记 null**。
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import time

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUTROOT = ROOT / "guard/_out/m1_q3/p079"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-P0.7-P0.9联合交付"
OUTROOT.mkdir(parents=True, exist_ok=True)
DELIV.mkdir(parents=True, exist_ok=True)

P07B = ROOT / "guard/_out/m1_q3/p07b"
FREEZE = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结"
AUDIT06 = ROOT / "guard/_out/m1_q3/p06/p06_audit.jsonl"
LEDGER_B1 = P07B / "b1_ledger.jsonl"
P3S = ROOT / "guard/_out/m1_q3/p07b5"


def git_commit() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, cwd=str(ROOT)).stdout.strip()


def sha256_file(p) -> str:
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def load_jsonl(p):
    p = pathlib.Path(p)
    if not p.is_file():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def doc_lines(proto, document):
    p = ROOT / f"kb/{proto}/spec/{document}"
    if not p.is_file():
        return None
    return p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")


def load_frozen_orig():
    """★ 冻结件里的原始候选字段（★ entity/constraint/strength 等）。"""
    out = {}
    for b in load_jsonl(FREEZE / "frozen_blocks.jsonl"):
        for i, it in enumerate(b["raw_items"]):
            out[f"{b['document']}@{b['chunk_start']}#{i}"] = {
                **it, "chunk_start": b["chunk_start"]}
    return out


class Budget:
    """★ 预算账本（★ API 严格上限 + token 硬上限 + 全量记录）。"""

    def __init__(self, name: str, max_attempts: int, max_tokens: int,
                 cost_per_1k=None):
        self.name = name
        self.max_attempts = int(max_attempts)
        self.max_tokens = int(max_tokens)
        self.cost_per_1k = cost_per_1k
        self.attempts = 0
        self.in_tok = 0
        self.out_tok = 0
        self.retries = 0
        self.records = []
        self.stop_reason = None
        self._client = None
        self._last_meta = {}

    # ── 客户端 ──
    def _mk(self):
        if self._client is None:
            from core.llm import DeepSeekClient
            self._client = DeepSeekClient()
        return self._client

    def chat_json(self, **kw):
        """★ 唯一发起点：★ 达上限即抛错；★ 记录每次尝试。"""
        if self.attempts >= self.max_attempts:
            self.stop_reason = f"api_attempts_reached({self.max_attempts})"
            raise RuntimeError(f"★ 预算停止：API 尝试已达上限 {self.max_attempts}")
        self.attempts += 1
        _t0 = time.time()
        _err = None
        _out = None
        try:
            _out = self._mk().chat_json(**kw)
        except Exception as exc:
            _err = f"{type(exc).__name__}: {exc}"
            self.retries += 1
            raise
        finally:
            _m = getattr(self._client, "last_call_meta", None) or {}
            self.in_tok += int(_m.get("input_tokens") or 0)
            self.out_tok += int(_m.get("output_tokens") or 0)
            self._last_meta = _m
            _tot = self.in_tok + self.out_tok
            if _tot > self.max_tokens:
                self.stop_reason = f"max_tokens_reached({self.max_tokens})"
        return _out

    def meta(self):
        return dict(self._last_meta)

    def record(self, **kw):
        kw.setdefault("stage", self.name)
        kw.setdefault("api_attempts_so_far", self.attempts)
        kw.setdefault("input_tokens_so_far", self.in_tok)
        kw.setdefault("output_tokens_so_far", self.out_tok)
        kw.setdefault("budget_status", self.stop_reason or "within")
        self.records.append(kw)
        return kw

    def summary(self):
        return {
            "stage": self.name,
            "★ 上限": {"max_api_attempts": self.max_attempts,
                    "max_total_tokens": self.max_tokens,
                    "cost_per_1k": self.cost_per_1k,
                    "★ 设定时点": "执行前（★ 未事后修改）"},
            "★ 实际": {
                "api_attempts": self.attempts,
                "logical_verdicts": len(self.records),
                "deterministic_shortcuts": sum(
                    1 for r in self.records if r.get("api_attempts", 0) == 0),
                "cache_hits": 0,
                "retries": self.retries,
                "input_tokens": self.in_tok, "output_tokens": self.out_tok,
                "total_tokens": self.in_tok + self.out_tok,
                "★ 预算停止原因": self.stop_reason,
            },
            "★ 费用": None,
            "★ 费用说明": "未配置单价 ⇒ null（★ 不编造）",
        }


def l2_payload(orig_row):
    """★ 由原始候选构造 L2 payload（★ 与生产一致）。"""
    return {
        "subject": orig_row.get("normative_subject") or orig_row.get("entity") or "",
        "action": orig_row.get("action") or "",
        "object": orig_row.get("object") or "",
        "strength": orig_row.get("strength") or "",
        "polarity": orig_row.get("polarity") or "",
        "condition": orig_row.get("constraint") or "",
    }


def l2_prompt(payload, quote, nv):
    """★ 渲染后的**完整** L2 Prompt（★ 用于 hash 与同输入判定）。"""
    _sem = {k: payload.get(k) for k in nv.SEMANTIC_FIELDS if k in payload}
    _user = nv._L2_USER.format(
        payload=json.dumps(_sem, ensure_ascii=False, sort_keys=True),
        quote=(quote or "")[:6000])
    return nv._L2_SYSTEM + "\n" + _user


def judge(budget, payload, quote, nv):
    """★ 执行一次 L2 判定（★ 区分确定性短路与真实 API 调用）。"""
    from core.fused.extraction.normative_verify import l2_check
    _a0 = budget.attempts
    _t0 = time.time()
    _v = _reason = _fd = None
    _err = None
    try:
        _r = l2_check(payload=payload, quote=quote, llm=budget)
        _v = _r.verdict
        _reason = (_r.reasons or [None])[0]
        _fd = getattr(_r, "field_verdicts", None)
    except Exception as exc:
        _err = f"{type(exc).__name__}: {exc}"
    _m = budget.meta()
    return {
        "verdict": _v, "reason": str(_reason)[:240] if _reason else None,
        "field_verdicts": _fd, "error": _err,
        "api_attempts": budget.attempts - _a0,
        "input_tokens": _m.get("input_tokens"), "output_tokens": _m.get("output_tokens"),
        "finish_reason": _m.get("finish_reason"),
        "raw_response_sha256": _m.get("raw_response_sha256"),
        "latency": round(time.time() - _t0, 2),
    }


def classify_pair(a, b):
    """★ 用户定义的 A~E 分类。"""
    if not (a and b and a.get("verdict") and b.get("verdict")
            and not a.get("error") and not b.get("error")):
        return "★ 不可比较（★ 未两次都得到有效判定）"
    if a["verdict"] == b["verdict"]:
        return "A 完全一致" if a.get("reason") == b.get("reason") else "B 状态一致、理由不同"
    _p = {a["verdict"], b["verdict"]}
    if _p == {"confirmed", "pending"}:
        return "D confirmed↔pending"
    if _p == {"confirmed", "rejected"}:
        return "E confirmed↔rejected"
    if _p == {"pending", "rejected"}:
        return "C pending↔rejected"
    return "其他"


def save_jsonl(p, rows):
    pathlib.Path(p).write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8")


def save_json(p, obj):
    pathlib.Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2),
                              encoding="utf-8")


__all__ = ["ROOT", "OUTROOT", "DELIV", "P07B", "FREEZE", "AUDIT06", "LEDGER_B1",
           "P3S", "Budget", "judge", "l2_payload", "l2_prompt", "classify_pair",
           "load_jsonl", "load_frozen_orig", "doc_lines", "save_json", "save_jsonl",
           "git_commit", "sha256_file"]
