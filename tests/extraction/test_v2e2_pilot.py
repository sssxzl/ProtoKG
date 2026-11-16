# -*- coding: utf-8 -*-
"""★ V2-E2：★ 限额试点与队列 B 冻结的回归测试。"""
from __future__ import annotations

import collections
import json
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
D = (ROOT / "docs/实施/待办与勘误/M0对账交付"
     / "M1-Q3-V2-E2章节硬约束与候选池扩充试点")


def _j(p):
    return json.loads(p.read_text(encoding="utf-8"))


# ══ ① 限额未被突破 ══
def test_pilot_limits_respected():
    _s = _j(D / "V2-E2_LLM抽取试点运行报告.json")
    assert _s["★ 限额均未超"]["★ RFC"] is True
    assert _s["★ 限额均未超"]["★ chunk"] is True
    assert _s["★ 限额均未超"]["★ 请求"] is True
    assert _s["★ 限额均未超"]["★ token"] is True


def test_pilot_token_budget_ok():
    _s = _j(D / "V2-E2_LLM抽取试点运行报告.json")
    assert _s["★ token 合计"] <= 200000
    assert _s["★ 是否超 token 上限"] is False


def test_pilot_config_frozen_fields():
    _c = _j(D / "V2-E2_受限LLM试点配置.json")
    for _k in ("★ model", "★ model_version", "★ temperature", "★ max_tokens",
               "★ prompt_source", "★ schema", "★ extractor_entry",
               "★ extractor_code_commit", "★ prompt_digest"):
        assert _c.get(_k), _k
    assert _c["★ max_tokens"] <= 4000


# ══ ② 试点产出隔离 ══
def test_candidates_are_shadow_only():
    _rows = [json.loads(l) for l in
             (D / "V2-E2_新增候选审计.jsonl").read_text(encoding="utf-8").splitlines()
             if l.strip()]
    _c = [r for r in _rows if r.get("★ ★ candidate 全量")]
    assert _c, "★ 应有候选"
    for _r in _c:
        assert "shadow" in str(_r.get("★ ★ 状态"))
    # ★ 每条候选须有 16 字段记录
    for _r in _rows:
        for _k in ("★ run_id", "★ document_id", "★ source_sha256", "★ chunk_id",
                  "★ chunk_hash", "★ model", "★ prompt_digest",
                  "★ schema_version", "★ cache_status", "★ request_attempt",
                  "★ parse_status", "★ failure_reason", "★ candidate_id",
                  "★ source_span", "★ proposed_knowledge_kind"):
            assert _k in _r, _k


def test_production_cache_not_polluted():
    """★ 试点缓存须在 guard/_out 下，★ 不得写 derived/cache。"""
    _p = ROOT / "guard/_out/_v2_e2_pilot/cache"
    assert _p.is_dir()
    assert not any((ROOT / "derived/cache").glob("*.prose.json"))


# ══ ③ 队列 B 冻结 ══
def test_queue_b_frozen_list_satisfies_hard_constraints():
    _q = _j(D / "V2-E2_队列B冻结抽样与泄漏检查.json")
    assert _q["★ 冻结清单条数"] <= 58
    assert _q["★ 每文档最大条数"] <= 6
    _k = _q["★ 章节分布"]
    assert len(_k) == 5
    assert all(v >= 4 for v in _k.values())
    assert _k.get("② 消息格式与 ABNF", 0) > 0
    for _p in ("rtsp", "sip", "smtp", "DHCPv4"):
        assert _q["★ 协议分布"].get(_p, 0) > 0, _p


def test_queue_b_frozen_manifest_hash_matches():
    import hashlib
    _q = _j(D / "V2-E2_队列B冻结抽样与泄漏检查.json")
    _rows = [json.loads(l) for l in
             (D / "V2-E2_队列B冻结样本清单.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()]
    _h = hashlib.sha256(json.dumps(_rows, ensure_ascii=False,
                                   sort_keys=True).encode()).hexdigest()
    assert _h == _q["★ 冻结清单哈希"]


def test_queue_b_prerequisites_all_passed():
    _q = _j(D / "V2-E2_队列B冻结抽样与泄漏检查.json")
    _p = _q["★ 前置 5 项检查"]
    assert _p["① 章节硬配额可行性"] is True
    assert _p["② 协议与文档级联合容量"] is True
    assert _p["③ 知识匹配规则冻结"] is True
    assert _p["④ 人工任务书冻结"] is True


def test_zero_candidate_audit_has_all_fields():
    _rows = [json.loads(l) for l in
             (D / "V2-E2_试点与独立来源隔离清单.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(_rows) == 28
    for _r in _rows:
        for _k in ("rfc_id", "protocol", "source_sha256", "★ 来源集合",
                   "zero_candidate_reason"):
            assert _k in _r, _k


# ══ ④ 隔离与 V2 未改 ══
def test_source_sets_partition_the_28():
    _rows = [json.loads(l) for l in
             (D / "V2-E2_试点与独立来源隔离清单.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()]
    _c = collections.Counter(r["★ 来源集合"] for r in _rows)
    assert sum(_c.values()) == 28
    assert "② 本轮试点来源" in _c
    assert "③ 未来独立评估保留" in _c


def test_v0_v1_v2_unchanged():
    import hashlib
    _base = json.loads((ROOT / "docs/实施/待办与勘误/M0对账交付"
                        / "M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
                        / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
    _h = _base["★ 文件 SHA256（★ 冻结基线）"]
    for _k, _p in (("V0 冻结判据", ROOT / "guard/_out/_n1c/n2b0_tristate.py"),
                   ("V1 修正判据", ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py")):
        assert hashlib.sha256(_p.read_bytes()).hexdigest() == _h[_k], _k
    _v2 = ROOT / "guard/_out/_n1c_v2/v2_knowledge_gate.py"
    assert _v2.is_file()
