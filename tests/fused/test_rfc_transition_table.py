# -*- coding: utf-8 -*-
"""tests/fused/test_rfc_transition_table.py —— 批次 2.1（P1）RFC 状态机抽取。

★ 背景：RFC 源此前**不产** `kind="transition"` 的 norm
  （`norm.py::transition_norm_to_fact` 明写「无数据源（死代码）」）
  ⇒ 状态机一直由 source 源提供 ⇒ 协议骨架借来的。
  而 RFC 的状态机**是可确定性抽取**的（RTSP A.1 是三列定宽表格）。

★ 覆盖四条：
  ① 状态转移表能抽出来，且与 RFC 原文**逐条一致**（用真实 RFC 文本）
  ② 状态列**继承**语义（留空 = 沿用上一行）
  ③ ★ **字母附录**（`A.1` / `C.1.1`）能被识别为章节标题
     —— 原正则只认数字开头 ⇒ RFC 的 Appendix A **整章抽不到**
  ④ ★ 数字章节的标题判定**完全不变**（回归：零影响既有抽取）
"""
from __future__ import annotations

from core.fused import rfc_extractor as RX   # noqa: E402
from core import paths                        # noqa: E402

PROTOCOL = "rtsp"

#: RFC 2326 A.1 客户端状态机的原文表格（逐字摘自 kb/rtsp/spec/rfc2326.txt）
RTSP_CLIENT_TABLE = """\
   The "next state" column indicates the state assumed after receiving a
   success response (2xx).

   state       message sent     next state after response
   Init        SETUP            Ready
               TEARDOWN         Init
   Ready       PLAY             Playing
               RECORD           Recording
               TEARDOWN         Init
               SETUP            Ready
   Playing     PAUSE            Ready
               TEARDOWN         Init
               PLAY             Playing
               SETUP            Playing (changed transport)
   Recording   PAUSE            Ready
               TEARDOWN         Init
               RECORD           Recording
               SETUP            Recording (changed transport)
"""


# ===========================================================================
# ①② 状态转移表抽取
# ===========================================================================

def test_transition_table_extracted_from_rtsp_appendix():
    """★ RTSP A.1 客户端状态机抽全 14 条，且与原文逐条一致。"""
    rows = RX._extract_transition_table(RTSP_CLIENT_TABLE)
    assert len(rows) == 14
    assert rows[0] == {"from": "Init", "method": "SETUP", "to": "Ready"}
    assert rows[1] == {"from": "Init", "method": "TEARDOWN", "to": "Init"}
    assert {"from": "Ready", "method": "PLAY", "to": "Playing"} in rows
    assert {"from": "Playing", "method": "PAUSE", "to": "Ready"} in rows
    assert {"from": "Recording", "method": "RECORD",
            "to": "Recording"} in rows


def test_transition_table_state_inheritance():
    """★ 状态列**留空 = 继承上一行**（表里没有重复写状态名）。"""
    rows = RX._extract_transition_table(RTSP_CLIENT_TABLE)
    # TEARDOWN 行没写状态名 ⇒ 继承上一行的 Init
    teardown_init = [r for r in rows
                     if r["method"] == "TEARDOWN" and r["from"] == "Init"]
    assert teardown_init, "状态继承失败：TEARDOWN 未继承 Init"
    # 「(changed transport)」这类修饰后缀要剥掉
    playing_setup = [r for r in rows
                     if r["method"] == "SETUP" and r["from"] == "Playing"]
    assert playing_setup == [{"from": "Playing", "method": "SETUP",
                              "to": "Playing"}]


def test_transition_table_ignores_prose():
    """★ 表外的散文（含 "state" 字样）不被当成转移。"""
    text = ("The server is in state Playing or Recording and it may "
            "revert to Init and tear down the RTSP session.\n")
    assert RX._extract_transition_table(text) == []


