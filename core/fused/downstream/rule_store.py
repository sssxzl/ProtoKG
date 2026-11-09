# -*- coding: utf-8 -*-
"""core/fused/downstream/rule_store.py —— 四库分离（authoritative / candidate / revoked / feedback）。

★ 改进v2 问题⑤ 的**正面实现**：「规则反馈仍在修改权威规则内容」。
  反馈（探测结果 / 覆盖率回流）只能影响规则的**调度顺序**，
  **绝不**写回规则本身（`reflow_rules` 是**纯排序**）。

设计依据（文档原文）：
  · ``docs/实施/RFC源里程碑BCD路线图.md`` §3.3 强制机制 3（落盘隔离）+ §3.8 任务表 B-7；
  · ``docs/实施/RFC源知识抽取改造方案.md`` §3.5 的 ``reflow_rules()`` 伪代码（纯排序）。

四库（**文件级**隔离 —— 自动生成链路只读 ``rules.jsonl``，读不到候选）::

    derived/model/per_source/<协议>/rfc/semantic/rules.jsonl       ← authoritative（只有 SemanticRule）
    derived/model/per_source/<协议>/rfc/semantic/candidates.jsonl  ← candidate（只有 KnowledgeCandidate）
    derived/model/per_source/<协议>/rfc/semantic/revoked.jsonl     ← revoked（被撤销的 SemanticRule）
    derived/model/per_source/<协议>/rfc/semantic/feedback.jsonl    ← feedback（实验反馈，**不含规则内容**）

★ **feedback 库是「实验反馈」的唯一落点** —— 边界探测结果写这里，
  **不再**写进权威 facts ⇒ 规范事实与实验反馈严格分离（问题⑤）。
★ ``semantic/`` 目录**不在** ``*/facts/*.jsonl`` 之下 ⇒
  ``rag_seedgen.load_fact_views()``（glob ``*/facts/*.jsonl``）**读不到**本目录
  ⇒ 四库内容不会混进知识中枢的 fact 视图（强制机制 3 的**落盘侧**保证）。
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Optional

from core import paths
from core.fused.semantic import (
    EvidenceAnchor,
    ExecutableConstraint,
    KnowledgeCandidate,
    SemanticRule,
)

#: 四库 → 文件名（落在 ``derived/model/per_source/<协议>/rfc/semantic/`` 下）。
#:
#: - ``authoritative`` → ``rules.jsonl``：**只有** ``SemanticRule``（且 constraint 非 None）
#: - ``candidate``     → ``candidates.jsonl``：**只有** ``KnowledgeCandidate``
#: - ``revoked``       → ``revoked.jsonl``：被撤销的 ``SemanticRule``
#: - ``feedback``      → ``feedback.jsonl``：实验反馈，**不含规则内容**
LIBRARY_FILES: dict[str, str] = {
    "authoritative": "rules.jsonl",
    "candidate": "candidates.jsonl",
    "revoked": "revoked.jsonl",
    "feedback": "feedback.jsonl",
}

#: 落盘条目的类型标签（读侧据此判别，**不**依赖字段猜测）。
KIND_RULE = "semantic_rule"
KIND_CANDIDATE = "knowledge_candidate"
KIND_FEEDBACK = "feedback"

#: 反馈条目的**前缀命名空间** —— 探测反馈的键带此前缀 ⇒ 永远不会与
#: ``rule_id`` 撞键（``reflow_rules`` 按 rule_id 取反馈，取不到就用默认分）。
FEEDBACK_PROBE_PREFIX = "probe:"


# ===========================================================================
# 路径
# ===========================================================================

def semantic_dir(protocol: str) -> Path:
    """四库根目录 ``derived/model/per_source/<协议>/rfc/semantic/``。

    ★ 不在 ``*/facts/`` 之下 ⇒ 不会被 ``load_fact_views`` 读到
      （强制机制 3 的落盘侧保证）。
    """
    return paths.per_source_root(protocol) / "rfc" / "semantic"


def library_path(protocol: str, library: str) -> Path:
    """某个库的落盘路径（``library`` ∈ ``LIBRARY_FILES`` 的键）。"""
    if library not in LIBRARY_FILES:
        raise KeyError(f"未知库名：{library!r}（可用：{sorted(LIBRARY_FILES)}）")
    return semantic_dir(protocol) / LIBRARY_FILES[library]


# ===========================================================================
# 序列化（往返后 dataclass 必须**逐字段相等** ⇒ tuple 不能退化成 list）
# ===========================================================================

def _to_tuples(obj: Any) -> Any:
    """递归把 list 还原成 tuple（JSON 没有 tuple ⇒ 反序列化必须补回）。"""
    if isinstance(obj, dict):
        return {k: _to_tuples(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return tuple(_to_tuples(v) for v in obj)
    return obj


def _rule_to_dict(rule: SemanticRule) -> dict:
    """``SemanticRule`` → 可 JSON 化的 dict（tuple 保持 tuple）。"""
    if not isinstance(rule, SemanticRule):
        raise TypeError(f"期望 SemanticRule，实得 {type(rule).__name__}")
    return asdict(rule)


def _rule_from_dict(data: dict) -> SemanticRule:
    """dict → ``SemanticRule``（tuple 还原 ⇒ 与原对象 ``==`` 相等）。

    ★ **必须重建嵌套 dataclass**：JSON 反序列化后 ``evidence`` / ``constraint``
      只是普通 dict ⇒ 直接塞回 ``SemanticRule`` 会让字段类型退化成 dict，
      整个 dataclass 的 ``==`` 断言随即失败（规则内容「看起来」变了）。
    """
    payload = dict(data)
    ev = payload.get("evidence")
    if isinstance(ev, dict):
        payload["evidence"] = EvidenceAnchor(**_to_tuples(ev))
    constraint = payload.get("constraint")
    if isinstance(constraint, dict):
        payload["constraint"] = ExecutableConstraint(**_to_tuples(constraint))
    return SemanticRule(**_to_tuples(payload))


def _candidate_to_dict(cand: KnowledgeCandidate) -> dict:
    """``KnowledgeCandidate`` → 可 JSON 化的 dict。"""
    if not isinstance(cand, KnowledgeCandidate):
        raise TypeError(f"期望 KnowledgeCandidate，实得 {type(cand).__name__}")
    return asdict(cand)


def _candidate_from_dict(data: dict) -> KnowledgeCandidate:
    """dict → ``KnowledgeCandidate``（同上：重建嵌套的 ``EvidenceAnchor``）。"""
    payload = dict(data)
    ev = payload.get("evidence")
    if isinstance(ev, dict):
        payload["evidence"] = EvidenceAnchor(**_to_tuples(ev))
    return KnowledgeCandidate(**_to_tuples(payload))


def _write_jsonl(path: Path, rows: Iterable[dict]) -> Path:
    """写 jsonl（覆盖写；父目录自动创建）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _read_jsonl(path: Path) -> list[dict]:
    """读 jsonl → dict 列表（文件不存在 ⇒ 空列表）。"""
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


