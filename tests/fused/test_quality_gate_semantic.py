# -*- coding: utf-8 -*-
"""B-9：语义规则质量闸（强制机制 4）测试。

覆盖：
  ① 报告新增的四个度量（语义规则总数 / 可执行率 / 候选拒绝原因直方图 /
     `constraint is None` 计数）**存在且可序列化**；
  ② 可执行率**分母为 0 时记 0.0**（不是 1.0）且报告显式说明；
  ③ `constraint is None` 计数 > 0 ⇒ **阻断构建**，且给出**可定位**信息
     （rule_id / 协议 / reject_reason / 源锚点）——**反向验证**；
  ④ 候选 `convertible=true` 计数 > 0 ⇒ **阻断构建**，且可定位 ——**反向验证**；
  ⑤ `gate_exercised` 自检：无规则/候选时**不得**让「0 违规」看起来像「通过」；
  ⑥ `rules_only` 模式：只产语义规则与候选、三闸生效、**不改** D-6 开关位；
  ⑦ 落盘格式与 `rule_store` 兼容（`load_rules` / `load_candidates` 可读回）。

★ 所有写盘都在 pytest 的 `tmp_path` 下 ⇒ **不污染仓库 `derived/`**。
"""
from __future__ import annotations

import json

import pytest

from core.fused.extraction import rfc_extractor as rx


# ===========================================================================
# 测试夹具：构造**违规**的四库（模拟「误把候选写进规则库」等事故）
# ===========================================================================

def _evidence(source_anchor: str = "file:rfc2326.txt#@42") -> dict:
    return {
        "evidence_id": "e0011223344556",
        "spec_version": "RFC 2326",
        "section_path": ["Protocol Parameters"],
        "source_anchor": source_anchor,
        "span_text": "The value MUST be less than 100.",
        "span_start": 100,
        "span_end": 138,
        "evidence_kind": "normative",
        "explicitness": "explicit",
        "source_class": "normative_spec",
    }


def _write_rule_without_constraint(root, protocol: str = "rtsp") -> None:
    """写一条 **constraint=None** 的规则（强制机制 4 的第一类违规）。"""
    d = rx.semantic_library_dir(protocol, root)
    d.mkdir(parents=True, exist_ok=True)
    row = {
        "kind": rx._KIND_RULE,
        # 行级 reject_reason：模拟「这条其实是不可转换的候选，被误写进规则库」
        "reject_reason": "operator_unresolved",
        "rule": {
            "rule_id": "rdeadbeefdeadbeef",
            "evidence": _evidence(),
            "constraint": None,
            "subject_type": "field",
            "subject_name": "Transport",
            "rule_state": "authoritative",
            "supersedes": None,
            "model_confidence": 1.0,
            "validated": False,
        },
    }
    (d / rx._RULES_FILE).write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_convertible_candidate(root, protocol: str = "rtsp") -> None:
    """写一条 **convertible=true** 的候选（强制机制 4 的第二类违规）。"""
    d = rx.semantic_library_dir(protocol, root)
    d.mkdir(parents=True, exist_ok=True)
    row = {
        "kind": rx._KIND_CANDIDATE,
        "reject_reason": "field_unbound",
        "candidate": {
            "candidate_id": "c0011223344556",
            "evidence": _evidence(),
            "subject_type": "",
            "subject_name": "",
            "raw_text": "The field MUST contain exactly one value.",
            "convertible": True,
            "reject_reason": "field_unbound",
        },
    }
    (d / rx._CANDIDATES_FILE).write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")


# ===========================================================================
# ① 报告新增的四个度量
# ===========================================================================

def test_quality_report_exposes_b9_metrics():
    """B-9 的四个度量 + 自检字段必须在报告里可序列化。"""
    d = rx.rfc_quality_report("rtsp").to_dict()
    # ① 语义规则总数（分协议 + 合计）
    assert "semantic_rules_total" in d
    assert isinstance(d["semantic_rules_total"], dict)
    assert "total" in d["semantic_rules_total"]
    # ② 可执行率
    assert "executable_rate" in d
    assert isinstance(d["executable_rate"], float)
    assert "executable_rate_note" in d
    # ③ 候选拒绝原因直方图
    assert "reject_reason_histogram" in d
    assert isinstance(d["reject_reason_histogram"], dict)
    # ④ `constraint is None` 计数
    assert "constraint_none_count" in d
    assert isinstance(d["constraint_none_count"], int)
    # 自检字段
    assert isinstance(d["gate_exercised"], bool)
    assert "gate_note" in d
    # 第二类违规计数
    assert "convertible_true_count" in d


