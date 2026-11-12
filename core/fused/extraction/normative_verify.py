# -*- coding: utf-8 -*-
"""core/fused/extraction/normative_verify.py —— **规范声明的三级校验**（L1 / L2 / L3）。

★ 对应改进计划 §3：

  | 层级 | 机制 | 处理结果 |
  |---|---|---|
  | **L1** | 确定性检查（区间存在 / 规范关键词与原文一致 / 否定与强度一致 /
    字段完整性 / 格式约束） | 不通过 ⇒ 拒收或待审 |
  | **L2** | 语义支持检查（独立核验原文与事实字段的对应） | 支持 / 不支持 / 不确定 |
  | **L3** | 人工确认的关键语义回归样本 | 衡量 L1/L2 可靠性 |

★ ★ **两类问题必须分开**（★ 硬约束）
  · **抽取错误**：声明与原文证据不一致 ⇒ 拒收或待审
  · **规范声明冲突**：两条声明**均有证据支持**，但可比较作用域内要求不一致
    ⇒ ★ **保留两条**，标记冲突 / 待消解 ⇒ ⇒ **不得**因来源冲突直接拒收

★ ★ **禁止**「因否定/条件未落在跨度内 ⇒ 丢掉极性 ⇒ 保留正面陈述」
  ⇒ 证据不足只能**拒收或待审**。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.fused.extraction.normative_rule import (
    NON_SEMANTIC_FIELDS, SEMANTIC_FIELDS, is_rule_text, normalize_keyword, parse_rule_text,
)

#: 判定结果三态
CONFIRMED = "confirmed"      # 已证实事实
PENDING = "pending"          # 待审候选
REJECTED = "rejected"        # 拒收结果
CONFLICT = "conflict"        # ★ 规范声明冲突（**不是**拒收！）

#: 否定词（用于 L1 的否定一致性检查）
_NEGATION_WORDS: tuple[str, ...] = ("NOT", "MUST NOT", "SHALL NOT",
                                    "SHOULD NOT", "NOT RECOMMENDED")


@dataclass
class VerificationResult:
    """一次校验的结果。"""

    verdict: str                       # CONFIRMED / PENDING / REJECTED / CONFLICT
    reasons: list[str] = field(default_factory=list)
    field_verdicts: dict[str, str] = field(default_factory=dict)
    evidence_spans: list[tuple] = field(default_factory=list)
    verifier_version: str = "l1-v1"

    @property
    def confirmed(self) -> bool:
        return self.verdict == CONFIRMED

    @property
    def rejected(self) -> bool:
        return self.verdict == REJECTED

    @property
    def pending(self) -> bool:
        return self.verdict == PENDING


# ===========================================================================
# L1 · 确定性检查
# ===========================================================================

def l1_check(*, rule_text_value: str, quote: str = "",
             evidence_span: Optional[tuple] = None,
             keyword_raw: str = "") -> VerificationResult:
    """**L1 · 确定性检查**（★ 不调 LLM ⇒ 完全可复现）。

    Args:
        rule_text_value: 规则文本（``[RULE:v1] {json}``）。
        quote: 原文引用（证据文本）⇒ 用于核对关键词/否定是否一致。
        evidence_span: 证据跨度（``(start, end)``）⇒ 存在性检查。
        keyword_raw: 原文规范关键词（如 ``MUST NOT``）⇒ 强度/极性一致性核对。

    Returns:
        :class:`VerificationResult`。
    """
    _reasons: list[str] = []
    _fv: dict[str, str] = {}

    # ① 规则文本格式
    if not is_rule_text(rule_text_value):
        return VerificationResult(REJECTED, ["不是规则文本（无 [RULE:v1] 前缀）"])
    payload = parse_rule_text(rule_text_value)
    if payload is None:
        return VerificationResult(REJECTED, ["规则文本的 JSON 解析失败"])

    # ② 证据跨度存在性
    if evidence_span is not None:
        try:
            _s, _e = int(evidence_span[0]), int(evidence_span[1])
            if _s <= 0 or _e < _s:
                _reasons.append(f"证据跨度非法：{evidence_span}")
        except (TypeError, ValueError, IndexError):
            _reasons.append(f"证据跨度不可解析：{evidence_span!r}")

    # ③ 字段完整性（语义字段必须齐全）
    for _f in SEMANTIC_FIELDS:
        if _f not in payload:
            _fv[_f] = "missing"
            _reasons.append(f"缺少语义字段：{_f}")

    # ④ 强度 / 极性的**内部一致性**
    _st = payload.get("strength")
    _po = payload.get("polarity")
    if _st and _po:
        _fv["strength"] = "ok"
        _fv["polarity"] = "ok"
    else:
        _fv["strength"] = "unknown" if not _st else "ok"
        _fv["polarity"] = "unknown" if not _po else "ok"
        if not _st:
            _reasons.append("规范强度未定（不得凭推测赋值）")
        if not _po:
            _reasons.append("极性未定（不得凭推测赋值）")

    # ⑤ ★ **与原文的一致性**：关键词归一后必须与 payload 一致
    if keyword_raw:
        _norm = normalize_keyword(keyword_raw)
        if _norm is None:
            _reasons.append(f"关键词无法归一：{keyword_raw!r}")
            _fv["keyword"] = "unknown"
        else:
            _k_st, _k_po = _norm
            if _st and _st != _k_st:
                _reasons.append(
                    f"强度与原文不一致：payload={_st} vs 原文={_k_st}")
                _fv["strength"] = "mismatch"
            if _po and _po != _k_po:
                _reasons.append(
                    f"极性与原文不一致：payload={_po} vs 原文={_k_po}")
                _fv["polarity"] = "mismatch"

    # ⑥ ★ **否定词必须在证据里出现**（当极性为 negative 时）
    if _po == "negative":
        _q = (quote or "").upper()
        if _q and not any(_w in _q for _w in _NEGATION_WORDS):
            _reasons.append("极性为 negative，但证据文本里没有否定词")
            _fv["polarity"] = "unsupported"
        elif not _q:
            _reasons.append("极性为 negative，但没有证据文本可核对")
            _fv["polarity"] = "unverified"

    # ⑦ 缺失值三态的合法性
    for _f in ("condition_status", "exception_status"):
        _v = payload.get(_f)
        if _v not in ("stated", "absent", "unknown"):
            _reasons.append(f"{_f} 取值非法：{_v!r}")
            _fv[_f] = "invalid"
        elif _v == "stated" and not payload.get(_f.replace("_status", "")):
            _reasons.append(f"{_f}=stated 但没有内容")
            _fv[_f] = "inconsistent"

    # ⑧ 非语义字段不得进 value
    for _f in NON_SEMANTIC_FIELDS:
        if _f in payload:
            _reasons.append(f"非语义字段混入了 value：{_f}")
            _fv[_f] = "leaked"

    _hard = [r for r in _reasons if "不一致" in r or "非法" in r or "混入" in r
             or "解析失败" in r or "不可解析" in r]
    if _hard:
        return VerificationResult(REJECTED, _reasons, _fv,
                                  [evidence_span] if evidence_span else [])
    if _reasons:
        # ★ 证据不足 ⇒ **待审**（★ 不得简化为更「简单」的事实）
        return VerificationResult(PENDING, _reasons, _fv,
                                  [evidence_span] if evidence_span else [])
    return VerificationResult(CONFIRMED, [], _fv,
                              [evidence_span] if evidence_span else [])


# ===========================================================================
# L2 · 语义支持检查（独立核验）
# ===========================================================================

_L2_SYSTEM = (
    "你是协议规范核验员。给定一条候选规范声明与原文证据，"
    "逐字段判断原文是否支持该声明。只输出 JSON。"
)

_L2_USER = """候选声明（JSON）：
{payload}

