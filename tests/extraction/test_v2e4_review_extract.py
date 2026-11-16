# -*- coding: utf-8 -*-
"""★ V2-E4：★ 队列 B 发放包与 9 份抽取的回归测试。"""
from __future__ import annotations

import collections
import csv
import io
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
     / "M1-Q3-V2-E4队列B审核启动与保留抽取")


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def _jl(p):
    return [json.loads(l) for l in
            pathlib.Path(p).read_text(encoding="utf-8").splitlines() if l.strip()]


# ══ ① 只读证据包 ══
def test_readonly_evidence_pack_has_54_with_context():
    _rows = _jl(D / "V2-E4_队列B只读证据包.jsonl")
    assert len(_rows) == 54
    for _r in _rows:
        assert _r["★ 上下文行"]
        assert _r["★ 证据跨度（行号）"]
        assert _r["rfc_sha256"]
        assert _r["★ 证据原文 sha256"]


def test_readonly_evidence_pack_has_no_model_state():
    _rows = _jl(D / "V2-E4_队列B只读证据包.jsonl")
    for _r in _rows:
        for _k in _r:
            assert "模型状态" not in _k
            assert "V2" not in _k or "★ 章节类型" in _k
            assert "已生成候选" not in _k


def test_readonly_pack_html_exists_and_hash_matches():
    _h = _j(D / "V2-E4_队列B只读证据包哈希.json")
    import hashlib
    assert hashlib.sha256((D / "V2-E4_队列B只读证据包.html").read_bytes()
                          ).hexdigest() == _h["★ 只读证据包 html"]


# ══ ② 9 份抽取：限额与隔离 ══
def test_extract_limits_respected():
    _s = _j(D / "V2-E4_9份抽取运行报告.json")
    assert _s["★ 各限额是否未超"]["★ RFC"] is True
    assert _s["★ 各限额是否未超"]["★ 请求"] is True
    assert _s["★ 各限额是否未超"]["★ token"] is True
    assert _s["★ 各限额是否未超"]["★ 费用"] is True
    assert _s["★ 实际 RFC 文档数"] <= 9
    assert _s["★ token 合计"] <= 120000


def test_h3_candidates_are_shadow_only():
    _rows = _jl(D / "V2-E4_H3新增候选原始.jsonl")
    assert _rows
    for _r in _rows:
        assert "shadow" in str(_r["★ ★ 状态"])
        assert "H3" in str(_r["★ 来源批次"]) if "★ 来源批次" in _r else True
        assert _r["★ source_sha256"]


def test_raw_llm_output_fully_recorded():
    _rows = _jl(D / "V2-E4_H3原始LLM输出.jsonl")
    assert len(_rows) >= 20
    for _r in _rows:
        _it = _r["★ ★ 原始 LLM 输出（★ 全字段）"]
        assert "entity" in _it and "meaning" in _it
        assert _r["★ model"] and _r["★ prompt_digest"]


def test_stage_attribution_present():
    _s = _j(D / "V2-E4_9份抽取运行报告.json")
    _st = _s["★ §四 分阶段字段归因"]
    assert "★ 阶段1：原始 LLM Schema 应产生的字段" in _st
    assert "★ 阶段2：后续结构化派生是否执行" in _st
    assert "★ 阶段3：派生结果是否缺失" in _st
    # ★ 不得用「norm 层不存在的 subject 键」衡量 LLM
    _all = _st["★ 阶段1：实际产生（★ 合计）"]
    assert "normative_subject" in _all
    assert "subject" not in _all


# ══ ③ 候选池冻结清单 ══
def test_pool_freeze_manifest():
    _rows = _jl(D / "V2-E4_候选池独立评估冻结清单.jsonl")
    assert len(_rows) == 23
    _ids = [r["gold_candidate_id"] for r in _rows]
    assert len(set(_ids)) == len(_ids)
    for _r in _rows:
        assert _r["★ 来源批次"].startswith("★ H3")
        assert _r["★ 状态"].startswith("★ shadow")


def test_h1_h2_h3_not_merged():
    """★ ★ H1 / H2 / H3 不得静默合并（★ 冻结清单只含 H3）。"""
    _rows = _jl(D / "V2-E4_候选池独立评估冻结清单.jsonl")
    for _r in _rows:
        assert "H1" not in _r["★ 来源批次"]
        assert "H2" not in _r["★ 来源批次"]


# ══ ④ 回收校验器 ══
def test_recovery_verifier_detects_evidence_tampering():
    """★ 校验器必须能发现证据字段被改。"""
    import importlib.util
    _sp = importlib.util.spec_from_file_location(
        "p72", ROOT / "guard/_out/_n1c_v2/e4/p72_freeze_pool.py")
    _m = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(_m)
    _src = (ROOT / "docs/实施/待办与勘误/M0对账交付"
             / "M1-Q3-V2-E3队列B盲审发放与保留来源预案"
             / "V2-E3_队列B_审核者A_片段级标注表.csv")
    _tmp = ROOT / "guard/_out/_n1c_v2/e4/_tamper_test.csv"
    _rows = list(csv.DictReader(io.StringIO(
        _src.read_text(encoding="utf-8"))))
    _rows[0]["★ 原文（不可编辑）"] = "TAMPERED"
    with _tmp.open("w", newline="", encoding="utf-8") as f:
        _w = csv.DictWriter(f, fieldnames=list(_rows[0].keys()),
                            quoting=csv.QUOTE_ALL, lineterminator="\n")
        _w.writeheader()
        _w.writerows(_rows)
    _ok, _rep = _m.verify_recovered(_tmp, "tamper")
    assert _ok is False
    assert _rep["★ 错误数"] >= 1
    _tmp.unlink()


def test_recovery_verifier_passes_untouched():
    import importlib.util
    _sp = importlib.util.spec_from_file_location(
        "p72b", ROOT / "guard/_out/_n1c_v2/e4/p72_freeze_pool.py")
    _m = importlib.util.module_from_spec(_sp)
    _sp.loader.exec_module(_m)
    _src = (ROOT / "docs/实施/待办与勘误/M0对账交付"
             / "M1-Q3-V2-E3队列B盲审发放与保留来源预案"
             / "V2-E3_队列B_审核者A_片段级标注表.csv")
    _ok, _rep = _m.verify_recovered(_src, "clean")
    assert _ok is True
    assert _rep["★ 错误数"] == 0
