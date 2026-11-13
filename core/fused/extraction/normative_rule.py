# -*- coding: utf-8 -*-
"""core/fused/extraction/normative_rule.py —— 规范规则的表示契约（准备阶段冻结）。

★ 这个模块是「准备阶段」的产物：把改进计划里冻结的语义契约落成可测、可引用的代码。
  后续的抽取、校验、去重、发布都引用这里的常量与函数 ⇒ 避免文档与实现漂移。

一、为什么要把「行为位置」与「规范内容」分开（Rule Slot / Assertion）

问题一（身份碰撞）：事实身份由 protocol + version + subject + aspect + condition
  决定 ⇒ 同一主体、同 aspect、同条件下的多条行为规则（MUST send ACK 与
  MUST update timer）会撞成同一身份 ⇒ 质量闸判「重复身份」并 fail-closed
  ⇒ 只能保留一条 ⇒ 义务丢失。

问题二（冲突不可见）：若把 strength / polarity 也放进身份 ⇒ 同一行为位置上的
  相反要求（MUST send ACK 与 MUST NOT send ACK）会分成两个身份 ⇒ 永不进入
  同一事实槽位 ⇒ 永不触发冲突处理 ⇒ 冲突不可见。

解法：
  Rule Slot（规则槽位）= protocol + version + subject + kind + action + object
                         + condition + scope          → 进事实身份
  Assertion（规范声明）= strength + polarity + condition + exception + scope
                         → 进声明内容（claim 的值）

★ 原文措辞与证据不进 value（否则会造成伪冲突）⇒ 落点是 claim 的证据记录
  （Evidence.quote 存原文措辞、Evidence.locator 存跨度）。

二、规范关键词归一化（RFC 2119 / RFC 8174）

  strength 只表达要求等级（不含否定）、polarity 表达极性 ⇒ 二者分离 ⇒ 避免双重否定。
  keyword_raw 保留原文完整措辞（落 Evidence.quote）⇒ 便于核对。
"""
import json
from typing import Optional

#: 关键词归一化表（原文措辞 → (strength, polarity)）
KEYWORD_NORMALIZATION: dict[str, tuple[str, str]] = {
    "MUST": ("MUST", "positive"),
    "REQUIRED": ("MUST", "positive"),
    "SHALL": ("MUST", "positive"),
    "MUST NOT": ("MUST", "negative"),
    "SHALL NOT": ("MUST", "negative"),
    "SHOULD": ("SHOULD", "positive"),
    "RECOMMENDED": ("SHOULD", "positive"),
    "SHOULD NOT": ("SHOULD", "negative"),
    "NOT RECOMMENDED": ("SHOULD", "negative"),
    "MAY": ("MAY", "positive"),
    "OPTIONAL": ("MAY", "positive"),
}

#: 强度等级（不含否定）
STRENGTHS: tuple[str, ...] = ("MUST", "SHOULD", "MAY")

#: 极性
POLARITIES: tuple[str, ...] = ("positive", "negative")

#: 缺失值三态
STATUSES: tuple[str, ...] = ("stated", "absent", "unknown")

#: 「仅仅没抽到」的默认值（不得默认成 absent）
DEFAULT_MISSING_STATUS: str = "unknown"

#: 规范语义值：参与语义比较 ⇒ 进 value
SEMANTIC_FIELDS: tuple[str, ...] = (
    "kind", "strength", "polarity",
    "condition", "condition_status",
    "exception", "exception_status",
    "scope", "action", "object",
    # ★ 跨节引用：★ **参与语义比较**（它是规范内容的一部分）
    #   ⇒ 但**不塞进 condition**（★ 引用 ≠ 条件）
    "cross_ref", "cross_ref_status",
)

#: 原文 / 证据 / 校验元信息：不参与语义比较 ⇒ 不进 value
NON_SEMANTIC_FIELDS: tuple[str, ...] = (
    "keyword_raw", "evidence_refs", "source", "verifier_version",
)

#: ★ **跨节引用的状态**
#:   · ``unknown``    —— 未提及引用
#:   · ``stated``     —— 片段里明确引用了某个章节
#:   · ``resolved``   —— 该章节**已在本文档内定位到**
#:   · ``unresolved`` —— 引用存在但**无法定位**（⇒ ⇒ L1 判待审）
CROSS_REF_STATUSES: tuple[str, ...] = ("unknown", "stated", "resolved", "unresolved")

