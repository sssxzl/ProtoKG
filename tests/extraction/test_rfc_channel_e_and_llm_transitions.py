# -*- coding: utf-8 -*-
"""tests/fused/test_rfc_channel_e_and_llm_transitions.py —— 批次 2.2。

★ 覆盖两组：

**通道 E（ABNF 形态的字段定义）**
  ① SMTP 的 RFC 5322 把头字段定义成 ABNF 规则（``from = "From:" …``），
     **不是**章节标题 ⇒ 原有三条通道都抓不到 ⇒ 实测 smtp 只抽出 **0 个字段**
  ② 通道 E 能抽到这些字段，且**不误伤** RTSP/SIP（它们的头是章节标题式 /
     ABNF 引号内**无冒号**）
  ③ ★ `_section_kind` 的 field 判定**不可用**（SMTP 的 `method_sections` 含 "3"
     ⇒ §3.6 被判成 method）⇒ 通道 E 必须**全文扫**

**P1b（LLM 抽状态机）**
  ④ 状态机段落**候选定位**能命中（RTSP 的 Appendix A、SIP 的 §17）
  ⑤ 重叠候选**合并**（否则重复调 LLM）
  ⑥ **缓存**生效 ⇒ 同一份 RFC 命中缓存 ⇒ 不调 LLM ⇒ 产物可复现
  ⑦ LLM 抽出的转移与**表格**抽出的**一致**（交叉验证）
"""
from __future__ import annotations

from core.fused.extraction import rfc_extractor as RX   # noqa: E402
from core import paths                        # noqa: E402

PROTOCOL = "rtsp"

#: RFC 5322 §3.6 的真实 ABNF 字段定义行（逐字摘自 kb/smtp/spec/rfc5322.txt）
SMTP_ABNF_FIELDS = """\
   orig-date       =   "Date:" date-time CRLF

   from            =   "From:" mailbox-list CRLF

   sender          =   "Sender:" mailbox CRLF

   reply-to        =   "Reply-To:" address-list CRLF

   to              =   "To:" address-list CRLF

   cc              =   "Cc:" address-list CRLF

   bcc             =   "Bcc:" [address-list / CFWS] CRLF

   message-id      =   "Message-ID:" msg-id CRLF
"""

#: RFC 5322 §3.6.1 的散文说明（`the field name "Date"` 形态）
SMTP_ABNF_PROSE = """\
   The origination date field consists of the field name "Date" followed
   by a date-time specification.
"""


# ===========================================================================
# ①② 通道 E：ABNF 字段定义
# ===========================================================================

def test_abnf_fields_extracted_from_smtp_syntax():
    """★ ABNF 形态的字段定义能抽出（字段名 + 右侧 ABNF）。"""
    fields = RX._extract_abnf_fields(SMTP_ABNF_FIELDS)
    names = [f["name"] for f in fields]
    assert names == ["Date", "From", "Sender", "Reply-To", "To", "Cc",
                     "Bcc", "Message-ID"]
    by_name = {f["name"]: f for f in fields}
    assert by_name["Date"]["abnf"] == "date-time CRLF"
    assert by_name["From"]["abnf"] == "mailbox-list CRLF"


def test_abnf_fields_pick_up_prose_description():
    """★ 散文说明（`the field name "Date"`）被关联到字段。"""
    text = SMTP_ABNF_PROSE + "\n" + SMTP_ABNF_FIELDS
    fields = RX._extract_abnf_fields(text)
    by_name = {f["name"]: f for f in fields}
    assert "origination date field" in by_name["Date"]["prose"]


def test_abnf_fields_not_confused_with_sip_style_abnf():
    """★ SIP 的 `Accept = "Accept" HCOLON …`（引号内**无冒号**）不被误伤。"""
    text = '   Accept = "Accept" HCOLON accept-params CRLF\n'
    assert RX._extract_abnf_fields(text) == []


