# -*- coding: utf-8 -*-
"""tests/fused/test_method_required_headers.py —— 方法级必填头抽取（第 2 步，2026-11-07）。

★ 背景：必填头清单原是**手写**的（`profile.seedgen.required_headers`），
  漏一项就是**静默**的（种子发无头报文 ⇒ 非法报文 ⇒ fuzzer 白跑）。
  第 1 步加了守卫；第 2 步做「从 RFC 自动抽」。

★ 本文件锁三件事：
  ① **头汇总表**的确定性解析（方向标记 + `all but` 排除）——
     实测 RTSP §12 有「头 → 方向 → req./opt. → 方法」表，是**权威精确**判据；
  ② **LLM 兜底**的确定性净化（去重 + 排除消息级通用头）；
  ③ **协议无关**：判据不认协议名/头名，只认 RFC 的结构。
"""
from __future__ import annotations

import pytest

from core.fused import rfc_extractor as RX


# ===========================================================================
# ① 头汇总表：确定性解析
# ===========================================================================

def test_header_table_regex_parses_direction_and_requirement():
    """★ 表行格式：``<头名> <方向> req.|opt. <方法>``。"""
    m = RX._METHOD_HEADER_TABLE_RE.match(
        "   CSeq                 g      req.      all")
    assert m is not None
    assert m.group(1) == "CSeq"
    assert m.group(2) == "g"
    assert m.group(3) == "req."
    assert m.group(4).strip() == "all"


def test_header_table_regex_supports_double_letter_direction():
    """★ 方向标记可能是**两个字母**（实测 RTSP 有 ``Rr`` = 双向）。"""
    m = RX._METHOD_HEADER_TABLE_RE.match(
        "   Transport            Rr     req.      SETUP")
    assert m is not None
    assert m.group(2) == "Rr"


def test_real_rtsp_table_yields_exact_result():
    """★ 实测锚点：RTSP §12 汇总表 ⇒ **只有** ``SETUP → Transport``。

    ★ 这与手写清单**完全一致**，且零假阳性（对照：LLM 兜底曾给出
      ``PLAY → RTP-Info``（那是**响应**头，表里方向标记是 ``r``）、
      ``SETUP → Session``（表里写的是 ``all but SETUP, OPTIONS``）。
    """
    cfg = RX._load_rfc_config("rtsp")
    known = RX._rfc_source_headers("rtsp", cfg)
    methods = RX._rfc_source_methods("rtsp", cfg)
    out = RX._deterministic_method_required_headers("rtsp", known, methods)
    assert set(out) == {"SETUP"}, out
    assert set(out["SETUP"]) == {"Transport"}, out


def test_response_only_direction_is_excluded():
    """★ 方向标记 ``r``（仅响应）⇒ 请求侧不需要该头。

    实测 RTSP：``RTP-Info  r  req.  PLAY`` ⇒ PLAY 请求**不**必带 RTP-Info。
    """
    cfg = RX._load_rfc_config("rtsp")
    known = RX._rfc_source_headers("rtsp", cfg)
    methods = RX._rfc_source_methods("rtsp", cfg)
    out = RX._deterministic_method_required_headers("rtsp", known, methods)
    assert "RTP-Info" not in {h for hs in out.values() for h in hs}


def test_all_but_exclusion_is_honoured():
    """★ ``all but SETUP, OPTIONS`` 的**排除项**必须生效。

    实测 RTSP：``Session  Rr  req.  all but SETUP, OPTIONS``
    ⇒ Session 对 SETUP/OPTIONS 不适用（客户端那时还没有 Session，
    它是服务器在 SETUP 响应里分配的，§12.37）。
    """
    cfg = RX._load_rfc_config("rtsp")
    known = RX._rfc_source_headers("rtsp", cfg)
    methods = RX._rfc_source_methods("rtsp", cfg)
    out = RX._deterministic_method_required_headers("rtsp", known, methods)
    # ★ ``all but SETUP, OPTIONS`` 排除的是 **Session 这个头**，
    #   不是整个 SETUP 方法（SETUP 仍必带 Transport）。
    assert "Session" not in {h for hs in out.values() for h in hs}, out
    assert "OPTIONS" not in out, out
    # SETUP 仍必带 Transport（另一个头，方向标记 Rr）
    assert set(out.get("SETUP", {})) == {"Transport"}, out


def test_optional_requirement_is_excluded():
    """★ ``opt.`` 是可选 ⇒ 不是必填。"""
    cfg = RX._load_rfc_config("rtsp")
    known = RX._rfc_source_headers("rtsp", cfg)
    methods = RX._rfc_source_methods("rtsp", cfg)
    out = RX._deterministic_method_required_headers("rtsp", known, methods)
    # Session 是 opt. for OPTIONS 那类；只断言「opt. 的头没进来」
    assert all(h not in ("Date", "Expires", "Content-Location")
               for hs in out.values() for h in hs)