#: ★ **代词表**（★ 主体用这些词 ⇒ **无法可靠确定主体** ⇒ 不进正式归并）
PRONOUN_SUBJECTS: frozenset = frozenset({
    "it", "they", "them", "this", "these", "those", "he", "she", "we", "you",
    "its", "their", "该", "其", "此", "它", "他们", "它们", "这", "那",
})


#: 规则类型标识（进 Rule Slot ⇒ 降低与普通 definition 的身份混淆）
RULE_KIND: str = "normative_rule"

#: 规则文本前缀（隔离判据：普通定义无此前缀）
RULE_PREFIX: str = "[RULE:v1]"

#: 规则文本的 schema 版本
RULE_SCHEMA_VERSION: int = 1


def normalize_keyword(raw: str) -> Optional[tuple[str, str]]:
    """把原文规范关键词归一化为 (strength, polarity)。

    ★ 无显式关键词 ⇒ 返回 None：按 RFC 8174 的澄清，「不含关键词」不等于
      「不具规范性」⇒ 不得凭模型推测赋予具体强度 ⇒ 由调用方记 unknown。

    Args:
        raw: 原文措辞（如 MUST NOT）。

    Returns:
        (strength, polarity)；无法归一化 ⇒ None。
    """
    if not raw:
        return None
    # ★ 2026-11-13（独立复核意见 P1-5）：★ **只认全大写**（RFC 8174）
    #   ⇒ 「只有**全大写**的 BCP 14 关键词才有特殊含义」；小写 must/should/may
    #     是**普通英语** ⇒ ⇒ **不得**无条件提升为 MUST/SHOULD/MAY
    #   ⇒ ★ 小写 ⇒ 返回 None ⇒ 强度保持**未知** ⇒ 归「待审」⇒ 不误赋强度
    _raw = " ".join(str(raw).strip().split())
    if _raw != _raw.upper():
        return None
    return KEYWORD_NORMALIZATION.get(_raw)


def build_payload(*, subject: str, action: str, object_: str,
                  strength: Optional[str], polarity: Optional[str],
                  condition: Optional[str] = None,
                  condition_status: Optional[str] = None,
                  exception: Optional[str] = None,
                  exception_status: Optional[str] = None,
                  cross_ref: Optional[str] = None,
                  cross_ref_status: Optional[str] = None,
                  scope: Optional[str] = None,
                  kind: str = RULE_KIND) -> dict:
    """构造规范语义 payload（只含 SEMANTIC_FIELDS）。

    ★ 缺失值三态的默认：condition_status / exception_status 缺省为 unknown
      （不得默认成 absent）。
    ★ 强度未定：strength=None ⇒ 记 unknown ⇒ 归「待审」
      （宁可强度未定，不可强度错）。
    """
    _st = strength if strength in STRENGTHS else None
    _po = polarity if polarity in POLARITIES else None
    _cs = condition_status if condition_status in STATUSES else DEFAULT_MISSING_STATUS
    _es = exception_status if exception_status in STATUSES else DEFAULT_MISSING_STATUS
    _xr = cross_ref_status if cross_ref_status in CROSS_REF_STATUSES else "unknown"
    # ★ 2026-11-13（人工核对 03b）：**不再静默改写**
    #   「显式声明 stated 却缺内容」是**输入不一致** ⇒ 若在此静默回落 unknown
    #   ⇒ ⇒ 会掩盖错误输入，并让 L1 的 ``inconsistent`` 检查**永不可达**
    #   ⇒ ⇒ 现在**原样保留** ⇒ 由 L1 判「不一致」⇒ 拒收 / 待审并留原因
    payload = {
        "kind": kind,
        "strength": _st,
        "polarity": _po,
        "condition": condition,
        "condition_status": _cs,
        "exception": exception,
        "exception_status": _es,
        "scope": scope,
        "action": action,
        "object": object_,
        # ★ 跨节引用**独立成字段**（★ 04：「引用本身不等于条件」）
        "cross_ref": cross_ref,
        "cross_ref_status": _xr,
    }
    return {k: payload[k] for k in SEMANTIC_FIELDS if k in payload}


