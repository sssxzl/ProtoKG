# -*- coding: utf-8 -*-
"""tests/fused/test_all_sources_state_machines.py —— 批次 2.3。

★ 用户要求：「每个知识源获取的状态机信息也都保存到结构化知识中枢中，
  后期让 LLM 依据我们定的规则进行判别」⇒ 本期只做**保存 + 预留判别接口**。

★ 覆盖五条：
  ① **各源的状态机都在中枢里**（facts 层：语义确定的 `target_state`）
  ② **bundle 提供按源分组的全量**（`transitions_by_source`）⇒ 后期 LLM 的输入
  ③ ★ **消费端行为不变**（`transitions` 仍是「当前采用的一套」）
     ⇒ 「保存」与「使用」分离
  ④ 中枢目录下有**候选区** `state_machines.json`（语义待判别的条目也存着）
  ⑤ 判别落点 `_select_active_transitions()` 存在且**可替换**
"""
from __future__ import annotations

import json

import pytest

from core import paths                                      # noqa: E402
from core.fused.downstream import rag_seedgen as RS        # noqa: E402

PROTOCOL = "rtsp"


@pytest.fixture()
def bundle():
    views = RS.load_fact_views(PROTOCOL)
    if not views:
        pytest.skip("中枢为空（需先跑 build_hub）")
    return RS.assemble_bundle(views, PROTOCOL)


# ===========================================================================
# ① 各源的状态机都在中枢里
# ===========================================================================

def test_all_sources_state_machines_are_in_hub(bundle):
    """★ 各来源的状态机**都在**中枢的 facts 里（按 authority 可分）。"""
    by_src = bundle.get("transitions_by_source") or {}
    assert by_src, "中枢里没有任何来源的状态机"
    assert "profile" in by_src, "协议骨架的状态机没在中枢里"
    # 每条都有来源标注 ⇒ 逐条可追
    for src, rows in by_src.items():
        for row in rows:
            assert len(row) == 3, f"{src} 的状态机条目形态异常：{row}"
            assert all(str(x) for x in row), f"{src} 有空字段：{row}"


def test_rfc_source_state_machines_are_in_hub():
    """★ RFC 源自己贡献的状态机也进了中枢（rtsp 开启了 enable_transitions）。"""
    views = RS.load_fact_views(PROTOCOL)
    if not views:
        pytest.skip("中枢为空")
    auths = set()
    for v in views:
        if (v.get("fact_key") or {}).get("aspect") != "target_state":
            continue
        for c in (v.get("all_claims") or []):
            if c.get("authority"):
                auths.add(c["authority"])
    assert "profile" in auths, "骨架的状态机缺失"
    assert "rfc" in auths, "RFC 源的状态机没进中枢（enable_transitions 未开？）"


# ===========================================================================
# ② 按源分组的全量
# ===========================================================================

def test_transitions_by_source_is_complete(bundle):
    """★ `transitions_by_source` 的条目总数 ≥ `transitions`（不丢信息）。"""
    by_src = bundle.get("transitions_by_source") or {}
    total = sum(len(v) for v in by_src.values())
    assert total >= len(bundle["transitions"]), (
        f"按源分组的总数 {total} < 采用的一套 {len(bundle['transitions'])}")


def test_transitions_by_source_has_no_unknown_source(bundle):
    """★ 每条状态机的来源都能对上（无来源不明条目）。"""
    by_src = bundle.get("transitions_by_source") or {}
    avail = set(bundle.get("available_sources") or [])
    for src in by_src:
        if src in ("(unknown)", ""):
            pytest.fail("存在来源不明的状态机条目")
        assert src in avail, f"状态机来源 {src} 不在 available_sources {avail}"


# ===========================================================================
# ③ 消费端行为不变（保存与使用分离）
# ===========================================================================

def test_active_transitions_unchanged(bundle):
    """★ `transitions` 仍是**当前采用的一套**（本期 = 协议骨架那套）。"""
    by_src = bundle.get("transitions_by_source") or {}
    profile_rows = by_src.get("profile") or []
    assert profile_rows, "协议骨架那套不在（本期采用它）"
    assert set(bundle["transitions"]) == set(
        tuple(r) for r in profile_rows), "采用的一套与协议骨架不一致"


def test_transitions_are_deduplicated(bundle):
    """★ 采用的一套**去重**（同一 (from, method, to) 只出现一次）。"""
    rows = bundle["transitions"]
    assert len(rows) == len(set(rows))


# ===========================================================================
# ④ 中枢目录的候选区
# ===========================================================================

def test_state_machine_candidates_file_exists():
    """★ 中枢目录下有 `state_machines.json`（语义待判别的条目也存着）。"""
    path = paths.per_source_root(PROTOCOL) / "state_machines.json"
    if not path.is_file():
        pytest.skip("尚未生成候选区（需先跑 build_hub）")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc.get("protocol") == PROTOCOL
    sources = doc.get("sources") or {}
    assert sources, "候选区为空"
    # 每一路候选都应是 {from, method, to} 三元组
    for src, rows in sources.items():
        for row in rows:
            assert set(row) == {"from", "method", "to"}, (
                f"{src} 的候选形态异常：{row}")


def test_candidates_include_skeleton_and_rfc():
    """★ 候选区同时含「协议骨架」与「RFC 源」两路（供后期 LLM 并列判别）。"""
    path = paths.per_source_root(PROTOCOL) / "state_machines.json"
    if not path.is_file():
        pytest.skip("尚未生成候选区")
    sources = json.loads(path.read_text(encoding="utf-8")).get("sources") or {}
    assert any(k.startswith("profile") for k in sources), "缺协议骨架的候选"
    assert any(k.startswith("rfc") for k in sources), "缺 RFC 源的候选"


# ===========================================================================
# ⑤ 判别落点
# ===========================================================================

def test_select_active_transitions_is_the_llm_hook():
    """★ `_select_active_transitions()` = **后期 LLM 判别的接入点**。

    判据：它是**独立函数**（可整体替换）⇒ 后期把默认规则换成「LLM 判别
    结果」即可，**其它环节不必改动**。
    """
    fn = RS._select_active_transitions
    assert callable(fn)
    # 当前默认：优先协议骨架那套
    by_src = {"profile": [("Init", "SETUP", "Ready")],
              "rfc": [("A", "B", "C")]}
    assert fn(by_src) == [("Init", "SETUP", "Ready")]
    # 没有协议骨架时 ⇒ 用全部
    assert fn({"rfc": [("A", "B", "C")]}) == [("A", "B", "C")]
    # 空输入不炸
    assert fn({}) == []
