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
import json
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

#: 关键 token 集合 —— 触发 Session **裸值** / Transport 边界
#:
#: ★ 批次 2.5（F7）：Session 候选值的**来源**从 traffic 抓包文件
#:   （``fused_hub/targets/<proto>_request_templates.json``）改为**中枢**
#:   （见 :func:`_hub_session_candidates`）⇒ 组合形式 ``"Session: <值>"`` 的
#:   取值集合**随本次参与源而变** ⇒ 它不再属于「与源集合无关」的部分，
#:   改由 :func:`_required_key_tokens` **按源集合派生**。
#:   ★ 纯 RFC 单源档下，traffic 侧真实抓包值（000022B8 / 107518505 /
#:     7477886380351771441）不再作为候选来源：其中 000022B8 仍以**裸值**形式
#:     留在字典里（来自冻结的基础字典 ``rtsp_base.dict``），但不再有
#:     ``"Session: 000022B8"`` 组合形式。
KEY_TOKENS_CORE = frozenset({
    "000022B8",                # 触发 Session 裸值（基础字典自带 ⇒ 与源集合无关）
    "interleaved=0-1",         # Transport 边界（profile 下沉 ⇒ 与源集合无关）
    "client_port=50000-50001",  # Transport 边界（profile 下沉 ⇒ 与源集合无关）
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


def _hub_session_candidates(bundle: dict) -> list[str]:
    """中枢本次参与源给出的 Session 取值（= 定向字典的 Session 候选来源）。

    ★ 批次 2.5（F7）：Session 候选值改由**中枢**给出 ⇒ 这里按中枢的
      ``headers.Session.source_values`` × ``available_sources`` **独立重算**
      （不调用生产函数 ``extract_session_candidates`` ⇒ 断言不自证），
      供「字典里的 Session 值来自中枢」这条契约使用。
    """
    hdr = (bundle.get("headers") or {}).get("Session") or {}
    src_values = hdr.get("source_values") or {}
    available = {str(s).lower() for s in (bundle.get("available_sources") or [])}
    out: set = set()
    for src, vals in (src_values or {}).items():
        if str(src).lower() in available:
            out.update(str(v) for v in (vals or []))
    return sorted(out)


def _traffic_capture_session_values(protocol: str = "rtsp") -> list[str]:
    """traffic 侧真实抓包产物里的 Session 取值（= F7 **之前**的候选来源）。

    用于反向断言：这些值**不得**再以 ``Session: <值>`` 组合形式进入字典。
    """
    path = ROOT / "fused_hub" / "targets" / f"{protocol}_request_templates.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    out: set = set()
    for info in (data.get("methods") or {}).values():
        for v in ((info or {}).get("examples") or {}).get("Session") or []:
            out.add(str(v))
    return sorted(out)


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


def _required_key_tokens(bundle: dict, protocol: str = "rtsp") -> frozenset:
    """本次**应**出现在字典里的关键 token 集合（按源集合分流）。

    ★ 批次 2.5（F7）：``Session: <值>`` 组合形式的 Session 候选改**从中枢**取
      ⇒ 必含组合形式随中枢候选集变化（不再恒为 traffic 抓包路径的固定 3 个）。
    ★ 批次 2.5（F3）：``track1/track2`` 由**会话语义**（url_template）派生 ⇒
      仅在 expert_note 参与本次构建时才出现在字典里。
    """
    toks = set(KEY_TOKENS_CORE)
    toks |= {f"Session: {s}" for s in _hub_session_candidates(bundle)}
    if _session_semantics_available(protocol):
        toks |= KEY_TOKENS_SESSION
    return frozenset(toks)


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
    ★ 批次 2.5（F7）：Session 组合形式的关键 token 由**中枢**给出 ⇒ 按源集合
      分流（必含集合随本次参与源变化，不再是写死的 "Session: 000022B8"）。
    """
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    assert _required_key_tokens(bundle) <= toks


def test_targeted_dict_contains_session_candidates(bundle, resources):
    """★ 批次 2.5（F7）后：Session 候选**来源改为中枢**（不再直读 traffic 抓包文件）。

    ★ F7 之前：候选值来自 ``fused_hub/targets/<proto>_request_templates.json``
      （traffic 侧的真实抓包产物）⇒ 纯 RFC 单源实验也会混进外网抓包 Session 值。
    ★ F7 之后：候选值来自**中枢**（``headers.Session.source_values``
      × ``available_sources``）⇒ 候选集合随本次参与源而变。

    ⇒ 本断言按**新来源**校验（不调用生产函数自证 ⇒ 用独立重算的
      :func:`_hub_session_candidates` 作期望值）：
      ① 中枢给出的每个 Session 取值 ⇒ **裸值**与 ``"Session: <值>"`` 组合形式
         都必须出现在字典里；
      ② 字典里的 ``"Session: <值>"`` 组合形式集合 **==** 中枢取值集合
         （不多不少 ⇒ 字典不掺入字典外来源的组合形式）；
      ③ traffic 抓包侧**独有**的取值不得再以组合形式进入字典
         （裸值 ``000022B8`` 仍可能来自冻结的基础字典 ``rtsp_base.dict``
         ⇒ 只禁组合形式，不禁裸值）。
    """
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources))
    hub = _hub_session_candidates(bundle)
    assert hub, "中枢本次参与源应给出 Session 取值"

    # ① 中枢给出的每个取值 ⇒ 裸值 + 组合形式都在字典里
    for s in hub:
        assert s in toks, f"中枢 Session 取值未进字典（裸值）: {s!r}"
        assert f"Session: {s}" in toks, f"中枢 Session 取值未进字典（组合）: {s!r}"

    # ② 字典里的 Session 组合形式集合 == 中枢取值集合
    combos = {t[len("Session: "):] for t in toks if t.startswith("Session: ")}
    assert combos == set(hub), (
        "字典里的 Session 组合形式应恰为中枢取值集合；"
        f"多出={sorted(combos - set(hub))} 缺少={sorted(set(hub) - combos)}")

    # ③ traffic 抓包侧独有的取值不得再以组合形式进入字典
    traffic_only = sorted(set(_traffic_capture_session_values("rtsp")) - set(hub))
    assert traffic_only, "traffic 抓包值应与中枢取值有差异（否则本断言恒真）"
    for s in traffic_only:
        assert f"Session: {s}" not in toks, (
            f"traffic 抓包取值不应再作为 Session 候选进入字典: {s!r}")

    # ④ 生产实现与独立重算一致（生产函数不应自相矛盾）
    assert extract_session_candidates("rtsp", bundle) == hub


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
    ⇒ 纯 RFC 单源档：36（批次 2.5 F7 后：Session 候选改走中枢 ⇒ 30→36）；
      含 expert_note 的多源档：38（+track1/track2）。
    """
    toks = _tokens(generate_targeted_dict(bundle, protocol="rtsp",
                                           resources=resources, compact=True))
    if _session_semantics_available("rtsp"):
        assert len(toks) == 38  # 36 + track1/track2（expert_note 档）
    else:
        assert len(toks) == 36  # 批次 2.5 F7 后为 36（Session 候选走中枢：30→36）


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
    assert _required_key_tokens(bundle) <= toks


def test_compact_key_density_higher(bundle, resources):
    """C′ 的关键 token 密度显著高于完整定向档（稀释风险对冲的前提）。

    ★ 批次 2.5（F3）：分子（命中关键 token 数）与分母（token 总数）都随
      会话语义是否入中枢而变 ⇒ 阈值**按源集合分流**。
      · 纯 RFC 单源档：4 / 30 ≈ 0.133（批次 2.5 重标定后为 0.133，旧值 0.18）
      · 含 expert_note 多源档：6 / 32 = 0.188（旧值 0.18）
    """
    required = _required_key_tokens(bundle)
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
        assert d_cmp >= 0.13  # 批次 2.5 F7 后为 0.333（Session 候选走中枢：0.133→0.333）


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
