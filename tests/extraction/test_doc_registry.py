# -*- coding: utf-8 -*-
"""tests/extraction/test_doc_registry.py —— 文档级登记的测试（第四批）。

★ 关键边界：**「文档自述状态」≠「当前生效状态」**
  ⇒ ⇒ 测试要保证：抽不到的记 unknown / 空，**不猜**
  ⇒ ⇒ 且 `status_label` 只表示 self_declared
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.fused.extraction.doc_registry import (  # noqa: E402
    CATEGORY_EXPERIMENTAL, CATEGORY_INFORMATIONAL, CATEGORY_STANDARD,
    CATEGORY_UNKNOWN, SELF_DECLARED, UNKNOWN, parse_header,
)

_HEADER = """Network Working Group                                       Example WG
Request for Comments: 2326                              Obsoletes: 2545
Updates: 2545, 2549                                      Category: Standards Track
                                                            February 1998

Abstract
   This document describes the protocol.
"""

_INFORMATIONAL = """Request for Comments: 9110                              Category: Informational
                                                            October 2001
"""


def test_parse_rfc_number():
    """编号抽取。"""
    r = parse_header(_HEADER, protocol="rtsp", filename="rfc2326.txt")
    assert r.rfc_number == "2326"


def test_parse_title():
    """标题抽取（编号之后的标题行）。"""
    r = parse_header(_HEADER, filename="rfc2326.txt")
    assert r.title                     # ★ 标题抽到了（右侧或下一行）
    assert "Request for Comments" not in r.title


def test_parse_category_is_self_declared():
    """类别 = **该文档自述**的 Category。"""
    r = parse_header(_HEADER, filename="rfc2326.txt")
    assert r.category == CATEGORY_STANDARD


def test_parse_updates_obsoletes():
    """Updates / Obsoletes 抽取。"""
    r = parse_header(_HEADER, filename="rfc2326.txt")
    assert "2545" in r.updates
    assert "2549" in r.updates
    assert "2545" in r.obsoletes


def test_parse_date():
    """日期抽取。"""
    r = parse_header(_HEADER, filename="rfc2326.txt")
    assert r.date == "February 1998"


def test_parse_informational_category():
    """Informational 类别。"""
    r = parse_header(_INFORMATIONAL, filename="rfc9110.txt")
    assert r.category == CATEGORY_INFORMATIONAL
    assert r.date == "October 2001"


def test_missing_fields_are_unknown_not_guessed():
    """★ 抽不到 ⇒ 记 unknown / 空（**不猜**）。"""
    r = parse_header("just some text without any rfc header\n",
                     filename="x.txt")
    assert r.rfc_number == ""
    assert r.category == CATEGORY_UNKNOWN
    assert r.status_label == UNKNOWN
    assert not r.updates and not r.obsoletes


def test_status_label_means_self_declared_only():
    """★ ``status_label`` 只表示「自述」⇒ **不得**解读为「当前生效」。"""
    r = parse_header(_HEADER, filename="rfc2326.txt")
    assert r.status_label == SELF_DECLARED
    _d = r.to_dict()
    assert "当前生效" not in _d["status_label"]
    assert "当前生效" in _d["note"]     # ★ note 必须声明「≠ 当前生效」


def test_obsoletes_does_not_block_extraction():
    """★ **不因状态/被 Obsoletes 就拒抽** ⇒ 登记信息不含「拒抽」标记。"""
    r = parse_header(_HEADER, filename="rfc2326.txt")
    _d = r.to_dict()
    assert "reject" not in _d and "block" not in _d
    assert "reject" not in _d["note"] and "block" not in _d["note"]


def test_normative_refs_exclude_self():
    """规范性引用**不含自身**编号。"""
    r = parse_header(_HEADER + "\nSee also RFC 2326 and RFC 1000.\n",
                     filename="rfc2326.txt")
    assert "2326" not in r.normative_refs
    assert "1000" in r.normative_refs


def test_experimental_category():
    """Experimental 类别。"""
    r = parse_header("Request for Comments: 1234   Category: Experimental\n"
                     "                                  March 2020\n",
                     filename="rfc1234.txt")
    assert r.category == CATEGORY_EXPERIMENTAL
