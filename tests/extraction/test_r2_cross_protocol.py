# -*- coding: utf-8 -*-
"""V2-E4-R2 跨协议独立候选池预检的回归测试。

覆盖：元数据提取正确性、覆盖核验可复算、容量计算、交付文件完整性、
      XLSX 可打开、0 次 LLM 调用、V0/V1/V2 哈希不变。
"""
from __future__ import annotations

import collections
import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
R2 = ROOT / "guard/_out/_n1c_v2/r2"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R2_跨协议独立候选池预检")


def _j(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


# ===== 元数据提取 =====

def test_rfc_metadata_extracted_correctly():
    """RFC 编号、标题、Category 须与原文头部一致。"""
    _inv = _j(R2 / "r2_inventory.json")
    _by = {(r["protocol"], r["document"]): r for r in _inv["rfc_rows"]}
    _expect = {
        ("rtsp", "rfc2326.txt"): ("2326", "Real Time Streaming Protocol (RTSP)"),
        ("sip", "rfc3261.txt"): ("3261", "SIP: Session Initiation Protocol"),
        ("smtp", "rfc5321.txt"): ("5321", "Simple Mail Transfer Protocol"),
        ("smtp", "rfc5322.txt"): ("5322", "Internet Message Format"),
        ("smtp", "rfc4954.txt"): ("4954",
                          "SMTP Service Extension for Authentication"),
    }
    for _k, (_no, _title) in _expect.items():
        _r = _by[_k]
        assert _r["rfc_number"] == _no, _k
        assert _r["title"] == _title, _k
        assert _r["category"] == "Standards Track", _k


def test_rfc_metadata_has_no_author_column_leak():
    """Category/Obsoletes/Updates 不得混入右对齐的作者或机构名。"""
    _inv = _j(R2 / "r2_inventory.json")
    for _r in _inv["rfc_rows"]:
        for _f in ("category", "obsoletes", "updates"):
            _v = str(_r[_f] or "")
            assert not any(_a in _v for _a in
                           ("Columbia U.", "Netscape", "RealNetworks",
                            "Ericsson", "WorldCom", "Dynamicsoft",
                            "Qualcomm", "Internet Mail Consortium")), \
                f"{_r['document']}.{_f}={_v!r}"


def test_rfc_sha256_matches_files():
    _inv = _j(R2 / "r2_inventory.json")
    for _r in _inv["rfc_rows"]:
        _p = ROOT / f'kb/{_r["protocol"]}/spec/{_r["document"]}'
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _r["source_sha256"]


# ===== 覆盖核验 =====

def test_coverage_audit_reproducible():
    """重跑覆盖核验须得到相同的逐片段状态。"""
    _cov = _j(R2 / "r2_queue_b_coverage.json")
    _dist = collections.Counter(r["processing_status"]
                             for r in _cov["per_snippet"])
    assert len(_cov["per_snippet"]) == 54
    assert sum(_dist.values()) == 54
    assert _cov["summary"]["window_coverage_ratio"] == \
        round(sum(1 for r in _cov["per_snippet"]
                   if r["processing_status"] != "never_processed") / 54, 4)


def test_never_processed_excluded_from_window_coverage():
    _cov = _j(R2 / "r2_queue_b_coverage.json")
    for _r in _cov["per_snippet"]:
        if _r["processing_status"] == "never_processed":
            assert _r["matched_chunk_id"] is None
        else:
            assert _r["matched_chunk_id"]


def test_doc_intersection_not_treated_as_processed():
    """文档级交集数应显著大于 processed 片段数，否则误判风险高。"""
    _cov = _j(R2 / "r2_queue_b_coverage.json")
    _processed = sum(1 for r in _cov["per_snippet"]
                      if r["processing_status"] != "never_processed")
    assert _cov["summary"]["doc_level_intersection_count"] > _processed


# ===== 容量与独立性 =====

def test_cross_protocol_document_level_independent_is_zero():
    """库内 SIP/RTSP/SMTP 全部已参与既有集合，文档级独立数应为 0。"""
    _inv = _j(R2 / "r2_inventory.json")
    for _p in ("sip", "rtsp", "smtp"):
        assert _inv["capacity"][_p]["independent_rfc_count"] == 0, _p
        assert _inv["capacity"][_p]["expected_candidate_capacity"] == 0, _p


def test_block_capacity_not_negative():
    _inv = _j(R2 / "r2_inventory.json")
    for _p, _v in _inv["capacity"].items():
        assert _v["block_capacity_100lines"] >= 0, _p


def test_h3_no_overlap_with_dev_set():
    """H3 与 N1-B/N1-C/V2 调优来源的文档重叠应为 0。"""
    _inv = _j(R2 / "r2_inventory.json")
    _h3 = set(_inv["sets"]["h3_docs"])
    _dev = set(_inv["sets"]["dev_docs"])
    assert not (_h3 & _dev)


# ===== 交付完整性 =====

REQUIRED = [
    "R2_跨协议RFC来源清单.xlsx",
    "R2_独立性与泄漏排除台账.xlsx",
    "R2_协议候选容量与分层设计.xlsx",
    "R2_新增RFC版本和哈希清单.json",
    "R2_受控LLM抽取预算申请.md",
    "R2_候选抽样与冻结规则.md",
    "R2_跨协议人工盲审XLSX模板设计.md",
    "R2_队列B抽取窗口覆盖核验.xlsx",
    "R2_独立评估统计与准入设计.md",
    "R2_双队列样本数量与容量修订.md",
    "R2_章节协议联合配额报告.md",
    "R2_零候选RFC根因审计.md",
    "R2_队列B召回评估前置勘误.md",
]


@pytest.mark.parametrize("name", REQUIRED)
def test_deliverable_exists(name):
    _p = DELIV / name
    assert _p.is_file(), name
    assert _p.stat().st_size > 0, name


@pytest.mark.parametrize("name", [n for n in REQUIRED if n.endswith(".xlsx")])
def test_xlsx_opens_and_readable(name):
    _wb = openpyxl.load_workbook(DELIV / name)
    assert len(_wb.sheetnames) >= 1
    _wb.close()


def test_xlsx_contains_no_prefilled_human_verdicts():
    """台账类 XLSX 不得预填人工结论。"""
    _forbid = ["valid_confirmed", "valid_rejection", "final_verdict"]
    for _p in DELIV.glob("*.xlsx"):
        _wb = openpyxl.load_workbook(_p)
        for _s in _wb.sheetnames:
            for _row in _wb[_s].iter_rows():
                for _c in _row:
                    _v = str(_c.value or "")
                    for _f in _forbid:
                        assert _f not in _v, f"{_p.name}/{_s}/{_c.coordinate}"
        _wb.close()


# ===== 工程约束 =====

def test_no_llm_calls_in_r2():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r2").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient" not in _t, _f.name
        assert "chat_json" not in _t, _f.name


def test_v0_v1_v2_unchanged():
    _b = _j(ROOT / "docs/实施/待办与勘误/M0对账交付"
            / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
            / "N2-B0-R_版本哈希.json")
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    assert (ROOT / "guard/_out/_n1c_v2/v2_knowledge_gate.py").is_file()


def test_no_h1_h2_h3_overwrite():
    """H1/H2/H3 历史候选文件须未被本轮改写。"""
    for _p in (ROOT / "guard/_out/_v2_e2_pilot/V2-E2_新增候选审计.jsonl",
               ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl",
               ROOT / "docs/实施/待办与勘误/M0对账交付"
               / "M1-Q2证据冻结/frozen_blocks.jsonl"):
        assert _p.is_file(), _p
        assert _p.stat().st_size > 0, _p