# ===========================================================================
# 库 1：authoritative（rules.jsonl）—— 只有 SemanticRule
# ===========================================================================

def save_rules(protocol: str, rules: Iterable[SemanticRule], *,
               sink_dir: Optional[Path] = None) -> Path:
    """落盘权威规则库（**覆盖写**）。返回落盘路径。

    ★ 批次 2.5：``sink_dir`` 可把落盘**重定向**到别处 ⇒ **干跑隔离**用
      （此前干跑用 ``TemporaryDirectory`` 包裹，但本函数写的是**绝对路径**
      ⇒ 临时目录根本没起作用 ⇒ **干跑真的改了生产库**！实测踩到：
      ``publish_semantic_rules.py --dry-run`` 把 rtsp 规则库从 5 条改成 2 条。
    """
    rows = [{"kind": KIND_RULE, "rule": _rule_to_dict(r)} for r in rules]
    dest = (Path(sink_dir) / "rules.jsonl" if sink_dir is not None
            else library_path(protocol, "authoritative"))
    return _write_jsonl(dest, rows)


def publish_rules(protocol: str, rows: Iterable[Any], *,
                    replace: bool = True,
                    spec_versions: Optional[Iterable[str]] = None,
                    sink_dir: Optional[Path] = None) -> dict:
    """把规则**分流**发布进四库（**受控通道**：实验产物 → 生产库）。

    ★ 分流规则（两层模型的正确用法）：
      · **合格**的规则 ⇒ **权威库**（``rules.jsonl``）⇒ 知识中枢能读到 ⇒
        投影出 ``legal_boundary`` / ``response_expectation`` ⇒ 消费端有输入；
      · **不合格**的规则 ⇒ **候选库**（``candidates.jsonl``）⇒ **不静默丢弃**
        （带 ``reject_reason``，供人工复核）。

    ★ 质量闸（发布前逐条判定，与 :func:`load_rules` 的三重保险**同口径**）：
      ① 可反序列化为 ``SemanticRule``；
      ② ``constraint is not None``（无约束者**结构上装不下** operator/operand）；
      ③ :func:`core.fused.semantic.sanitize_rule` 的三类移除判定。

    ★ ``replace=False`` ⇒ **追加**到既有权威库（按 ``rule_id`` 去重）。

    Returns:
        报告 dict：``{"authoritative": n, "candidate": n, "rejects": {...},
        "path": str, "candidate_path": str}``。
    """
    from core.fused.semantic import KnowledgeCandidate, sanitize_rule

    accepted: list[SemanticRule] = []
    demoted: list[KnowledgeCandidate] = []
    rejects: dict[str, int] = {}

    def _count(reason: str) -> None:
        rejects[reason] = rejects.get(reason, 0) + 1

    # ★★ 批次 2.5（F1）：**按协议过滤**规则（防跨协议污染）。
    #   背景：B-10 实验产物 ``group_E{1,2}/rules.jsonl`` 是**多协议混合**的
    #   （实测 RFC 2326:11 / RFC 3261:9 / RFC 5321:1）⇒ 若不过滤，
    #   **SIP 的 RFC 3261 规则会进 RTSP 的库** ⇒ 投影出「Supported/Via 必须
    #   存在」这类与 RTSP 无关的约束（RTSP 库实测 5 条里 3 条是 SIP 的）。
    #   判据：``rule.evidence.spec_version`` ∈ 允许集合
    #   （允许集合来自 ``fused_hub/targets/<协议>/rfc_config.json`` 的
    #   ``spec_version``；缺省 = **不过滤**，保持旧行为）。
    _allowed_specs: Optional[set[str]] = None
    if spec_versions is not None:
        _allowed_specs = {str(s).strip() for s in spec_versions if str(s).strip()}

    for row in rows:
        rule: Any = row
        if isinstance(row, dict):
            try:
                rule = _rule_from_dict(row)
            except Exception:
                _count("malformed")
                continue
        if not isinstance(rule, SemanticRule):
            _count("not_a_rule")
            continue
        # ★★ 跨协议过滤（见上文 F1 说明）：spec_version 不在允许集合 ⇒ 拒绝
        if _allowed_specs is not None:
            _sv = str(getattr(rule.evidence, "spec_version", "") or "").strip()
            if _sv not in _allowed_specs:
                _count("cross_protocol")
                continue
        if rule.constraint is None:
            _count("no_constraint")
            demoted.append(KnowledgeCandidate(
                candidate_id=f"pub-{rule.rule_id}",
                evidence=rule.evidence,
                subject_type=rule.subject_type,
                subject_name=rule.subject_name,
                raw_text=rule.evidence.span_text,
                convertible=False,
                reject_reason="no_constraint",
            ))
            continue
        kept, reason = sanitize_rule(rule)
        if kept is None:
            _count(reason or "unknown")
            demoted.append(KnowledgeCandidate(
                candidate_id=f"pub-{rule.rule_id}",
                evidence=rule.evidence,
                subject_type=rule.subject_type,
                subject_name=rule.subject_name,
                raw_text=rule.evidence.span_text,
                convertible=False,
                reject_reason=reason,
            ))
            continue
        accepted.append(kept)

    # 去重（按 rule_id，保留首次出现）
    seen: set[str] = set()
    uniq: list[SemanticRule] = []
    for r in accepted:
        if r.rule_id in seen:
            _count("duplicate_rule_id")
            continue
        seen.add(r.rule_id)
        uniq.append(r)

    path = (Path(sink_dir) / "rules.jsonl" if sink_dir is not None
            else library_path(protocol, "authoritative"))
    if replace:
        saved = save_rules(protocol, uniq, sink_dir=sink_dir)
    else:
        existing = load_rules(path) if path.is_file() else []
        merged = list(existing)
        have = {r.rule_id for r in existing}
        merged += [r for r in uniq if r.rule_id not in have]
        saved = save_rules(protocol, merged, sink_dir=sink_dir)

    # ★ 候选库**追加**（不得覆盖）：分批发布时，后一批的候选会把前一批**丢掉**
    #   ⇒ 候选是「不可转换者的去处」，丢了就**永久消失**（不可恢复）。
    cand_path = None
    if demoted:
        cpath = (Path(sink_dir) / "candidates.jsonl" if sink_dir is not None
                 else library_path(protocol, "candidate"))
        existing_c = load_candidates(cpath) if cpath.is_file() else []
        have_c = {c.candidate_id for c in existing_c}
        merged_c = list(existing_c)
        merged_c += [c for c in demoted if c.candidate_id not in have_c]
        cand_path = save_candidates(protocol, merged_c, sink_dir=sink_dir)

    return {
        "authoritative": len(uniq),
        "candidate": len(demoted),
        "authoritative_total": len(load_rules(saved)),
        "candidate_total": (len(load_candidates(cand_path))
                            if cand_path else 0),
        "rejects": dict(sorted(rejects.items())),
        "path": str(saved),
        "candidate_path": str(cand_path) if cand_path else "",
    }


