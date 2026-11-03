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
    load_fact_views, assemble_bundle, load_source_manifest,
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

#: 关键 token 集合 —— **与源集合无关**的部分（Session 触发值 / Transport 边界）
KEY_TOKENS_CORE = frozenset({
    "000022B8", "Session: 000022B8",
    "interleaved=0-1", "client_port=50000-50001",
})

#: 关键 token 集合 —— 依赖**会话语义**（url_template ⇒ track 编号）的部分
#:
#: ★ 批次 2.5（F3）：会话语义三段（precondition / session_header / url_template）
#:   **不再直读 profile.json**，改为只从中枢 facts 来，且由 ``build_hub``
#:   **只在构建 expert_note 源时**物化 ⇒ 纯 RFC 单源档没有 track1/track2。
KEY_TOKENS_SESSION = frozenset({"track1", "track2"})


def _hub_source_set(protocol: str = "rtsp") -> list[str]:
    """中枢本次参与的源集合（``sources.json`` = 唯一权威）。"""
    doc = load_source_manifest(protocol) or {}
    return [str(s).strip().lower() for s in (doc.get("source_set") or [])]


def _apply_allowed_methods(src_set: list[str]) -> bool:
    """是否启用 ``profile.allowed_methods`` 白名单（与 ``scripts/seedgen.py`` 同判据）。

    ★ 批次 2.5（F6）：白名单是**源码侧**知识 ⇒ 只有 ``source`` 参与本次构建时启用。
    """
    return (not src_set) or ("source" in src_set)


def _session_semantics_available(protocol: str = "rtsp") -> bool:
    """会话语义（precondition / session_header / url_template）是否入中枢。

    ★ 批次 2.5（F3）：三段只在**构建 expert_note 源时**由 ``build_hub`` 物化进中枢。
    """
    return "expert_note" in _hub_source_set(protocol)


def _required_key_tokens(protocol: str = "rtsp") -> frozenset:
    """本次**应**出现在字典里的关键 token 集合（按源集合分流）。"""
    if _session_semantics_available(protocol):
        return KEY_TOKENS_CORE | KEY_TOKENS_SESSION
    return KEY_TOKENS_CORE


@pytest.fixture(scope="module")
def bundle():
    """知识中枢 bundle（RTSP）—— 与 ``scripts/seedgen.py`` 生产口径一致。"""
    src_set = _hub_source_set("rtsp")
    return assemble_bundle(load_fact_views("rtsp"), source_set=src_set or None,
                           apply_allowed_methods=_apply_allowed_methods(src_set))


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
    """定向字典覆盖全部**本次适用**的关键触发 token。

    ★ 批次 2.5（F3）：``track1/track2`` 由**会话语义**（url_template）派生 ⇒
      仅在 expert_note 参与本次构建时才出现在字典里 ⇒ 按源集合分流断言。
    """
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    assert _required_key_tokens() <= toks


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
    """输出格式：每行 "token"、字典序、末尾换行。

    ★ 批次 2.5（协议级 C 档重标定）：定向字典实测 **218** token（旧 123）。

    ★★ 已知 B 类失败（护栏基线已登记 ⇒ **不是**本轮回归）：
      ``generate_targeted_dict`` 对**裸 token** 排序后再逐行加引号，而引号
      （0x22）大于空格（0x20）⇒ 当一个 token 是另一个的前缀时（如
      ``RTSP/1.0`` 与 ``RTSP/1.0 200 OK\\r\\n``），**渲染后的行序不再字典序**
      ⇒ 下方 ``lines == sorted(lines)`` 当前必然失败。
      ⇒ 这是**生产侧**的「排序键与渲染格式不一致」，属生产缺陷
      （修法应改生产代码的排序键），**不在本测试侧放宽断言**
      （放宽成「token 序递增」会把「输出文件本身有序」这个契约悄悄丢掉）。
    """
    text = generate_targeted_dict(bundle, protocol="rtsp",
                                   resources=resources)
    lines = text.splitlines()
    assert all(ln.startswith('"') and ln.endswith('"') for ln in lines)
    assert lines == sorted(lines), (
        "定向字典的行序非字典序（生产侧：按裸 token 排序 ⇒ 前缀 token 的"
        "渲染行序反转）")
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
    """C′ 精简档 token 数 —— **按源集合分流**。

    ★ 批次 2.5（F3）：精简档会并入 ``url_template`` 派生的 track 编号
      （``track1`` / ``track2``），而 ``url_template`` 属会话语义三段
      ⇒ **只在 ``expert_note`` 参与本次中枢构建时**才有这两个 token。
    ⇒ 纯 RFC 单源档：30（批次 2.5 重标定后为 30，旧值 32）；
      含 expert_note 的多源档：32。
    """
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources, compact=True))
    if _session_semantics_available("rtsp"):
        assert len(toks) == 32
    else:
        assert len(toks) == 30  # 批次 2.5 重标定后为 30（旧值 32）


def test_compact_dict_is_superset_of_base(bundle, resources, base_tokens):
    """C′ 也必须是基础字典的严格超集。"""
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources, compact=True))
    assert base_tokens < toks


def test_compact_dict_keeps_all_key_tokens(bundle, resources):
    """C′ 保留全部**本次适用**的关键 token（关键密度更高）。

    ★ 批次 2.5（F3）：``track1`` / ``track2`` 来自会话语义（``url_template``）
      ⇒ 纯 RFC 单源档**不应**要求它们存在，否则断言的是旧口径。
    """
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources, compact=True))
    assert _required_key_tokens() <= toks


def test_compact_key_density_higher(bundle, resources):
    """C′ 的关键 token 密度显著高于完整定向档（稀释风险对冲的前提）。

    ★ 批次 2.5（F3）：分子（命中关键 token 数）与分母（token 总数）都随
      会话语义是否入中枢而变 ⇒ 阈值**按源集合分流**。
      · 纯 RFC 单源档：4 / 30 ≈ 0.133（批次 2.5 重标定后为 0.133，旧值 0.18）
      · 含 expert_note 多源档：6 / 32 = 0.188（旧值 0.18）
    """
    required = _required_key_tokens()
    full = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    compact = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                              resources=resources,
                                              compact=True))
    d_full = len(required & full) / len(full)
    d_cmp = len(required & compact) / len(compact)
    assert d_cmp > d_full
    if _session_semantics_available("rtsp"):
        assert d_cmp >= 0.18
    else:
        assert d_cmp >= 0.13  # 批次 2.5 重标定后为 0.133（旧值 0.18）


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
