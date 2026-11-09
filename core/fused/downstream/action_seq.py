# -*- coding: utf-8 -*-
"""core/fused/downstream/action_seq.py —— 字段级 action-sequence 变异（SemFuzz 迁移项 A）。

为什么存在
----------
上游 SemFuzz（arXiv 2603.05989）实测：「**确定性 action-sequence 变异把测试用例
有效率从 36% 提到 87%**」。其关键洞察是**不要让 LLM 直接编辑原始字节**
（二进制协议里长度字段会级联出错）⇒ **LLM 只产出抽象动作序列，由确定性引擎执行**。

本模块就是那条「确定性引擎」：

* :class:`Action` —— 一个字段级动作（SemFuzz 的 (p, m, f, d, e) 里的 d+e 两元组）；
* :class:`ActionSequence` —— 一个完整的变异计划（**LLM 的唯一输出形态**）；
* :func:`apply_actions` —— **确定性地**把动作序列作用到一颗真实种子上（**不原地改**）；
* :func:`plan_actions` —— 为一颗真实种子规划动作序列（**规则打底、LLM 兜底**，与 B-6 同构）。

它与既有四条种子生成路径（``edge_cover`` / ``generic_danger`` / 漏洞边界对 /
``canonical_flow``）的**本质区别**：那四条是「**从零构造**」，本模块是
「**在真实抓包种子上做字段级变异**」。

硬性设计约束
------------
1. **field_path 取值域封闭**（:data:`FIELD_PATH_SCALARS` + ``headers.<Name>``）：
   域外路径 ⇒ **拒绝该动作并记 ``reject_reason``**，**绝不静默忽略**。
2. **确定性**：同一 (种子, ActionSequence) ⇒ 输出**逐字节相同**。
   · 不使用随机数 / 时间戳 / 无序集合迭代；
   · 头部按**插入序**保留（``add`` 追加、``update`` 原地改值、``remove`` 删除）；
   · 头部名**大小写不敏感**匹配，但**保留原有拼写**。
3. **不原地修改**：:func:`apply_actions` 永远返回**新**种子，输入对象逐字段不变。
4. **可扩展**：新增动作 op 只需在 :data:`ACTION_OPS` 注册一项规格，
   **调用方（seedgen / 后续批次）零改动**。

协议差异**全部下沉到 profile.json**（本仓既有约定）：本模块不硬编码任何协议名、
方法名或字段名——连「.raw 怎么切消息」都由 ``profile.raw_format`` 驱动。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from core import paths
from core.fused.downstream.target_env import (  # noqa: E402
    _split_url_parts,        # 私有工具：与归一化/端点抽取口径一致
    allowed_endpoints as _allowed_endpoints,   # ★ 与 corpus_gate 的 G1 **共用一份**
)
from core.models import SeedCorpus, SeedMessage

#: ★ P2-1（2026-11-06）：``required_headers`` 桶里既有**方法级**清单，
#:   也有 ``"*"`` 键下的**消息级**清单（RFC 源的 ``required_header_global``）。
#:   ⇒ 一律用 ``required_headers_for()`` 读，避免「只 .get(method)」漏掉全局头。
from core.fused.downstream.rag_seedgen import required_headers_for  # noqa: E402

# ===========================================================================
# 0. 封闭取值域（常量）
# ===========================================================================

#: op 取值域（**封闭**）：域外 op ⇒ ``reject_reason="unknown_op"``。
OP_ADD = "add"
OP_REMOVE = "remove"
OP_UPDATE = "update"

#: 标量 field_path（**封闭**）：消息 URL / 命令参数 / 消息体。
FIELD_PATH_SCALARS: tuple[str, ...] = ("url", "argument", "body")

#: 消息级头的 field_path 前缀：``headers.<Name>``（``<Name>`` 大小写不敏感匹配）。
HEADER_PATH_PREFIX = "headers."

#: 拒绝原因词表（**可观测**：每一次拒绝都必须落一条台账）。
REJECT_UNKNOWN_OP = "unknown_op"
REJECT_FIELD_PATH_OUT_OF_DOMAIN = "field_path_out_of_domain"
REJECT_MSG_INDEX_OUT_OF_RANGE = "msg_index_out_of_range"
REJECT_MISSING_VALUE = "missing_value"
REJECT_UNEXPECTED_VALUE = "unexpected_value"
REJECT_HEADER_NOT_FOUND = "header_not_found"
REJECT_HEADER_ALREADY_EXISTS = "header_already_exists"
REJECT_EXPECTED_CLASS_OUT_OF_VOCAB = "expected_class_out_of_vocab"
REJECT_MALFORMED_ACTION = "malformed_action"
#: ★ P1-1：``value`` 含控制字符（CR/LF/NUL/其它 C0）⇒ 拒绝。
#:   实测（QA）：塞含 ``\r\n`` 的 value ⇒ ``.raw`` 里**真的凭空多出一个头**
#:   （``X-Evil: pwned``）或消息**提前截断** ⇒ 这是**协议/头注入**风险。
REJECT_VALUE_HAS_CONTROL_CHARS = "value_has_control_chars"
#: ★ P0-1 纵深防御：``url`` 字段的端点不在**合法端点集合**内 ⇒ 拒绝。
#:   合法端点集合与 **合法端点闸**的 G1 **共用同一份实现**
#:   （``core.fused.downstream.target_env.allowed_endpoints``）。
REJECT_ENDPOINT_NOT_ALLOWED = "endpoint_not_allowed"
#: ★ R-2：``value`` 是**空串** ⇒ 拒绝。
#:   实测（QA 第二段复验）：``missing-required-header`` 规则用知识中枢取值池的
#:   兜底值补齐**必填**头，而兜底值 **18/29（62%）是空串** ⇒ 落盘成 ``CSeq: ``
#:   ⇒ 服务端**必然拒收** ⇒ **零价值却占掉契约名额**
#:   （对 SemFuzz「36%→87%」是**负贡献**，不是正贡献）。
#:   ⇒ 空串**不是**合法的新头值；真要清空某字段请用 ``remove``。
REJECT_EMPTY_VALUE = "empty_value"
#: ★ P2-3：``value`` 超过长度上限 ⇒ 拒绝（防止 LLM 产出 MB 级字段把语料撑爆）。
REJECT_VALUE_TOO_LONG = "value_too_long"
#: ★ P2-2：删除**必填**头 ⇒ 拒绝并记台账。
#:   必填头由知识中枢 ``required_headers`` 声明（按方法分组）；
#:   删掉它 ⇒ 服务端必然拒收 ⇒ **零价值**，且此前**零台账**（静默）。
REJECT_HEADER_IS_REQUIRED = "header_is_required"

#: 单个字段值的**长度上限**（P2-3；超长 ⇒ 拒绝）。
MAX_VALUE_LENGTH = 4096

#: action-seq 种子在 :class:`~core.models.SeedCorpus` 上的 ``generated_by`` 标记。
ACTION_SEQ_GENERATED_BY = "rule-based:action-seq"

#: 单条种子的动作序列长度上限（序列太长会让单条种子偏离真实会话太远）。
MAX_PLAN_ACTIONS = 3

#: 头部名合法性（RFC 7230 token 子集：字母数字 + ``-`` / ``_``）。
#: ★ P2-1：**不含 ``.``** —— 本模块的 field_path 是**扁平**的（``headers.<Name>``），
#:   若允许 ``.``，则 ``headers.A.B`` 会被解读成「头名 A.B」，
#:   而调用方（尤其 LLM）可能本意是「头 A 的子字段 B」⇒ **语义歧义**。
#:   本仓三个协议（SIP / RTSP / SMTP）的**真实头名一个都不含 ``.``**
#:   （已对 ``kb/*/spec/**`` 全量机检：0 命中）⇒ 收紧取值域**零误杀**，
#:   且域外路径会走 ``field_path_out_of_domain`` 拒绝分支（**可观测**）。
_HEADER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")

#: 「头部行」形态（抓包日志 / .raw 里的 ``Name: value``）。
_HEADER_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._-]*\s*:")


# ===========================================================================
# 1. 数据模型
# ===========================================================================

@dataclass(frozen=True)
class Action:
    """一个字段级动作（SemFuzz 的 (p, m, f, d, e) 里的 d+e 两元组）。

    Attributes:
        op:         ``"add"`` / ``"remove"`` / ``"update"``（**封闭取值域**）。
        msg_index:  作用于第几条消息（0 基；越界 ⇒ 拒绝）。
        field_path: ``"headers.<Name>"`` / ``"url"`` / ``"argument"`` / ``"body"``
                    （**封闭取值域**；域外 ⇒ 拒绝）。
        value:      ``add`` / ``update`` 的新值；``remove`` 必须为 ``None``。
    """

    op: str
    msg_index: int
    field_path: str
    value: Optional[str] = None

    def to_dict(self) -> dict:
        """转成可 JSON 序列化的 dict（LLM 互操作 / 落盘溯源）。"""
        return {
            "op": self.op,
            "msg_index": self.msg_index,
            "field_path": self.field_path,
            "value": self.value,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        """从 dict 构造（LLM 输出解析）；**不做域校验**（校验在 apply/plan 阶段）。"""
        return cls(
            op=str(d.get("op", "")),
            msg_index=d.get("msg_index", -1),
            field_path=str(d.get("field_path", "")),
            value=d.get("value"),
        )


@dataclass(frozen=True)
class ActionSequence:
    """一个完整的变异计划（**LLM 的唯一输出形态**）。

    Attributes:
        actions:        动作序列（有序 ⇒ 执行顺序即序列顺序）。
        intent:         人类可读意图（进 ``seed.description``）。
        expected_class: 期望响应类别（进 oracle；空 = 无期望）。
    """

    actions: tuple[Action, ...] = ()
    intent: str = ""
    expected_class: str = ""

    def to_dict(self) -> dict:
        """转成可 JSON 序列化的 dict。"""
        return {
            "actions": [a.to_dict() for a in self.actions],
            "intent": self.intent,
            "expected_class": self.expected_class,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ActionSequence":
        """从 dict 构造（LLM 输出解析）。"""
        raw_actions = d.get("actions") or []
        actions = tuple(Action.from_dict(a) for a in raw_actions
                        if isinstance(a, dict))
        return cls(
            actions=actions,
            intent=str(d.get("intent", "") or ""),
            expected_class=str(d.get("expected_class", "") or ""),
        )


@dataclass(frozen=True)
class ActionRejection:
    """一条**拒绝记录**（域外路径 / 越界下标 / 缺值 …）。"""

    action: Optional[Action]
    reject_reason: str
    detail: str = ""

    def to_dict(self) -> dict:
        """转成可 JSON 序列化的 dict。"""
        return {
            "action": self.action.to_dict() if self.action else None,
            "reject_reason": self.reject_reason,
            "detail": self.detail,
        }


class ActionLedger:
    """拒绝台账 —— ``reject_reason`` 的**唯一可观测载体**。

    用法::

        ledger = ActionLedger()
        apply_actions(seed, seq, ledger=ledger)
        ledger.reason_counts()   # {'field_path_out_of_domain': 2}
    """

    def __init__(self) -> None:
        self._items: list[ActionRejection] = []

    def reject(self, action: Optional[Action], reason: str,
               detail: str = "") -> ActionRejection:
        """登记一条拒绝记录，返回该记录。"""
        item = ActionRejection(action=action, reject_reason=str(reason),
                               detail=str(detail))
        self._items.append(item)
        return item

    @property
    def rejections(self) -> tuple[ActionRejection, ...]:
        """全部拒绝记录（按发生顺序）。"""
        return tuple(self._items)

    def reason_counts(self) -> dict[str, int]:
        """按 ``reject_reason`` 聚合的计数（确定性顺序：按首次出现）。"""
        counts: dict[str, int] = {}
        for item in self._items:
            counts[item.reject_reason] = counts.get(item.reject_reason, 0) + 1
        return counts

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        return bool(self._items)

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"ActionLedger(rejections={len(self._items)}, " \
               f"reasons={self.reason_counts()})"


# ===========================================================================
# 2. field_path 取值域（封闭）
# ===========================================================================

def normalize_field_path(field_path: Any) -> Optional[tuple[str, str]]:
    """把 ``field_path`` 归一化到**封闭取值域**。

    Args:
        field_path: 原始路径串。

    Returns:
        ``("header", "<Name>")`` / ``("url", "")`` / ``("argument", "")`` /
        ``("body", "")``；**域外返回 ``None``**（调用方据此拒绝并记
        ``reject_reason="field_path_out_of_domain"``）。

    ★ P2-1（无歧义）：``headers.<Name>`` 是**扁平**路径 —— ``<Name>`` 取
      ``headers.`` 之后的**全部**文本，且**不允许含 ``.``**。
      ⇒ ``headers.A.B`` 落在域外（被拒绝并记账），**不会**被当成
      「头 A 的子字段 B」，也**不会**被当成「头名 A.B」而凭空建头。
      子字段语义请用 ``body``（整段消息体）。
    """
    text = str(field_path or "").strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in FIELD_PATH_SCALARS:
        return (lowered, "")
    if lowered.startswith(HEADER_PATH_PREFIX):
        name = text[len(HEADER_PATH_PREFIX):].strip()
        if not name or not _HEADER_NAME_RE.match(name):
            return None
        return ("header", name)
    return None


def find_header(headers: Optional[dict], name: str) -> Optional[str]:
    """按名字（**大小写不敏感**）在 headers 桶里找键，返回**原始拼写的键**。

    找不到返回 ``None``。
    """
    if not headers:
        return None
    if name in headers:
        return name
    low = str(name).lower()
    for key in headers:
        if str(key).lower() == low:
            return key
    return None


# ===========================================================================
# 3. op 规格表（**扩展点**：新增 op 只需注册一项，调用方零改动**）
# ===========================================================================

@dataclass(frozen=True)
class ActionOpSpec:
    """一个动作 op 的规格。

    Attributes:
        name:      op 名（``add`` / ``remove`` / ``update`` …）。
        apply:     执行器 ``(action, message) -> None``（就地改目标消息）。
        validate:  校验器 ``(action, message) -> Optional[str]``；
                    返回 ``reject_reason`` 或 ``None``（合法）。
    """

    name: str
    apply: Callable[[Action, SeedMessage], None]
    validate: Callable[[Action, SeedMessage], Optional[str]]


def _allowed_endpoint_set(profile: Optional[dict]) -> Optional[set[str]]:
    """该协议的**合法端点集合**（``host:port``）；无 profile ⇒ ``None``（不启用校验）。

    ★ 与 **合法端点闸**的 G1 **共用同一份实现**
      （``core.fused.downstream.target_env.allowed_endpoints``）⇒ 口径不会漂移。
    ★ 返回 ``None``（而非空集）表示「**未启用**端点校验」—— 与「启用了但集合为空」
      语义不同（后者意味着该协议没有端点概念，如 SMTP）。
    """
    if not profile:
        return None
    endpoints, _sources = _allowed_endpoints(profile, {})
    return endpoints


def _has_control_chars(value: Any) -> bool:
    """``value`` 是否含**控制字符**（CR / LF / NUL / 其它 C0）。

    ★ P1-1（安全）：头值里出现 ``\r\n`` ⇒ 落盘时会**凭空多出一个头**
      （QA 实测 ``X-Evil: pwned``）或让消息**提前截断**
      ⇒ 这是**协议/头注入**风险，必须在生成侧 fail-closed。
      ``\t`` 放行（协议里常见的分隔符）；其余 C0 与 DEL 一律拒绝。
    """
    if not isinstance(value, str):
        return False
    for ch in value:
        code = ord(ch)
        if ch == "\t":
            continue
        if code < 0x20 or code == 0x7F:
            return True
    return False


def _endpoint_of_value(value: Any) -> str:
    """从 URL 值里取出 ``host:port``（无则空串）。

    与 ``action_seq.allowed_endpoints`` 的**口径一致**：剥 ``user@``、去 ``<>``。
    """
    if not isinstance(value, str) or not value:
        return ""
    _scheme, netloc, _path, _query, _fragment = _split_url_parts(value)
    if not netloc:
        return ""
    return netloc.rsplit("@", 1)[-1].strip("<>")


def _validate_header_existence(action: Action, message: SeedMessage) -> Optional[str]:
    """头部类动作的存在性校验：``add`` 要求**不存在**、``update``/``remove``
    要求**存在**（否则拒绝，避免静默新建 / 静默空转）。"""
    kind, name = normalize_field_path(action.field_path)
    if kind != "header":
        return None
    existing = find_header(message.headers, name)
    if action.op == OP_ADD and existing is not None:
        return REJECT_HEADER_ALREADY_EXISTS
    if action.op in (OP_UPDATE, OP_REMOVE) and existing is None:
        return REJECT_HEADER_NOT_FOUND
    return None


def _apply_add(action: Action, message: SeedMessage) -> None:
    """``add``：新增字段（头部不存在时才允许）。"""
    kind, name = normalize_field_path(action.field_path)
    if kind == "header":
        message.headers[name] = action.value or ""
        return
    if kind == "url":
        message.url = action.value or ""
    elif kind == "argument":
        message.argument = action.value or ""
    elif kind == "body":
        message.body = action.value or ""


def _apply_update(action: Action, message: SeedMessage) -> None:
    """``update``：改值（头部保留**原有拼写与位置**）。"""
    kind, name = normalize_field_path(action.field_path)
    if kind == "header":
        existing = find_header(message.headers, name)
        if existing is None:
            return
        message.headers[existing] = action.value or ""
        return
    if kind == "url":
        message.url = action.value or ""
    elif kind == "argument":
        message.argument = action.value or ""
    elif kind == "body":
        message.body = action.value or ""


def _apply_remove(action: Action, message: SeedMessage) -> None:
    """``remove``：删字段（标量字段置空串；头部按键删除）。"""
    kind, name = normalize_field_path(action.field_path)
    if kind == "header":
        existing = find_header(message.headers, name)
        if existing is not None:
            message.headers.pop(existing, None)
        return
    if kind == "url":
        message.url = ""
    elif kind == "argument":
        message.argument = ""
    elif kind == "body":
        message.body = ""


#: **op 规格表**（扩展点）。新增 op = 注册一项 + 在 :func:`apply_actions` 之外
#: **不需要改动任何调用方**。
ACTION_OPS: dict[str, ActionOpSpec] = {
    OP_ADD: ActionOpSpec(name=OP_ADD, apply=_apply_add,
                          validate=_validate_header_existence),
    OP_UPDATE: ActionOpSpec(name=OP_UPDATE, apply=_apply_update,
                             validate=_validate_header_existence),
    OP_REMOVE: ActionOpSpec(name=OP_REMOVE, apply=_apply_remove,
                             validate=_validate_header_existence),
}

#: 合法 op 集合（由规格表派生 ⇒ 单一事实来源）。
VALID_OPS: tuple[str, ...] = tuple(sorted(ACTION_OPS))


# ===========================================================================
# 4. apply_actions —— 确定性执行
# ===========================================================================

def _reject_reason(action: Action, message: Optional[SeedMessage],
                   allowed_endpoints: Optional[set[str]] = None,
                   required_headers: Optional[dict] = None) -> Optional[str]:
    """判定一个动作是否该被拒绝；合法返回 ``None``。

    校验顺序（固定 ⇒ 拒绝原因可复现）：
        1. op 是否在规格表里；
        2. ``msg_index`` 是否落在消息范围内；
        3. ``field_path`` 是否在封闭取值域内；
        4. 值语义（``remove`` 不得带值；``add``/``update`` 必须带值）；
        5. ★ **值不含控制字符**（P1-1：CR/LF/NUL ⇒ 头注入 / 消息截断）；
        6. ★ **值非空**（R-2：``CSeq: `` ⇒ 服务端必拒收 ⇒ 零价值）；
        7. ★ **值长度不超限**（P2-3）；
        8. op 专属校验（头部的存在性）；
        9. ★ **不得删必填头**（P2-2；需 ``required_headers`` 上下文）；
       10. ★ **端点在合法端点集合内**（P0-1 纵深防御；仅当调用方给了白名单）。
    """
    op = getattr(action, "op", None)
    if not isinstance(op, str) or op not in ACTION_OPS:
        return REJECT_UNKNOWN_OP
    index = getattr(action, "msg_index", None)
    if not isinstance(index, int) or isinstance(index, bool) or index < 0:
        return REJECT_MSG_INDEX_OUT_OF_RANGE
    if message is None:
        return REJECT_MSG_INDEX_OUT_OF_RANGE
    if normalize_field_path(getattr(action, "field_path", "")) is None:
        return REJECT_FIELD_PATH_OUT_OF_DOMAIN
    value = getattr(action, "value", None)
    if op == OP_REMOVE:
        if value is not None:
            return REJECT_UNEXPECTED_VALUE
    else:
        if value is None:
            return REJECT_MISSING_VALUE
        if not isinstance(value, str):
            return REJECT_MALFORMED_ACTION
    # ★ P1-1：控制字符 ⇒ 拒绝（生成侧 fail-closed，不等落盘后再查）
    if op != OP_REMOVE and _has_control_chars(value):
        return REJECT_VALUE_HAS_CONTROL_CHARS
    # ★ R-2：空串不是合法的新值（落盘 ``CSeq: `` ⇒ 服务端必拒收 ⇒ 零价值）。
    if op != OP_REMOVE and not value.strip():
        return REJECT_EMPTY_VALUE
    # ★ P2-3：值长度上限（防止 LLM 产出 MB 级字段把语料撑爆）。
    if op != OP_REMOVE and len(value) > MAX_VALUE_LENGTH:
        return REJECT_VALUE_TOO_LONG
    spec = ACTION_OPS[op]
    reason = spec.validate(action, message)
    if reason is not None:
        return reason
    # ★ P2-2：删**必填**头 ⇒ 拒绝（服务端必然拒收 ⇒ 零价值；此前零台账）。
    if op == OP_REMOVE and required_headers:
        kind, name = normalize_field_path(getattr(action, "field_path", ""))
        if kind == "header":
            method = str(getattr(message, "method", "") or "").upper()
            reqs = {str(r).lower()
                    for r in required_headers_for(required_headers, method)}
            if name.lower() in reqs:
                return REJECT_HEADER_IS_REQUIRED
    # ★ P0-1 纵深防御：``url`` 字段的端点必须在**合法端点集合**内。
    #   合法端点集合与 **合法端点闸** 的 G1 **共用一份实现**
    #   （``core.fused.downstream.target_env.allowed_endpoints``）⇒ 口径不会漂移。
    if allowed_endpoints is not None:
        kind, _name = normalize_field_path(getattr(action, "field_path", ""))
        if kind == "url":
            endpoint = _endpoint_of_value(value)
            if endpoint and endpoint not in allowed_endpoints:
                return REJECT_ENDPOINT_NOT_ALLOWED
    return None


def apply_actions(seed: SeedCorpus, seq: ActionSequence,
                  *, ledger: ActionLedger,
                  profile: Optional[dict] = None,
                  required_headers: Optional[dict] = None) -> SeedCorpus:
    """把动作序列**确定性地**作用到一个真实种子上，返回新种子（**不原地改**）。

    Args:
        seed:   输入种子（**不会被修改**）。
        seq:    动作序列。
        ledger: **必需的**拒绝台账；域外 ``field_path`` / 越界 ``msg_index`` /
                缺值等**一律拒绝并登记 reject_reason**（不抛异常、不静默忽略）。
                ★ P1-2：台账是**必传**的 —— 早前它是可选参数、默认 ``None``，
                  于是「拒绝了但没人接」的拒绝被**静默吞掉**，直接违反本模块的
                  硬性约束①「拒绝必须可观测」。现在**不给台账就调不动**。
        required_headers: 可选的**必填头表**（``{方法: [头名…]}``）；
                给了 ⇒ ``remove`` 必填头会被拒绝并记账（P2-2）。

    Returns:
        新的 :class:`~core.models.SeedCorpus`：
        · ``messages`` 逐条按动作序列顺序变更；
        · ``description`` 追加 ``[action-seq: <intent>]``；
        · ``target_vuln_class`` 写入 ``seq.expected_class``（非空时）；
        · ``generated_by`` 置为 ``rule-based:action-seq``。

    ★ **确定性**：同一 (种子, ActionSequence) ⇒ 输出**逐字节相同**。
    """
    # 深拷贝（messages / headers 全部重建）⇒ 输入对象逐字段不变。
    new_seed = SeedCorpus.from_dict(seed.to_dict())
    actions = tuple(getattr(seq, "actions", ()) or ())
    # ★ P0-1 纵深防御：合法端点集合（与 corpus_gate 的 G1 **共用一份实现**）。
    #   ★ 无 profile ⇒ 白名单为 ``None`` ⇒ **不启用**端点校验（避免缺上下文时误杀）；
    #     控制字符校验**始终**生效（纯安全规则，不需要上下文）。
    allowed = _allowed_endpoint_set(profile)

    applied = 0
    for action in actions:
        index = getattr(action, "msg_index", -1)
        message = None
        if isinstance(index, int) and not isinstance(index, bool) \
                and 0 <= index < len(new_seed.messages):
            message = new_seed.messages[index]
        reason = _reject_reason(action, message, allowed, required_headers)
        if reason is not None:
            ledger.reject(action, reason, _reject_detail(action))
            continue
        ACTION_OPS[action.op].apply(action, message)
        applied += 1

    # ★ P1-4 / P2-4：**没有任何动作实际生效** ⇒ **原样返回**。
    #   · 零变异（applied == 0）却把 `generated_by` 改写成 ⑤ 层
    #     ⇒ 它会被当作「⑤ 种子」优先保留、挤掉基准层（QA 实测 8/238 = 3%）；
    #   · 空 `ActionSequence` 仍改写 description / generated_by
    #     ⇒ 与 `mutate_seed` docstring 的「等价」承诺矛盾。
    #   ⇒ 判据：**实际生效的动作数 == 0** ⇒ 一个字段都不改。
    if applied == 0:
        return new_seed

    intent = str(getattr(seq, "intent", "") or "")
    expected = str(getattr(seq, "expected_class", "") or "")
    origin = seed.description or ""
    if intent:
        new_seed.description = (f"{origin} [action-seq: {intent}]" if origin
                                else f"[action-seq: {intent}]")
    else:
        new_seed.description = (f"{origin} [action-seq]" if origin
                                else "[action-seq]")
    if expected:
        new_seed.target_vuln_class = expected
    new_seed.generated_by = ACTION_SEQ_GENERATED_BY
    return new_seed


def _reject_detail(action: Action) -> str:
    """拒绝记录的补充说明（可读文本，不参与判定）。"""
    return (f"op={getattr(action, 'op', None)!r} "
            f"msg_index={getattr(action, 'msg_index', None)!r} "
            f"field_path={getattr(action, 'field_path', None)!r}")


# ===========================================================================
# 5. plan_actions —— 规则打底、LLM 兜底
# ===========================================================================

def _header_pool(bucket: Optional[dict], name: str) -> list[str]:
    """取知识中枢 headers 桶里某字段的取值池（大小写不敏感匹配）。"""
    if not bucket:
        return []
    info = bucket.get(name)
    if info is None:
        low = str(name).lower()
        for key, value in bucket.items():
            if str(key).lower() == low:
                info = value
                break
    if not isinstance(info, dict):
        return []
    return [str(v) for v in (info.get("values") or [])]


#: 「序号型」头值的形态：``数字`` 或 ``数字 + 空格 + 方法名``。
#:   SIP 的 CSeq 是 ``2 INVITE``、RTSP 的 CSeq 是 ``2`` ⇒ 二者都命中。
_SEQ_VALUE_RE = re.compile(r"^(\d+)(\s+(\S+))?$")


def _sample_header_value(messages: list, header: str) -> str:
    """从同一种子**已有消息**里取该头的**真实值样本**（不发明值）。

    ★ 动机（批次 1.5 改动 4）：知识中枢的 ``headers`` 取值池对某些必填头
      是**空的**（实测 sip 26/63 个头缺 values，而 ``CSeq`` 恰是必填头）
      ⇒ 补齐动作必被拒（空值）⇒ ⑤ 种子缺该头 ⇒ 服务端拒收 ⇒ 零价值。
    ★ 但**同一种子的真实抓包里该头是有值的**（实测 SIP 已发表语料的 CSeq
      **83/83 全部有值**）⇒ 可以**搬运真实值**，不必臆造。
    """
    for msg in messages:
        key = find_header(msg.headers, header)
        if key is None:
            continue
        value = str(msg.headers[key] or "").strip()
        if value:
            return value
    return ""


def _sequence_like_value(messages: list, header: str, method: str) -> str:
    """按已有样本的**形态**生成该头的下一个序号值（序号型头用）。

    ★ 为什么要**生成**而不是直接搬运：序号型头（``CSeq``）直接搬运会与
      已有消息**序号冲突**（两条 ``CSeq: 2``）⇒ 服务端按序号单调性拒收。
    ★ **形态继承**：样本带方法名后缀（``2 INVITE``）⇒ 新值也带（用**当前
      消息**的方法名）；样本是纯数字（``2``）⇒ 新值也是纯数字。
    ★ **协议无关**：判定只看「值是否以数字开头」⇒ SIP / RTSP 都适用。
    """
    samples: list[str] = []
    for msg in messages:
        key = find_header(msg.headers, header)
        if key is None:
            continue
        value = str(msg.headers[key] or "").strip()
        if value:
            samples.append(value)
    if not samples:
        return ""
    matched = [_SEQ_VALUE_RE.match(s) for s in samples]
    if not any(matched):
        return samples[-1]          # 非序号型 ⇒ 直接搬运真实值
    max_num = 0
    tail = ""
    for s, m in zip(samples, matched):
        if not m:
            continue
        max_num = max(max_num, int(m.group(1)))
        if m.group(2):
            tail = m.group(2)
    if tail and not tail.strip().isdigit():
        tail = f" {method}"        # 方法名后缀 ⇒ 用当前消息的方法
    return f"{max_num + 1}{tail}"


def _default_header_value(bucket: Optional[dict], name: str) -> str:
    """字段兜底值：取知识中枢 headers 取值池里的**首个非空**取值（非协议硬编码）。

    ★ R-2：池首值可能是**空串**（知识中枢里该头只有空取值）⇒ 直接用它会落盘成
      ``CSeq: `` ⇒ 服务端必然拒收 ⇒ 零价值。
      ⇒ 这里**跳过空值**继续找下一个非空取值；池里全空 ⇒ 返回空串
      （调用方据此**拒绝该动作并记台账**，而不是写空串）。
    """
    for value in _header_pool(bucket, name):
        if str(value).strip():
            return str(value)
    return ""


def _replayed_cseq(current: str, following: str) -> str:
    """CSeq 重放值：取下一条消息的**序号**，并保留本条消息原有的「方法后缀」形态。

    例：``current="1 REGISTER"`` / ``following="2 INVITE"`` ⇒ ``"2 REGISTER"``
    （只复制序号，不把方法名也复制过来 ⇒ 变异后仍是**同方法**的重放）。
    """
    current_parts = str(current).split()
    following_parts = str(following).split()
    if not following_parts:
        return str(current)
    number = following_parts[0]
    if len(current_parts) >= 2:
        return f"{number} {current_parts[1]}"
    return number


def _rule_plan(seed: SeedCorpus, bundle: dict, *, protocol: str,
               profile: Optional[dict] = None,
               ledger: Optional[ActionLedger] = None) -> ActionSequence:
    """**规则打底**：从知识中枢（bundle）+ 种子自身内容推导字段级动作。

    规则（按优先级依次尝试；**每条规则最多产出一个动作**，不同规则可叠加 ⇒
    得到一条真正的「动作序列」）：

    ===========================  ======  =======================================
    规则名                        op      语义
    ===========================  ======  =======================================
    ``missing-required-header``  add     补齐该方法**必填**却缺失的头
    ``session-header-repair``    add     从前序消息**搬运**会话头（Session 等）
    ``drop-optional-header``     remove  删掉该方法**非必填**的头
    ``cseq-replay``              update  把 CSeq 改成下一条消息的 CSeq（重放边界）
    ``value-pool-boundary``      update  换成知识中枢取值池里的**另一个**取值
    ``drop-argument``            remove  删掉命令参数（行命令协议）
    ``resolve-url-placeholder``  update  把 URL 里的 ``<stream>`` 占位符解掉
    ===========================  ======  =======================================

    ★ **协议无关**：规则只消费 bundle 的通用桶（``required_headers`` /
      ``session_header`` / ``headers``）与 profile 的 ``url_placeholders``，
      **不含任何协议名硬编码**；唯一的字段级例外是「序列号字段 CSeq」
      （与 ``core/fused/downstream/edge_cover.py`` 的既有处理一致）——
      它由专门的 ``cseq-replay`` 规则负责，不参与取值池替换。
    """
    bundle = bundle or {}
    required_headers = bundle.get("required_headers") or {}
    session_header = bundle.get("session_header") or {}
    headers_bucket = bundle.get("headers") or {}
    placeholders = (profile or {}).get("url_placeholders") or {}
    stream_value = str(placeholders.get("<stream>") or "")
    messages = list(seed.messages)

    actions: list[Action] = []
    names: list[str] = []
    touched: set[tuple[int, str]] = set()

    def _take(rule: str, action: Action) -> bool:
        """登记一个动作；同一 ``(消息下标, 字段)`` 只允许被改一次。"""
        key = (int(action.msg_index), str(action.field_path).lower())
        if key in touched:
            return False
        touched.add(key)
        actions.append(action)
        names.append(rule)
        return True

    # 每条规则最多产出一个动作（用 `_rule_done` 提前退出外层扫描）
    def _rule_done(before: int) -> bool:
        return len(names) > before

    # --- R1 缺失必填头补齐 -------------------------------------------------
    before = len(names)
    for index, message in enumerate(messages):
        for header in required_headers_for(required_headers,
                                           str(message.method)):
            if find_header(message.headers, header) is not None:
                continue
            value = _default_header_value(headers_bucket, header)
            if not value:
                # ★ 批次 1.5 改动 4：取值池为空 ⇒ **按同一种子已有样本的
                #   形态生成/搬运真实值**（序号型生成下一序号，普通值直接搬运）
                #   ⇒ 补齐动作**不再必被拒** ⇒ ⑤ 种子不再缺必填头
                #   ⇒ 服务端不再拒收（此前 sip 9/24 条 ⑤ 种子缺 CSeq）。
                sample = _sample_header_value(messages, header)
                if sample:
                    value = _sequence_like_value(
                        messages, header, str(message.method).upper())
            if not value:
                # ★ R-2：知识中枢里**取不到非空兜底值** ⇒ **不产出这个动作**。
                #   落盘 ``CSeq: `` ⇒ 服务端必然拒收 ⇒ 零价值却占掉契约名额
                #   （对 SemFuzz「36%→87%」是负贡献）。
                #   ⇒ 记一条拒绝台账（**可观测**，不是静默跳过），
                #     并**继续试下一个必填头**（不占用动作名额）。
                if ledger is not None:
                    ledger.reject(None, REJECT_EMPTY_VALUE,
                                  f"rule=missing-required-header header={header}")
                continue
            _take("missing-required-header",
                  Action(OP_ADD, index, f"{HEADER_PATH_PREFIX}{header}", value))
            break
        if _rule_done(before):
            break

    # --- R2 会话头搬运（从前序消息复制真实值） -----------------------------
    before = len(names)
    for index, message in enumerate(messages):
        for spec in session_header.get(str(message.method).upper()) or []:
            if not isinstance(spec, dict):
                continue
            header = str(spec.get("header") or "")
            try:
                occurrence = int(spec.get("from_occurrence", 1))
            except (TypeError, ValueError):
                occurrence = 1
            if not header or find_header(message.headers, header) is not None:
                continue
            donor_index = occurrence - 1
            if not (0 <= donor_index < len(messages)):
                continue
            donor_key = find_header(messages[donor_index].headers, header)
            if donor_key is None:
                continue
            _take("session-header-repair",
                  Action(OP_ADD, index, f"{HEADER_PATH_PREFIX}{header}",
                         str(messages[donor_index].headers[donor_key])))
            break
        if _rule_done(before):
            break

    # --- R3 删掉非必填头 ---------------------------------------------------
    before = len(names)
    for index, message in enumerate(messages):
        reqs = {str(r).lower()
                for r in required_headers_for(required_headers,
                                              str(message.method))}
        for header in list(message.headers.keys()):
            if str(header).lower() in reqs:
                continue
            _take("drop-optional-header",
                  Action(OP_REMOVE, index, f"{HEADER_PATH_PREFIX}{header}"))
            break
        if _rule_done(before):
            break

    # --- R4 CSeq 重放（把本条消息的 CSeq 序号改成下一条的序号） ------------
    for index in range(len(messages) - 1):
        current = messages[index]
        following = messages[index + 1]
        current_key = find_header(current.headers, "CSeq")
        following_key = find_header(following.headers, "CSeq")
        if current_key is None or following_key is None:
            continue
        _take("cseq-replay",
              Action(OP_UPDATE, index, f"{HEADER_PATH_PREFIX}{current_key}",
                     _replayed_cseq(str(current.headers[current_key]),
                                    str(following.headers[following_key]))))
        break

    # --- R5 取值池边界替换（换成池子里**另一个**取值；跳过序列号字段） ------
    before = len(names)
    for index, message in enumerate(messages):
        for header, value in list(message.headers.items()):
            if str(header).lower() == "cseq":
                continue
            pool = _header_pool(headers_bucket, header)
            candidates = [v for v in pool if v != str(value)]
            if not candidates:
                continue
            _take("value-pool-boundary",
                  Action(OP_UPDATE, index,
                         f"{HEADER_PATH_PREFIX}{header}", candidates[0]))
            break
        if _rule_done(before):
            break

    # --- R6 删掉命令参数（行命令协议） -------------------------------------
    before = len(names)
    for index, message in enumerate(messages):
        if not message.argument:
            continue
        _take("drop-argument", Action(OP_REMOVE, index, "argument"))
        break

    # --- R7 URL 占位符解算（profile 声明了 <stream> 时） -------------------
    if stream_value:
        before = len(names)
        for index, message in enumerate(messages):
            if "<stream>" not in (message.url or ""):
                continue
            _take("resolve-url-placeholder",
                  Action(OP_UPDATE, index, "url",
                         message.url.replace("<stream>", stream_value)))
            break

    # 动作数上限（序列太长会让单条种子偏离真实会话太远）
    actions = actions[:MAX_PLAN_ACTIONS]
    names = names[:MAX_PLAN_ACTIONS]

    intent = "+".join(names)
    return ActionSequence(actions=tuple(actions), intent=intent)


def _sanitize_actions(seed: SeedCorpus, actions: tuple[Action, ...],
                       ledger: ActionLedger,
                       allowed_endpoints: Optional[set[str]] = None,
                       required_headers: Optional[dict] = None
                       ) -> tuple[Action, ...]:
    """剔除对当前种子**不合法**的动作（越界 / 域外 / 缺值 …），并登记拒绝原因。

    ★ 逐条判定用的是「动作执行到该步时的中间状态」——故必须**顺序**判定。
    """
    kept: list[Action] = []
    # 用一份**影子种子**模拟执行顺序，使存在性判定与真实执行一致。
    shadow = SeedCorpus.from_dict(seed.to_dict())
    for action in actions:
        index = getattr(action, "msg_index", -1)
        message = None
        if isinstance(index, int) and not isinstance(index, bool) \
                and 0 <= index < len(shadow.messages):
            message = shadow.messages[index]
        reason = _reject_reason(action, message, allowed_endpoints,
                                required_headers)
        if reason is not None:
            ledger.reject(action, reason, _reject_detail(action))
            continue
        kept.append(action)
        ACTION_OPS[action.op].apply(action, message)
    return tuple(kept)


def _expected_class_vocabulary(bundle: dict) -> set[str]:
    """期望响应类别的**封闭词表**（来自知识中枢 statuses 桶）。

    词表为空 ⇒ **任何** ``expected_class`` 都不被接受（fail-closed）。
    """
    statuses = (bundle or {}).get("statuses") or {}
    return {str(k).strip() for k in statuses.keys() if str(k).strip()}


def render_action_prompt(seed: SeedCorpus, bundle: dict, *, protocol: str,
                         profile: Optional[dict] = None) -> tuple[str, str]:
    """渲染 LLM 提示（**只允许产出 ActionSequence，绝不允许产出字节**）。

    Returns:
        ``(system, user)``。
    """
    system = (
        "你是协议模糊测试的变异规划器。你**只能**输出一个 JSON 对象，"
        "描述对给定真实种子做的**字段级动作序列**。\n"
        "硬性约束：\n"
        "1. **禁止输出任何原始字节 / 报文 / 十六进制**；你只输出抽象动作。\n"
        "2. `field_path` 只能取以下**封闭取值域**之一：\n"
        "   - `headers.<Name>`（消息级头，`<Name>` 大小写不敏感匹配）\n"
        "   - `url`（消息 URL）\n"
        "   - `argument`（命令参数；URL 类协议留空）\n"
        "   - `body`（消息体）\n"
        "   其它任何路径都会被**拒绝**。\n"
        "3. `op` 只能取 `add` / `remove` / `update`；`remove` 的 `value` 必须为 null，"
        "`add` / `update` 必须带 `value`。\n"
        "4. `msg_index` 是 0 基的消息下标，必须落在消息条数范围内。\n"
        "5. 输出格式（严格 JSON，无多余文字）：\n"
        '{"intent": "<一句话意图>", "expected_class": "", '
        '"actions": [{"op": "update", "msg_index": 0, '
        '"field_path": "headers.CSeq", "value": "1"}]}'
    )
    lines: list[str] = []
    lines.append(f"协议: {protocol}")
    lines.append(f"消息条数: {len(seed.messages)}")
    lines.append("种子（按消息顺序；每条给出方法与已有字段）：")
    for index, message in enumerate(seed.messages):
        fields = [f"{k}={v}" for k, v in message.headers.items()]
        detail = "; ".join(fields) if fields else "(无字段)"
        extra = ""
        if message.url:
            extra += f" url={message.url}"
        if message.argument:
            extra += f" argument={message.argument}"
        if message.body:
            extra += " body=<非空>"
        lines.append(f"  [{index}] {message.method} | {detail}{extra}")
    vocabulary = sorted(_expected_class_vocabulary(bundle))
    if vocabulary:
        lines.append(f"可用的 expected_class 词表（留空表示无期望）: "
                     f"{', '.join(vocabulary)}")
    else:
        lines.append("expected_class: 无可用词表 ⇒ 必须留空")
    user = "\n".join(lines)
    return system, user


def parse_action_sequence(raw: Any, bundle: dict, *,
                          ledger: ActionLedger) -> ActionSequence:
    """解析 LLM 输出为 :class:`ActionSequence`（**域外动作一律拒绝**）。

    ★ LLM **不允许产出字节**：本函数只接受「动作描述」形态的 dict；
      任何 ``field_path`` 落在封闭取值域之外 → 拒绝并记
      ``reject_reason="field_path_out_of_domain"``。
    """
    payload = raw
    if isinstance(payload, list):
        payload = {"actions": payload}
    if not isinstance(payload, dict):
        if ledger is not None:
            ledger.reject(None, REJECT_MALFORMED_ACTION,
                          f"LLM 输出类型非法: {type(raw).__name__}")
        return ActionSequence()
    data = payload.get("actions")
    if data is None and isinstance(payload.get("action_sequence"), dict):
        data = payload["action_sequence"].get("actions")
    if not isinstance(data, list):
        if ledger is not None:
            ledger.reject(None, REJECT_MALFORMED_ACTION,
                          "LLM 输出缺 actions 数组")
        return ActionSequence()
    actions = tuple(Action.from_dict(item) for item in data
                    if isinstance(item, dict))
    intent = str(payload.get("intent") or "")
    expected = str(payload.get("expected_class") or "").strip()
    if expected:
        vocabulary = _expected_class_vocabulary(bundle)
        if expected not in vocabulary:
            if ledger is not None:
                ledger.reject(None, REJECT_EXPECTED_CLASS_OUT_OF_VOCAB,
                              f"expected_class={expected!r} 不在词表内")
            expected = ""
    return ActionSequence(actions=actions, intent=intent,
                          expected_class=expected)


def plan_actions(seed: SeedCorpus, bundle: dict, *, protocol: str,
                 llm: Any = None, profile: Optional[dict] = None,
                 ledger: ActionLedger) -> ActionSequence:
    """为一个真实种子规划动作序列。

    ★ **规则打底、LLM 兜底**（与 B-6 同构）：
      确定性规则先给出动作序列；**规则给不出**任何动作时，才请 LLM 兜底。
    ★ **LLM 只允许产出 ActionSequence，不允许产出字节**（SemFuzz 的硬约束）：
      LLM 的每个动作都要过封闭取值域校验，域外动作**拒绝并记 reject_reason**。
    ★ LLM 不可用 / 超时 / 输出不可解析 ⇒ **降级为规则结果**（不抛异常、不阻断）。

    Args:
        seed:    真实种子（只读）。
        bundle:  知识中枢（``assemble_bundle`` 产物）。
        protocol: 协议名（进 prompt）。
        llm:     可选的 LLM 客户端（``core.llm.LLMClient`` 形态）；
                  ``None`` ⇒ **纯规则**（确定性）。
        profile: 可选的协议 profile（``url_placeholders`` 等）；``None`` ⇒
                  相关规则不触发。
        ledger:  **必需的**拒绝台账（P1-2：不给台账 ⇒ 拒绝会被静默吞掉）。

    Returns:
        :class:`ActionSequence`（**动作均已通过合法性校验**）。
    """
    # ★ P2-2：必填头表（按方法分组）⇒ ``remove`` 必填头会被拒绝并记账。
    required_headers = (bundle or {}).get("required_headers") or None
    rules = _rule_plan(seed, bundle, protocol=protocol, profile=profile,
                       ledger=ledger)
    # ★ P0-1 纵深防御：合法端点集合（与 corpus_gate 的 G1 共用同一份实现）
    allowed = _allowed_endpoint_set(profile)
    rules = ActionSequence(
        actions=_sanitize_actions(seed, rules.actions, ledger, allowed,
                                   required_headers),
        intent=rules.intent,
        expected_class=rules.expected_class,
    )
    if rules.actions or llm is None:
        return rules
    # 规则给不出 ⇒ LLM 兜底
    try:
        system, user = render_action_prompt(seed, bundle, protocol=protocol,
                                            profile=profile)
        raw = llm.chat_json(system=system, user=user, temperature=0.2,
                            max_tokens=2000)
    except Exception:
        # LLM 不可用 / 超时 / 抛错 ⇒ 降级为规则结果（不抛、不阻断）
        return rules
    planned = parse_action_sequence(raw, bundle, ledger=ledger)
    planned = ActionSequence(
        actions=_sanitize_actions(seed, planned.actions, ledger, allowed,
                                   required_headers),
        intent=planned.intent,
        expected_class=planned.expected_class,
    )
    return planned if planned.actions else rules


# ===========================================================================
# 6. 底料：真实抓包种子（① 已发表语料 → ② kb 真实抓包）
# ===========================================================================

def _request_line_fields(profile: dict) -> tuple[bool, bool]:
    """从 ``profile.raw_format.request_line`` 解析出「有 url / 有 argument」。"""
    template = str((profile.get("raw_format") or {}).get("request_line")
                   or "{method} {url} {version}")
    fields = template.split()
    has_url = any("{url}" in f for f in fields)
    has_argument = any("{argument}" in f for f in fields)
    return has_url, has_argument


def _build_message(request_line: str, profile: dict) -> Optional[SeedMessage]:
    """把一条请求行解析成 :class:`~core.models.SeedMessage`。

    协议差异**全部来自 profile.raw_format.request_line 模板**（零协议硬编码）。
    """
    text = str(request_line or "").strip()
    if not text:
        return None
    tokens = text.split()
    if not tokens:
        return None
    has_url, has_argument = _request_line_fields(profile)
    url = tokens[1] if (has_url and len(tokens) > 1) else ""
    argument = " ".join(tokens[1:]) if (has_argument and len(tokens) > 1) else ""
    return SeedMessage(method=tokens[0].upper(), headers={}, body="",
                       url=url, argument=argument)


def _split_raw_messages(text: str, profile: dict) -> list[str]:
    """把 .raw 文本切成消息块（**由 profile.raw_format 驱动**）。

    · 有头部模板的协议（``header_line`` 非空）⇒ 以**空行**分隔消息；
    · 行命令协议（``header_line`` 为空）⇒ **一行一条消息**。
    """
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    header_line = str((profile.get("raw_format") or {}).get("header_line") or "")
    if header_line:
        return [block for block in re.split(r"\n[ \t]*\n", normalized) if block.strip()]
    return [line for line in normalized.split("\n") if line.strip()]


def parse_raw_seed(text: str, profile: dict, *, protocol: str = "",
                    description: str = "") -> Optional[SeedCorpus]:
    """把一条 .raw 文本解析成 :class:`~core.models.SeedCorpus`（**可逆**）。

    · 消息切分、请求行字段（``url`` / ``argument``）、头部解析全部由
      ``profile.raw_format`` 驱动 ⇒ **协议无关**。
    · 方法不在 ``profile.allowed_methods`` 内 ⇒ 该消息**跳过**（不造垃圾消息）。
    """
    blocks = _split_raw_messages(text, profile)
    if not blocks:
        return None
    header_line = str((profile.get("raw_format") or {}).get("header_line") or "")
    allowed = {str(m).strip().upper()
               for m in (profile.get("allowed_methods") or []) if str(m).strip()}
    messages: list[SeedMessage] = []
    for block in blocks:
        lines = block.split("\n")
        message = _build_message(lines[0], profile)
        if message is None:
            continue
        if allowed and message.method not in allowed:
            continue
        if header_line:
            body_lines: list[str] = []
            for line in lines[1:]:
                stripped = line.strip()
                if not stripped:
                    continue
                if _HEADER_LINE_RE.match(stripped):
                    name, _, value = stripped.partition(":")
                    message.headers[name.strip()] = value.strip()
                else:
                    body_lines.append(stripped)
            if body_lines:
                message.body = "\n".join(body_lines)
        messages.append(message)
    if not messages:
        return None
    # ★ selected_url 保持空串：① 与既有语料一致（文件名不带流名段）；
    #   ② 消息级 url 缺失时由 scripts/seedgen.py 的 _apply_url_placeholders
    #   按 profile.default_url 兜底（避免落到 "rtsp://localhost/seed"）。
    return SeedCorpus(
        protocol=protocol or str(profile.get("protocol") or ""),
        description=description or "action-seq base seed",
        target_methods=[m.method for m in messages],
        target_state_path=[],
        messages=messages,
        generated_by="action-seq:base",
        selected_url="",
    )


#: 「时间戳形态的批次目录」目录名（``scripts/seedgen.py`` 每次生成一个批次目录）：
#: 形如 ``20261031_171135`` / ``20261021_105316``。
#: ★ 这类目录是**自动产出**（每次跑生成器就多一个）⇒ 未正式发布（无
#:   ``manifest.json``）的**不得**作为底料（可能混着已废弃、被污染的语料）。
#: ★ **语义命名**的目录（``rq4_B`` / ``pfb_exp_B`` /
#:   ``live555_20261024_110155`` / ``dict_rtsp`` / ``focused20_*`` …）是
#:   **人工/工具整理的正式语料**（有的**天然没有** manifest，例如真实抓包语料
#:   ``live555_20261024_110155`` —— ``docs/工具/验收与规范/CI与验收说明.md:122`` 记载
#:   「CI 无法重建」）⇒ **一律保留**，不因缺 manifest 而排除。
TIMESTAMP_DIR_PATTERN = re.compile(r"^\d{8}_\d{6}$")


def _is_timestamp_batch_dir(name: str) -> bool:
    """目录名是否呈「时间戳形态」（``20261031_171135``）。"""
    return bool(TIMESTAMP_DIR_PATTERN.match(str(name or "").strip()))


def _dir_has_action_seq_layer(directory: Path) -> bool:
    """该语料目录是否是**含 action_seq 层**的目录（即本层自己的产物）。

    判据：读该目录的 ``manifest.json``，看 ``layers`` 里是否含 ``action_seq``。
    manifest 缺失/损坏 ⇒ **不排除**（保守：宁可多取也不静默丢底料）。
    """
    manifest = directory / "manifest.json"
    if not manifest.is_file():
        return False
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    layers = data.get("layers") or []
    return any(str(x).strip() == "action_seq" for x in layers)


def _published_group_dirs(protocol: str, group: Optional[str],
                          root: Optional[Path]) -> list[Path]:
    """列出 ``derived/seeds/<protocol>/`` 下与聚焦组匹配的语料目录（按新→旧）。

    ★ 指定了 ``group`` 时**只返回匹配的目录**（manifest 记录的 focus_group
      优先，其次目录名以组字母结尾）——**绝不拿别的组的语料冒充**（那会让
      「底料 = 本组的真实语料」这一前提失效）。

    ★★ 只承认「**正式发布过**」的**时间戳形态**批次目录：
      ``derived/seeds/<协议>/`` 下混着两类目录——
        · **时间戳形态**（``^\\d{8}_\\d{6}$``，如 ``20261031_171135`` /
          ``20261021_105316``）= ``scripts/seedgen.py`` **每次生成**一个批次目录
          的**自动产出** ⇒ 正式发布时会写 ``manifest.json``
          ⇒ **无 manifest ⇒ 未正式发布 ⇒ 排除**。
          （未正式发布的时间戳批次里可能混着**已书面废弃、且被外网摄像机 URL
          污染**的语料：``docs/实验/RQ4_AFLNet实验设计.md:770``：「``derived/seeds/
          rtsp/20261031_171135`` 这份**已被污染**，不应作为任何实验语料使用」；
          同文件 716 行量化：含 ``isapi`` / ``10.11.26.98`` 的文件 **22/37 = 59.5%**。
          本函数按 **mtime 新→旧**排序 ⇒ 未发布的污染目录会排在第一
          ⇒ ⑤ 层会把**已废弃的污染语料**当底料。）
        · **语义命名**（``rq4_B`` / ``pfb_exp_B`` /
          ``live555_20261024_110155`` / ``dict_rtsp`` / ``focused20_*`` …）
          = **人工/工具整理的正式语料** ⇒ **一律保留**。
          ★ 其中 ``live555_20261024_110155`` 是**真实抓包语料**（**天然没有**
            manifest —— ``docs/工具/验收与规范/CI与验收说明.md:122`` 记载「CI 无法重建」）
            ⇒ **绝不能**因为缺 manifest 而被排除。
      ⇒ 护栏只针对**时间戳形态**：既挡掉废弃污染目录，也挡住将来任何
        「新生成但未正式发布」的时间戳批次（同类问题不再复发），
        同时**不误伤**语义命名的正式语料。
      ★ 护栏作用在**候选筛选**这一步 ⇒ ``group`` 为空（不做组匹配、任何目录都进候选）
        的分支**同样**被挡住（否则等于没修）。
      ★ ``group='B'`` 等既有路径**行为不变**：参与匹配的时间戳目录**都带**
        ``manifest.json``（正式发布）⇒ 筛选结果一致。
    """
    base = Path(root) if root else paths.seeds_dir(protocol)
    if not base.is_dir():
        return []
    candidates: list[tuple[float, Path, int]] = []
    wanted = str(group or "").strip().upper()
    for child in sorted(base.iterdir()):
        if not child.is_dir():
            continue
        raws = list(child.glob("*.raw"))
        if not raws:
            continue
        # ★★ 护栏：**时间戳形态**的批次目录必须带 ``manifest.json`` 才算
        #   「正式发布」⇒ 可作底料；无 manifest ⇒ 生成过但未发布的中间产物
        #   ⇒ 可能混着**已废弃且被污染**的语料
        #   （docs/实验/RQ4_AFLNet实验设计.md:770）⇒ 绝不入候选。
        #   ★ **语义命名**的目录（rq4_B / pfb_exp_B / live555_* / dict_rtsp
        #     / focused20_* …）是**人工/工具整理的正式语料**，**一律保留** ——
        #     真实抓包语料 live555_20261024_110155 就**没有** manifest
        #     （docs/工具/验收与规范/CI与验收说明.md:122：CI 无法重建）⇒ 不能误伤。
        if _is_timestamp_batch_dir(child.name) \
                and not (child / "manifest.json").is_file():
            continue
        # ★ P0-2（断自喂）：**排除本层自己产出的目录**。
        #   自喂闭环的成因：action_seq 的产物与基准层**写在同一个目录**，
        #   而该目录的 manifest 带 `focus_group` ⇒ `_published_group_dirs` 给它
        #   最高匹配优先级 ⇒ **下一轮把自己的产物当底料** ⇒ 变异的变异
        #   （QA 实测：连跑 3 次底料条数 39 → 50 → 98，指数膨胀）。
        #   ⇒ 底料只取「**不含 action_seq 层**」的目录（= 已发表的基准语料）。
        if _dir_has_action_seq_layer(child):
            continue
        match = 0
        if wanted:
            manifest = child / "manifest.json"
            if manifest.exists():
                try:
                    data = json.loads(manifest.read_text(encoding="utf-8"))
                    recorded = str((data.get("seedgen") or {})
                                    .get("focus_group") or "").strip().upper()
                    if recorded == wanted:
                        match = 2
                except (json.JSONDecodeError, OSError):
                    match = 0
            if match < 2 and child.name.strip().upper().endswith(wanted):
                match = max(match, 1)
            if match == 0:
                continue          # ★ 不属于本组 ⇒ 不作为底料
        mtime = max((p.stat().st_mtime for p in raws), default=0.0)
        candidates.append((mtime, child, match))
    # 匹配组优先；同匹配度按 mtime 新→旧
    candidates.sort(key=lambda item: (-item[2], -item[0], item[1].name))
    return [item[1] for item in candidates]


def _load_published_seeds(protocol: str, profile: dict, *,
                          group: Optional[str] = None,
                          root: Optional[Path] = None,
                          strict_source_only: bool = False,
                          source_set: Optional[Iterable[str]] = None,
                          base_corpus_from: Optional[Path] = None,
                          base_corpus_trusted: bool = False
                          ) -> list[SeedCorpus]:
    """来源 ①：``derived/seeds/<protocol>/<组>/*.raw``（已发表的语料）。

    ★★ **严格单源模式**（``strict_source_only``）：底料语料本身可能含**其它源**
      的知识（实测：``derived/seeds/rtsp/rq4_B`` 里有 **12 条 ``vuln_boundary``
      种子** = vuln 源的漏洞模式）⇒ 单源实验必须把它们排除。
      判据：读该目录 ``manifest.json`` 的 ``seeds[].layer_name``
      → ``vuln_boundary`` 层在 ``vuln`` ∉ source_set 时**排除**；
      → manifest **缺失** ⇒ 无法证明干净 ⇒ **整目录排除**（保守）。
    """
    seeds: list[SeedCorpus] = []
    src_set = {str(s).strip().lower() for s in (source_set or ())}
    # ★★ 批次 2.5（F5）：**两段式底料** —— 显式指定底料目录时
    #   **只**用它（不再从「任意历史批次」里挑）⇒ 底料来源**可证**。
    #   ★ 校验：底料 manifest 的 ``provenance.source_set`` 必须 ⊆ 本次源集合
    #     ⇒ 否则**拒绝**（底料带别的源的知识 ⇒ 跨源污染）。
    if base_corpus_from is not None:
        _dir = Path(base_corpus_from)
        if not _dir.is_absolute():
            _dir = (Path(root).parent / _dir if root is not None
                    else Path.cwd() / _dir)
        if not _dir.is_dir():
            print(f"[⑤ 底料] ★ 指定的底料目录不存在: {_dir} ⇒ 无底料")
            return []
        _mf = _dir / "manifest.json"
        if not _mf.is_file():
            print(f"[⑤ 底料] ★ 底料目录无 manifest（无法证明来源干净）: {_dir}"
                  f" ⇒ 拒绝使用")
            return []
        try:
            _doc = json.loads(_mf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            print(f"[⑤ 底料] ★ 底料 manifest 解析失败: {_mf} ⇒ 拒绝使用")
            return []
        _prov = ((_doc.get("provenance") or {}).get("source_set") or [])
        _prov_set = {str(s).strip().lower() for s in _prov}
        if src_set and _prov_set and not _prov_set.issubset(src_set):
            print(f"[⑤ 底料] ★ 底料的源集合 {sorted(_prov_set)} **不是**本次"
                  f" {sorted(src_set)} 的子集 ⇒ **拒绝**（跨源污染）")
            return []
        print(f"[⑤ 底料] 使用显式指定的底料: {_dir.name}"
              f"（源集合={sorted(_prov_set) or '（未声明）'}，{len(_prov_set & src_set)} 个源在本次集合内）")
        return _read_published_dir(_dir, protocol, profile, strict_source_only,
                                    src_set)
    for directory in _published_group_dirs(protocol, group, root):
        seeds = _read_published_dir(directory, protocol, profile,
                                    strict_source_only, src_set)
        if seeds:
            break        # 只取**最新**的匹配目录（避免重复底料）
    return seeds


def _read_published_dir(directory: Path, protocol: str, profile: dict,
                        strict_source_only: bool,
                        src_set: set[str]) -> list[SeedCorpus]:
    """读一个语料目录下的 ``*.raw``（⑤ 层底料）。

    ★ **严格单源模式**：排除 ``vuln_boundary`` 层的底料（vuln 源知识）；
      manifest **缺失** ⇒ 无法证明干净 ⇒ **整目录排除**（保守）。
    """
    seeds: list[SeedCorpus] = []
    _skip: set[str] = set()
    if strict_source_only:
        _mf = directory / "manifest.json"
        if not _mf.is_file():
            print("[⑤ 严格单源] 排除无 manifest 的语料目录（无法证明干净）: "
                  f"{directory.name}")
            return seeds
        try:
            _doc = json.loads(_mf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return seeds
        _by_name = {str(s.get("filename") or ""): str(s.get("layer_name") or "")
                    for s in (_doc.get("seeds") or [])}
        if "vuln" not in src_set:
            _skip = {n for n, lay in _by_name.items()
                     if lay == "vuln_boundary"}
        if _skip:
            print(f"[⑤ 严格单源] {directory.name}: 排除 {len(_skip)} 条 "
                  "vuln_boundary 底料（vuln 源知识）")
    for raw_path in sorted(directory.glob("*.raw")):
        if raw_path.name in _skip:
            continue
        try:
            text = raw_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parsed = parse_raw_seed(
            text, profile, protocol=protocol,
            description=f"action-seq base: {raw_path.name}")
        if parsed is None:
            continue
        parsed.seed_id = f"aseq-{raw_path.stem}"
        seeds.append(parsed)
    return seeds


def _parse_capture_log(text: str, profile: dict) -> list[SeedMessage]:
    """把一份真实抓包日志解析成消息序列（**profile.traffic_schema 驱动**）。

    · ``request_pattern`` 命中行 ⇒ 一条请求（方法组 1）；
    · 请求行之后**同前缀**或**头部行形态**的连续行 ⇒ 该请求的头部；
    · ``response_pattern`` 命中行 / 空行 ⇒ 块结束。
    """
    schema = profile.get("traffic_schema") or {}
    pattern = str(schema.get("request_pattern") or "").strip()
    if not pattern:
        return []
    try:
        request_re = re.compile(pattern)
    except re.error:
        return []
    response_pattern = str(schema.get("response_pattern") or "").strip()
    try:
        response_re = re.compile(response_pattern) if response_pattern else None
    except re.error:
        response_re = None
    allowed = {str(m).strip().upper()
               for m in (profile.get("allowed_methods") or []) if str(m).strip()}
    header_line = str((profile.get("raw_format") or {}).get("header_line") or "")

    lines = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    messages: list[SeedMessage] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        match = request_re.match(line)
        if not match or match.lastindex is None or match.lastindex < 1:
            index += 1
            continue
        method = str(match.group(1)).strip().upper()
        if allowed and method not in allowed:
            index += 1
            continue
        prefix = line[:match.start(1)]
        message = _build_message(line[match.start(1):], profile)
        if message is None:
            index += 1
            continue
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor]
            if not candidate.strip():
                break
            if request_re.match(candidate):
                break
            if response_re is not None and response_re.match(candidate):
                break
            if prefix and candidate.startswith(prefix):
                payload = candidate[len(prefix):]
            elif header_line and _HEADER_LINE_RE.match(candidate.strip()):
                payload = candidate.strip()
            else:
                break
            if header_line:
                name, sep, value = payload.partition(":")
                if sep and name.strip():
                    message.headers[name.strip()] = value.strip()
            cursor += 1
        messages.append(message)
        index = cursor
    return messages


def _load_capture_seeds(protocol: str, profile: dict, *,
                        root: Optional[Path] = None) -> list[SeedCorpus]:
    """来源 ②：``kb/<protocol>/数据流量/**`` 里的真实抓包。"""
    base = Path(root) if root else paths.kb_source_dir(protocol, "traffic")
    if not base.is_dir():
        return []
    log_files = {str(n) for n in
                 ((profile.get("traffic_schema") or {}).get("log_files") or [])}
    if not log_files:
        log_files = {"client.log"}
    seeds: list[SeedCorpus] = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.name not in log_files:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        messages = _parse_capture_log(text, profile)
        if not messages:
            continue
        seeds.append(SeedCorpus(
            protocol=protocol,
            description=f"action-seq base: capture {path.name}",
            target_methods=[m.method for m in messages],
            target_state_path=[],
            messages=messages,
            generated_by="action-seq:base",
            selected_url="",
            seed_id=f"aseq-cap-{path.parent.name}-{path.stem}",
        ))
    return seeds


def load_real_base_seeds(protocol: str, profile: dict, *,
                         group: Optional[str] = None,
                         derived_root: Optional[Path] = None,
                         kb_root: Optional[Path] = None,
                         strict_source_only: bool = False,
                         source_set: Optional[Iterable[str]] = None,
                         base_corpus_from: Optional[Path] = None,
                         base_corpus_trusted: bool = False
                         ) -> tuple[list[SeedCorpus], str]:
    """按优先级取「**真实抓包底料**」（不是从零构造）。

    优先级：

    ① ``derived/seeds/<protocol>/<组>/*.raw``（已发表的语料）
    ② ``kb/<protocol>/数据流量/**`` 里的真实抓包
    ③ 都取不到 ⇒ 返回 ``([], "")`` —— 调用方**如实报告**，**不得造假**。

    Returns:
        ``(种子列表, 来源标签)``；来源标签 ∈
        ``{"internal-two-stage", "explicit-base-corpus",
        "published-corpus", "traffic-capture", ""}``。
    """
    seeds = _load_published_seeds(protocol, profile, group=group,
                                  root=derived_root,
                                  strict_source_only=strict_source_only,
                                  source_set=source_set,
                                  base_corpus_from=base_corpus_from,
                                  base_corpus_trusted=base_corpus_trusted)
    if seeds:
        # ★ 批次 2.5（F5）：底料来源必须**如实**标注（否则下游审计会把
        #   「内部两段式（同源）」误判成「published-corpus（历史语料）」）
        #   · base_corpus_trusted=True ⇒ **内部两段式**（本次刚产的基准层）
        #   · base_corpus_from 显式给出 ⇒ 外部底料（已过 provenance 校验）
        #   · 否则 ⇒ 自动找到的 published 目录（**保持原语义**）
        if base_corpus_trusted:
            return seeds, "internal-two-stage"
        if base_corpus_from is not None:
            return seeds, "explicit-base-corpus"
        return seeds, "published-corpus"
    # ★ 批次 2.5（F5）：**显式指定了底料** ⇒ 它若被拒绝（来源不干净 / 不存在）
    #   ⇒ **不再回退**到 traffic 抓包（那也是跨源污染，且违背「显式指定」的意图）
    if base_corpus_from is not None:
        return [], ""
    # ★ 严格单源模式：``traffic`` ∉ source_set ⇒ **禁用**真实抓包兜底
    #   （``kb/<协议>/数据流量/`` 是 traffic 源的原始输入 ⇒ 属跨源污染）
    if strict_source_only and "traffic" not in {
            str(s).strip().lower() for s in (source_set or ())}:
        return [], ""
    seeds = _load_capture_seeds(protocol, profile, root=kb_root)
    if seeds:
        return seeds, "traffic-capture"
    return [], ""


def mutate_seed(seed: SeedCorpus, bundle: dict, *, protocol: str,
                llm: Any = None, profile: Optional[dict] = None,
                ledger: ActionLedger
                ) -> tuple[SeedCorpus, ActionSequence]:
    """对一颗真实种子做一次字段级变异（规划 + 执行）。

    Returns:
        ``(新种子, 动作序列)``；动作序列为空 ⇒ 新种子与输入等价（无变异）。
    """
    seq = plan_actions(seed, bundle, protocol=protocol, llm=llm,
                       profile=profile, ledger=ledger)
    return apply_actions(seed, seq, ledger=ledger,
                         profile=profile,
                         required_headers=(bundle or {}).get("required_headers")
                         or None), seq


__all__ = [
    "Action",
    "ActionSequence",
    "ActionRejection",
    "ActionLedger",
    "ActionOpSpec",
    "ACTION_OPS",
    "ACTION_SEQ_GENERATED_BY",
    "VALID_OPS",
    "FIELD_PATH_SCALARS",
    "HEADER_PATH_PREFIX",
    "OP_ADD",
    "OP_REMOVE",
    "OP_UPDATE",
    "REJECT_UNKNOWN_OP",
    "REJECT_FIELD_PATH_OUT_OF_DOMAIN",
    "REJECT_MSG_INDEX_OUT_OF_RANGE",
    "REJECT_MISSING_VALUE",
    "REJECT_UNEXPECTED_VALUE",
    "REJECT_HEADER_NOT_FOUND",
    "REJECT_HEADER_ALREADY_EXISTS",
    "REJECT_EXPECTED_CLASS_OUT_OF_VOCAB",
    "REJECT_MALFORMED_ACTION",
    "REJECT_VALUE_HAS_CONTROL_CHARS",
    "REJECT_ENDPOINT_NOT_ALLOWED",
    "REJECT_EMPTY_VALUE",
    "REJECT_VALUE_TOO_LONG",
    "REJECT_HEADER_IS_REQUIRED",
    "MAX_VALUE_LENGTH",
    "normalize_field_path",
    "find_header",
    "apply_actions",
    "plan_actions",
    "parse_action_sequence",
    "render_action_prompt",
    "parse_raw_seed",
    "load_real_base_seeds",
    "mutate_seed",
]
