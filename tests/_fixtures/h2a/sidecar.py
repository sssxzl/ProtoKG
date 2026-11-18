# -*- coding: utf-8 -*-
"""★ H2-H2A §三：★ **方案 A 的影子 sidecar**（★ 旁路 provenance / field-flow）。

★ ★ **不接入生产**；★ **不修改旧候选 / Norm / Fact / 正式中枢**
★ ★ 只记录**实际存在**的数据与**确定性转换关系**
★ ★ 记录失败必须**可观察**，★ 但**不得污染原始抽取结果**
★ ★ 同一来源与候选的**重复离线执行必须可区分且可复算**
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib
import time
import uuid

# ★ ★ 字段适用性（★ 与 H1 适用性矩阵一致）
APPLICABILITY = {
    "prose_constraint": {"entity": "required", "meaning": "required",
                  "normative_subject": "optional", "action": "optional",
                  "object": "optional", "strength": "optional",
                  "polarity": "optional", "condition": "optional",
                  "exception": "optional", "constraint": "required",
                  "cross_ref_status": "optional"},
    "prose_semantics": {"entity": "required", "meaning": "required",
                 "normative_subject": "not_applicable", "action": "not_applicable",
                 "object": "not_applicable", "strength": "not_applicable",
                 "polarity": "not_applicable", "condition": "not_applicable",
                 "exception": "not_applicable", "constraint": "optional",
                 "cross_ref_status": "not_applicable"},
}
# ★ canonical 实际承载路径（★ 自 norm.py:513 与 normative_rule.py）
CANONICAL_CARRIER = {
    "entity": "★ Rule Slot / definition aspect（★ 经 name）",
    "meaning": "★ 声明文本（★ 与 constraint 合并进 content）",
    "constraint": "★ 声明文本（★ 降级分支下为**唯一**承载）",
    "normative_subject": "★ Rule Slot 的 subject.name（★ 仅正常路径）",
    "action": "★ Rule Slot qualifiers.action（★ 仅正常路径）",
    "object": "★ Rule Slot qualifiers.object（★ 仅正常路径）",
    "strength": "★ Assertion（★ [RULE:v1] JSON）",
    "polarity": "★ Assertion（★ [RULE:v1] JSON）",
    "condition": "★ Assertion（★ [RULE:v1] JSON）",
    "exception": "★ Assertion（★ [RULE:v1] JSON）",
    "cross_ref_status": "★ Assertion（★ [RULE:v1] JSON）",
    "cross_ref": "★ Assertion（★ [RULE:v1] JSON）",
}
SEMANTIC = ["strength", "polarity", "condition", "exception", "action",
            "object", "cross_ref", "cross_ref_status"]
LOSSLESS = "★ 无损失"
CARRIER_ONLY = "★ 语义仅由声明文本承载（★ 结构化字段未进 Rule Slot/Assertion）"
NOT_APPLICABLE = "★ 字段不适用（★ 非语义损失）"
UNMEASURED = "★ unmeasured（★ 未提供 canonical 真实视图）"
UNRESOLVED = "★ unresolved"


class FieldFlowSidecar:
    """★ 旁路字段流转 sidecar（★ 追加式，★ 失败可观察但不影响抽取）。"""

    def __init__(self, out_dir, *, run_id: str = None,
                 protocol: str = "", entry_type: str = ""):
        self.out_dir = pathlib.Path(out_dir)
        self.run_id = run_id or f"sidecar-{uuid.uuid4().hex[:12]}"
        self.protocol = protocol
        self.entry_type = entry_type
        self.path = self.out_dir / f"{self.run_id}.fieldflow.jsonl"
        self.write_errors = []
        self._seq = 0

    # ---------- 写入（★ 失败只记录，★ 不抛）----------
    def _write(self, rec):
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            return True
        except Exception as exc:                # noqa: BLE001
            self.write_errors.append(f"{type(exc).__name__}: {exc}")
            return False

    def record(self, *, candidate_id: str, knowledge_kind: str,
               source_reference: str, normalized_document_id: str,
               source_sha256: str, source_span, raw_llm: dict,
               derived: dict, norm: dict, mapping_branch: str,
               canonical_carrier: dict = None,
               unresolved_reason: str = "") -> int:
        """★ 记录一条候选的字段流转（★ 逐字段）。"""
        _n = 0
        _applic = APPLICABILITY.get(knowledge_kind, {})
        _known = set(APPLICABILITY.get("prose_constraint", {}).keys()) \
            | set(APPLICABILITY.get("prose_semantics", {}).keys())
        for _f in sorted((set(raw_llm.keys()) | set(norm.keys())) & _known):
            _rv = raw_llm.get(_f)
            _dv = derived.get(_f)
            _nv = norm.get(_f)
            _app = _applic.get(_f, "unknown")
            if _app == "not_applicable":
                _loss = NOT_APPLICABLE
            elif canonical_carrier is None:
                _loss = UNMEASURED
            elif _f in SEMANTIC and mapping_branch != "normal":
                _loss = CARRIER_ONLY
            else:
                _loss = LOSSLESS
            _rec = {
                "run_id": self.run_id,
                "candidate_id": candidate_id,
                "knowledge_kind": knowledge_kind,
                "source_reference": source_reference,
                "normalized_document_id": normalized_document_id,
                "source_sha256": source_sha256,
                "source_span": source_span,
                "field": _f,
                "raw_llm_field": _f,
                "raw_llm_value": _rv,
                "derived_field": _f,
                "derived_value": _dv,
                "norm_field": _f,
                "norm_value": _nv,
                "field_applicability": _app,
                "transformation_type": _t_type(_rv, _dv, _nv),
                "mapping_branch": mapping_branch,
                "canonical_carrier": (canonical_carrier or {}).get(_f),
                "semantic_loss_status": _loss,
                "unresolved_reason": unresolved_reason,
                "ts": time.time(),
                "seq": self._seq,
            }
            self._seq += 1
            if self._write(_rec):
                _n += 1
        return _n

    def events(self):
        """★ 读取已写入的事件（★ 追加式，★ 可复读）。"""
        if not self.path.is_file():
            return []
        return [json.loads(l) for l in
                self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def events(self):
        """★ 读取已写入的事件（★ 追加式，★ 可复读）。"""
        if not self.path.is_file():
            return []
        return [json.loads(l) for l in
                self.path.read_text(encoding="utf-8").splitlines() if l.strip()]

    def summary(self) -> dict:
        _recs = []
        if self.path.is_file():
            _recs = [json.loads(l) for l in
                      self.path.read_text(encoding="utf-8").splitlines() if l.strip()]
        _loss = collections.Counter(r["semantic_loss_status"] for r in _recs)
        return {
            "★ run_id": self.run_id,
            "★ 记录条数": len(_recs),
            "★ 写入错误数": len(self.write_errors),
            "★ 写入错误（★ 可观察）": self.write_errors[:5],
            "★ 语义损失状态分布": dict(_loss),
            "★ 候选数": len({r["candidate_id"] for r in _recs}),
            "★ 事件文件": str(self.path),
            "★ 事件文件 SHA256": (hashlib.sha256(self.path.read_bytes()).hexdigest()
                              if self.path.is_file() else None),
            "★ ★ 重复执行可区分": ("★ 是（★ run_id 唯一 + ts + seq）"
                            if len({r["run_id"] for r in _recs}) <= 1 else "★ 否"),
        }


def _t_type(raw, derived, norm):
    if raw is None and derived is None and norm is None:
        return "★ 未涉及"
    if raw is not None and norm is None:
        return "★ 直通丢失（★ LLM 有、Norm 无）"
    if raw is not None and norm is not None:
        return "★ 直通"
    if derived is not None and norm is not None:
        return "★ 派生"
    return "★ 其他"


def mapping_branch_of(norm: dict) -> str:
    """★ 复刻生产 `prose_constraint_norm_to_facts` 的分支判定（★ 只读）。"""
    _name = str(norm.get("name") or "")
    _act = str(norm.get("action") or "").strip()
    _obj = str(norm.get("object") or "").strip()
    _ss = str(norm.get("subject_status") or "")
    if _ss and _ss != "resolved":
        return "★ 分支1：主体未解析 ⇒ normative_unspecified"
    if (not _act or not _obj
            or (_act.lower() == _name.lower() and _obj.lower() == _name.lower())):
        return "★ 分支2：动作/对象缺失或占位 ⇒ 普通 definition"
    return "★ 正常路径：Rule Slot + Assertion"


__all__ = ["APPLICABILITY", "CANONICAL_CARRIER", "FieldFlowSidecar",
           "mapping_branch_of", "LOSSLESS", "CARRIER_ONLY",
           "NOT_APPLICABLE", "UNMEASURED", "UNRESOLVED"]
