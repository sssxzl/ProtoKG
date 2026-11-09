# -*- coding: utf-8 -*-
"""tests/fused/test_required_headers_guard.py —— 必填头覆盖守卫（2026-11-07）。

★ 为什么有这个文件：
  必填头清单是**人工撰写**的（`profile.seedgen.required_headers`）。
  漏一项的后果是**静默**的：种子照发该方法，但报文**一个头都没有**
  ⇒ 对目标是非法报文 ⇒ fuzzer 白跑，且**没有任何指标会红**。

  实测（守卫之前）：rtsp 的 `RECORD` 在 RFC 原生状态机的 transitions 里，
  但人工清单只有 8 个方法、**漏了 RECORD** ⇒ 实测生成出三条
  `RECORD | headers={} | url=rtsp://...` 的**无头报文**。

★ 本文件锁四件事：
  ① **漏项被抓到**（守卫的判据①：transitions 里的方法必须有必填头条目）；
  ② **命令协议天然豁免**（smtp 的 `required_headers` 为空是正确的）；
  ③ **判据零协议名**（换任意协议名结论不变）；
  ④ **不误报**（只在 methods 桶但不在 transitions 里的方法不该报）。
"""
from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_hub.py"


def _load_build_hub():
    spec = importlib.util.spec_from_file_location("_build_hub_guard", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bh():
    return _load_build_hub()


@pytest.fixture(autouse=True)
def _restore_semantic_switch():
    """★ 本仓有**全局**开关 ``semantic_rules_enabled()``：测试里打开后必须恢复。

    少了这个 fixture 会污染后续测试（实测：`test_semantic_chain` 的
    「默认路径不应有 semantic_rules 键」在整跑时失败、单跑通过）。
    """
    from core.fused.semantic.llm_ensemble import (semantic_rules_enabled,
                                         set_semantic_rules_enabled)
    _prev = semantic_rules_enabled()
    yield
    set_semantic_rules_enabled(_prev)


@pytest.fixture(autouse=True)
def _restore_semantic_switch():
    """★ 本仓有**全局**开关 ``semantic_rules_enabled()``：测试里打开后必须恢复。

    少了这个 fixture 会污染后续测试（实测：`test_semantic_chain` 的
    「默认路径不应有 semantic_rules 键」在整跑时失败、单跑通过）。
    """
    from core.fused.semantic.llm_ensemble import (semantic_rules_enabled,
                                         set_semantic_rules_enabled)
    _prev = semantic_rules_enabled()
    yield
    set_semantic_rules_enabled(_prev)


class _FakePath:
    """只提供 `read_text` / `is_file` 的假 profile 路径（守卫只读它）。"""

    def __init__(self, data: dict):
        self._data = data

    def read_text(self, encoding="utf-8") -> str:
        return json.dumps(self._data, ensure_ascii=False)

    def is_file(self) -> bool:
        return True


def _prof(protocol="fakeproto", *, header_line="{key}: {value}",
          request_line="{method} {url} {version}", required=None):
    return {
        "protocol": protocol,
        "raw_format": {"request_line": request_line, "header_line": header_line},
        "seedgen": {"required_headers": dict(required or {})},
    }


def _bundle(*methods):
    """构造一个只含 transitions/methods 的假 bundle。"""
    return {
        "transitions": [("S", m, "S") for m in methods],
        "methods": {m: {} for m in methods},
    }


# ===========================================================================
# ① 漏项被抓到
# ===========================================================================

def test_guard_reports_missing_required_headers(bh, monkeypatch, capsys):
    """★ 核心：transitions 里的方法缺必填头条目 ⇒ 必须报出来。"""
    monkeypatch.setattr(bh.paths, "target_profile",
                        lambda p: _FakePath(_prof(required={"FOO": ["CSeq"]})))
    missing = bh._check_required_headers_coverage(
        "fakeproto", bundle=_bundle("FOO", "BAR"))
    assert missing == ["BAR"], missing
    out = capsys.readouterr().out
    assert "守卫" in out
    assert "BAR" in out


def test_guard_passes_when_complete(bh, monkeypatch):
    """覆盖完整 ⇒ 无缺失。"""
    monkeypatch.setattr(bh.paths, "target_profile",
                        lambda p: _FakePath(_prof(required={"FOO": ["CSeq"],
                                                            "BAR": ["CSeq"]})))
    assert bh._check_required_headers_coverage(
        "fakeproto", bundle=_bundle("FOO", "BAR")) == []


def test_guard_reports_all_missing(bh, monkeypatch):
    """多个漏项要全报出来（不能只报第一个）。"""
    monkeypatch.setattr(bh.paths, "target_profile",
                        lambda p: _FakePath(_prof(required={})))
    missing = bh._check_required_headers_coverage(
        "fakeproto", bundle=_bundle("A", "B", "C"))
    assert missing == ["A", "B", "C"], missing


# ===========================================================================
# ② 命令协议豁免
# ===========================================================================

def test_command_protocol_is_exempt(bh, monkeypatch):
    """★ 命令协议（`header_line` 为空）⇒ 整体豁免，不报。

    实测 smtp：`raw_format.header_line = ''`（命令协议无头部行语法），
    它的 `required_headers` 为空是**正确的**。
    ★ 判据是**语法**不是协议名 ⇒ 换任何命令协议都豁免。
    """
    monkeypatch.setattr(bh.paths, "target_profile",
                        lambda p: _FakePath(_prof(
                            header_line="", request_line="{method} {argument}")))
    assert bh._check_required_headers_coverage(
        "fakecmd", bundle=_bundle("CMD1", "CMD2")) == []


def test_real_command_protocol_passes(bh):
    """★ 实测 smtp：真实语料下守卫通过（不误报）。"""
    assert bh._check_required_headers_coverage("smtp") == []


def test_real_header_protocols_pass(bh):
    """★ 实测 rtsp / sip：补完 RECORD 后守卫通过。"""
    assert bh._check_required_headers_coverage("rtsp") == []
    assert bh._check_required_headers_coverage("sip") == []


# ===========================================================================
# ③ 判据零协议名
# ===========================================================================

def test_guard_is_protocol_agnostic(bh, monkeypatch):
    """★ 换任意协议名，守卫结论不变。"""
    for proto in ("rtsp", "sip", "smtp", "fakeproto", "zzz"):
        monkeypatch.setattr(
            bh.paths, "target_profile",
            lambda p: _FakePath(_prof(protocol=p, required={"FOO": ["CSeq"]})))
        assert bh._check_required_headers_coverage(
            proto, bundle=_bundle("FOO", "BAR")) == ["BAR"], proto


def test_guard_code_has_no_protocol_name_whitelist():
    """★ 代码级守卫：守卫的**可执行代码**里不得出现协议名白名单。

    ★ 用 AST 剥掉 docstring 与注释后再扫 —— 否则 docstring 里
      「实测 rtsp 的 RECORD…」这类说明会被误判。
    """
    import ast
    src = inspect.getsource(_load_build_hub()._check_required_headers_coverage)
    tree = ast.parse(src)
    doc_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                doc_lines.update(range(node.body[0].lineno,
                                       node.body[0].end_lineno + 1))
    code_lines = []
    for i, line in enumerate(src.splitlines(), 1):
        if i in doc_lines:
            continue
        code_lines.append(line.split("#", 1)[0])
    code = "\n".join(code_lines).lower()
    for name in ("rtsp", "sip", "smtp", "http", "ftp"):
        assert name not in code, f"守卫的可执行代码里出现了协议名 {name}"


# ===========================================================================
# ④ 不误报：只在 methods 桶、不在 transitions 里的方法
# ===========================================================================

def test_guard_does_not_report_methods_not_in_transitions(bh, monkeypatch):
    """★ 不误报：methods 桶里有、但 transitions 里没有的方法不该报。

    实测 rtsp 的 ANNOUNCE / REDIRECT 在 methods 桶里但不在 transitions 里
    ⇒ 种子不会发 ⇒ 不该报（否则守卫噪音大、真漏项被淹没）。
    """
    monkeypatch.setattr(bh.paths, "target_profile",
                        lambda p: _FakePath(_prof(required={"FOO": ["CSeq"]})))
    b = _bundle("FOO")
    b["methods"]["NOT_IN_TRANSITIONS"] = {}
    assert bh._check_required_headers_coverage("fakeproto", bundle=b) == []


# ===========================================================================
# ⑤ RECORD 已补（回归守卫：修好的东西不许退回去）
# ===========================================================================

def test_rtsp_record_has_required_headers():
    """★ rtsp 的 RECORD 必须有必填头（RFC 2326 §10.11 示例：CSeq + Session）。"""
    prof = json.loads(
        (ROOT / "fused_hub" / "targets" / "rtsp" / "profile.json")
        .read_text(encoding="utf-8"))
    rh = (prof.get("seedgen") or {}).get("required_headers") or {}
    assert "RECORD" in rh, "RECORD 的必填头又被删掉了"
    assert "CSeq" in rh["RECORD"]


def test_no_seed_message_without_headers():
    """★ 端到端：三协议生成的报文**不得有任何一个没有头部**（头部协议）。"""
    from core.fused.downstream import rag_seedgen as RS
    from core.fused.downstream.edge_cover import edge_cover
    from core.fused.semantic.llm_ensemble import set_semantic_rules_enabled
    set_semantic_rules_enabled(True)
    for proto in ("rtsp", "sip"):
        b = RS.assemble_bundle(RS.load_fact_views(proto), proto,
                               apply_allowed_methods=False)
        corp = edge_cover(b["transitions"],
                          required_headers=b["required_headers"],
                          headers=b["headers"],
                          message_instances=b["message_instances"],
                          protocol=proto)
        empty = [m.method for s in corp for m in s.messages if not m.headers]
        assert not empty, f"{proto} 有无头报文：{empty}"