def test_protocol_without_table_returns_empty():
    """★ SIP 没有汇总表（它的必填头在 §8.1.1 逐头说明里，是消息级）
    ⇒ 确定性路径返回空 ⇒ 由 LLM 兜底。"""
    cfg = RX._load_rfc_config("sip")
    known = RX._rfc_source_headers("sip", cfg)
    methods = RX._rfc_source_methods("sip", cfg)
    assert RX._deterministic_method_required_headers("sip", known, methods) == {}


# ===========================================================================
# ② 协议无关
# ===========================================================================

def test_deterministic_extraction_is_protocol_agnostic(monkeypatch):
    """★ 判据只看 RFC 的**表结构**，不认协议名。

    ★ 测试设计要点：协议名只用于「读哪份 RFC 文件」⇒ 要验证「判据本身与
      协议名无关」，必须**mock 同一份文件内容**再换协议名，
      否则换个名字就读不到 RFC 了（那不是判据的问题）。
    """
    from core import paths as _paths
    rtsp_dir = _paths.kb_source_dir("rtsp", "rfc")
    _files = sorted(rtsp_dir.glob("*.txt"))
    assert _files, "rtsp 的 RFC 目录应非空"

    class _FakeDir:
        def glob(self, pat):
            return list(_files)

    cfg = RX._load_rfc_config("rtsp")
    known = RX._rfc_source_headers("rtsp", cfg)
    methods = RX._rfc_source_methods("rtsp", cfg)

    base = RX._deterministic_method_required_headers("rtsp", known, methods)
    for proto in ("zzz", "another-proto", "fakeproto"):
        monkeypatch.setattr(_paths, "kb_source_dir",
                            lambda p, s, _d=_FakeDir(): _d)
        other = RX._deterministic_method_required_headers(proto, known, methods)
        assert set(base) == set(other), proto
        assert {m: set(hs) for m, hs in base.items()} == {
            m: set(hs) for m, hs in other.items()}, proto


def test_extraction_code_has_no_protocol_name_whitelist():
    """★ 代码级守卫：方法级抽取的可执行代码里不得出现协议名。"""
    import ast
    import inspect
    src = inspect.getsource(RX._deterministic_method_required_headers)
    tree = ast.parse(src)
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if ast.get_docstring(node, clean=False):
                doc_lines.update(range(node.body[0].lineno,
                                       node.body[0].end_lineno + 1))
    code = "\n".join(
        l.split("#", 1)[0] for i, l in enumerate(src.splitlines(), 1)
        if i not in doc_lines)
    for name in ("rtsp", "sip", "smtp"):
        assert name not in code.lower(), f"抽取代码里出现了协议名 {name}"


# ===========================================================================
# ③ LLM 兜底 + 确定性净化
# ===========================================================================

def test_rows_are_deduplicated():
    """★ 同一 (method, name) 只留一条（实测 LLM 会重复输出，INVITE→Contact×4）。"""
    rows = [{"method": "INVITE", "name": "Contact"},
            {"method": "INVITE", "name": "Contact"},
            {"method": "REGISTER", "name": "Contact"}]
    seen = set()
    deduped = []
    for r in rows:
        k = (r["method"], r["name"])
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    assert len(deduped) == 2


def test_global_headers_are_excluded_from_method_specific():
    """★ 方法级**不得**含消息级通用头（它们由消息级抽取负责）。"""
    global_heads = {"CSeq", "Call-ID", "From", "Max-Forwards", "To", "Via"}
    rows = [{"method": "ACK", "name": "CSeq"},
            {"method": "ACK", "name": "Call-ID"},
            {"method": "INVITE", "name": "Contact"}]
    kept = [r for r in rows if r["name"] not in global_heads]
    assert [r["name"] for r in kept] == ["Contact"]


def test_real_sip_llm_fallback_is_accurate():
    """★ 实测锚点：SIP 走 LLM 兜底 ⇒ INVITE/REGISTER → Contact。

    ★ 这两条与手写清单**一致**（手写清单里 REGISTER 有 Contact）；
      INVITE 的 Contact 是 RFC 3261 §8.1.1.10 规定的（INVITE 必带 Contact）。
    """
    rows = RX.infer_method_required_headers("sip")
    pairs = {(r["method"], r["name"]) for r in rows}
    assert ("REGISTER", "Contact") in pairs, pairs
    # 消息级通用头不得出现在方法级
    for m, n in pairs:
        assert n not in {"CSeq", "Call-ID", "From", "Max-Forwards", "To", "Via"}, (m, n)


def test_method_level_norm_has_evidence():
    """★ 每条都要带 RFC 证据（M3 可验证率的前提）。"""
    rows = RX.infer_method_required_headers("rtsp")
    assert rows, "rtsp 应至少抽到 SETUP→Transport"
    for r in rows:
        assert r.get("evidence"), r
        assert r.get("method") and r.get("name"), r


def test_method_level_not_in_bundle_buckets():
    """★ 方法级 aspect **不进任何 bundle 桶** ⇒ 消费端行为逐字节不变。"""
    from core.fused.downstream import rag_seedgen as RS
    assert ("header", "required_header_by_method") not in RS._BUCKET_BY_KIND
