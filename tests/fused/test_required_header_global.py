# -*- coding: utf-8 -*-
"""tests/fused/test_required_header_global.py —— RFC 源的**消息级必填头**（F1）。

★ F1 的三条设计承诺（逐条被本文件锁住）：
  ① **默认关闭** ⇒ 产物逐字节不变；
  ② 产出 aspect=required_header_global ⇒ **不进任何 bundle 桶**（消费端不受影响）；
  ③ 抽取**协议无关**（头名集由 `rfc_config.field_sections` 配置驱动）。
"""
from __future__ import annotations

import inspect
import pathlib
import re

from core.fused import rfc_extractor as RX
from core.fused import norm as NM
from core.fused.downstream import rag_seedgen as RS


# ===========================================================================
# ① 默认关闭 ⇒ 零影响
# ===========================================================================

def test_switch_code_default_off():
    """★ **代码内置默认**是关闭 ⇒ 未声明该键的协议不受影响。

    ★ 协议配置（`rfc_config.json`）**可以显式开启** —— 那时该协议会产出
      这批 RFC 源证据（但仍不进 bundle 桶 ⇒ 产物不变）。
    """
    import core.fused.rfc_extractor as _rx
    # 内置默认：构造一个「无协议专属配置」时的 cfg ⇒ 默认必须为 False
    import inspect
    src = inspect.getsource(_rx._load_rfc_config)
    assert '"enable_required_headers": False' in src, "代码内置默认必须是关闭"
    # 协议配置可显式开启
    cfg = RX._load_rfc_config("rtsp")
    assert "enable_required_headers" in cfg


def test_global_required_headers_land_in_required_headers_bucket():
    """★ P2-1（2026-11-06）：消息级必填头**进** ``required_headers`` 桶（``"*"`` 键）。

    ★ 这条改了契约：修复前该 aspect 刻意**不进任何桶**（当初的理由是
      「消费端行为不变」），代价是**抽出来就被丢掉** —— 实测 rtsp 1 条 /
      sip 6 条（To/From/CSeq/Call-ID/Max-Forwards/Via）全进了黑洞，
      ``required_headers`` 桶 100% 由 profile 骨架提供。

    现在的契约：**只进 ``required_headers``**（用 ``"*"`` 表示「所有方法都要带」），
    **不得**顺手映射到 ``methods`` —— 那会给 methods 桶造成空条目 ⇒ 种子漂移。
    消费端要用 ``required_headers_for()`` 读（全局 + 方法级合并）。
    """
    got = RS._BUCKET_BY_KIND.get(("header", "required_header_global"))
    assert got == "required_headers", (
        f"应映射到 required_headers，实际 {got!r}")
    # 该 aspect 只能有这一个桶归属
    owners = {b for (st, asp), b in RS._BUCKET_BY_KIND.items()
              if asp == "required_header_global"}
    assert owners == {"required_headers"}, f"桶归属不唯一：{owners}"


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


# ===========================================================================
# ⑤ 抽取主路径（★ 补 S0 之后才暴露的缺口：`3ee21ea` 提交里
#    infer_required_headers 用了**未 import 的 hashlib** ⇒ 开关一开即 NameError，
#    而当时的测试只覆盖「开关关闭」路径 ⇒ 未被发现。
#    本节用 StubLLM 覆盖**真实抽取路径**，防止同类问题复发。）
# ===========================================================================

def test_infer_required_headers_runs_with_stub_llm():
    """★ 开关开启 + 假 LLM ⇒ 能跑通全路径（候选→提示→解析→norm→缓存）。"""
    from core.fused import rfc_extractor as RX
    from core import paths
    d = paths.kb_source_dir("rtsp", "rfc")
    if not d.is_dir():
        import pytest
        pytest.skip("无 RFC 底料")
    calls = []

    class _Stub:
        def chat_json(self, **kw):
            calls.append(kw)
            return {"required_headers": [
                {"name": "CSeq", "evidence": "This field MUST be present in all requests."}]}

    import tempfile
    import core.fused.source_retrieval as _sr
    cfg = RX._load_rfc_config("rtsp")
    cfg["enable_required_headers"] = True
    orig_cfg, orig_cache = RX._load_rfc_config, _sr.CACHE_DIR
    # ★ 2026-11-06：rtsp 现在由**确定性判据**直接命中（§12.17，不需 LLM）⇒
    #   本测试的对象是「LLM 兜底分支」，故先临时关掉确定性判据以走到该分支。
    orig_det = RX._deterministic_message_required_headers
    RX._load_rfc_config = lambda _p: dict(cfg)
    RX._deterministic_message_required_headers = lambda *_a, **_k: {}
    with tempfile.TemporaryDirectory() as _td:
        _sr.CACHE_DIR = pathlib.Path(_td)      # ★ 隔离磁盘缓存
        try:
            norms = RX.infer_required_headers("rtsp", llm=_Stub())
        finally:
            RX._load_rfc_config, _sr.CACHE_DIR = orig_cfg, orig_cache
            RX._deterministic_message_required_headers = orig_det
    assert calls, "LLM 未被调用（候选为空 ⇒ 抽取路径没走到）"
    assert norms, "应产出至少一条 norm"
    assert norms[0]["name"] == "CSeq"
    # ★ 每次调用都必须带上「已知头名列表」约束（否则会自造头名）
    assert "CSeq" in calls[0]["user"]


def test_infer_required_headers_filters_unknown_names():
    """★ LLM 自造的头名必须被丢弃（不在已知头集内）。"""
    from core.fused import rfc_extractor as RX
    from core import paths
    d = paths.kb_source_dir("rtsp", "rfc")
    if not d.is_dir():
        import pytest
        pytest.skip("无 RFC 底料")

    class _Stub:
        def chat_json(self, **kw):
            return {"required_headers": [
                {"name": "X-Fake-Header", "evidence": "invented"},
                {"name": "CSeq", "evidence": "real"}]}

    import tempfile
    import core.fused.source_retrieval as _sr
    cfg = RX._load_rfc_config("rtsp")
    cfg["enable_required_headers"] = True
    orig_cfg, orig_cache = RX._load_rfc_config, _sr.CACHE_DIR
    # ★ 2026-11-06：同上 —— 本测试测的是 LLM 分支的头名过滤，先关确定性判据。
    orig_det = RX._deterministic_message_required_headers
    RX._load_rfc_config = lambda _p: dict(cfg)
    RX._deterministic_message_required_headers = lambda *_a, **_k: {}
    with tempfile.TemporaryDirectory() as _td:
        _sr.CACHE_DIR = pathlib.Path(_td)      # ★ 隔离磁盘缓存
        try:
            norms = RX.infer_required_headers("rtsp", llm=_Stub())
        finally:
            RX._load_rfc_config, _sr.CACHE_DIR = orig_cfg, orig_cache
            RX._deterministic_message_required_headers = orig_det
    names = {n["name"] for n in norms}
    assert "X-Fake-Header" not in names, "自造头名未被过滤"
