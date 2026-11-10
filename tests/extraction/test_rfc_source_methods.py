# -*- coding: utf-8 -*-
"""tests/fused/test_rfc_source_methods.py —— 「RFC 源方法集」的五种形态。

★ 五种形态（① 章节标题 / A′ 括号 / B ABNF 枚举 / **D ABNF 命令规则字面量**
  / **E 散文命令格式声明**）：
  §④ 是 2026-11-06 补的第 4 种 —— RFC 4954 用
  `auth-command = "AUTH" SP sasl-mech` 定义 AUTH，前三种全不命中；
  §⑤ 是 2026-11-07 补的第 5 种 —— RFC 3207 用散文
  "The format for the STARTTLS command is:" 定义 STARTTLS，前四种全不命中。

★ 背景（2026-11-06 实测缺陷）：原实现只认**形态 A**（章节标题 + 全大写 token），
  且**未排除目录行** ⇒ 三个协议全部抽错：

  | 协议 | 旧结果 | 问题 |
  |---|---|---|
  | rtsp | 11 | 恰好正确（§10 标题形态） |
  | sip  | {UAC, UAS} | **目录行噪声**（`12.1.1 UAS behavior ..... 70`）；§25 ABNF 里的真方法一个没抽到 |
  | smtp | 12（含 EXPAND/RECIPIENT/RESET/VERIFY/SMTP/STARTTLS） | 章节**描述词**当成了命令名；真命令只出现在括号里 `4.1.1.3.  RECIPIENT (RCPT)` |

★ 方法集是**质量闸判据 ②（可驱动）**的唯一来源（`_transition_quality_gate`），
  也是合并提示的白名单 ⇒ 抽错会**静默**把合法转移当垃圾扔掉。
"""
from __future__ import annotations

import re

import pytest

from core.fused.extraction import rfc_extractor as RX


def _has_spec(protocol: str) -> bool:
    from core import paths
    return paths.kb_source_dir(protocol, "rfc").is_dir()


# ===========================================================================
# ① 三种形态（合成底料，不依赖真实 RFC）
# ===========================================================================

def _fake_kb(tmp_path, monkeypatch, text: str):
    """把 `kb_source_dir` 指到临时目录，返回目录对象。"""
    d = tmp_path / "spec"
    d.mkdir()
    (d / "rfc.txt").write_text(text, encoding="utf-8")
    monkeypatch.setattr(RX.paths, "kb_source_dir", lambda _p, _s: d)
    return d


def test_form_a_heading_only(tmp_path, monkeypatch):
    """形态 A：整行只有方法名（`10.1 OPTIONS`）。"""
    _fake_kb(tmp_path, monkeypatch, (
        "10.1 OPTIONS\n"
        "10.2 DESCRIBE\n"
        "10.3 ANNOUNCE\n"
    ))
    ms = RX._rfc_source_methods("x", {"method_sections": ["10"]})
    assert ms == {"OPTIONS", "DESCRIBE", "ANNOUNCE"}


def test_form_a_rejects_heading_with_prose(tmp_path, monkeypatch):
    """★ 形态 A 要求**整行只有**方法名 ⇒ `10.4 OPTIONS request` 不算。"""
    _fake_kb(tmp_path, monkeypatch, "10.4 OPTIONS request\n10.5 SETUP\n")
    ms = RX._rfc_source_methods("x", {"method_sections": ["10"]})
    assert ms == {"SETUP"}, f"散文标题不应混入，实得 {sorted(ms)}"


def test_form_a_prime_paren(tmp_path, monkeypatch):
    """形态 A′：`4.1.1.3.  RECIPIENT (RCPT)` ⇒ 取**括号内**的真命令名。"""
    _fake_kb(tmp_path, monkeypatch, (
        "4.1.1.2.  MAIL (MAIL)\n"
        "4.1.1.3.  RECIPIENT (RCPT)\n"
        "4.1.1.4.  RESET (RSET)\n"
    ))
    ms = RX._rfc_source_methods("x", {"method_sections": ["4.1.1"]})
    assert ms == {"MAIL", "RCPT", "RSET"}, f"应取括号内，实得 {sorted(ms)}"


