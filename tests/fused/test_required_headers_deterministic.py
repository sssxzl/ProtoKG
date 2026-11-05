# -*- coding: utf-8 -*-
"""tests/fused/test_required_headers_deterministic.py —— 消息级必填头的**确定性判据**。

★ 为什么要这个文件（2026-11-06 实测）：
  给 LLM 缓存键并入 ``prompt_version`` 后重抽，RTSP 的必填头从 1 条（CSeq）
  变成 4 条，多出 Require / Proxy-Require / Unsupported —— **全部来自 §12
  头部汇总表**（``CSeq g req. all`` / ``Unsupported r req. all``），LLM 把
  ``req.``（= request header）误读成「required」⇒ 3 个假阳性。

★ 修法：确定性判据优先（零 LLM），覆盖两种规范写法：
   A) 枚举式（SIP §8.1.1）：``MUST ... contain the following header fields: X, Y``
   B) 逐头式（RTSP §12.17）：``<Head> ... MUST be present in all requests``

★ 本文件锁住：
  1. 真实 RFC 上的结果（rtsp=CSeq / sip=6 头 / smtp=空）；
  2. **反假阳性**：汇总表行不得被当必填；
  3. **窗口不跨章节**：不得「借用」邻节的 MUST 句；
  4. 协议无关性（G2）：源码不得含协议名 / 章节号 / 具体头名；
  5. 零 LLM：确定性命中时不构造 LLM 客户端（离线可跑）。
"""
from __future__ import annotations

import inspect
import re

import pytest

from core.fused import rfc_extractor as RX
from core import paths


def _det(protocol: str) -> dict[str, str]:
    cfg = RX._load_rfc_config(protocol)
    known = RX._rfc_source_headers(protocol, cfg)
    return RX._deterministic_message_required_headers(protocol, known)


def _has_rfc(protocol: str) -> bool:
    return paths.kb_source_dir(protocol, "rfc").is_dir()


# ===========================================================================
# ① 真实 RFC：结果必须与原文一致
# ===========================================================================

def test_rtsp_only_cseq():
    """★ RFC 2326：消息级必填头**只有 CSeq**（§12.17 原句）。"""
    if not _has_rfc("rtsp"):
        pytest.skip("无 RFC 底料")
    det = _det("rtsp")
    assert set(det) == {"CSeq"}, f"rtsp 确定性必填头应只有 CSeq，实得 {sorted(det)}"
    assert re.search(r"MUST\s+be\s+present\s+in\s+all\s+requests",
                     det["CSeq"], re.IGNORECASE), "证据句应含原文必填表述"


def test_sip_six_headers():
    """★ RFC 3261 §8.1.1 枚举式表述 ⇒ 恰好 6 个头。"""
    if not _has_rfc("sip"):
        pytest.skip("无 RFC 底料")
    det = _det("sip")
    assert set(det) == {"To", "From", "CSeq", "Call-ID", "Max-Forwards", "Via"}


def test_smtp_empty():
    """★ SMTP 是命令/响应式协议，RFC 5321 无「消息级必填头」表述 ⇒ 空。"""
    if not _has_rfc("smtp"):
        pytest.skip("无 RFC 底料")
    assert _det("smtp") == {}


# ===========================================================================
# ② 反假阳性：汇总表的列标记不得被当「必填」
# ===========================================================================

def test_summary_table_columns_not_treated_as_required():
    """★ RTSP §12 汇总表的 ``Unsupported r req. all`` / ``Require R req. all``
    里的 ``req.`` 是 **request header**（请求头），不是「必填」。
    只要判据是基于「MUST be present in all requests」这类原文表述，
    就**不可能**把这张表读成必填。
    """
    if not _has_rfc("rtsp"):
        pytest.skip("无 RFC 底料")
    det = _det("rtsp")
    for fake in ("Require", "Proxy-Require", "Unsupported"):
        assert fake not in det, f"汇总表列标记被误读为必填：{fake}"


# ===========================================================================
# ③ 窗口不跨章节：不得「借用」邻节的 MUST 句
# ===========================================================================

def test_window_does_not_borrow_next_section():
    """★ v1 缺陷：逐头式窗口 `lines[i+1:i+26]` 会跨到下一节 ⇒
    Content-Length / Content-Language / Content-Location / Content-Type
    被「借」了 CSeq 的 MUST 句 ⇒ 4 个假阳性。
    修正：窗口在**下一个章节标题**处截断。
    """
    if not _has_rfc("rtsp"):
        pytest.skip("无 RFC 底料")
    det = _det("rtsp")
    for fake in ("Content-Length", "Content-Language",
                 "Content-Location", "Content-Type"):
        assert fake not in det, f"窗口跨章节导致假阳性：{fake}"


# ===========================================================================
# ④ 协议无关性（G2）守卫
# ===========================================================================

def test_no_protocol_or_section_hardcode():
    """★ 机械化守卫：判据实现里不得出现协议名 / 章节号 / 具体头名。"""
    src = inspect.getsource(RX._deterministic_message_required_headers)
    # 去掉 docstring 与行注释（说明性文字里允许出现示例，不算硬编码）
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"#[^\n]*", "", src)
    for bad in ("rtsp", "sip", "smtp", "CSeq", "Via", "Call-ID",
                "12.17", "8.1.1"):
        assert not re.search(rf"\b{re.escape(bad)}\b", src), (
            f"确定性判据出现协议/章节/头特例「{bad}」⇒ 违反 G2")


def test_empty_known_returns_empty():
    """★ 头名集为空 ⇒ 直接返回空（不猜、不硬编码）。"""
    assert RX._deterministic_message_required_headers("rtsp", set()) == {}


# ===========================================================================
# ⑤ 零 LLM：确定性判据命中时**不构造** LLM 客户端
# ===========================================================================

def test_no_llm_client_when_deterministic_hits(monkeypatch):
    """★ rtsp 由确定性判据直接命中 ⇒ 不得构造 LLM 客户端（离线可跑）。"""
    if not _has_rfc("rtsp"):
        pytest.skip("无 RFC 底料")
    import core.llm as _llm_mod

    class _Boom:
        def __init__(self, *a, **k):
            raise AssertionError(
                "确定性判据命中时不应构造 LLM 客户端（否则离线不可跑）")

    monkeypatch.setattr(_llm_mod, "DeepSeekClient", _Boom)
    norms = RX.infer_required_headers("rtsp")          # llm=None
    assert {n["name"] for n in norms} == {"CSeq"}


# ===========================================================================
# ⑥ 判据覆盖两种规范写法（各自独立成立）
# ===========================================================================

def test_both_normative_forms_are_compiled():
    """★ 两个正则都必须存在且可编译（枚举式 / 逐头式）。"""
    assert RX._REQ_ENUM_RE.search(
        "MUST, at a minimum, contain the following header fields: To, From")
    assert RX._REQ_PER_HEADER_RE.search(
        "This field MUST be present in all requests and responses.")
    # 反例：汇总表列标记不应命中任何一条
    assert not RX._REQ_ENUM_RE.search("CSeq   g   req.   all")
    assert not RX._REQ_PER_HEADER_RE.search("Unsupported  r  req.  all")