原文证据：
{quote}

请逐字段输出「支持 / 不支持 / 不确定」，并给出该字段对应的证据片段与判定依据。
输出格式：
{{"fields": {{"<字段名>": {{"verdict": "支持|不支持|不确定",
   "evidence": "<原文片段>", "reason": "<依据>"}}}},
  "overall": "支持|不支持|不确定",
  "reason": "<整体判定依据>"}}"""


def l2_check(*, payload: dict, quote: str, llm=None,
             model_hint: str = "") -> VerificationResult:
    """**L2 · 语义支持检查**（★ 独立核验）。

    ★ ★ **「独立」的三层含义要分开**：独立调用 / 独立判断过程 / 独立事实证据
      ⇒ ⇒ 即使调用两次 LLM，若依赖**相同模型或相同的错误文本解析结果**，仍会
      **相关性错误** ⇒ ⇒ 可靠性由 L3 与影子抽样兜底。
    ★ ★ **「独立上下文」≠「验证器必须看到不同的原文」**
      ⇒ ⇒ 验证器看到的是**候选事实 + 能支持或反驳它的完整原始证据**。
    ★ **不得**把抽取模型给出的理由直接当成验证结论。
    ★ **模型说是」本身不构成证明**。

    Args:
        payload: 候选规范声明（语义字段）。
        quote: 原文证据（完整）。
        llm: LLM 客户端（None ⇒ 自建）。
        model_hint: 建议的验证模型（可与抽取模型不同 ⇒ 降低相关性错误）。

    Returns:
        :class:`VerificationResult`（verifier_version 记为 ``l2-v1``）。
    """
    if llm is None:
        try:
            from core.llm import DeepSeekClient
            llm = DeepSeekClient()
        except Exception as exc:  # noqa: BLE001
            return VerificationResult(
                PENDING, [f"无法构造 LLM 客户端（{exc}）⇒ 保守待审"],
                verifier_version="l2-v1")

    import json as _json
    _sem = {k: payload.get(k) for k in SEMANTIC_FIELDS if k in payload}
    _user = _L2_USER.format(payload=_json.dumps(_sem, ensure_ascii=False,
                                               sort_keys=True),
                            quote=(quote or "")[:6000])
    try:
        out = llm.chat_json(system=_L2_SYSTEM, user=_user, temperature=0.0,
                            max_tokens=16000)
    except Exception as exc:  # noqa: BLE001
        return VerificationResult(PENDING, [f"L2 调用失败：{exc}"],
                                  verifier_version="l2-v1")
    if isinstance(out, str):
        try:
            out = _json.loads(out)
        except (ValueError, TypeError):
            return VerificationResult(PENDING, ["L2 返回不可解析"],
                                      verifier_version="l2-v1")
    if not isinstance(out, dict):
        return VerificationResult(PENDING, ["L2 返回结构异常"],
                                  verifier_version="l2-v1")

    _fv: dict[str, str] = {}
    _reasons: list[str] = []
    for _fname, _fv_obj in (out.get("fields") or {}).items():
        if isinstance(_fv_obj, dict):
            _v = str(_fv_obj.get("verdict") or "").strip()
            _fv[_fname] = _v or "不确定"
            if _v not in ("支持",):
                _reasons.append(f"字段 {_fname}：{_v or '不确定'}"
                                f"（{_fv_obj.get('reason') or ''}）")
    _overall = str(out.get("overall") or "").strip()
    if not _overall:
        _overall = "不确定"
        _reasons.append("L2 未给出整体判定")
    if _overall == "支持" and not _reasons:
        return VerificationResult(CONFIRMED, [], _fv, verifier_version="l2-v1")
    if _overall == "不支持":
        return VerificationResult(REJECTED, _reasons, _fv,
                                  verifier_version="l2-v1")
    return VerificationResult(PENDING, _reasons, _fv, verifier_version="l2-v1")


# ===========================================================================
# 冲突判定（★ 与「拒收」严格分开）
# ===========================================================================

def detect_conflict(claims: list[dict]) -> Optional[dict]:
    """在**同一 Rule Slot** 内检测**规范声明冲突**。

    ★ ★ **这是「规范一致性」问题，不是「抽取错误」** ⇒ ⇒ 冲突的两条声明
      **都保留**（由中枢的多声明共存 + 冲突标记机制处理）⇒ ⇒
      ★ **不得**因冲突把其中一条当作幻觉拒收。

    Args:
        claims: 同一槽位的声明列表（每项含 ``value``（规则 payload 或规则文本）
            与 ``claim_id``）。

    Returns:
        冲突描述（``{"slot":…, "claims":[…], "reason":…}``）；无冲突 ⇒ ``None``。
    """
    _sem: list[tuple[str, str, str]] = []   # (claim_id, strength, polarity)
    for _c in claims or []:
        _v = _c.get("value")
        _payload = None
        if isinstance(_v, dict):
            _payload = _v
        elif isinstance(_v, str) and is_rule_text(_v):
            _payload = parse_rule_text(_v)
        if not _payload:
            continue
        _sem.append((str(_c.get("claim_id") or ""),
                     str(_payload.get("strength") or ""),
                     str(_payload.get("polarity") or "")))
    _pos = [c for c in _sem if c[2] == "positive"]
    _neg = [c for c in _sem if c[2] == "negative"]
    if _pos and _neg:
        # ★ 强度不同不算简单冲突（可能层级差异）⇒ 仅同强度不同极性算「候选冲突」
        _same_lv = {c[1] for c in _pos} & {c[1] for c in _neg}
        if _same_lv:
            return {
                "slot": sorted(_same_lv),
                "claims": [c[0] for c in _sem],
                "reason": ("同一规则槽位内存在**同强度、相反极性**的声明"
                           "⇒ ★ 属规范声明冲突 ⇒ **两条均保留**，标记冲突"),
                "kind": "normative_conflict",
            }
    return None


__all__ = [
    "CONFIRMED", "PENDING", "REJECTED", "CONFLICT",
    "VerificationResult", "l1_check", "l2_check", "detect_conflict",
]