def load_rules(path: Path) -> list[SemanticRule]:
    """只加载**可执行**规则（§3.3 强制机制 3 的三重保险）。

    ★ ① 读的是 ``rules.jsonl``（候选文件根本不在路径上）
      ② 逐条 ``isinstance(SemanticRule)`` 断言
      ③ ``constraint is None`` 的规则**直接拒绝**（不静默跳过）
      候选（``KnowledgeCandidate``）在结构上无法通过 ②。
    """
    out: list[SemanticRule] = []
    for d in _read_jsonl(path):
        if d.get("kind") != KIND_RULE:
            continue
        r = _rule_from_dict(d["rule"])
        if not isinstance(r, SemanticRule):     # 防御性（JSON 反序列化后）
            raise TypeError("rules.jsonl 出现非 SemanticRule 条目")
        if r.constraint is None:
            raise ValueError(f"rules.jsonl 出现无约束的规则: {r.rule_id}")
        out.append(r)
    return out


# ===========================================================================
# 库 2：candidate（candidates.jsonl）—— 只有 KnowledgeCandidate
# ===========================================================================

def save_candidates(protocol: str,
                    candidates: Iterable[KnowledgeCandidate], *,
                    sink_dir: Optional[Path] = None) -> Path:
    """落盘候选库（**覆盖写**）。返回落盘路径。

    ★ 批次 2.5：``sink_dir`` 同 :func:`save_rules`（干跑隔离用）。
    """
    rows = [{"kind": KIND_CANDIDATE, "candidate": _candidate_to_dict(c)}
            for c in candidates]
    dest = (Path(sink_dir) / "candidates.jsonl" if sink_dir is not None
            else library_path(protocol, "candidate"))
    return _write_jsonl(dest, rows)


