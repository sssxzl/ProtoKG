# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_dict.py —— 定向变异字典（C 组）的行为契约。

固化 RQ3 的关键不变式：

  · ★ **C 组字典必须是基础字典的严格超集** —— 这是 D→C 保持单变量的前提。
    （若 C 相对 D 同时「增」和「删」，D→C 就不再是单变量。）
  · 定向字典覆盖全部漏洞触发维度（Session 触发值 / track / Transport 边界）
  · 精简档（C′ 预案）token 数更少但关键 token 密度更高
  · `generate_protocol_dict` 的既有行为**逐字节不变**（102 token）
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.fused.downstream.rag_seedgen import (  # noqa: E402
    load_fact_views, assemble_bundle,
)
from core.fused.downstream.boundary_probe import (  # noqa: E402
    generate_protocol_dict, generate_targeted_dict, extract_session_candidates,
    load_base_dict_tokens, _is_dict_token,
)
from scripts.seedgen import _load_profile, _load_resources  # noqa: E402

#: 镜像内基础字典的仓库内副本
BASE_DICT = ROOT / "fused_hub" / "targets" / "rtsp" / "rtsp_base.dict"

#: 镜像内基础字典 MD5（实测）
BASE_DICT_MD5 = "464351f88db6c3f0bdac0de01859316b"

#: 关键 token 集合（触发 Session 值 / track / Transport 边界）
KEY_TOKENS = frozenset({
    "track1", "track2", "000022B8", "Session: 000022B8",
    "interleaved=0-1", "client_port=50000-50001",
})


@pytest.fixture(scope="module")
def bundle():
    """知识中枢 bundle（RTSP）。"""
    return assemble_bundle(load_fact_views("rtsp"))


@pytest.fixture(scope="module")
def resources():
    """资源实例清单。"""
    return _load_resources(_load_profile("rtsp"), "rtsp")


@pytest.fixture(scope="module")
def base_tokens():
    """基础字典 token 集合。"""
    return load_base_dict_tokens("rtsp")


def _tokens(text: str) -> set:
    """字典文本 → token 集合。"""
    return {ln.strip().strip('"') for ln in text.splitlines() if ln.strip()}


# ===========================================================================
# 基础字典
# ===========================================================================

def test_base_dict_file_matches_image_md5():
    """仓库内基础字典副本与镜像内 rtsp.dict 逐字节相同。"""
    assert BASE_DICT.exists()
    assert hashlib.md5(BASE_DICT.read_bytes()).hexdigest() == BASE_DICT_MD5


def test_base_dict_has_24_tokens(base_tokens):
    """基础字典 24 token。"""
    assert len(base_tokens) == 24


def test_base_dict_contains_trigger_session(base_tokens):
    """基础字典已含触发 Session 值 000022B8（这是「减法」结论的关键）。"""
    assert "000022B8" in base_tokens


# ===========================================================================
# generate_protocol_dict 的向后兼容
# ===========================================================================

def test_protocol_dict_unchanged_102(bundle, resources):
    """★ 既有行为逐字节不变：generate_protocol_dict 仍是 102 token。"""
    text = generate_protocol_dict(bundle, protocol="rtsp", resources=resources)
    toks = _tokens(text)
    assert len(toks) == 102


def test_protocol_dict_is_not_superset_of_base(bundle, resources, base_tokens):
    """★ 现状：102 token 字典**缺**基础字典的若干 token（是减法，非超集）。

    这正是必须新增 generate_targeted_dict 的原因。
    """
    toks = _tokens(generate_protocol_dict(bundle, protocol="rtsp",
                                          resources=resources))
    missing = base_tokens - toks
    assert missing, "102 token 字典应缺基础字典的部分 token"
    assert "000022B8" in missing


# ===========================================================================
# generate_targeted_dict 的核心契约
# ===========================================================================