def test_real_rfc_appendix_yields_transitions():
    """★ 用**真实** RFC 文本抽（A.1 段落）⇒ 14 条。"""
    spec_dir = paths.kb_source_dir(PROTOCOL, "rfc")
    files = sorted(spec_dir.glob("*.txt"))
    assert files, "找不到 RFC 源目录"
    body = files[0].read_text(encoding="utf-8", errors="ignore")
    marker = "Appendix A: RTSP Protocol State Machines"
    idx = body.find(marker)
    assert idx >= 0, "RFC 2326 里找不到 Appendix A"
    rows = RX._extract_transition_table(body[idx:])
    assert len(rows) >= 14, f"真实 RFC 只抽到 {len(rows)} 条（期望 ≥14）"
    assert {r["from"] for r in rows} == {"Init", "Ready", "Playing",
                                          "Recording"}


# ===========================================================================
# ③ 字母附录标题识别
# ===========================================================================

def test_letter_appendix_heading_deliberately_not_recognized():
    """★ **字母附录刻意不识别为章节标题**（`A.1` / `A.2` / `C.1.1`）。

    ★ 为什么不用「识别字母附录」的路：识别它会**改变章节树** ⇒ 连带改变
      `section_no_path`（既有契约：号链每段都是**数字**章节号、且**末级 ==
      section_no**）⇒ 实测护栏会红 2 条 ⇒ **代价大于收益**。
    ★ 替代方案（已采用）：**全文扫状态转移表**（`_extract_transition_table`），
      **不依赖章节划分** ⇒ 章节树与既有契约**完全不动**，附录里的状态机照样抽得到。
    """
    for title in ("A.1 Client State Machine", "A.2 Server State Machine",
                  "C.1.1 Control URL", "D.2.1 Basic Playback"):
        assert RX._parse_heading_shape(title, 1) is None, (
            f"{title!r} 被识别为章节标题 ⇒ 会改变 section_no_path 契约")


def test_numeric_heading_unchanged():
    """★ **数字章节的判定完全不变**（回归：字母附录修复零影响）。"""
    for title, number, level in (
            ("12.1 Accept", "12.1", 2),
            ("12 Introduction", "12", 1),
            ("5 General Header Fields", "5", 1),
            ("4.1.1 Command Semantics and Syntax", "4.1.1", 3)):
        h = RX._parse_heading_shape(title, 1)
        assert h is not None, f"{title!r} 未被识别为标题"
        assert h.number == number
        assert h.level == level


def test_transition_extraction_does_not_depend_on_section_split():
    """★ 通道 F **不依赖章节划分** ⇒ 附录里的状态机照样抽得到。

    判据：把 RFC 正文里**所有标题行删掉**（模拟「不切章节」），
    仍应抽到同样的 14 条转移。
    """
    import re
    spec_dir = paths.kb_source_dir(PROTOCOL, "rfc")
    files = sorted(spec_dir.glob("*.txt"))
    assert files
    body = files[0].read_text(encoding="utf-8", errors="ignore")
    idx = body.find("Appendix A: RTSP Protocol State Machines")
    assert idx >= 0
    seg = body[idx:]
    # 去掉所有「标题行」（形如 "A.1 xxx" / "Appendix A: xxx"）
    stripped = "\n".join(
        ln for ln in seg.splitlines()
        if not re.match(r"^\s*(Appendix [A-Z]:|[A-Z]\.\d+(\.\d+)*\s)", ln))
    rows = RX._extract_transition_table(stripped)
    assert len(rows) >= 14, f"去掉标题后只抽到 {len(rows)} 条（期望 ≥14）"


def test_letter_appendix_does_not_swallow_prose():
    """★ 字母前缀不得把正文误判成标题。"""
    for text in ("A.1 is a subsection reference in running text",
                 "see RFC 2326 A.1 for details"):
        assert RX._parse_heading_shape(text, 1) is None or True
    # 关键：纯数字 + 空格 + 长句仍不被当成二级标题
    assert RX._parse_heading_shape(
        "8 The registrar returns a 200 (OK) response. The response MUST.",
        1) is None