def load_candidates(path: Path) -> list[KnowledgeCandidate]:
    """只加载候选（``convertible`` 必须为 False —— 强制机制 4 的前置）。"""
    out: list[KnowledgeCandidate] = []
    for d in _read_jsonl(path):
        if d.get("kind") != KIND_CANDIDATE:
            continue
        c = _candidate_from_dict(d["candidate"])
        if not isinstance(c, KnowledgeCandidate):
            raise TypeError("candidates.jsonl 出现非 KnowledgeCandidate 条目")
        if c.convertible:
            raise ValueError(f"candidates.jsonl 出现可转换的候选: {c.candidate_id}")
        out.append(c)
    return out


# ===========================================================================
# 库 3：revoked（revoked.jsonl）—— 被撤销的 SemanticRule
# ===========================================================================

def save_revoked(protocol: str, rules: Iterable[SemanticRule]) -> Path:
    """落盘撤销库（**覆盖写**）。返回落盘路径。"""
    rows = [{"kind": KIND_RULE, "rule": _rule_to_dict(r)} for r in rules]
    return _write_jsonl(library_path(protocol, "revoked"), rows)


def load_revoked(path: Path) -> list[SemanticRule]:
    """加载撤销库（允许 ``constraint is None`` —— 撤销项不再参与执行）。"""
    out: list[SemanticRule] = []
    for d in _read_jsonl(path):
        if d.get("kind") != KIND_RULE:
            continue
        r = _rule_from_dict(d["rule"])
        if not isinstance(r, SemanticRule):
            raise TypeError("revoked.jsonl 出现非 SemanticRule 条目")
        out.append(r)
    return out


