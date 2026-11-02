# -*- coding: utf-8 -*-
"""core/fused/semantic.py —— 语义规则两层模型（里程碑 B-1）。

两层分离（评审 T2）：
  · 证据层 EvidenceAnchor —— 「这条规则从哪来」：可溯源、可复核、可对齐。
  · 可执行层 ExecutableConstraint —— 「确定性引擎能算什么」：operator/operand/precondition。
两层之间**不共享可变状态**；无法从证据层推出可执行层的条目，
一律降级为 KnowledgeCandidate（知识候选），**不进自动生成链路**（见 §3.3 强制机制）。

设计依据：docs/rfc_source_bcd_roadmap.md §3.1（模型字段）/ §3.2（rule_id 派生）
/ §3.3（强制机制 1~2）。

★ 本模块**只定义模型与 id 派生**，不含任何读写磁盘 / 调用 LLM / 抽取规范的逻辑
  ⇒ 导入它对既有生产链路**零影响**（B 阶段「只写新文件、不改既有行为」的第一步）。
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Optional

from core import paths

__all__ = [
    "EVIDENCE_KINDS",
    "EXPLICITNESS",
    "MODALITY_MANDATORY",
    "MODALITY_NONE",
    "MODALITY_OPTIONAL",
    "MODALITY_RECOMMENDED",
    "NORMATIVE_EVIDENCE_KINDS",
    "OPERATORS",
    "REJECT_REASONS",
    "RULE_STATES",
    "SOURCE_CLASSES",
    "EvidenceAnchor",
    "ExecutableConstraint",
    "KnowledgeCandidate",
    "SemanticRule",
    "compute_evidence_id",
    "compute_rule_id",
    "compute_explicitness",
    "convert_or_reject",
    "detect_modality",
    "load_source_text",
    "normalize_field_name",
    "parse_source_anchor",
    "try_convert",
    "try_convert_with_source",
]


def _operator_domain() -> frozenset[str]:
    """可执行算子全集（**OPERATORS 的唯一真源**）。

    ★ **新增算子必须同时更新本函数**（§3.3 强制机制 2 的配套约束）。
      `OPERATORS` 由本函数派生 ⇒ 不存在「改了 OPERATORS 字面量却忘了别处」的失守点。
    """
    return frozenset(
        {"eq", "ne", "lt", "gt", "le", "ge", "in", "present", "absent", "range"}
    )


#: 证据来源类别（评审 M1：四类来源必须分开记录，不能只靠 normative > observed）
SOURCE_CLASSES: frozenset[str] = frozenset(
    {"normative_spec", "observation", "model_inference", "human"}
)

#: 证据类型。normative/abnf = 规范性；table/prose = 描述性。
EVIDENCE_KINDS: frozenset[str] = frozenset(
    {"normative", "abnf", "table", "prose"}
)

#: 显式性。explicit = 区间已校验 **且** 证据类型为规范性（问题⑧ 的分离）。
EXPLICITNESS: frozenset[str] = frozenset(
    {"explicit", "quoted", "paraphrased"}
)

#: 可执行算子全集。**新增算子必须同时更新 _operator_domain()**（§3.3 强制机制 2）。
OPERATORS: frozenset[str] = _operator_domain()

#: 规则生命周期状态（评审 M1/T9：四库分离）
RULE_STATES: frozenset[str] = frozenset(
    {"authoritative", "candidate", "revoked", "feedback"}
)


@dataclass(frozen=True)
class EvidenceAnchor:
    """证据层：这条规则从哪来。用于溯源、人工复核、投票对齐。

    ★ 与 v3 文档 §3.1 的差异：此处**不含 rule_id**（rule_id 属规则层，见
      SemanticRule.rule_id）。原因见 §2.1 的 I-1：规则身份挂在证据层会导致
      「一条规则多条证据时 id 漂移」，违反 M7「violation_of 必须唯一标识一条规则」。
    """

    evidence_id: str  # 本条证据自身的唯一 id（多条证据 → 多 id）
    spec_version: str  # "RFC3261"（规范版本，M1 要求版本隔离）
    section_path: tuple[str, ...]  # ("21", "1.1")
    source_anchor: str  # "file:rfc3261.txt#@10560"（行锚点，可读）
    span_text: str  # ★ verbatim 原文片段（空 → 不能判 explicit）
    span_start: Optional[int]  # 在源文件全文中的字符区间起点（供 B2 校验）
    span_end: Optional[int]  # 同上终点（**半开区间** [start, end)）
    evidence_kind: str  # normative|abnf|table|prose
    explicitness: str  # explicit|quoted|paraphrased（由 B2/B6 计算写入）
    source_class: str  # 四类来源（评审 M1）


@dataclass(frozen=True)
class ExecutableConstraint:
    """可执行层：确定性引擎能解释、执行、校验、归因的约束。

    ★ 每个字段的存在理由 = 「给定它，能否算出 violation 布尔值」。
      不能算的字段一律不进本层（见 §3.0 判断 1）。
    """

    target_field: str  # 受约束字段路径（消息级约束用 ""）
    operator: str  # OPERATORS 之一
    operand: tuple[str, ...]  # 比较值；空 = 该算子无参（present/absent）
    operand_source: str  # "constant" | "field_ref"（长度由另一字段决定）
    operand_ref: Optional[str]  # operand_source=="field_ref" 时指向该字段
    applies_to_state: tuple[str, ...]  # 适用协议状态（空 = 任意状态）
    applies_to_method: tuple[str, ...]  # 适用方法（空 = 任意）
    expected_behavior: str  # 取自 rfc_config.expected_response_classes
    sender_role: str  # 构造约束的发送方："client" | "server"
    receiver_role: str  # 处理期望的接收方
    precondition: Optional[str]  # 前置条件（可为空 = 无前置）

    def __post_init__(self) -> None:
        """构造期自检（§3.3 强制机制 2）——**真的会抛 ValueError**，不做静默降级。

        六条校验逐字对齐设计文档 §3.3：
          ① operator 必须在 OPERATORS 内；
          ② 无参算子（present/absent）**不得**带 operand；
          ③ 有参算子**必须**带 operand；
          ④ operand_source=="field_ref" 时必须给 operand_ref；
          ⑤ operand_source=="constant" 时**不得**给 operand_ref；
          ⑥ target_field 为空时仅允许 present。
        """
        if self.operator not in OPERATORS:
            raise ValueError(f"非法 operator: {self.operator}")
        # 无参算子不得带 operand；有参算子必须带 operand
        if self.operator in ("present", "absent") and self.operand:
            raise ValueError(f"{self.operator} 不得带 operand: {self.operand}")
        if self.operator not in ("present", "absent") and not self.operand:
            raise ValueError(f"{self.operator} 必须带 operand")
        if self.operand_source == "field_ref" and not self.operand_ref:
            raise ValueError("operand_source=field_ref 必须给 operand_ref")
        if self.operand_source == "constant" and self.operand_ref:
            raise ValueError("operand_source=constant 不得给 operand_ref")
        if not self.target_field and self.operator != "present":
            # 消息级约束允许 target_field 为空，但只能是 present/absent
            raise ValueError("target_field 为空时仅允许 present/absent")


@dataclass(frozen=True)
class SemanticRule:
    """完整语义规则 = 证据层 + 可执行层 + 生命周期状态 + 规则身份。

    ★ rule_id 在**顶层**（不在证据层）—— 见 §2.1 的 I-1。
    """

    rule_id: str  # 全局唯一，由结构化身份派生（§3.2）
    evidence: EvidenceAnchor  # 证据层
    constraint: Optional[ExecutableConstraint]  # 可执行层；None = 不可转换
    subject_type: str  # "method" | "header" | "status" | "message_type"
    subject_name: str
    rule_state: str  # authoritative|candidate|revoked|feedback
    supersedes: tuple[str, ...]  # 被本规则替代的 rule_id
    model_confidence: Optional[float]  # ★ 与 explicitness/validated **分开记录**（T6）
    validated: bool  # B2 证据区间校验是否通过


#: ★ 批次 2（迁移项 D）：``sanitize_rule`` 的**移除原因词表**（封闭）。
#:   每一次移除**都必须**落一条（可观测，**不得静默丢弃**）。
SANITIZE_REJECT_REASONS: tuple[str, ...] = (
    "empty_subject",        # subject_name 与 target_field 都空 ⇒ 投影不出任何桶
    "empty_operand",        # 有参算子但 operand 空（构造期已拦 ⇒ 兜底）
    "self_reference",       # operand_ref == target_field ⇒ 自指约束
)


def sanitize_rule(rule: Any) -> tuple[Optional[SemanticRule], Optional[str]]:
    """规则后处理（批次 2 / 迁移项 D）：移除**伪规则 / 空规则**。

    ★ **动机**：SpecGPT 的后处理（校验 JSON 格式 + **移除伪状态/空状态**）我们没有
      ⇒ 本函数是等价物；LLM 兜底路径可能产出「结构合法但语义无效」的规则。

    ★ 三类移除（逐条记 ``reject_reason``，**不静默丢弃**）：

      ① ``empty_subject``：``subject_name`` 与 ``constraint.target_field``
         **都为空** ⇒ 投影时的归组键为空 ⇒ **投影不出任何桶**
         ⇒ 是无效负载（实测 E1 组 14 条里 **9 条**属此类）。
      ② ``empty_operand``：有参算子（``le/ge/lt/gt/eq/ne/in/range``）但
         ``operand`` 为空 ⇒ ``ExecutableConstraint.__post_init__`` 已拦，
         这里只是**兜底**（防止 LLM 兜底路径绕过构造校验）。
      ③ ``self_reference``：``operand_source == "field_ref"`` 且
         ``operand_ref == target_field`` ⇒ **自指约束**（拿自己比自己）⇒ 无意义。

    ★ **刻意不移除** ``expected_behavior`` 为空的规则：
      它**仍然能**投影出 **C（合法边界）**，只是出不了 **P（响应期望）**
      ⇒ 移除它会白白丢掉 C 侧知识。
      （实测 E1 组 **14/14 条** ``expected_behavior`` 全空 ⇒ 若一并移除，
      ``legal_boundary`` 会从 **5 条变成 0 条** ⇒ 整条 RFC 语义链路重新断开。）

    Args:
        rule: ``SemanticRule``（或带 ``.constraint`` / ``.subject_name`` 的对象）。

    Returns:
        ``(保留的规则, 移除原因)``：
        · 保留 ⇒ ``(rule, None)``；
        · 移除 ⇒ ``(None, "<reject_reason> ∈ SANITIZE_REJECT_REASONS>")``。
    """
    constraint = getattr(rule, "constraint", None)
    if constraint is None:
        return None, "empty_subject"
    subject_name = str(getattr(rule, "subject_name", "") or "").strip()
    target_field = str(getattr(constraint, "target_field", "") or "").strip()
    if not subject_name and not target_field:
        return None, "empty_subject"
    operator = str(getattr(constraint, "operator", "") or "")
    operand = tuple(getattr(constraint, "operand", ()) or ())
    if operator not in ("present", "absent") and not operand:
        return None, "empty_operand"
    operand_source = str(getattr(constraint, "operand_source", "") or "")
    operand_ref = str(getattr(constraint, "operand_ref", "") or "").strip()
    if operand_source == "field_ref" and operand_ref and operand_ref == target_field:
        return None, "self_reference"
    return rule, None


@dataclass(frozen=True)
class KnowledgeCandidate:
    """知识候选：**不可转换为可执行规则**的内容。

    ★ 这是「不可转换者只作知识候选、不进自动生成链路」的**载体类型**。
      它**没有** constraint 字段 —— 结构上就装不下 operator/operand。
      落盘到独立文件 candidates.jsonl，自动生成链路**读不到**它（§3.3 强制机制 3）。
    """

    candidate_id: str
    evidence: EvidenceAnchor
    subject_type: str
    subject_name: str
    raw_text: str  # 原始自由文本（仅供人工复核/检索）
    convertible: bool = False  # 恒为 False；显式保留以表达「曾尝试转换」
    reject_reason: Optional[str] = None  # 为何不可转换（可观测性，评审 M4）


def compute_rule_id(
    protocol: str,
    spec_version: str,
    section_path: tuple[str, ...],
    subject_type: str,
    subject_name: str,
    operator: str,
    operand: tuple[str, ...],
    operand_ref: Optional[str],
    expected_behavior: str,
) -> str:
    """rule_id = "r" + sha256(canonical_json(结构化身份))[:16]

    ★ 为什么这样派生（改进v2 §3.1 注释「全局唯一（不依赖内容哈希）」）：
      · **不含 span/span_text** → 同一规范文本被重新抽取（措辞微调、LLM 改写）
        得到的 id **不变** → 规则可跨构建对齐、可做增量更新。
      · **不含 LLM 输出顺序/编号** → LLM 非确定性不影响 id。
      · **含 operator + operand + section_path** → 同一字段的两条不同约束
        （如「长度 ≤ 63」与「长度 = 0」）得到**不同** id。
      · **含 spec_version** → 不同 RFC 版本的同名规则天然分开（M1 版本隔离）。
    ★ 唯一性边界：两个语义完全相同但位于不同章节的约束会得到不同 id
      （section_path 不同）——这是**有意的**：它们是可分别引用的两条知识。
    """
    ident = {
        "protocol": protocol,
        "spec_version": spec_version,
        "section_path": list(section_path),
        "subject_type": subject_type,
        "subject_name": subject_name,
        "operator": operator,
        "operand": list(operand),
        "operand_ref": operand_ref,
        "expected_behavior": expected_behavior,
    }
    raw = json.dumps(
        ident, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return "r" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def compute_evidence_id(
    rule_id: str, source_anchor: str, span_start: Optional[int]
) -> str:
    """证据 id = rule_id + 锚点位置 → 同规则不同证据可区分。"""
    raw = f"{rule_id}|{source_anchor}|{span_start}"
    return "e" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]


# ===========================================================================
# B-2：转换判定（证据层 → 可执行层）
#
# 设计依据：docs/rfc_source_bcd_roadmap.md
#   · §3.4（行 476-528）：C1~C7 判定顺序表 + C7 的「expected_behavior 缺失
#     不阻断」特例；
#   · §3.5（行 530-581）：规范性动词决定 explicitness 的上限（MAY/OPTIONAL
#     → optional_modality）；operator/operand 的三层方案（规则优先 + LLM
#     兜底 + 结构校验）。
#
# ★ **判定顺序是本任务的核心**（改进v2 问题⑧）：**先验证证据（C2），再判
#   显式性（C3）**。反过来就会把「模型推断的规则」错误提升为「规范性强制
#   要求」—— 先确认「这段原文确实是规范里那一句」，再判断「它算不算规范性
#   证据」。
#
# ★ 本模块**不实现 operator/operand 的模式表**（那是 B-5 的
#   `core/fused/semantic_rules.py`）：B-2 只定义 **resolver 注入接口**并给出
#   默认行为（无 resolver ⇒ C4 判 `operator_unresolved`）。
# ===========================================================================

#: 全部 reject_reason（**顺序 = 判定顺序**：C1~C7 + optional_modality）
REJECT_REASONS: tuple[str, ...] = (
    "no_span",  # C1
    "span_unverified",  # C2
    "non_normative_kind",  # C3
    "optional_modality",  # §3.5 规范性动词上限（C3 之后、C4 之前）
    "operator_unresolved",  # C4
    "operand_unresolved",  # C5
    "non_length_operand",  # C5'：单位不可换算成字节（seconds 等）→ 拒绝转换
    "field_unbound",  # C6
    "expectation_not_in_vocab",  # C7
)

#: C3 认可的规范性证据类型（§3.4 C3：normative / abnf）
NORMATIVE_EVIDENCE_KINDS: frozenset[str] = frozenset({"normative", "abnf"})

#: 规范性动词强度（MUST/SHALL/REQUIRED 强制；SHOULD/RECOMMENDED 建议；
#: MAY/OPTIONAL 可选；无规范动词 = 描述性）
MODALITY_MANDATORY = "mandatory"
MODALITY_RECOMMENDED = "recommended"
MODALITY_OPTIONAL = "optional"
MODALITY_NONE = "none"

#: 规范性动词（RFC 2119）。大小写不敏感 —— B-5 的模式表按小写书写正则，
#: 且 RFC 2119 §3 的关键字在正文中以全大写出现（实测 430/430 真实候选
#: 全为大写形式，无「仅小写」的情况）。
#: ★ 词边界用 `(?<!\w)...(?!\w)`（等价 `\b`）：避免 "MAYBE" / "REQUIREDLY"
#:   之类的子串误命中。
_RE_VERB_MANDATORY = re.compile(
    r"(?<!\w)(?:MUST|SHALL|REQUIRED)(?!\w)", re.IGNORECASE
)
_RE_VERB_RECOMMENDED = re.compile(
    r"(?<!\w)(?:SHOULD|RECOMMENDED)(?!\w)", re.IGNORECASE
)
_RE_VERB_OPTIONAL = re.compile(
    r"(?<!\w)(?:MAY|OPTIONAL)(?!\w)", re.IGNORECASE
)

#: 字段名规范化（大小写 + 下划线/连字符统一）—— §3.5 层次4 第2条：
#: 「线索与候选集做**精确匹配或规范化匹配**（大小写、下划线/连字符）」。
#: ★ **不做模糊匹配** —— 模糊匹配是幻觉的主要来源（§3.5 层次4 第3条）。
_RE_FIELD_SEP = re.compile(r"[-_]")


def detect_modality(span_text: str) -> str:
    """判定句子的**规范性动词强度**（§3.5 层次1 第3条）。

    返回 `MODALITY_MANDATORY` / `MODALITY_RECOMMENDED` / `MODALITY_OPTIONAL`
    / `MODALITY_NONE` 之一。

    ★ **强度取「最强命中」**（mandatory > recommended > optional）：
      同一句里出现多个规范性动词时，强制性的那一个说了算。
      理由（实测依据）：RFC 2119 的术语声明句
      `The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", ... "MAY", and
      "OPTIONAL" ...` **同时含有全部关键字** —— 若按「先命中者」判定，
      这类样板句会被误判为 MAY/OPTIONAL 而错误丢弃。

    ★ MAY/OPTIONAL **只在其为句中最强动词时**才算「可选」：
      "Systems MUST support TCP and MAY do X" 的强制部分是 MUST ⇒ 整句按
      mandatory 处理（丢弃它会丢掉一条真规则）。
    """
    text = span_text or ""
    if _RE_VERB_MANDATORY.search(text):
        return MODALITY_MANDATORY
    if _RE_VERB_RECOMMENDED.search(text):
        return MODALITY_RECOMMENDED
    if _RE_VERB_OPTIONAL.search(text):
        return MODALITY_OPTIONAL
    return MODALITY_NONE


def compute_explicitness(span_text: str, *, verified: bool, evidence_kind: str) -> str:
    """计算证据的 `explicitness`（§3.1 定义 + §4 M4 纯净度判据）。

    ★ §3.1：`explicit` = 区间已校验 **且** 证据类型为规范性。
    ★ §4 M4（行 955）：`explicitness=="explicit"` 的规则中，原文确实含
      MUST/SHALL/REQUIRED 的比例必须 **= 100%**（不纯即为污染）。
      ⇒ 因此「规范性动词」也是 explicit 的**必要条件**。

    三档取值：
      · `explicit`     —— 区间已校验 + evidence_kind 为 normative/abnf
                          + 句中含 MUST/SHALL/REQUIRED；
      · `quoted`       —— 区间已校验 + 规范性证据，但动词强度只到
                          SHOULD/RECOMMENDED（**建议**不是**强制**）；
      · `paraphrased`  —— 其余（区间不可核对 / 非规范性证据 / 无规范动词）。

    ★ B-2 的 `try_convert` **不写回 evidence.explicitness**（其签名固定为
      返回 (constraint, reject_reason)）—— 本函数供 B-6 计算/写入时使用。
    """
    if not verified or evidence_kind not in NORMATIVE_EVIDENCE_KINDS:
        return "paraphrased"
    modality = detect_modality(span_text)
    if modality == MODALITY_MANDATORY:
        return "explicit"
    if modality == MODALITY_RECOMMENDED:
        return "quoted"
    return "paraphrased"


def parse_source_anchor(source_anchor: str) -> tuple[Optional[str], Optional[int]]:
    """解析 `file:<name>#@<lineno>` → (文件名, 1-based 行号)。

    ★ 行号缺失或非数字（如 ABNF 通道的 `#@abnf` 标记）⇒ 行号为 `None`
      （调用方据此**跳过**行号包含性检查，但逐字比对照做）。
    """
    if not source_anchor:
        return None, None
    raw = source_anchor.strip()
    if raw.startswith("file:"):
        raw = raw[len("file:") :]
    fname, sep, tail = raw.partition("#@")
    lineno: Optional[int] = None
    if sep:
        try:
            lineno = int(tail.strip())
        except ValueError:
            lineno = None
    return (fname or None), lineno


def _splitline_offsets(text: str) -> dict[int, int]:
    """行号（1-based）→ 该行首字符在全文中的绝对偏移。

    ★ 与 `str.splitlines(keepends=True)` 的切分口径**完全一致**，与 B-3 的
      `_line_offsets` 同口径。
    ★ **为什么必须用 splitlines 口径**：RFC 正文含**换页符 `\x0c`**（实测
      rtsp 92 / sip 269 / smtp 95 处），`str.splitlines()` 会把它当行边界，
      而 `text.count("\\n")` 不会 ⇒ 两种口径的行号相差 9~11 行（实测
      430/430 全部不符）。B-3 的行号用的是 splitlines 口径。
    """
    offsets: dict[int, int] = {}
    pos = 0
    for lineno, seg in enumerate(text.splitlines(keepends=True), start=1):
        offsets[lineno] = pos
        pos += len(seg)
    return offsets


def load_source_text(protocol: str, source_anchor: str) -> Optional[str]:
    """按 `source_anchor` 从 `kb/<protocol>/spec/` 读取源文件全文（**只读**）。

    ★ 读法与 B-3 的 `rfc_extractor` **完全一致**
      （`read_text(encoding="utf-8", errors="ignore")`）—— 否则换行/编码
      口径不一致会导致字符偏移错位，C2 的逐字比对必然失败。

    ★ 找不到文件 ⇒ 返回 `None` ⇒ 调用方拿不到 `source_text` ⇒ C2 判
      `span_unverified`（**无法核对即不通过**）。
    """
    fname, _ = parse_source_anchor(source_anchor)
    if not fname:
        return None
    path = paths.kb_source_dir(protocol, "rfc") / fname
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8", errors="ignore")


def _as_evidence(candidate: Any) -> EvidenceAnchor:
    """把 candidate 归一为 `EvidenceAnchor`。

    接受：`EvidenceAnchor` 本体，或任何带 `.evidence` 字段的对象
    （`KnowledgeCandidate` / `SemanticRule`）。
    """
    if isinstance(candidate, EvidenceAnchor):
        return candidate
    ev = getattr(candidate, "evidence", None)
    if isinstance(ev, EvidenceAnchor):
        return ev
    raise TypeError(
        "candidate 必须是 EvidenceAnchor，或带 .evidence 字段的对象；"
        f"实际收到 {type(candidate).__name__}"
    )


def _as_str_tuple(value: Any) -> tuple[str, ...]:
    """把 operand / applies_to_* 的取值统一成 `tuple[str, ...]`。

    * `None` → `()`
    * 单个字符串 → `(value,)`（**不拆成字符**）
    * 序列 → 逐元素 `str()`
    * `set` / `frozenset` → **排序后**转 tuple（集合无序，若直接迭代会得到
      随 PYTHONHASHSEED 变化的顺序 ⇒ 破坏「同输入同 id」的确定性保证）
    """
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (set, frozenset)):
        return tuple(sorted(str(v) for v in value))
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    return (str(value),)


def normalize_field_name(name: str) -> str:
    """字段名规范化（大小写 + 下划线/连字符统一）。

    ★ 只做**规范化精确匹配**，不做模糊匹配（§3.5 层次4 第3条）。
    ★ **公共 API**：B-5 的 `core/fused/semantic_rules.py` 的字段绑定复用本函数
      ⇒ 两侧口径**必然一致**（不会出现「B-2 绑得上、B-5 绑不上」）。
    """
    return _RE_FIELD_SEP.sub("-", (name or "").strip().lower())


def _verify_span_in_source(
    ev: EvidenceAnchor, source_text: Optional[str]
) -> bool:
    """C2：区间在源文件中**逐字**可核对。

    判据（三条全过才算通过）：
      ① `source_text` 非 None（**无法核对即不通过** —— 问题⑧ 的正确姿态）；
      ② `source_text[span_start:span_end] == span_text`（**逐字比对**，
         不是「区间在范围内」这种弱校验）；
      ③ 区间起点落在 `source_anchor` 的行锚点所指的那一行内
         （splitlines 口径，见 `_splitline_offsets` 的说明）。

    ★ ② 的可靠性已实测：B-3 的 430 条真实候选（rtsp 80 / sip 80 / smtp 270）
      **430/430 逐字一致**。
    ★ ③ 是对 ② 的**补强**：它保证「anchor 指的文件/行」与「实际取到的区间」
      是同一处，防止 anchor 与正文错位（例如把 A 文件的正文配 B 文件的行号）。
      ★ ③ **只在行号可解析、且该行确实存在于 source_text 时**才施加；
        行号无法解析（如 `#@abnf`）或该行不存在于 source_text（source_text
        可能只是章节窗口而非全文）⇒ **跳过**③（不误杀），只保留 ①②。
    """
    if source_text is None:
        return False
    start = ev.span_start
    end = ev.span_end
    if start is None or end is None:
        return False
    if start < 0 or end > len(source_text) or start >= end:
        return False
    # ② 逐字比对（区间语义 = Python 切片，end 开区间 —— 与 B-3 实测口径一致）
    if source_text[start:end] != (ev.span_text or ""):
        return False
    # ③ 行锚点包含性
    _, lineno = parse_source_anchor(ev.source_anchor)
    if lineno is not None:
        offsets = _splitline_offsets(source_text)
        line_start = offsets.get(lineno)
        if line_start is not None:
            # 该行**存在于** source_text ⇒ 行号口径可用 ⇒ 施加包含性约束
            # （防止「把 A 文件的正文配 B 文件的行号」这类静默错配）。
            line_end = offsets.get(lineno + 1)
            if line_end is None:
                line_end = len(source_text)
            if not (line_start <= start < line_end):
                return False
        # 该行**不存在于** source_text（source_text 可能只是章节窗口而非全文）
        # ⇒ **跳过**行号检查（不误杀），逐字比对 ② 仍然生效。
    return True


def try_convert(
    candidate: Any,
    *,
    source_text: Optional[str] = None,
    known_fields: Iterable[str] = (),
    expected_vocab: Iterable[str] = (),
    resolver: Optional[Callable[[str], Optional[dict]]] = None,
) -> tuple[Optional[ExecutableConstraint], Optional[str]]:
    """证据层 → 可执行层的**纯函数**转换判定（§3.4 C1~C7）。

    返回 `(constraint, reject_reason)`：
      · 全部通过 ⇒ `(ExecutableConstraint, None)`；
      · 任一不通过 ⇒ `(None, "<reject_reason>")`，`reject_reason ∈ REJECT_REASONS`。

    Args:
        candidate: `EvidenceAnchor`，或带 `.evidence` 字段的对象
            （`KnowledgeCandidate` / `SemanticRule`）。
        source_text: **源文件全文**，供 C2 核对区间。
            缺省为 `None` ⇒ C2 判 `span_unverified`
            （**无法核对即不通过**：不能核对就不该算 explicit）。
            建议用 `load_source_text(protocol, anchor)` 取得。
        known_fields: C6 的协议已知字段集（**由调用方传入**，B-2 不读
            profile/rfc_config，保持纯函数性）。空集合 ⇒ 无字段可绑定。
        expected_vocab: C7 的词表（来自 `rfc_config.expected_response_classes`），
            同样由调用方传入。
        resolver: **operator/operand 的解析器**（B-5 注入真实模式表）。

    **resolver 契约**（B-2 只定义接口，默认 `None` ⇒ C4 判
    `operator_unresolved`）::

        resolver(span_text: str) -> Optional[dict]

    返回的 dict 至少含 `"operator"`（必须在 `OPERATORS` 内），可选键：

        ==================  ==========================================
        键                   含义
        ==================  ==========================================
        "operator"          算子名（`OPERATORS` 之一）
        "operand"           比较值（序列 / 单值 / None）；present/absent
                            必须为空
        "operand_source"    "constant"（默认）| "field_ref"
        "operand_ref"       字段引用（`operand_source=="field_ref"` 时必填）
        "target_field"      受约束字段；"" = 消息级约束
        "expected_behavior" 处理期望；缺失/"" = **无处理期望**
        "applies_to_state"  可选透传（默认 ()）
        "applies_to_method" 可选透传（默认 ()）
        "sender_role"       可选透传（默认 "client"）
        "receiver_role"     可选透传（默认 "server"）
        "precondition"      可选透传（默认 None）
        "reject_reason"     **可选否决**：resolver 认得这句约束但**不可转换**
                            （如单位是 seconds）⇒ 填一个 `REJECT_REASONS` 里的
                            原因（如 "non_length_operand"），本函数**原样返回**。
                            未登记的原因 ⇒ 抛 ValueError（不默默接受）。
        ==================  ==========================================

    返回 `None` ⇒ C4 判 `operator_unresolved`（**不猜**）。

    ★ **与 B-5 的衔接**：`core/fused/semantic_rules.py` 落地 ≥12 条**有序**
      正则模式表，产出一个符合上述契约的 `resolver` 注入本函数即可；
      B-2 **不实现**任何 operator 正则（模式表是 B-5 的独立资产）。
    ★ **与 B-6 的衔接**：`llm_out_of_vocab` 由 B-6 在 LLM 兜底层自行判定，
      本函数只认 `OPERATORS` 词表 —— resolver 返回词表外的算子 ⇒
      C4 判 `operator_unresolved`（**不默默接受**）。

    ★ **C7 的重要特例**（§3.4 行 528）：`expected_behavior` **缺失不阻断**
      转换 —— 约束的「构造侧」（C）可以独立成立，缺 P（处理期望）时该规则
      **只能用于「构造违规种子」，不能用于「判定 oracle 预期」**。
      ⇒ 缺失时 C7 判**通过**，产出的 `ExecutableConstraint.expected_behavior`
      置为 `""`（**不是 None、不是猜一个**）。
      ★ 该语义与 C 阶段 `close_loop(seed, result, expected=None)` 的
        「`expected=None` ⇒ 跳过语义偏离判定」**必须对齐**。
    """
    ev = _as_evidence(candidate)
    span_text = ev.span_text or ""

    # ── C1：无区间 = 无法溯源 = 不能算 explicit ──────────────────────
    if ev.span_start is None or ev.span_end is None or not span_text:
        return None, "no_span"

    # ── C2：区间在源文件中可核对（**先验证证据**）────────────────────
    if not _verify_span_in_source(ev, source_text):
        return None, "span_unverified"

    # ── C3：证据类型必须是规范性（表格/散文里的约束不是 RFC 的 MUST）───
    if ev.evidence_kind not in NORMATIVE_EVIDENCE_KINDS:
        return None, "non_normative_kind"

    # ── optional_modality：规范性动词强度上限（§3.5 层次1 第3条）────
    #    位置在 C3 之后、C4 之前：先确认「它是规范性证据」，再看「动词强度
    #    是否只是 MAY/OPTIONAL」。放 C3 之前会让描述性散文因含 "may" 而被
    #    误标为 optional_modality（掩盖了更根本的 non_normative_kind）。
    modality = detect_modality(span_text)
    if modality == MODALITY_OPTIONAL:
        return None, "optional_modality"

    # ── C4：从 span_text 能解析出**唯一**的 operator ─────────────────
    if resolver is None:
        return None, "operator_unresolved"
    parsed = resolver(span_text)
    if not parsed or not isinstance(parsed, dict):
        return None, "operator_unresolved"
    # ★ resolver 可用 "reject_reason" 键**显式否决**（B-5 的单位拒转换走这条）：
    #   「模式表认得这句约束，但它的操作数不可换算 ⇒ 明确拒转换，不猜」。
    veto = parsed.get("reject_reason")
    if veto:
        if veto not in REJECT_REASONS:
            raise ValueError(f"resolver 返回未登记的 reject_reason: {veto}")
        return None, str(veto)
    operator = parsed.get("operator")
    if not operator or operator not in OPERATORS:
        return None, "operator_unresolved"

    # ── C5：能解析出 operand（数值/集合/字段引用）─────────────────────
    operand = _as_str_tuple(parsed.get("operand"))
    operand_source = parsed.get("operand_source") or "constant"
    operand_ref = parsed.get("operand_ref") or None
    if operand_source not in ("constant", "field_ref"):
        return None, "operand_unresolved"
    if operator in ("present", "absent"):
        # 无参算子：不得带 operand（构造校验强制机制 2 的第②条）
        if operand:
            return None, "operand_unresolved"
    elif not operand:
        # 有参算子：必须带 operand（强制机制 2 的第③条）
        return None, "operand_unresolved"
    if operand_source == "field_ref":
        # 字段引用：必须给出 operand_ref（强制机制 2 的第④条）
        if not operand_ref:
            return None, "operand_unresolved"
    elif operand_ref:
        # constant：不得给 operand_ref（强制机制 2 的第⑤条）
        return None, "operand_unresolved"

    # ── C6：target_field 能绑定到协议已知字段集 ─────────────────────
    target_field = parsed.get("target_field") or ""
    if target_field:
        known = {normalize_field_name(f) for f in known_fields}
        if normalize_field_name(target_field) not in known:
            return None, "field_unbound"
    elif operator != "present":
        # 消息级约束（target_field=""）仅允许 present（强制机制 2 的第⑥条）
        return None, "field_unbound"

    # ── C7：expected_behavior ∈ 词表；**缺失不阻断** ─────────────────
    expected_behavior = parsed.get("expected_behavior") or ""
    if expected_behavior:
        if expected_behavior not in set(expected_vocab):
            return None, "expectation_not_in_vocab"
        if modality == MODALITY_RECOMMENDED:
            # §3.5 层次1 第3条 SHOULD 行：「期望响应不可断言」
            # ⇒ 用 C7 特例的 "" 表达「无处理期望」（该规则只能用于构造违规
            #    种子，不能用于判定 oracle 预期）。
            expected_behavior = ""

    # ★ 到这里构造校验强制机制 2 的 6 条**已全部显式检查过** ⇒ 构造不会抛
    #   ValueError（若抛了，说明上面的前置校验有漏，那是本函数的 bug）。
    constraint = ExecutableConstraint(
        target_field=target_field,
        operator=operator,
        operand=operand,
        operand_source=operand_source,
        operand_ref=operand_ref,
        applies_to_state=_as_str_tuple(parsed.get("applies_to_state")),
        applies_to_method=_as_str_tuple(parsed.get("applies_to_method")),
        expected_behavior=expected_behavior,
        sender_role=parsed.get("sender_role") or "client",
        receiver_role=parsed.get("receiver_role") or "server",
        precondition=parsed.get("precondition") or None,
    )
    return constraint, None


def try_convert_with_source(
    candidate: Any,
    protocol: str,
    *,
    known_fields: Iterable[str] = (),
    expected_vocab: Iterable[str] = (),
    resolver: Optional[Callable[[str], Optional[dict]]] = None,
) -> tuple[Optional[ExecutableConstraint], Optional[str]]:
    """`try_convert` 的便捷封装：**自动**按 anchor 读取源文件全文再判定。

    ★ 避免调用方「传错 source_text」（把 A 文件的正文配 B 文件的 anchor）
      这一类静默错误 —— C2 的逐字比对会把这种错配判成 `span_unverified`，
      但**根因**在调用方，很难排查。
    """
    ev = _as_evidence(candidate)
    return try_convert(
        candidate,
        source_text=load_source_text(protocol, ev.source_anchor),
        known_fields=known_fields,
        expected_vocab=expected_vocab,
        resolver=resolver,
    )


def convert_or_reject(
    candidate: Any,
    *,
    source_text: Optional[str] = None,
    known_fields: Iterable[str] = (),
    expected_vocab: Iterable[str] = (),
    resolver: Optional[Callable[[str], Optional[dict]]] = None,
) -> tuple[Optional[ExecutableConstraint], Optional[KnowledgeCandidate]]:
    """转换判定的**产物形态**封装（B-8 落盘用）。

    返回 `(constraint, knowledge_candidate)`，二者**恰有一个**非 None：
      · 转换成功 ⇒ `(ExecutableConstraint, None)`；
      · 转换失败 ⇒ `(None, KnowledgeCandidate(reject_reason=...))`。

    ★ 这就是「不可转换者只作知识候选、不进自动生成链路」的**产物载体**：
      失败项落 `candidates.jsonl`（强制机制 3），成功项落 `rules.jsonl`，
      自动生成链路只读后者。
    """
    ev = _as_evidence(candidate)
    constraint, reject_reason = try_convert(
        candidate,
        source_text=source_text,
        known_fields=known_fields,
        expected_vocab=expected_vocab,
        resolver=resolver,
    )
    if constraint is not None:
        return constraint, None

    if isinstance(candidate, KnowledgeCandidate):
        base = {
            "candidate_id": candidate.candidate_id,
            "subject_type": candidate.subject_type,
            "subject_name": candidate.subject_name,
            "raw_text": candidate.raw_text,
        }
    else:
        base = {
            "candidate_id": f"c{ev.evidence_id}",
            "subject_type": "",
            "subject_name": "",
            "raw_text": ev.span_text or "",
        }
    return None, KnowledgeCandidate(
        evidence=ev,
        convertible=False,
        reject_reason=reject_reason,
        **base,
    )
