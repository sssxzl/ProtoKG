# -*- coding: utf-8 -*-
"""tests/fused/test_required_header_global.py —— RFC 源的**消息级必填头**（F1）。

★ F1 的三条设计承诺（逐条被本文件锁住）：
  ① **默认关闭** ⇒ 产物逐字节不变；
  ② 产出 aspect=required_header_global ⇒ **不进任何 bundle 桶**（消费端不受影响）；
  ③ 抽取**协议无关**（头名集由 `rfc_config.field_sections` 配置驱动）。
"""
from __future__ import annotations

import inspect
import re

from core.fused import rfc_extractor as RX
from core.fused import norm as NM
from core.fused.downstream import rag_seedgen as RS


# ===========================================================================
# ① 默认关闭 ⇒ 零影响
# ===========================================================================

def test_switch_defaults_off():
    """★ 默认关闭 ⇒ `infer_required_headers` 直接返回空 ⇒ 产物不受影响。"""
    cfg = RX._load_rfc_config("rtsp")
    assert "enable_required_headers" in cfg
    assert cfg["enable_required_headers"] is False, "默认必须是关闭"
    # 即使显式调用也返回空（开关未开）
    assert RX.infer_required_headers("rtsp") == []


def test_no_bundle_bucket_for_new_aspect():
    """★ 新 aspect **不进任何 bundle 桶** ⇒ 消费端行为不变。"""
    for (_stype, _aspect), _bucket in RS._BUCKET_BY_KIND.items():
        assert _aspect != "required_header_global", (
            f"新 aspect 不该进 bundle 桶（会改产物）：{(_stype, _aspect)}")


# ===========================================================================
# ② norm → fact 转换器
# ===========================================================================

def test_norm_converter_emits_new_aspect():
    """★ norm(kind=required_header_global) → Fact(aspect=required_header_global)。"""
    assert "required_header_global" in NM.RFC_KIND_MAP
    norm = {"name": "CSeq", "content": "name=CSeq",
            "protocol": "rtsp", "source": "file:x#@1"}
    facts = NM.RFC_KIND_MAP["required_header_global"](norm)
    assert len(facts) == 1
    f = facts[0]
    assert f.fact_key.aspect == "required_header_global"
    assert f.fact_key.subject.name == "CSeq"


def test_norm_converter_skips_empty_name():
    norm = {"name": "", "content": "name="}
    assert NM.RFC_KIND_MAP["required_header_global"](norm) == []


# ===========================================================================
# ③ 协议无关性守卫
# ===========================================================================

def test_extraction_source_has_no_protocol_specific_constants():
    """★ G2：抽取实现不得含协议名或协议特定头名。"""
    code = "\n".join(inspect.getsource(f) for f in (
        RX.infer_required_headers, RX._rfc_source_headers,
        RX._PROMPT_REQUIRED_HEADER if callable(RX._PROMPT_REQUIRED_HEADER)
        else (lambda: "")))
    code = re.sub(r'"""[\s\S]*?"""', "", code)
    for name in ("rtsp", "sip", "smtp", "CSeq", "Via", "Call-ID"):
        assert not re.search(rf"\b{re.escape(name)}\b", code), (
            f"必填头抽取出现了协议/头特例「{name}」⇒ 违反 G2")


# ===========================================================================
# ④ 真实协议：头名集由配置驱动
# ===========================================================================

def test_rfc_source_headers_are_config_driven():
    """★ 头名集必须来自 `rfc_config.field_sections`（换协议只改配置）。"""
    from core import paths
    d = paths.kb_source_dir("rtsp", "rfc")
    if not d.is_dir():
        import pytest
        pytest.skip("无 RFC 底料")
    cfg = RX._load_rfc_config("rtsp")
    assert cfg.get("field_sections"), "rtsp 配置未声明 field_sections"
    hs = RX._rfc_source_headers("rtsp", cfg)
    assert len(hs) > 10, f"头名集过小：{len(hs)}"
    assert "CSeq" in hs, "缺 CSeq"
    # 配置为空 ⇒ 头名集为空（不猜、不硬编码）
    assert RX._rfc_source_headers("rtsp", {"field_sections": []}) == set()