# ===========================================================================
# 库 4：feedback（feedback.jsonl）—— 实验反馈，**不含规则内容**
# ===========================================================================

def save_feedback(protocol: str, table: dict[str, dict]) -> Path:
    """落盘反馈表（**覆盖写**）。``table`` 的键是 rule_id（探测反馈用带前缀的键）。"""
    return _write_feedback_at(library_path(protocol, "feedback"), table)


def _write_feedback_at(path: Path, table: dict[str, dict]) -> Path:
    """把反馈表写到**指定**路径（键排序 ⇒ 落盘字节确定）。"""
    rows = [{"kind": KIND_FEEDBACK, "key": k, "record": v}
            for k, v in sorted(table.items())]
    return _write_jsonl(path, rows)


def load_feedback(path: Path) -> dict[str, dict]:
    """读反馈表 → ``{key: record}``（同键后写覆盖先写 ⇒ 表格语义）。"""
    out: dict[str, dict] = {}
    for d in _read_jsonl(path):
        if d.get("kind") != KIND_FEEDBACK:
            continue
        key = str(d.get("key") or "")
        if not key:
            continue
        rec = d.get("record")
        out[key] = dict(rec) if isinstance(rec, dict) else {}
    return out


def record_feedback(protocol: str, key: str, record: dict,
                    *, sink: Optional[Path] = None) -> Path:
    """把**一条**反馈并入反馈表（覆盖写整表；同键的字段做**合并**更新）。

    ★ 反馈**只影响调度顺序**，**不含**也不修改任何规则内容（问题⑤）。
    """
    target = Path(sink) if sink is not None else library_path(protocol, "feedback")
    table = load_feedback(target)
    merged = dict(table.get(key, {}))
    merged.update(record)
    table[key] = merged
    return _write_feedback_at(target, table)


def probe_feedback_key(protocol: str, method: str, dim: str) -> str:
    """探测反馈的键 —— 带命名空间前缀 ⇒ 永远不与 ``rule_id`` 撞键。"""
    return f"{FEEDBACK_PROBE_PREFIX}{protocol}:{method}:{dim}"


# ===========================================================================
# 覆盖率回流（任务 B7）—— 反馈**只改调度优先级**，不改规则内容
# ===========================================================================

def reflow_rules(rules: list[SemanticRule],
                 feedback: dict[str, dict]) -> list[SemanticRule]:
    """按反馈表调整规则的**选择优先级**，返回按优先级排序的规则列表。

    ★ 规则本身（evidence / constraint）**一字不改** —— 反馈是独立数据，
      不写回 SemanticRule。规范事实与实验反馈严格分离（问题⑤ / 四库分离）。
    ★ 排序键 ``(-priority_score, rule_id)`` ⇒ **确定性**：
      同优先级按 rule_id 兜底，不依赖输入顺序。
    ★ 兜底键用 ``r.rule_id``（顶层，I-1 已统一）。
    """
    def priority(r: SemanticRule) -> float:
        fb = feedback.get(r.rule_id) or {}
        return float(fb.get("priority_score", 0.0))

    # 排序稳定：同优先级保持原顺序（按 rule_id 兜底，保证确定性）
    return sorted(rules, key=lambda r: (-priority(r), r.rule_id))


__all__ = [
    "LIBRARY_FILES", "KIND_RULE", "KIND_CANDIDATE", "KIND_FEEDBACK",
    "FEEDBACK_PROBE_PREFIX",
    "semantic_dir", "library_path",
    "save_rules", "load_rules",
    "save_candidates", "load_candidates",
    "save_revoked", "load_revoked",
    "save_feedback", "load_feedback", "record_feedback", "probe_feedback_key",
    "reflow_rules",
]