def test_targeted_dict_is_strict_superset_of_base(bundle, resources,
                                                  base_tokens):
    """★ C 组定向字典必须是基础字典的**严格超集**（D→C 单变量的前提）。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    assert base_tokens < toks, "定向字典必须是基础字典的严格超集"
    assert base_tokens <= toks, "定向字典不能丢失基础字典的任何 token"
    assert len(toks) > len(base_tokens)


def test_targeted_dict_token_count(bundle, resources):
    """定向字典 123 token（与 DICT_FROZEN.json 冻结值一致）。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    assert len(toks) == 123


def test_targeted_dict_contains_all_key_tokens(bundle, resources):
    """定向字典覆盖全部 6 个关键触发 token。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    assert KEY_TOKENS <= toks


def test_targeted_dict_contains_session_candidates(bundle, resources):
    """定向字典含从真实流量模板抽取的 Session 候选（非硬编码）。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    for s in extract_session_candidates("rtsp"):
        assert s in toks
        assert f"Session: {s}" in toks


def test_targeted_dict_all_tokens_pass_filter(bundle, resources):
    """定向字典的每个 token 都通过 _is_dict_token（无中文/括号/占位符污染）。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    for t in toks:
        assert _is_dict_token(t), f"token 未通过过滤: {t!r}"


def test_targeted_dict_sorted_and_quoted(bundle, resources):
    """输出格式：每行 "token"、字典序、末尾换行。"""
    text = generate_targeted_dict(bundle, protocol="rtsp",
                                   resources=resources)
    lines = text.splitlines()
    assert all(ln.startswith('"') and ln.endswith('"') for ln in lines)
    assert lines == sorted(lines)
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_targeted_dict_without_base_tokens_is_smaller(bundle, resources,
                                                      base_tokens):
    """base_tokens=None 时不并入基础 token（构造逻辑可控）。"""
    full = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    without = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                              resources=resources,
                                              base_tokens=set()))
    assert len(without) < len(full)
    assert not (base_tokens & without) or base_tokens - without


def test_targeted_dict_without_trigger_fields(bundle, resources):
    """include_trigger_fields=False 时不并入漏洞触发字段名。"""
    full = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    without = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                              resources=resources,
                                              include_trigger_fields=False))
    assert len(without) < len(full)
    assert "Digest" in full and "Digest" not in without


# ===========================================================================
# C′ 精简档
# ===========================================================================

def test_compact_dict_token_count(bundle, resources):
    """C′ 精简档 32 token。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources, compact=True))
    assert len(toks) == 32


def test_compact_dict_is_superset_of_base(bundle, resources, base_tokens):
    """C′ 也必须是基础字典的严格超集。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources, compact=True))
    assert base_tokens < toks


def test_compact_dict_keeps_all_key_tokens(bundle, resources):
    """C′ 保留全部关键 token（关键密度更高 = 0.188 vs 0.049）。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources, compact=True))
    assert KEY_TOKENS <= toks


def test_compact_key_density_higher(bundle, resources):
    """C′ 的关键 token 密度显著高于完整定向档（稀释风险对冲的前提）。"""
    full = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    compact = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                              resources=resources,
                                              compact=True))
    d_full = len(KEY_TOKENS & full) / len(full)
    d_cmp = len(KEY_TOKENS & compact) / len(compact)
    assert d_cmp > d_full
    assert d_cmp >= 0.18


# ===========================================================================
# 协议无关性
# ===========================================================================

def test_transport_tokens_come_from_profile():
    """★ 协议特有串下沉到 profile（方案 α），不硬编码在 boundary_probe.py。"""
    profile = _load_profile("rtsp")
    bp = profile.get("boundary_probe") or {}
    toks = bp.get("transport_tokens") or []
    assert toks, "profile 应声明 boundary_probe.transport_tokens"
    assert any("interleaved=" in t for t in toks)


def test_load_base_dict_tokens_missing_file_returns_empty():
    """基础字典文件缺失时返回空集合（调用方须显式报错，不静默降级）。"""
    assert load_base_dict_tokens("no_such_protocol") == set()