def test_report_metrics_are_backward_compatible():
    """★ 新字段**不得**破坏既有字段：既有键仍在、既有闸仍生效。"""
    rep = rx.rfc_quality_report("rtsp")
    d = rep.to_dict()
    for key in ("protocol", "norm_count", "fact_count", "dup_fact_ids",
                "toc_only_norms", "toc_sourced_by_line", "kinds",
                "blocking_issues", "offline_metrics", "warnings", "passed"):
        assert key in d
    # 既有构建闸结论不变（三协议仍通过）
    for proto in ("rtsp", "sip", "smtp"):
        assert rx.rfc_quality_report(proto).passed


# ===========================================================================
# ② 可执行率：分母为 0 ⇒ 0.0（**不是** 1.0）
# ===========================================================================

def test_executable_rate_zero_denominator_is_zero_not_one(tmp_path):
    """★ 空集**不得**伪装成 100%：分母 0 ⇒ 可执行率 0.0 + 显式说明。"""
    audit = rx.audit_semantic_library("rtsp", root=tmp_path)
    assert audit.rules_total == 0
    rep = rx.semantic_quality_report("rtsp", audit)
    assert rep.executable_rate == 0.0
    assert rep.executable_rate != 1.0
    assert "0.0" in rep.executable_rate_note
    assert "空集" in rep.executable_rate_note
    assert rep.executable_rate_note.strip()


