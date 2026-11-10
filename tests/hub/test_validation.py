"""tests/test_validation.py —— fail-closed 验证。"""
from __future__ import annotations

import pytest

from core.fused.hub.models import (
    Subject, FactKey, ConditionAlways, Value, Claim, Fact, FactMetadata,
    AspectSpec,
)
from core.fused.hub.registry import Registry, UnregisteredReferenceError
from core.fused.hub.validation import (
    ValueTypeMismatchError, UnregisteredAspectError, UnregisteredEpistemicError,
    validate_value, validate_subject, validate_aspect, validate_epistemic,
    validate_claim, validate_fact,
)


def _empty_registry():
    return Registry(base_dir=__import__("pathlib").Path("core") / "fused" / "hub" / "registry")


def test_validate_value_type_mismatch_raises():
    """value.type != aspect_spec.value_type → 抛 ValueTypeMismatchError。"""
    spec = AspectSpec(name="existence", value_type="bool")
    v = Value(type="scalar", data=1)
    with pytest.raises(ValueTypeMismatchError):
        validate_value(v, spec)


def test_validate_value_type_match_ok():
    spec = AspectSpec(name="existence", value_type="bool")
    validate_value(Value(type="bool", data=True), spec)  # 不抛


def test_validate_subject_unregistered_raises():
    """未注册的 Subject.type → 抛 UnregisteredReferenceError。"""
    reg = _empty_registry()
    s = Subject(type="never_registered_type", name="SETUP")  # 不在注册表
    with pytest.raises(UnregisteredReferenceError):
        validate_subject(s, reg)


def test_validate_aspect_unregistered_raises():
    reg = _empty_registry()
    fk = FactKey(protocol="rtsp", version="1.0",
                 subject=Subject(type="method", name="SETUP"),
                 aspect="never_registered_aspect",
                 condition=ConditionAlways())
    with pytest.raises(UnregisteredAspectError):
        validate_aspect(fk, reg)


def test_validate_epistemic_unregistered_raises():
    reg = _empty_registry()
    with pytest.raises(UnregisteredEpistemicError):
        validate_epistemic("never_registered", reg)


def test_validate_claim_raises_on_unregistered_epistemic():
    reg = _empty_registry()
    c = Claim(claim_id="c1_x", fact_id="f1_x",
              value=Value(type="scalar", data=1),
              epistemic_type="unregistered_type",
              authority="x", scope=None, evidence=())
    with pytest.raises(UnregisteredEpistemicError):
        validate_claim(c, reg)


def test_validate_fact_integration_with_real_registry(tmp_path):
    """集成: 写一份最小 registry, 验证 fact 全过。"""
    import json
    sub = tmp_path / "subject_type_registry.json"
    sub.write_text(json.dumps({
        "core_version": "1.0", "registered_types": [{"type": "method"}]
    }), encoding="utf-8")
    asp = tmp_path / "aspect_registry.json"
    asp.write_text(json.dumps({
        "core_version": "1.0",
        "registered_aspects": [{"name": "existence", "value_type": "bool"}]
    }), encoding="utf-8")
    epi = tmp_path / "epistemic_type_registry.json"
    epi.write_text(json.dumps({
        "core_version": "1.0",
        "registered_types": [{"name": "normative"}]
    }), encoding="utf-8")

    from core.fused.hub.registry import Registry as _R
    reg = _R(tmp_path)
    f = Fact(
        fact_id="f1_x",
        fact_key=FactKey(protocol="rtsp", version="1.0",
                         subject=Subject(type="method", name="SETUP"),
                         aspect="existence", condition=ConditionAlways()),
        claims=(Claim(claim_id="c1_x", fact_id="f1_x",
                     value=Value(type="bool", data=True),
                     epistemic_type="normative",
                     authority="rfc", scope=None, evidence=()),),
        metadata=FactMetadata(created_at="2026-10-08", profile_version="v1"))
    validate_fact(f, reg)   # 不抛


def test_validate_fact_integration_value_type_mismatch(tmp_path):
    """集成: 注册了 method+existence(bool)+normative, 但 claim 给 int → 抛。"""
    import json
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "subject_type_registry.json").write_text(
        json.dumps({"core_version": "1.0", "registered_types": [{"type": "method"}]}),
        encoding="utf-8")
    (tmp_path / "aspect_registry.json").write_text(
        json.dumps({"core_version": "1.0",
                    "registered_aspects": [{"name": "existence", "value_type": "bool"}]}),
        encoding="utf-8")
    (tmp_path / "epistemic_type_registry.json").write_text(
        json.dumps({"core_version": "1.0",
                    "registered_types": [{"name": "normative"}]}),
        encoding="utf-8")
    from core.fused.hub.registry import Registry as _R
    reg = _R(tmp_path)
    f = Fact(
        fact_id="f1_x",
        fact_key=FactKey(protocol="rtsp", version="1.0",
                         subject=Subject(type="method", name="SETUP"),
                         aspect="existence", condition=ConditionAlways()),
        claims=(Claim(claim_id="c1_x", fact_id="f1_x",
                     value=Value(type="scalar", data=1),    # 类型不匹配
                     epistemic_type="normative",
                     authority="rfc", scope=None, evidence=()),),
        metadata=FactMetadata(created_at="2026-10-08", profile_version="v1"))
    with pytest.raises(ValueTypeMismatchError):
        validate_fact(f, reg)