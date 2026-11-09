# -*- coding: utf-8 -*-
"""tests/fused/test_entity_headers.py —— 实体头机制（B2，2026-11-07）。

★ 背景：SMTP 的 ``DATA`` 命令之后是**邮件内容**（RFC 5321 §2.3.9：
  「message content includes the message header section and the possibly
  structured message body」）⇒ 邮件头段必须带 ``Date`` / ``From`` / ``To``
  （RFC 5322 §3.6）。但原实现：
    · 头段是 ``profile.raw_format.command_extra`` 里的**硬编码文本**（只有 Subject）；
    · 头排在正文**后面**（渲染顺序错）；
    · 命令协议 ``header_line=""`` ⇒ 连 ``msg.headers`` 都不会被渲染。
  ⇒ 生成的 DATA 报文是**缺头且顺序错**的非法邮件。

★ 本文件锁四件事：
  ① 实体头机制**协议无关**（判据只看配置段，不认协议名）；
  ② 渲染顺序：头在正文之前；
  ③ 取值来自**知识中枢 headers 桶**（RFC 抽取），不硬编码；
  ④ ABNF 抽取的两处既有缺陷已修（MULTILINE / 地址类头豁免）。
"""
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


# ===========================================================================
# ① 协议无关：判据只看配置段
# ===========================================================================

def test_entity_headers_read_from_profile_config():
    """★ 实体头来自 ``profile.raw_format.entity_headers``（配置层）。"""
    from core.fused.downstream import rag_seedgen as RS
    b = RS.assemble_bundle(RS.load_fact_views("smtp"), "smtp")
    assert b.get("entity_headers") == {"DATA": ["Date", "From", "To"]}


def test_entity_headers_protocol_agnostic():
    """★ 换协议名 ⇒ 读的是**那个协议**的 profile（不共享 smtp 的配置）。"""
    from core.fused.downstream import rag_seedgen as RS
    b = RS.assemble_bundle(RS.load_fact_views("rtsp"), "rtsp")
    assert not b.get("entity_headers"), "rtsp 不该有实体头（它的报文没有实体内容）"


def test_entity_headers_code_has_no_protocol_name():
    """★ 代码级守卫：实体头机制里不得出现协议名。"""
    import ast
    import inspect
    from core.fused.downstream import rag_seedgen as RS
    src = inspect.getsource(RS._entity_headers_from_profile)
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
        assert name not in code.lower(), f"实体头机制里出现了协议名 {name}"


# ===========================================================================
# ② 渲染顺序：头在正文之前
# ===========================================================================

def test_entity_headers_rendered_before_body():
    """★ RFC 5321 §2.3.9：头段属于 message content ⇒ 必须在正文之前。"""
    from core.fused.downstream import rag_seedgen as RS
    from core.fused.downstream.edge_cover import edge_cover
    from core.fused.semantic.llm_ensemble import set_semantic_rules_enabled
    from core.raw_writers import seedcorpus_to_raw
    set_semantic_rules_enabled(True)
    b = RS.assemble_bundle(RS.load_fact_views("smtp"), "smtp",
                            apply_allowed_methods=False)
    corp = edge_cover(b["transitions"], required_headers=b["required_headers"],
                      headers=b["headers"],
                      message_instances=b["message_instances"],
                      protocol="smtp",
                      entity_headers=b.get("entity_headers"))
    for s in corp:
        raw = seedcorpus_to_raw(s, target_host="127.0.0.1", target_port=25)
        txt = raw.decode("utf-8", "replace")
        if "DATA" not in txt:
            continue
        i = txt.find("DATA")
        seg = txt[i:i + 400]
        for h in ("Date:", "From:", "To:"):
            assert h in seg, f"{h} 不在 DATA 段里：{seg[:200]!r}"
        # 头必须在正文（ProtoKG SMTP fuzz test body）之前
        assert seg.find("Date:") < seg.find("ProtoKG SMTP fuzz test body"), seg
        return
    pytest.skip("本次 edge_cover 未产出 DATA 报文")


def test_command_protocol_has_no_command_headers():
    """★ 命令协议的命令本身**没有头**（`header_line=""`）⇒ 头只出现在实体内容里。"""
    prof = json.loads(
        (ROOT / "fused_hub" / "targets" / "smtp" / "profile.json")
        .read_text(encoding="utf-8"))
    rf = prof["raw_format"]
    assert rf["header_line"] == "", "命令协议的 header_line 应为空"
    assert rf.get("entity_header_line"), "实体内容仍需头行模板"


# ===========================================================================
# ③ 取值来自知识中枢（不硬编码）
# ===========================================================================