def test_form_b_abnf_multiline(tmp_path, monkeypatch):
    """形态 B：ABNF 枚举，**续行以 `/` 开头**（SIP §25 的真实排版）。"""
    _fake_kb(tmp_path, monkeypatch, (
        "25.1  Method\n"
        "   Method = INVITEm / ACKm / OPTIONSm / BYEm / CANCELm\n"
        "            / REGISTERm\n"
        "            / extension-method\n"
    ))
    ms = RX._rfc_source_methods("x", {"method_sections": ["25"]})
    assert ms == {"INVITE", "ACK", "OPTIONS", "BYE", "CANCEL", "REGISTER"}, (
        f"ABNF 续行未收全，实得 {sorted(ms)}")


def test_form_b_not_gated_by_method_sections(tmp_path, monkeypatch):
    """★ ABNF 形态不受 `method_sections` 限制（方法表所在章节名未必固定）。"""
    _fake_kb(tmp_path, monkeypatch, "   Method = HELOm / QUITm\n")
    ms = RX._rfc_source_methods("x", {"method_sections": ["99"]})
    assert ms == {"HELO", "QUIT"}


def test_toc_lines_excluded(tmp_path, monkeypatch):
    """★ 目录行（点线）必须排除 —— 旧实现抽出的 `UAS` 就是这里来的。"""
    _fake_kb(tmp_path, monkeypatch, (
        "12.1.1 UAS behavior .......................... 70\n"
        "12.1.2 UAC behavior\n"
    ))
    ms = RX._rfc_source_methods("x", {"method_sections": ["12"]})
    assert ms == set(), f"目录行不得产出方法名，实得 {sorted(ms)}"


def test_keyword_atoms_excluded(tmp_path, monkeypatch):
    """RFC 关键字 / 角色缩写不得当成方法。"""
    _fake_kb(tmp_path, monkeypatch, "10.1 MUST\n10.2 UAC\n10.3 SHALL\n10.4 PLAY\n")
    ms = RX._rfc_source_methods("x", {"method_sections": ["10"]})
    assert ms == {"PLAY"}, f"关键字原子混入，实得 {sorted(ms)}"


def test_empty_config_yields_empty_set():
    """不猜、不硬编码：配置没声明章节 ⇒ 空集。"""
    assert RX._rfc_source_methods("rtsp", {"method_sections": []}) == set()
    assert RX._rfc_source_methods("rtsp", {}) == set()


# ===========================================================================
# ② 真实 RFC 回归（底料缺失则跳过）
# ===========================================================================

def test_rtsp_methods_unchanged():
    """★ rtsp 是**唯一本来就抽对**的协议（§10 标题形态）⇒ 修复前后必须一致。"""
    if not _has_spec("rtsp"):
        pytest.skip("无 rtsp RFC 底料")
    ms = RX._rfc_source_methods("rtsp", RX._load_rfc_config("rtsp"))
    assert ms == {"ANNOUNCE", "DESCRIBE", "GET_PARAMETER", "OPTIONS", "PAUSE",
                  "PLAY", "RECORD", "REDIRECT", "SETUP", "SET_PARAMETER",
                  "TEARDOWN"}, f"rtsp 方法集漂移：{sorted(ms)}"


def test_sip_methods_from_abnf():
    """★ sip 的真方法只在 §25 ABNF 里；且**不得**出现目录行噪声 UAC/UAS。"""
    if not _has_spec("sip"):
        pytest.skip("无 sip RFC 底料")
    ms = RX._rfc_source_methods("sip", RX._load_rfc_config("sip"))
    assert {"INVITE", "ACK", "OPTIONS", "BYE", "CANCEL", "REGISTER"} <= ms, (
        f"sip 真方法缺失：{sorted(ms)}")
    assert "UAC" not in ms and "UAS" not in ms, (
        f"目录行噪声仍在：{sorted(ms)}")