def serialize_payload(payload: dict) -> str:
    """把 payload 序列化为规范化 JSON 文本（写入前预归一化）。

    ★ 规范化内容：键名按字典序、无多余空白、紧凑分隔符
      ⇒ 语义相同的声明 ⇒ 文本必然相同 ⇒ 不伪冲突。
    ★ 只输出 SEMANTIC_FIELDS（非语义字段一律剔除）。
    """
    _sem = {k: payload.get(k) for k in SEMANTIC_FIELDS if k in payload}
    return json.dumps(_sem, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def rule_text(payload: dict) -> str:
    """生成写入 definition 的规则文本（[RULE:v1] + 规范化 JSON）。"""
    return RULE_PREFIX + " " + serialize_payload(payload)


def is_rule_text(text: str) -> bool:
    """是否是规则文本（隔离判据：普通定义无此前缀）。"""
    return bool(text) and str(text).lstrip().startswith(RULE_PREFIX)


def parse_rule_text(text: str) -> Optional[dict]:
    """解析规则文本 ⇒ payload（非规则文本 ⇒ None）。"""
    if not is_rule_text(text):
        return None
    _body = str(text).lstrip()[len(RULE_PREFIX):].strip()
    try:
        _d = json.loads(_body)
    except (ValueError, TypeError):
        return None
    if not isinstance(_d, dict):
        return None
    return {k: _d[k] for k in SEMANTIC_FIELDS if k in _d}


def is_pronoun_subject(name: str) -> bool:
    """主体是否**代词**（★ 代词 ⇒ 无法可靠确定主体 ⇒ 不进正式归并）。

    ★ 人工核对 05：代词指代未解析时**不得**参与正式归并；应解析出主体或转待审。
    """
    _n = " ".join(str(name or "").strip().lower().split())
    return _n in PRONOUN_SUBJECTS


def subject_resolvable(name: str) -> bool:
    """主体是否**可可靠确定**（★ 非代词 ⇒ 可）。"""
    return bool(str(name or "").strip()) and not is_pronoun_subject(name)



def semantic_key(payload: dict) -> str:
    """语义比较键（相同语义 ⇒ 相同键 ⇒ 不伪冲突）。"""
    return serialize_payload(payload)


def rule_slot(*, protocol: str, version: str, subject: str,
              action: str, object_: str,
              condition: Optional[str] = None,
              scope: Optional[str] = None,
              kind: str = RULE_KIND) -> dict:
    """构造 Rule Slot（进事实身份 ⇒ 不含 strength/polarity/exception）。

    ★ 为什么不含强度与极性：同一行为位置上的相反要求必须落进同一槽位
      ⇒ 才能被关联、才能触发冲突处理 ⇒ 否则冲突不可见。

    ★ 条件与作用域的规范化口径（稳定序列化 ≠ 语义归一）
      ① 保留条件原文（由调用方保留在 payload 里）
      ② 本函数用规范化条件字段计算身份
      ③ 无法可靠归一化时保持不确定性（调用方不得强行合并）
      ④ 不同哈希不得直接解释为「规范内容一定不同」
    """
    return {
        "protocol": protocol,
        "version": version,
        "kind": kind,
        "subject": subject,
        "action": action,
        "object": object_,
        "condition": condition,
        "scope": scope,
    }


def slot_key(slot: dict) -> str:
    """Rule Slot 的稳定键（规范化 JSON ⇒ 键序确定）。"""
    return json.dumps(slot, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"))


def compare_slots(a: dict, b: dict) -> bool:
    """两个 Rule Slot 是否同一槽位（候选关联依据，非冲突结论）。"""
    return slot_key(a) == slot_key(b)


__all__ = [
    "KEYWORD_NORMALIZATION", "STRENGTHS", "POLARITIES", "STATUSES",
    "DEFAULT_MISSING_STATUS", "SEMANTIC_FIELDS", "NON_SEMANTIC_FIELDS",
    "CROSS_REF_STATUSES", "PRONOUN_SUBJECTS",
    "is_pronoun_subject", "subject_resolvable",
    "RULE_KIND", "RULE_PREFIX", "RULE_SCHEMA_VERSION",
    "normalize_keyword", "build_payload", "serialize_payload", "rule_text",
    "is_rule_text", "parse_rule_text", "semantic_key",
    "rule_slot", "slot_key", "compare_slots",
]
