"""core/fused/models.py —— Layer 0 中枢核心数据结构（v2 设计真源）。

本模块是 Layer 0 中枢核心数据结构的唯一实现（架构已于 2026-10-09 退役）。

设计真源: fused_hub/docs/fused_knowledge_hub_design.md 第三部分。
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


# ===========================================================================
# Value / ValueType
# ===========================================================================

ValueType = str   # 12 种之一: scalar/enum/set/sequence/range/pattern/struct/
                  # ref/observation/binary/union/text
                  # 12 种（见 fused_hub/docs/fused_knowledge_hub_design.md §Value 表）


@dataclass(frozen=True)
class Value:
    type: ValueType
    data: Any


# ===========================================================================
# Subject（递归：qualifiers 可能含嵌套 Subject，关系作为 Subject）
# ===========================================================================

@dataclass(frozen=True)
class Subject:
    type: str
    name: str
    qualifiers: dict = field(default_factory=dict)
    path: list = field(default_factory=list)


# ===========================================================================
# AspectSpec / AspectRegistry Entry（Aspect 是字符串键，契约结构件）
# ===========================================================================

@dataclass(frozen=True)
class AspectSpec:
    name: str
    value_type: ValueType
    applicable_subject_types: tuple = ("*",)       # tuple of str | "*"
    resolution_semantics: str = "consensus"
    cardinality: str = "one"                       # "one" | "many"


# ===========================================================================
# Condition（联合类型，8 种）
# ===========================================================================

@dataclass(frozen=True)
class ConditionAlways:
    type: str = "always"


@dataclass(frozen=True)
class ConditionNever:
    type: str = "never"


@dataclass(frozen=True)
class ConditionUnknown:
    type: str = "unknown"


@dataclass(frozen=True)
class ConditionPredicate:
    type: str = "predicate"
    subject: Any = None      # Subject (dataclass 不允许前向引用, 实际是 Subject)
    aspect: str = ""
    op: str = "eq"           # eq/neq/in/not_in/gt/gte/lt/lte/matches/contains/exists/not_exists/before/after
    value: Any = None        # Value


@dataclass(frozen=True)
class ConditionAnd:
    type: str = "and"
    operands: tuple = ()


@dataclass(frozen=True)
class ConditionOr:
    type: str = "or"
    operands: tuple = ()


@dataclass(frozen=True)
class ConditionNot:
    type: str = "not"
    operand: Any = None      # Condition


@dataclass(frozen=True)
class ConditionRef:
    type: str = "ref"
    condition_id: str = ""


# ===========================================================================
# FactKey / Subject / Aspect 构成身份
# ===========================================================================

@dataclass(frozen=True)
class FactKey:
    protocol: str
    version: str
    subject: Any = None     # Subject
    aspect: str = ""
    condition: Any = None   # Condition


# ===========================================================================
# Scope
# ===========================================================================

@dataclass(frozen=True)
class Scope:
    observation_population: Any = None  # str | None
    measurement_unit: Any = None        # str | None
    independence: str = "unknown"       # independent / dependent / unknown
    bounded: bool = False
    bounds: dict = field(default_factory=dict)


# ===========================================================================
# Evidence / Locator（联合）
# ===========================================================================

@dataclass(frozen=True)
class LocatorLine:
    type: str = "line"
    file: str = ""
    line: int = 0
    col: Any = None        # int | None


@dataclass(frozen=True)
class LocatorByte:
    type: str = "byte"
    file: str = ""
    offset: int = 0
    length: int = 0


@dataclass(frozen=True)
class LocatorTime:
    type: str = "time"
    file: str = ""
    timestamp: str = ""


@dataclass(frozen=True)
class LocatorField:
    type: str = "field"
    file: str = ""
    path: tuple = ()         # tuple of str


@dataclass(frozen=True)
class LocatorRange:
    type: str = "range"
    file: str = ""
    start: int = 0
    end: int = 0


@dataclass(frozen=True)
class Evidence:
    evidence_id: str
    claim_id: str
    source_type: str
    source_id: str
    document: str
    locator: Any = None         # Locator (any of the five)
    quote: Any = None
    content_fingerprint: str = ""
    extraction_fingerprint: str = ""


# ===========================================================================
# Claim
# ===========================================================================

@dataclass(frozen=True)
class Claim:
    claim_id: str
    fact_id: str
    value: Any = None            # Value
    epistemic_type: str = ""
    authority: str = ""
    scope: Any = None            # Scope
    evidence: tuple = ()         # tuple of Evidence
    confidence: Any = None       # float | None


# ===========================================================================
# Resolution / Support / Generalization
# ===========================================================================

@dataclass(frozen=True)
class Support:
    independent: int = 0
    dependent: int = 0
    unknown: int = 0
    total: int = 0


@dataclass(frozen=True)
class Generalization:
    scope: str = "unknown"        # protocol-wide / single-scenario / unknown
    confidence: Any = None        # float | None


@dataclass(frozen=True)
class Resolution:
    status: str = "unresolved"    # resolved / unresolved
    method: str = "insufficient"   # single/consensus/precedence/conflict/insufficient
    basis_claim_ids: tuple = ()
    reason: str = ""
    reason_code: str = ""
    policy_version: str = ""
    support: Any = None          # Support | None
    generalization: Any = None    # Generalization | None


# ===========================================================================
# Alignment
# ===========================================================================

@dataclass(frozen=True)
class Alignment:
    claim_id: str
    relation: str = ""          # supports / contradicts / refines / deviates / ...
    target: Any = None          # "resolution" | {"claim_id": str}
    reason: Any = None


# ===========================================================================
# Fact
# ===========================================================================

@dataclass(frozen=True)
class FactMetadata:
    created_at: str = ""
    profile_version: str = ""


@dataclass(frozen=True)
class Fact:
    fact_id: str
    fact_key: Any = None         # FactKey
    claims: tuple = ()           # tuple of Claim
    resolution: Any = None      # Resolution | None
    alignments: tuple = ()      # tuple of Alignment
    metadata: Any = None        # FactMetadata