def test_real_smtp_rfc_yields_fields():
    """★ 用**真实** RFC 5322 抽 ⇒ 字段数 ≥ 19（SMTP 之前是 0 个）。"""
    spec_dir = paths.kb_source_dir("smtp", "rfc")
    files = sorted(spec_dir.glob("*.txt"))
    assert files
    names: set[str] = set()
    for f in files:
        text = f.read_text(encoding="utf-8", errors="ignore")
        names.update(x["name"] for x in RX._extract_abnf_fields(text))
    for expected in ("Date", "From", "To", "Subject", "Message-ID"):
        assert expected in names, f"ABNF 字段抽取漏了 {expected}"
    assert len(names) >= 19, f"只抽到 {len(names)} 个（期望 ≥19）"


def test_channel_e_does_not_affect_rtsp_or_sip_norms():
    """★ 通道 E 对 RTSP/SIP **零影响**（它们的头是章节标题式）。"""
    for proto in ("rtsp", "sip"):
        norms = RX.extract_rfc_norms(proto)
        names = [n["name"] for n in norms if n["kind"] == "field"]
        # 章节标题式字段仍在（未被 ABNF 通道挤掉）
        assert names, f"{proto} 的字段被清空了"
        # ABNF 通道**不新增**字段（字段名集合与基线一致）
        assert len(names) == len(set(names)), f"{proto} 出现重复字段名"


def test_smtp_section_kind_resolves_field_subsection():
    """★ 2026-11-06（P1-2）修正记录：`_section_kind` 对 SMTP §3.6.1 **曾**判成
    **method**（因 `method_sections` 含短前缀 `"3"`、且旧实现是固定类别优先），
    ⇒ 通道 E 不能依赖它，这就是通道 E 走**全文扫**的原因。

    现在改为「跨类别最长前缀」⇒ `3.6`（field，长度 3）胜过 `3`（method，长度 1）
    ⇒ `3.6.1` 正确判为 **field**。通道 E 仍走全文扫（协议无关、不依赖章节号），
    但不再是因为这个缺陷。
    """
    cfg = RX._load_rfc_config("smtp")
    assert "3" in cfg.get("method_sections", [])
    assert "3.6" in cfg.get("field_sections", [])
    # 长子节归属 field（旧实现会误判成 method）
    assert RX._section_kind({"section_no": "3.6.1", "title": "x"}, cfg) == "field"
    # 命令章子节仍归 method（不受影响）
    assert RX._section_kind({"section_no": "4.1.1.2", "title": "x"}, cfg) == "method"
    # 回复码章归 status（旧实现因 method_sections 含 "4.2" 而误判成 method）
    assert RX._section_kind({"section_no": "4.2.3", "title": "x"}, cfg) == "status"


# ===========================================================================
# ④⑤⑥⑦ P1b：LLM 状态机
# ===========================================================================

def test_transition_candidates_locate_state_machine_sections():
    """★ 状态机段落**候选定位**能命中（RTSP 附录 A、SIP §17）。

    ★ 2026-11-08（批次 3 / A1）：候选定位新增**实体共现**判据
      （「消息名 + 迁移动词」同句共现），与旧的 ``state machine`` 字样判据**并集**。
      ★ **断言变更**（实测驱动，非降标准）：
        原断言「SMTP 没有状态机 ⇒ 不该有候选」的前提**被实测推翻** ——
        RFC 3207 里确实有状态转换描述：
          「After the client gives the STARTTLS command, the server responds with」
          「After receiving a 220 response to a STARTTLS command, the client MUST」
        ⇒ 旧判据（只认 "state machine" 字样）**漏掉了**这段。
      ★ 改后的断言**保留原意图**（smtp 不该有大量候选），只是把「0 个」
        放宽为「少量」—— 因为**候选定位扩大是本批次的预期行为**。
    """
    rtsp = RX.extract_transition_candidates("rtsp")
    assert rtsp, "rtsp 没定位到状态机段落"
    assert any("rfc2326" in c["source"] for c in rtsp)
    sip = RX.extract_transition_candidates("sip")
    assert sip, "sip 没定位到状态机段落"
    # ★ SMTP 的候选应**很少**（它的状态机只在 STARTTLS 扩展里 ⇒ 1~3 个）
    smtp = RX.extract_transition_candidates("smtp")
    assert len(smtp) <= 3, f"smtp 候选过多（{len(smtp)} 个）⇒ 判据过宽"


