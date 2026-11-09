"""core/fused/validation.py —— fail-closed 验证。

失败即抛错, 不静默。
"""
from __future__ import annotations

from core.fused.hub.exceptions import FusedSchemaError
from core.fused.hub.registry import UnregisteredReferenceError
from core.fused.hub.models import (
    Subject, Value, FactKey, Claim, Fact, AspectSpec, ValueType,
)


# ===========================================================================
# 自定义错误
# ===========================================================================

class ValueTypeMismatchError(FusedSchemaError):
    code = "value_type_mismatch"


class UnregisteredAspectError(FusedSchemaError):
    code = "unregistered_aspect"


class UnregisteredEpistemicError(FusedSchemaError):
    code = "unregistered_epistemic"


# ===========================================================================
# 验证函数
# ===========================================================================

def validate_value(value: Value, aspect_spec) -> None:
    """验证 value.type 与 aspect 声明的 value_type 一致。"""
    if value.type != aspect_spec.value_type:
        raise ValueTypeMismatchError(
            f"Value.type={value.type!r} 与 AspectSpec({aspect_spec.name!r})."
            f"value_type={aspect_spec.value_type!r} 不匹配",
            context={"value_type": value.type,
                     "expected": aspect_spec.value_type,
                     "aspect": aspect_spec.name})


def validate_subject(subject: Subject, registry) -> None:
    """未注册的 Subject.type → 抛 UnregisteredReferenceError。"""
    types = {t.get("type") for t in registry.subject_types}
    if subject.type not in types:
        raise UnregisteredReferenceError(
            f"Subject.type={subject.type!r} 未在 registry 注册",
            context={"subject_type": subject.type,
                     "registered": sorted(types)})


def validate_aspect(fact_key, registry) -> None:
    """未注册的 aspect 名 → 抛 UnregisteredAspectError。"""
    names = {a.get("name") for a in registry.aspects}
    if fact_key.aspect not in names:
        raise UnregisteredAspectError(
            f"fact_key.aspect={fact_key.aspect!r} 未在 registry 注册",
            context={"aspect": fact_key.aspect,
                     "registered": sorted(names)})


def validate_epistemic(epistemic_type: str, registry) -> None:
    """未注册的 epistemic_type → 抛 UnregisteredEpistemicError。"""
    types = {t.get("name") for t in registry.epistemic_types}
    if epistemic_type not in types:
        raise UnregisteredEpistemicError(
            f"epistemic_type={epistemic_type!r} 未在 registry 注册",
            context={"epistemic_type": epistemic_type,
                     "registered": sorted(types)})


def validate_claim(claim: Claim, registry) -> None:
    """Claim 完整验证: epistemic_type 注册 + value/aspect 匹配需 fact_key。"""
    validate_epistemic(claim.epistemic_type, registry)
    # value 单独不验证(没有 aspect 上下文), 由 validate_fact 提供完整性


def validate_fact(fact: Fact, registry) -> None:
    """完整验证一个 Fact: subject / aspect / epistemic 全部注册 + 类型匹配。"""
    from core.fused.hub.models import AspectSpec
    validate_subject(fact.fact_key.subject, registry)
    validate_aspect(fact.fact_key, registry)

    # 找到 aspect_spec, 验证 value.type
    spec_dict = {a.get("name"): a for a in registry.aspects}
    aspect_name = fact.fact_key.aspect
    if aspect_name in spec_dict:
        ad = spec_dict[aspect_name]
        spec = AspectSpec(
            name=ad["name"],
            value_type=ad["value_type"],
            applicable_subject_types=tuple(ad.get("applicable_subject_types", ("*",))),
            resolution_semantics=ad.get("resolution_semantics", "consensus"),
            cardinality=ad.get("cardinality", "one"))
        for claim in fact.claims:
            validate_value(claim.value, spec)
            validate_epistemic(claim.epistemic_type, registry)


def validate_all(fact: Fact, registry) -> None:
    """兼容层验证入口。"""
    validate_fact(fact, registry)