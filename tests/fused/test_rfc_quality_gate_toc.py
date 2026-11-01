# -*- coding: utf-8 -*-
"""tests/fused/test_rfc_quality_gate_toc.py —— A 阶段质量闸的 **TOC 隔离检出力**测试。

背景（审查发现，2026-11-01）
---------------------------
改进v2 问题② 警告：「否则可能实现了『重复 ID 为零』，但没有彻底消除知识污染」。

实测证实了这个警告：
  · monkeypatch 令 ``_is_toc_line`` 恒返回 False（模拟「修正① 未实施」，
    TOC 行进入章节树）后，**三协议的 norms 数、dup_norm_id、dup_fact_ids
    全部不变** ⇒ 这两个指标**失去检出力**（污染被去重机制掩盖）。
  · 真实危害在 SIP：其 **50 个 outcome** 的 reason 全部被污染成
    「Trying ........  183」这类**目录文字**（点线 + 页码），
    而 dup 指标全绿 —— 知识库被目录条目彻底顶替。

⇒ 本文件锁住新增的 ``toc_only_norms`` 检查：它**不依赖去重**，且用
**独立于被测函数**的形态判据划分 TOC/正文，故抽取侧的 TOC 判定一旦失效，
本检查即刻检出并阻断构建。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.fused import rfc_extractor as rx  # noqa: E402


PROTOCOLS = ("rtsp", "sip", "smtp")


# ===========================================================================
# 正常态：三个协议都不应有 TOC 泄漏
# ===========================================================================

@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_no_toc_leak_in_normal_run(protocol):
    """正常抽取下，任何 norm 的标识文本都不得「只在 TOC 行出现」。"""
    leaked = rx._count_toc_only_norms(protocol, rx.extract_rfc_norms(protocol))
    assert leaked == [], f"{protocol} 检出 TOC 泄漏: {leaked[:5]}"


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_quality_report_passes_normally(protocol):
    """三个目标协议的质量闸正常应通过（含新增检查）。"""
    rep = rx.rfc_quality_report(protocol)
    assert rep.passed, f"{protocol} 质量闸未通过: {rep.blocking_issues}"
    assert rep.toc_only_norms == []


# ===========================================================================
# ★ 检出力：模拟「TOC 隔离失效」必须被检出并阻断
# ===========================================================================

def test_toc_isolation_failure_is_detected_on_sip(monkeypatch):
    """★ 核心检出力测试：TOC 判定失效 → SIP 必须被检出并阻断构建。

    SIP 的 §21 状态码标题带 reason 文本（``100 Trying``），TOC 版与正文版
    **内容不同** ⇒ TOC 行一旦进入章节树，其「目录文字」会顶替正文 reason
    （实测 50 个 outcome 全部被污染）。这是唯一有污染路径的协议。
    """
    norms_good = rx.extract_rfc_norms("sip")
    assert norms_good, "SIP 应能抽出 norm"

    # 模拟「修正① 未实施」：TOC 判定恒 False → TOC 行进入章节树
    monkeypatch.setattr(rx, "_is_toc_line", lambda line: False)
    norms_bad = rx.extract_rfc_norms("sip")

    # ① 污染确实发生了（否则本测试就失去意义）
    good = {(n["kind"], n["name"]): n.get("content", "") for n in norms_good}
    bad = {(n["kind"], n["name"]): n.get("content", "") for n in norms_bad}
    polluted = [k for k in set(good) & set(bad) if good[k] != bad[k]]
    assert polluted, "对照前提失效：TOC 判定坏掉后产物本应变化 —— " \
                    "若此断言失败说明污染路径已变，需重新设计本测试"

    # ② 目录文字确实进了 content（点线 + 页码）
    dotted = [c for c in bad.values() if "..." in c]
    assert dotted, "污染内容应含 TOC 的点线特征"

    # ③ ★ 新检查必须检出（这正是它存在的理由）
    leaked = rx._count_toc_only_norms("sip", norms_bad)
    assert leaked, "★ toc_only_norms 未检出 TOC 隔离失效 —— 检查失去检出力"

    # ④ 且必须阻断构建
    rep = rx.rfc_quality_report("sip", facts=None, norms=norms_bad)
    assert not rep.passed, "TOC 隔离失效时质量闸必须不通过"
    assert any("TOC 隔离失效" in b for b in rep.blocking_issues), \
        f"阻断项应指明 TOC 隔离失效，实际: {rep.blocking_issues}"


def test_new_check_does_not_rely_on_is_toc_line(monkeypatch):
    """★ 新检查**不得**复用 ``_is_toc_line``（否则与被检查对象自证）。

    这条锁住审查中发现的实现缺陷：初版实现用 ``_is_toc_line`` 划分 TOC/正文，
    而该函数被破坏时划分同时失效 → 检查恒为 0（实测检出 0 条）。
    """
    # 破坏被测函数后，独立判定仍应能识别 TOC 行
    monkeypatch.setattr(rx, "_is_toc_line", lambda line: False)
    lines = [
        "   21.1.1     100 Trying ......................... 183",
        "REGISTER sip:127.0.0.1 SIP/2.0",
    ]
    toc = rx._independent_toc_lines(lines)
    assert len(toc) == 1, f"独立判定应识别出 1 行 TOC，实际 {toc}"
    assert "Trying" in list(toc)[0]


def test_independent_toc_lines_detects_dotted_entries():
    """独立判定：点线引导是 TOC 的可靠形态特征。"""
    toc_line = "   12.1       Accept ................................. 45"
    body_line = "Accept: the acceptable media types."
    toc = rx._independent_toc_lines([toc_line, body_line])
    assert toc_line in toc
    assert body_line not in toc


def test_report_serializes_toc_only_norms():
    """报告的 dict 序列化须带上新指标（供 CI/审计消费）。"""
    d = rx.rfc_quality_report("rtsp").to_dict()
    assert "toc_only_norms" in d
    assert isinstance(d["toc_only_norms"], list)


# ===========================================================================
# P0-2：溯源行判据（对 method/field 也有效）
# ===========================================================================

def test_source_line_criterion_detects_all_kinds():
    """★ P0-2：溯源行判据对 method / field / outcome **一律有效**。

    旧判据（``_count_toc_only_norms``）用「标识文本只出现在目录行」作条件，
    对 **method/field 检出力 = 0**（其 name 必然同时出现在正文）。
    新判据（``_count_toc_sourced_by_line``）回查每个 norm 的 **source 行号**
    所在行是否被判为目录 —— 不依赖字符串匹配，三类 kind 一律有效。
    """
    import re
    from core.fused import rfc_extractor as rx

    lines = (ROOT / "kb" / "sip" / "spec" / "rfc3261.txt").read_text(
        encoding="utf-8", errors="ignore").splitlines()
    toc_idx = next(i for i, l in enumerate(lines)
                   if rx._is_toc_line(l) and re.match(r"^\s*\d+\.\d", l))
    src = f"file:rfc3261.txt#@{toc_idx + 1}"
    fake = [
        {"kind": "method", "name": "REGISTER", "content": "REGISTER", "source": src},
        {"kind": "field", "name": "Accept", "content": "Accept", "source": src},
        {"kind": "outcome", "name": "100", "content": "100 | when: x", "source": src},
    ]
    leaked = rx._count_toc_sourced_by_line("sip", fake)
    assert len(leaked) == 3, f"溯源行判据应检出 3 类，实际 {leaked}"
    # 旧判据对 method/field 无效（这正是新增判据的理由）
    assert len(rx._count_toc_only_norms("sip", fake)) == 0


@pytest.mark.parametrize("protocol", PROTOCOLS)
def test_no_toc_sourced_by_line_in_normal_run(protocol):
    """正常抽取下，无任何 norm 的来源行是目录行（零误报）。"""
    leaked = rx._count_toc_sourced_by_line(protocol, rx.extract_rfc_norms(protocol))
    assert leaked == [], f"{protocol} 检出目录来源的 norm: {leaked[:5]}"


def test_report_serializes_toc_sourced_by_line():
    """报告的 dict 序列化须带上 P0-2 指标。"""
    d = rx.rfc_quality_report("rtsp").to_dict()
    assert "toc_sourced_by_line" in d
    assert isinstance(d["toc_sourced_by_line"], list)