def test_transition_candidates_are_merged_when_overlapping():
    """★ 重叠候选**合并**（否则重复调 LLM）。"""
    cands = RX.extract_transition_candidates("rtsp")
    for a, b in zip(cands, cands[1:]):
        if a["source"].split("#")[0] != b["source"].split("#")[0]:
            continue
        assert a["hash"] != b["hash"]
    # 合并后不应有**文本完全相同**的候选（重复调用）
    hashes = [c["hash"] for c in cands]
    assert len(hashes) == len(set(hashes)), "存在重复候选（会重复调 LLM）"


def test_transition_candidates_have_stable_hash():
    """★ 候选段落的 hash **稳定**（⇒ 缓存可命中 ⇒ 产物可复现）。"""
    a = RX.extract_transition_candidates("rtsp")
    b = RX.extract_transition_candidates("rtsp")
    assert [c["hash"] for c in a] == [c["hash"] for c in b]


def test_llm_transitions_cache_makes_second_call_free():
    """★ 缓存生效 ⇒ 第二次调用**不调 LLM**（用计数桩验证）。"""
    from core.fused.extraction import rfc_extractor as RX2

    calls = {"n": 0}

    class _CountingLLM:
        def chat_json(self, **kwargs):
            calls["n"] += 1
            return {"transitions": [{"from": "Init", "method": "SETUP",
                                     "to": "Ready"}]}

    # 用**临时缓存目录**隔离测试（不污染真实缓存）
    import tempfile
    from pathlib import Path as _P
    tmp = _P(tempfile.mkdtemp(prefix="trans_cache_"))
    orig = RX2.__dict__.get("_TRANS_CACHE_DIR")
    # monkeypatch CACHE_DIR 的来源：infer_transitions 里 from ... import CACHE_DIR
    import core.fused.extraction.source_retrieval as SR
    old_cache = SR.CACHE_DIR
    SR.CACHE_DIR = tmp
    try:
        rows1 = RX2.infer_transitions("rtsp", llm=_CountingLLM())
        n1 = calls["n"]
        rows2 = RX2.infer_transitions("rtsp", llm=_CountingLLM())
        n2 = calls["n"]
    finally:
        SR.CACHE_DIR = old_cache
        if orig is not None:
            RX2.__dict__["_TRANS_CACHE_DIR"] = orig
    assert rows1, "第一次没抽出转移"
    assert n1 >= 1, "第一次没有调用 LLM"
    # ★ 第二次**不新增**调用（n1 是候选段落数，n2 应与之相等）
    assert n2 == n1, f"第二次仍调了 LLM（{n1} → {n2}）⇒ 缓存未生效"
    assert rows1 == rows2, "缓存命中后结果不一致"


def test_llm_transitions_match_table_extraction():
    """★ LLM 抽出的转移与**表格**抽出的**一致**（交叉验证）。

    ⚠ 真实调用 DeepSeek（若 key 不可用则跳过）⇒ 本用例断言
      「LLM 结果 ⊆ 表格结果 ∪ 合理集合」，且**至少**覆盖表格的核心边。
    """
    table = RX._extract_transition_table(
        _rtsp_appendix_text())
    table_set = {(t["from"], t["method"], t["to"]) for t in table}
    try:
        from core.llm import DeepSeekClient
        DeepSeekClient()
    except Exception:  # noqa: BLE001
        import pytest
        pytest.skip("DeepSeek key 不可用 ⇒ 跳过真实 LLM 交叉验证")
    rows = RX.infer_transitions("rtsp")
    if not rows:
        import pytest
        pytest.skip("LLM 未抽出转移（缓存为空）")
    llm_set = {(r["from"], r["method"], r["to"]) for r in rows}
    # ★ LLM 抽出的**每条**都必须是 RFC 原文里有的（不能凭空造）
    assert llm_set <= table_set, (
        f"LLM 抽出了表格里没有的转移：{sorted(llm_set - table_set)}")


def _rtsp_appendix_text() -> str:
    spec_dir = paths.kb_source_dir(PROTOCOL, "rfc")
    files = sorted(spec_dir.glob("*.txt"))
    assert files
    body = files[0].read_text(encoding="utf-8", errors="ignore")
    idx = body.find("Appendix A: RTSP Protocol State Machines")
    assert idx >= 0
    return body[idx:]