def test_executable_rate_with_candidates_but_no_rules(tmp_path):
    """有候选、无规则时：闸口**已检验**，但可执行率仍是 0.0。"""
    _write_convertible_candidate(tmp_path)
    # 改成**合法**候选（convertible=False）⇒ 不触发阻断，只验证分母口径
    d = rx.semantic_library_dir("rtsp", tmp_path)
    row = json.loads((d / rx._CANDIDATES_FILE).read_text(encoding="utf-8"))
    row["candidate"]["convertible"] = False
    (d / rx._CANDIDATES_FILE).write_text(
        json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    audit = rx.audit_semantic_library("rtsp", root=tmp_path)
    rep = rx.semantic_quality_report("rtsp", audit)
    assert audit.rules_total == 0
    assert audit.candidates_total == 1
    assert rep.executable_rate == 0.0
    assert rep.gate_exercised is True


# ===========================================================================
# ③ 反向验证：`constraint is None` ⇒ 阻断 + 可定位信息
# ===========================================================================

def test_constraint_none_rule_blocks_build_with_locatable_info(tmp_path):
    """★ 反向验证（闸口必须有牙齿）：`constraint is None` ⇒ 阻断构建。"""
    _write_rule_without_constraint(tmp_path)

    audit = rx.audit_semantic_library("rtsp", root=tmp_path)
    assert audit.rules_total == 1
    assert audit.constraint_none_count == 1
    assert audit.convertible_true_count == 0

    rep = rx.semantic_quality_report("rtsp", audit)
    assert not rep.passed, "含 `constraint is None` 的规则库**必须**阻断构建"
    issue = " ".join(rep.blocking_issues)
    assert "constraint is None" in issue
    # ★ 可定位信息：rule_id / 协议 / reject_reason / 源锚点
    assert "rdeadbeefdeadbeef" in issue
    assert "rtsp" in issue
    assert "operator_unresolved" in issue
    assert "file:rfc2326.txt#@42" in issue

    detail = rep.constraint_none_details[0]
    assert detail["rule_id"] == "rdeadbeefdeadbeef"
    assert detail["protocol"] == "rtsp"
    assert detail["reject_reason"] == "operator_unresolved"
    assert detail["source_anchor"] == "file:rfc2326.txt#@42"

    # 可执行率必须**掉下来**（不是 1.0）
    assert rep.executable_rate == 0.0
    assert rep.semantic_executable_rules == 0


def test_rule_store_loader_also_rejects_constraint_none(tmp_path):
    """对照证据：`rule_store.load_rules` 对同一条数据**直接抛异常**。

    ⇒ 正说明闸口必须走**原始 JSONL 审计**（否则只能炸、无法计数）。
    """
    from core.fused.downstream import rule_store
    _write_rule_without_constraint(tmp_path)
    path = tmp_path / "rtsp" / "rfc" / "semantic" / rx._RULES_FILE
    with pytest.raises(ValueError):
        rule_store.load_rules(path)


# ===========================================================================
# ④ 反向验证：候选 `convertible=true` ⇒ 阻断 + 可定位信息
# ===========================================================================

def test_convertible_true_candidate_blocks_build_with_locatable_info(tmp_path):
    """★ 反向验证：候选 `convertible=true` ⇒ 阻断构建（可定位）。"""
    _write_convertible_candidate(tmp_path)

    audit = rx.audit_semantic_library("rtsp", root=tmp_path)
    assert audit.convertible_true_count == 1
    assert audit.constraint_none_count == 0

    rep = rx.semantic_quality_report("rtsp", audit)
    assert not rep.passed, "含 `convertible=true` 的候选库**必须**阻断构建"
    issue = " ".join(rep.blocking_issues)
    assert "convertible=true" in issue
    assert "c0011223344556" in issue
    assert "rtsp" in issue
    assert "field_unbound" in issue

    detail = rep.convertible_true_details[0]
    assert detail["candidate_id"] == "c0011223344556"
    assert detail["protocol"] == "rtsp"
    assert detail["reject_reason"] == "field_unbound"


def test_candidate_loader_also_rejects_convertible_true(tmp_path):
    """对照证据：`rule_store.load_candidates` 对同一条数据**直接抛异常**。"""
    from core.fused.downstream import rule_store
    _write_convertible_candidate(tmp_path)
    path = tmp_path / "rtsp" / "rfc" / "semantic" / rx._CANDIDATES_FILE
    with pytest.raises(ValueError):
        rule_store.load_candidates(path)


# ===========================================================================
# ⑤ 自检：`gate_exercised` 不得让「0 违规」看起来像「通过」
# ===========================================================================

def test_gate_exercised_false_when_nothing_produced(tmp_path):
    """★ 无任何规则/候选 ⇒ 必须显式写明「闸口未被检验」。"""
    audit = rx.audit_semantic_library("rtsp", root=tmp_path)
    rep = rx.semantic_quality_report("rtsp", audit)
    assert rep.gate_exercised is False
    assert "闸口未被检验" in rep.gate_note
    assert "不等于" in rep.gate_note
    # 空集**不阻断**（库里没有东西 ⇒ 没有可违规的东西）
    assert rep.passed


def test_gate_exercised_true_when_rules_exist(tmp_path):
    """有规则 ⇒ 闸口**确实**被检验过。"""
    bundle = rx.build_semantic_rules("rtsp")
    rx.save_semantic_library("rtsp", bundle.rules, bundle.candidates,
                             root=tmp_path)
    audit = rx.audit_semantic_library("rtsp", root=tmp_path)
    rep = rx.semantic_quality_report("rtsp", audit)
    assert rep.gate_exercised is True
    assert "闸口**已检验**" in rep.gate_note


# ===========================================================================
# ⑥ `rules_only` 模式
# ===========================================================================

def test_rules_only_produces_only_rules_and_candidates(tmp_path):
    """`rules_only` 产出：**只有**语义规则与知识候选，且契约成立。"""
    bundle = rx.build_semantic_rules("rtsp")
    assert bundle.rules, "rtsp 应产出可执行语义规则"
    assert bundle.candidates, "rtsp 应产出知识候选"
    # 契约：规则**必带** constraint；候选**必** convertible=False 且有拒绝原因
    assert all(r.constraint is not None for r in bundle.rules)
    assert all(not c.convertible for c in bundle.candidates)
    assert all(c.reject_reason for c in bundle.candidates)
    assert bundle.reject_reason_histogram
    assert sum(bundle.reject_reason_histogram.values()) == len(bundle.candidates)


def test_rules_only_library_passes_gate_and_is_readable(tmp_path):
    """落盘后的四库：三闸通过 + `rule_store` 读得回（格式兼容）。"""
    from core.fused.downstream import rule_store
    bundle = rx.build_semantic_rules("rtsp")
    written = rx.save_semantic_library("rtsp", bundle.rules, bundle.candidates,
                                       root=tmp_path)
    audit = rx.audit_semantic_library("rtsp", root=tmp_path)
    assert audit.rules_total == len(bundle.rules)
    assert audit.candidates_total == len(bundle.candidates)
    assert audit.constraint_none_count == 0
    assert audit.convertible_true_count == 0
    rep = rx.semantic_quality_report("rtsp", audit)
    assert rep.passed
    assert rep.gate_exercised is True
    assert rep.executable_rate == 1.0
    # 格式兼容 ⇒ rule_store 的加载器可读回（且不抛异常）
    rules = rule_store.load_rules(written["rules"])
    cands = rule_store.load_candidates(written["candidates"])
    assert len(rules) == len(bundle.rules)
    assert len(cands) == len(bundle.candidates)


def test_build_hub_rules_only_cli_does_not_flip_d6(tmp_path, monkeypatch):
    """★ `rules_only` **不得**改变 D-6 开关位（全局默认仍为关闭）。"""
    from core.fused.semantic.llm_ensemble import (ENV_KEY, semantic_rules_enabled,
                                         set_semantic_rules_enabled)
    from scripts import build_hub

    monkeypatch.delenv(ENV_KEY, raising=False)
    # ★ 预先用 monkeypatch 设好根目录 ⇒ 用例结束后 pytest 自动还原，
    #   避免 `PROTORAG_SEMANTIC_ROOT` 泄漏到其它用例。
    monkeypatch.setenv(rx.SEMANTIC_ROOT_ENV_KEY, str(tmp_path))
    set_semantic_rules_enabled(None)
    assert semantic_rules_enabled() is False

    rc = build_hub.main([
        "--sources", "rfc", "--protocol", "rtsp", "--rules-only",
        "--semantic-root", str(tmp_path),
    ])
    assert rc == 0
    # D-6 仍然是「关闭」
    assert semantic_rules_enabled() is False
    assert ENV_KEY not in __import__("os").environ
    # 产物落在隔离根下（**不碰**仓库 derived/）
    assert (tmp_path / "rtsp" / "rfc" / "semantic" / rx._RULES_FILE).is_file()
    assert (tmp_path / "rtsp" / "rfc" / "semantic"
            / rx._CANDIDATES_FILE).is_file()
    # **只产**语义规则与候选：facts 目录不存在
    assert not (tmp_path / "rtsp" / "rfc" / "facts").exists()
    set_semantic_rules_enabled(None)


def test_clean_source_dir_preserves_semantic_library(tmp_path):
    """★ facts 清理**不得**删掉语义四库（否则规则库会静默消失）。"""
    from scripts import build_hub
    src = tmp_path / "rtsp" / "rfc"
    (src / "semantic").mkdir(parents=True)
    (src / "semantic" / rx._RULES_FILE).write_text("{}\n", encoding="utf-8")
    (src / "facts").mkdir()
    (src / "facts" / "rfc.jsonl").write_text("{}\n", encoding="utf-8")

    build_hub._clean_source_dir(src)
    assert (src / "semantic" / rx._RULES_FILE).is_file(), \
        "语义四库必须被清理逻辑**保护**"
    assert not (src / "facts" / "rfc.jsonl").exists()


# ===========================================================================
# ⑦ 多协议汇总（分协议 + 合计）
# ===========================================================================

def test_multi_protocol_audit_gives_per_protocol_and_total(tmp_path):
    """多协议审计 ⇒ `semantic_rules_total` 同时给**分协议**与**合计**。"""
    for proto in ("rtsp", "sip"):
        bundle = rx.build_semantic_rules(proto)
        rx.save_semantic_library(proto, bundle.rules, bundle.candidates,
                                 root=tmp_path)
    audit = rx.audit_semantic_library(["rtsp", "sip"], root=tmp_path)
    rep = rx.semantic_quality_report("rtsp", audit)
    totals = rep.semantic_rules_total
    assert totals["rtsp"] >= 1
    assert totals["sip"] >= 1
    assert totals["total"] == totals["rtsp"] + totals["sip"]
    assert rep.semantic_candidates_total >= 2
    assert rep.passed
    assert rep.gate_exercised is True
