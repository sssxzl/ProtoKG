# -*- coding: utf-8 -*-
"""V2-E4-R20 回归测试：FTP 独立验证预注册与预算核验。

覆盖：独立性审计通过、输入冻结清单、配对预注册、盲审方案、预算费率与硬停止、
      执行前门禁未通过项、历史冻结件未改、生产隔离与零 LLM。
"""
from __future__ import annotations

import hashlib
import json
import pathlib

import openpyxl
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUTD = ROOT / "guard/_out/_n1c_v2/r20"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R20_FTP独立验证预注册与预算核验")
V2GATE = (ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-N2-B0-V2知识类型闸门/scripts/v2_knowledge_gate.py")
V2NEXT = ROOT / "guard/_out/_n1c_v2/r16/v2_knowledge_gate_next.py"

AUD = json.loads((OUTD / "r20_audit.json").read_text(encoding="utf-8"))
BUD = json.loads((OUTD / "r20_budget.json").read_text(encoding="utf-8"))
FRZ = json.loads((DELIV / "R20_RFC3659输入与证据冻结清单.json")
                 .read_text(encoding="utf-8"))


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


# ===== 独立性审计 =====
def test_independence_audit_passed():
    _t = (DELIV / "R20_FTP独立性审计报告.md").read_text(encoding="utf-8")
    assert "独立测试身份成立" in _t
    assert "从未进入抽取流程" in _t
    assert "索引清单条目" in _t


def test_audit_evidence_structural():
    _t = (DELIV / "R20_FTP独立性审计报告.md").read_text(encoding="utf-8")
    assert "无 ftp 目录" in _t
    assert "lib_rfc_by_protocol" in _t


def test_audit_scanned_broad_enough():
    assert AUD["scanned_files"] > 500
    _dev = {a["开发环节"]: a["★ 是否出现 3659/959/FTP"]
            for a in AUD["dev_audit"]}
    for _k in ("R14 评估", "R16 影子", "R17 定版", "R4A 盲审包",
               "R7 预注册", "R8 补录", "R13 门禁"):
        assert _dev[_k] is False, _k


# ===== 输入冻结清单 =====
def test_input_freeze_manifest():
    assert FRZ["★ 主评估文档"]["rfc_number"] == "3659"
    assert FRZ["★ 主评估文档"]["source_url"].endswith("rfc3659.txt")
    assert FRZ["★ 背景参考文档"]["rfc_number"] == "959"
    assert "不纳入主评分分母" in FRZ["★ 背景参考文档"]["★ 使用边界"]
    assert "不得根据预览到的模型输出" in FRZ["★ 适用与排除规则"]["★ 片段选择规则"]
    assert "DNS" in FRZ["★ 后续跨表示协议候选"]
    assert "本轮不执行" in FRZ["★ 后续跨表示协议候选"]


# ===== 配对预注册 =====
def test_prereg_paired_method():
    _t = (DELIV / "R20_V2与V2next配对评估预注册.md").read_text(encoding="utf-8")
    assert "同一份" in _t
    assert "不得" in _t and "单独优化候选抽取" in _t
    assert "预测全部相同" in _t


def test_prereg_nine_metrics():
    _t = (DELIV / "R20_V2与V2next配对评估预注册.md").read_text(encoding="utf-8")
    for _k in ("knowledge_kind 准确率与混淆矩阵", "eligibility 准确率",
               "target_route 准确率", "三维度同时正确的候选比例",
               "逐候选配对变化", "修复数量、由对变错数量与净变化",
               "mixed_or_uncertain 的真实分布", "完整样本分母",
               "统计不确定性"):
        assert _k in _t, _k


def test_prereg_discloses_correlation():
    _t = (DELIV / "R20_V2与V2next配对评估预注册.md").read_text(encoding="utf-8")
    assert "确定性映射" in _t
    assert "不是两次独立验证" in _t
    assert "不等于" in _t and "召回率" in _t


# ===== 盲审方案 =====
def test_blind_review_isolation():
    _t = (DELIV / "R20_独立人工Gold盲审方案.md").read_text(encoding="utf-8")
    assert "不得" in _t and "查看机器预测" in _t
    assert "D、C、F" in _t
    assert "降级为开发集" in _t


def test_two_denominators_separated():
    _t = (DELIV / "R20_独立人工Gold盲审方案.md").read_text(encoding="utf-8")
    assert "候选级分类评价" in _t
    assert "原子知识召回评价" in _t
    assert "不得混用" in _t


# ===== 预算 =====
def test_budget_rates_match_project():
    assert BUD["rates"]["input_per_1m"] == 0.15
    assert BUD["rates"]["output_per_1m"] == 0.60


def test_budget_rate_recalc_matches_measured():
    """★ 用项目费率复算 R3 ⇒ 与实测 1.000x。"""
    _b = BUD["baseline"]
    _calc = (_b["input_tokens"] * 0.15 + _b["output_tokens"] * 0.60) / 1e6
    assert abs(_calc - _b["cost_usd"]) < 1e-5, (_calc, _b["cost_usd"])


def test_budget_under_cap():
    assert BUD["normal_cost"] < BUD["budget_cap"]
    assert BUD["worst_cost"] < BUD["budget_cap"]
    assert BUD["pilot_worst"] < BUD["pilot_cap"]
    assert BUD["budget_cap"] == 5.00
    assert BUD["pilot_cap"] == 1.00


def test_budget_report_lists_required_items():
    _wb = openpyxl.load_workbook(DELIV / "R20_LLM请求与token费用估算.xlsx")
    _text = ""
    for _s in _wb.sheetnames:
        _ws = _wb[_s]
        for _row in _ws.iter_rows(values_only=True):
            for _v in _row:
                if _v is not None:
                    _text += str(_v) + " "
    _wb.close()
    for _k in ("API 提供商", "模型 ID", "input 费率", "output 费率",
               "计划处理块数", "请求批数", "预计 input token",
               "预计 output token", "最大重试次数", "最坏情况费用",
               "正常费用", "缓存使用", "缓存失效规则", "来源版本检查",
               "硬停止"):
        assert _k in _text, _k


def test_hard_stop_and_no_scope_shrink():
    _t = (DELIV / "R20_运行事件持久化与预算硬停止检查.md").read_text(
        encoding="utf-8")
    assert "不得自动切换模型或缩减评估范围" in _t
    assert "每批调用前执行" in _t
    assert "cache_hit" in _t and "local_replay" in _t
    assert "LLMDiagnostics.flush()" in _t
    assert "unavailable" in _t


# ===== 执行前门禁 =====
def test_execution_gate_has_open_items():
    _t = (DELIV / "R20_执行前门禁与版本哈希报告.md").read_text(encoding="utf-8")
    assert "未通过 4 项" in _t
    assert "当前不可提交正式执行申请" in _t
    assert "不等于" in _t and "已批准实际调用" in _t


# ===== 冻结件未改 =====
def test_frozen_artifacts_unchanged():
    assert _sha(V2GATE) == (
        "81566fb71905e313bed67660e5d5ff788f3fbad46ccb145286e98457bd185047")
    assert _sha(V2NEXT) == (
        "cc2a9b822e8f3f0c7a457296bb3efee85de2f89a8c4fe886cac05d1a4aedf22f")
    assert _sha(ROOT / "docs/实施/待办与勘误/M0对账交付"
                / "M1-Q3-V2-E4-R13_Gold分层冻结与剩余原子复核"
                / "R13_候选级评估冻结基线.jsonl") == (
        "36742b0955339edb4a1d08ef936bf1270e5c70262ea37180f5a11ff9cc960f0b")
    assert _sha(ROOT / "docs/实施/待办与勘误/M0对账交付"
                / "M1-Q3-V2-E4-R19_原子Goldv5冻结与独立验证门禁准备"
                / "R19_原子Gold_v5冻结基线.jsonl") == (
        "6ba3ae961ab564908aa8879d81ac77788931376c256e039027327022ff2b110c")


def test_r14_and_r3_untouched():
    assert _sha(ROOT / "guard/_out/_n1c_v2/r3/pool/R3_跨协议候选冻结基线.jsonl") \
        == ("694836b4bf497a083125b2d8b89c81a2854356f5967797359ec9af097f1a3b4a")
    for _n in ("R14_候选级分类评估结果.xlsx",
               "R14_评估执行日志与环境哈希.md"):
        assert (ROOT / "docs/实施/待办与勘误/M0对账交付"
                / "M1-Q3-V2-E4-R14_候选级分类一次性评估" / _n).is_file(), _n


# ===== 交付文件 =====
def test_deliverables_exist():
    for _n in ("R20_FTP独立性审计报告.md",
               "R20_RFC3659输入与证据冻结清单.json",
               "R20_V2与V2next配对评估预注册.md",
               "R20_独立人工Gold盲审方案.md",
               "R20_LLM请求与token费用估算.xlsx",
               "R20_运行事件持久化与预算硬停止检查.md",
               "R20_执行前门禁与版本哈希报告.md"):
        _p = DELIV / _n
        assert _p.is_file(), _n
        assert _p.stat().st_size > 0, _n


# ===== 生产隔离 =====
def test_production_unchanged():
    import ast
    _b = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                     / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                     / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _b["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert _sha(_p) == _h[_k], _k
    _src = (ROOT / "core/fused/extraction/prose_semantics.py").read_text(
        encoding="utf-8")
    for _n in ast.walk(ast.parse(_src)):
        if isinstance(_n, ast.Assign) and getattr(_n.targets[0], "id", "") \
                == "_PROMPT":
            assert hashlib.sha256(
                _n.value.value.encode()).hexdigest()[:16] \
                == "d97fbe611ac9aa61"
            break
    _m = json.loads((ROOT / "core/fused/hub/knowledge_slots.json")
                    .read_text(encoding="utf-8"))
    assert len(_m["aspect_map"]) >= 21


def test_no_llm_calls_in_r20():
    for _f in sorted((ROOT / "guard/_out/_n1c_v2/r20").glob("*.py")):
        _t = _f.read_text(encoding="utf-8")
        assert "DeepSeekClient(" not in _t, _f.name
        assert "client.chat_json(" not in _t, _f.name
        assert "requests.post" not in _t, _f.name