def test_smtp_methods_use_real_commands():
    """★ smtp 取真命令名（括号形态 + 散文格式声明）。

    ★ 描述词 EXPAND/RECIPIENT/RESET/VERIFY **不得**混入（章节标题的
      描述词 ≠ 命令名）。
    ★ ``SMTP`` 是**协议自身名**（不是命令）⇒ 形态 E 的排除项之一。
    ★ ``STARTTLS`` 是 **RFC 3207 §4 定义的命令**（形态 E 抽出）⇒ 必须出现；
      它此前被列为「描述词」是 2026-11-06 的真实缺口，本次已补上。
    """
    if not _has_spec("smtp"):
        pytest.skip("无 smtp RFC 底料")
    ms = RX._rfc_source_methods("smtp", RX._load_rfc_config("smtp"))
    for name in ("MAIL", "RCPT", "DATA", "QUIT", "RSET", "VRFY", "EXPN"):
        assert name in ms, f"smtp 真命令 {name} 缺失，实得 {sorted(ms)}"
    assert "STARTTLS" in ms, f"STARTTLS（RFC 3207 §4）缺失，实得 {sorted(ms)}"
    for bad in ("EXPAND", "RECIPIENT", "RESET", "VERIFY", "SMTP"):
        assert bad not in ms, f"描述词 {bad} 被当成命令，实得 {sorted(ms)}"


# ===========================================================================
# ③ 协议无关性守卫（G2）
# ===========================================================================

def test_no_protocol_or_method_hardcode():
    """★ G2：函数体内不得出现协议名或协议特定方法名（须完全配置驱动）。"""
    import inspect
    src = inspect.getsource(RX._rfc_source_methods)
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"#[^\n]*", "", src)
    for bad in ("rtsp", "sip", "smtp", "INVITE", "RCPT", "SETUP", "OPTIONS"):
        assert not re.search(rf"\b{re.escape(bad)}\b", src), (
            f"方法集抽取出现了协议/方法特例「{bad}」⇒ 违反 G2")


# ===========================================================================
# ④ 形态 D：ABNF「命令规则 = "大写字面量"」（2026-11-06 新增）
# ===========================================================================

def test_abnf_quoted_command_form():
    """`auth-command = "AUTH" SP sasl-mech` ⇒ 抽出 AUTH。

    这是 RFC 4954 §8 定义 AUTH 的方式：**既不是**章节标题（§4 的标题是
    小写的 "The AUTH Command"），**也不是** hex 伴生规则（SIP 那种）
    ⇒ 三种既有形态全不命中，AUTH 只能靠 profile 骨架"补"（单源口径下即污染）。
    """
    text = (
        "8.  ABNF\n\n"
        "   auth-command      = \"AUTH\" SP sasl-mech [SP initial-response]\n"
        "   sasl-mech         = \"PLAIN\" / \"LOGIN\" / \"CRAM-MD5\"\n"
    )
    assert RX._extract_abnf_quoted_commands(text) == ["AUTH"]


def test_abnf_quoted_ignores_non_command_rules():
    """非 `*-command` 规则一律不采信（否则 `version = "HTTP/1.1"` 会混进来）。"""
    text = (
        "   version  = \"HTTP/1.1\"\n"
        "   separator = \"/\"\n"
        "   method-list = \"GET\" / \"PUT\"\n"
    )
    assert RX._extract_abnf_quoted_commands(text) == []


def test_abnf_quoted_requires_uppercase_literal():
    """小写字面量不是命令名（ABNF 里小写通常表示关键字/参数值）。"""
    assert RX._extract_abnf_quoted_commands('   foo-command = "bar"\n') == []


def test_smtp_auth_extracted_from_real_rfc():
    """★ 真实语料：smtp 必须有 AUTH（来自 rfc4954），且两个消费者一致。"""
    if not _has_spec("smtp"):
        pytest.skip("无 smtp RFC 底料")
    cfg = RX._load_rfc_config("smtp")
    ms = RX._rfc_source_methods("smtp", cfg)
    norm_methods = {n["name"] for n in RX.extract_rfc_norms("smtp")
                    if n.get("kind") == "method"}
    assert "AUTH" in ms, f"AUTH 缺失，实得 {sorted(ms)}"
    assert "AUTH" in norm_methods, f"norms 里没有 AUTH，实得 {sorted(norm_methods)}"
    # 两个消费者必须一致（否则质量闸与 norms 会互相矛盾）
    assert ms == norm_methods, (
        f"方法集两处不一致：_rfc_source_methods={sorted(ms)} "
        f"vs extract_rfc_norms={sorted(norm_methods)}")


def test_abnf_quoted_no_false_positive_on_rtsp_sip():
    """rtsp / sip 的 RFC 里没有 `*-command` 规则 ⇒ 该通道不得增产方法。"""
    for proto in ("rtsp", "sip"):
        if not _has_spec(proto):
            continue
        text = RX._rfc_full_text(proto)
        assert RX._extract_abnf_quoted_commands(text) == [], proto
