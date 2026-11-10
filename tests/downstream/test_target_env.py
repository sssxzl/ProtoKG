# -*- coding: utf-8 -*-
"""tests/fused/test_target_env.py —— target_env 端点/资源归一化的**真实 profile** 回归测试。

★ 为什么单独建这个文件（而不是并进 test_rq4_target_url_normalization.py）：

那 24 条测试**全部用虚构 profile**，导致一个 P0 缺陷漏检：端点归一化对
**真实 SIP profile** 也生效，把 ``sip:bob@127.0.0.1`` 改成 ``sip:127.0.0.1:5060``
（user part 丢失、凭空加端口），破坏已发表 RQ4 SIP 语料的逐字节不变性。

本文件专门用**仓库内真实 profile**（``profiles/<协议>/profile.json``）
锁住这些真实场景 —— 尤其是「SIP URI 必须逐字节不变」这条锁，没有它同类回归会再犯。

覆盖的缺陷（对应 QA-4 报告 `guard/rtsp_url_pollution_verify.md` §9）：
  P0-1  SIP 被端点归一化误改
  P1-1  资源归一化丢弃路径后缀（track / 尾斜杠）
  P1-2  相对路径被整体丢弃
  P1-3  query / fragment 被静默丢弃
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from core.fused.downstream.target_env import (  # noqa: E402
    endpoint_normalization_enabled,
    normalize_seed_resource,
    normalize_target_endpoint,
    target_endpoint,
)

TARGETS = ROOT / "profiles"


def _load(protocol: str) -> dict:
    return json.loads((TARGETS / protocol / "profile.json").read_text(encoding="utf-8"))


# ===========================================================================
# P0-1：SIP 端点归一化必须逐字节不变（★ 真实 profile 的锁）
# ===========================================================================

def test_real_sip_profile_declares_no_rewritable_endpoint():
    """真实 SIP profile 不应声明可改写的**层级式**端点（domain 是逻辑实体标识）。

    SIP 的 default_url 是 ``sip:127.0.0.1:5060``（**无 ``://``**，非层级式 URI），
    其 domain 不决定路由 → 不应被端点归一化改写。
    """
    prof = _load("sip")
    default_url = str(prof.get("default_url") or "")
    assert default_url, "SIP 应有 default_url"
    assert "://" not in default_url, \
        f"SIP default_url 应是非层级式（无 ://），实际 {default_url!r}"


@pytest.mark.parametrize("uri", [
    "sip:bob@127.0.0.1",
    "sip:alice@127.0.0.1",
    "sip:127.0.0.1",
    "sip:127.0.0.1:5060",
    "sips:alice@example.com",
    "sip:alice@example.com;transport=udp",
    "sip:35104723@sip.cybercity.dk",
])
def test_sip_uri_is_not_rewritten(uri):
    """★ P0-1 的锁：真实 SIP profile 下，任何 SIP URI 必须**逐字节不变**。"""
    prof = _load("sip")
    assert normalize_target_endpoint(uri, prof) == uri, \
        f"SIP URI 被改写了: {uri} -> {normalize_target_endpoint(uri, prof)}"


def test_sip_endpoint_normalization_is_disabled():
    """真实 SIP profile 未声明开关 → 端点归一化应缺省关闭。"""
    assert endpoint_normalization_enabled(_load("sip")) is False


def test_smtp_endpoint_normalization_is_disabled():
    """真实 SMTP profile（default_url 为空、无 url_placeholders）→ 缺省关闭。"""
    assert endpoint_normalization_enabled(_load("smtp")) is False


def test_rtsp_endpoint_normalization_is_enabled():
    """★ 真实 RTSP profile 必须显式开启开关（锁住「开关被关掉但没人发现」）。

    这条若失败，意味着 RTSP 的端点归一化被静默关掉了 —— 污染会原样回来
    且全程无报错（QA-4 决定性实验：开关 OFF → 89 次摄像机 URL）。
    """
    prof = _load("rtsp")
    assert endpoint_normalization_enabled(prof) is True, \
        "RTSP 的 seedgen 端点归一化开关必须为 true"


# ===========================================================================
# P1-2：相对路径不丢弃
# ===========================================================================

def test_relative_url_is_not_dropped():
    """裸相对路径（无 scheme、无 '/'）应原样返回，不能变成裸端点。"""
    prof = _load("rtsp")
    assert normalize_target_endpoint("mp3AudioTest", prof) == "mp3AudioTest"
    assert normalize_target_endpoint("track1", prof) == "track1"


# ===========================================================================
# P1-3：query / fragment 保留
# ===========================================================================

def test_query_and_fragment_are_preserved():
    """端点归一化时 query / fragment 必须原样带回。"""
    prof = _load("rtsp")
    out = normalize_target_endpoint("rtsp://10.11.26.98:554/x?a=1#frag", prof)
    assert out == "rtsp://127.0.0.1:8554/x?a=1#frag", out


def test_resource_normalization_preserves_query_fragment():
    """资源归一化时 query / fragment 也必须原样带回。"""
    prof = _load("rtsp")
    out = normalize_seed_resource(
        "rtsp://127.0.0.1:8554/isapi/x?a=1#frag", ["mp3AudioTest"], "mp3AudioTest")
    assert out == "rtsp://127.0.0.1:8554/mp3AudioTest?a=1#frag", out


# ===========================================================================
# P1-1：路径后缀保留（track / 尾斜杠）
# ===========================================================================

def test_track_suffix_is_preserved():
    """SETUP 的 /track{N} 形态必须保留（不塌成单资源 URL）。"""
    out = normalize_seed_resource(
        "rtsp://127.0.0.1:8554/isapi/x/trackID=1", ["mp3AudioTest"], "mp3AudioTest")
    assert out == "rtsp://127.0.0.1:8554/mp3AudioTest/track1", out


def test_trailing_slash_is_preserved():
    """PLAY/TEARDOWN 的尾斜杠形态必须保留。"""
    out = normalize_seed_resource(
        "rtsp://127.0.0.1:8554/isapi/x/", ["mp3AudioTest"], "mp3AudioTest")
    assert out == "rtsp://127.0.0.1:8554/mp3AudioTest/", out


def test_plain_resource_no_shape_suffix():
    """无 track / 无尾斜杠的 URL 不改写时原样（幂等），改写时不加多余后缀。"""
    out = normalize_seed_resource(
        "rtsp://127.0.0.1:8554/isapi/x", ["mp3AudioTest"], "mp3AudioTest")
    assert out == "rtsp://127.0.0.1:8554/mp3AudioTest", out


# ===========================================================================
# 幂等性 / 语义边界
# ===========================================================================

def test_already_playable_resource_is_untouched():
    """已可播资源 → 原样返回（幂等，是连续性硬不变式）。"""
    out = normalize_seed_resource(
        "rtsp://127.0.0.1:8554/mp3AudioTest/track1", ["mp3AudioTest"], "matroskaFileTest")
    assert out == "rtsp://127.0.0.1:8554/mp3AudioTest/track1"


def test_fallback_inside_allowed_set():
    """改写时 fallback 必须是 allowed 集合内的资源名（不得引入新的不可播名）。"""
    allowed = ["mp3AudioTest", "matroskaFileTest"]
    out = normalize_seed_resource(
        "rtsp://127.0.0.1:8554/isapi/x/track1", allowed, "mp3AudioTest")
    # 结果资源名必须来自 allowed
    assert "mp3AudioTest" in out
    assert "isapi" not in out


def test_no_fallback_no_rewrite():
    """无 fallback 资源时不改写（不猜）。"""
    out = normalize_seed_resource(
        "rtsp://127.0.0.1:8554/isapi/x", ["mp3AudioTest"], "")
    assert out == "rtsp://127.0.0.1:8554/isapi/x"