def test_entity_header_values_come_from_hub():
    """★ 实体头的取值取自 ``headers`` 桶（RFC 抽取），不写死。"""
    from core.fused.downstream import rag_seedgen as RS
    from core.fused.downstream.edge_cover import build_message
    from core.fused.semantic.llm_ensemble import set_semantic_rules_enabled
    set_semantic_rules_enabled(True)
    b = RS.assemble_bundle(RS.load_fact_views("smtp"), "smtp",
                            apply_allowed_methods=False)
    eh = (b.get("entity_headers") or {}).get("DATA") or []
    assert eh, "smtp 应声明 DATA 的实体头"
    m = build_message("DATA", required_headers=b["required_headers"],
                      headers=b["headers"], cseq=1, entity_headers=eh)
    for h in eh:
        assert h in m.headers, f"{h} 未填进报文"
        assert m.headers[h], f"{h} 的取值是空串（headers 桶里没有取值）"
        # 取值必须能在 headers 桶里找到（⇒ 来自 RFC 抽取，不是硬编码）
        pool = (b["headers"].get(h) or {}).get("values") or []
        assert m.headers[h] in [str(v) for v in pool], (h, m.headers[h])


def test_smtp_mail_headers_are_extracted_from_rfc():
    """★ RFC 5322 的邮件头必须被抽到（Date/From/To/Subject…）。"""
    from core.fused.extraction.rfc_extractor import (_rfc_source_headers,
                                          _load_rfc_config)
    cfg = _load_rfc_config("smtp")
    known = _rfc_source_headers("smtp", cfg)
    for h in ("Date", "From", "To", "Subject", "Message-ID"):
        assert h in known, f"{h} 没被抽到（known={sorted(known)[:10]}）"


# ===========================================================================
# ④ 两处既有缺陷已修
# ===========================================================================

def test_abnf_field_regex_has_multiline():
    """★ ``_RE_ABNF_FIELD`` 必须带 ``re.MULTILINE``。

    ★ 没有它时 ``^`` 只匹配**整个字符串开头** ⇒ 在整篇 RFC 文本上
      ``finditer`` **永远命中 0 条**（实测邮件规范的 20 个 ABNF 头全丢）。
      ★ 这个 bug 极隐蔽：逐行 ``match`` 能命中 ⇒ 单行测试通过、全文扫描全灭。
    """
    from core.fused.extraction import rfc_extractor as RX
    assert RX._RE_ABNF_FIELD.flags & __import__("re").MULTILINE, \
        "_RE_ABNF_FIELD 缺 re.MULTILINE ⇒ 全文 finditer 恒 0 条"


def test_abnf_field_extraction_works_on_full_text():
    """★ 全文扫描能抽到 ABNF 头名。"""
    from core.fused.extraction.rfc_extractor import _extract_abnf_fields
    txt = (ROOT / "kb" / "smtp" / "spec" / "rfc5322.txt").read_text(
        encoding="utf-8", errors="ignore")
    names = {f["name"] for f in _extract_abnf_fields(txt)}
    for h in ("Date", "From", "To"):
        assert h in names, f"{h} 没抽到（names={sorted(names)[:8]}）"


def test_address_headers_exempt_from_uri_exclusion():
    """★ 地址类头（ABNF rhs 含 mailbox/address）豁免「整条地址实例」排除规则。

    理由：``From: John Doe <jdoe@machine.example>`` 的**整个值**就是邮箱地址
    （不是「URI 实例」）⇒ 按 URI 规则排除会把邮件头的取值**全灭**。
    """
    from core.fused.extraction.rfc_extractor import _is_address_header
    assert _is_address_header("From", "mailbox-list CRLF") is True
    assert _is_address_header("To", "address-list CRLF") is True
    assert _is_address_header("Date", "date-time CRLF") is False
    assert _is_address_header("Subject", " unstructured CRLF") is False


def test_address_header_values_extracted():
    """★ 地址类头的取值要能抽到（实测 From/To 各有多个取值）。"""
    from core.fused.extraction.rfc_extractor import (_doc_content_lines,
                                          _extract_field_value_samples,
                                          _extract_abnf_fields,
                                          _is_address_header)
    txt = (ROOT / "kb" / "smtp" / "spec" / "rfc5322.txt").read_text(
        encoding="utf-8", errors="ignore")
    # ★ 两个 API 约定（build 里就是这么调的）：
    #   ① 必须用 `_doc_content_lines`（清洗 + TOC 隔离后的正文行）——
    #      直接用原始行会因 TOC 隔离而漏掉示例块；
    #   ② `known` 的键必须是**小写**（抽取器按 `raw_name.lower()` 查）。
    content_lines = _doc_content_lines(txt.splitlines())
    body = "\n".join(t for _, t in content_lines)
    # ★ `known` 的键必须是**小写**（抽取器内部按 `raw_name.lower()` 查）
    fields = {f["name"].lower(): f["name"] for f in _extract_abnf_fields(body)}
    addr = {f["name"].lower() for f in _extract_abnf_fields(body)
            if _is_address_header(f["name"], f.get("abnf") or "")}
    assert "from" in addr and "to" in addr
    samples = _extract_field_value_samples([t for _, t in content_lines],
                                           fields, address_fields=addr)
    assert samples.get("From"), "From 的取值没抽到"
    assert samples.get("To"), "To 的取值没抽到"
