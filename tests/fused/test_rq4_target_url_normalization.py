# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_target_url_normalization.py —— 种子 URL 目标侧归一化的回归测试。

背景（缺陷 3）
--------------
`traffic` 源是**混合抓包**：同一份 ``traffic.jsonl`` 里既有 live555 的
``rtsp://127.0.0.1:8554/mp3AudioTest/track1``，也有**别的设备**（某 IP 摄像机
``rtsp://10.11.26.98:554/isapi/streaming/channels/101``）。若种子**原样透传**抓包
里的 Request-URI，就会打向目标环境根本不存在的设备 —— 实测某份语料 37 个种子中
22 个（59.5%）指向该摄像机，且**所有健康度指标都不会红**（静默退化）。

修复分两级（``core/fused/downstream/target_env.py``）：
  · **端点**（协议级，依据 ``profile.default_url``）—— 换成本 profile 描述的服务；
  · **资源段**（环境级，依据目标环境可播清单）—— 换成该种子已分配的可播资源。

本测试锁住三件事：
  1. 污染 URL 被完全归正（端点 + 资源段）；
  2. **幂等性**——已正确的 URL 原样返回（这是连续性硬不变式的保证）；
  3. **协议无关 + profile 驱动**——不硬编码任何协议名/主机名/会话名。
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


# ---------------------------------------------------------------------------
# 夹具：用一份**虚构的** profile（不依赖具体协议/主机/会话名）
# ---------------------------------------------------------------------------
@pytest.fixture()
def profile() -> dict:
    """一份最小的协议 profile：只有 default_url 与占位符。"""
    return {
        "default_url": "rtsp://127.0.0.1:8554/",
        "url_placeholders": {"<server>": "127.0.0.1:8554", "<stream>": "streamA"},
    }


# ---------------------------------------------------------------------------
# 1. 端点归一化
# ---------------------------------------------------------------------------
def test_target_endpoint_reads_default_url(profile):
    assert target_endpoint(profile) == ("rtsp", "127.0.0.1:8554")


def test_target_endpoint_falls_back_to_server_placeholder():
    """default_url 缺失时回落到 url_placeholders['<server>']。"""
    p = {"url_placeholders": {"<server>": "10.0.0.1:9000"}}
    assert target_endpoint(p) == ("", "10.0.0.1:9000")


def test_target_endpoint_absent_returns_empty():
    """profile 未声明目标端点 → ("", "")（= 不做归一化，不猜）。"""
    assert target_endpoint({}) == ("", "")
    assert target_endpoint({"url_placeholders": {}}) == ("", "")


def test_foreign_host_endpoint_is_replaced(profile):
    """★ 缺陷核心：外部设备的端点被换成本 profile 的目标服务。"""
    got = normalize_target_endpoint(
        "rtsp://10.11.26.98:554/isapi/streaming/channels/101", profile)
    assert got == "rtsp://127.0.0.1:8554/isapi/streaming/channels/101"


def test_path_is_preserved_when_only_endpoint_changes(profile):
    """端点归一化**只动端点**，不动路径（资源名归资源归一化管）。"""
    got = normalize_target_endpoint("rtsp://evil.example:1234/a/b/c", profile)
    assert got == "rtsp://127.0.0.1:8554/a/b/c"


def test_already_correct_endpoint_is_untouched(profile):
    """★ 幂等性：已指向目标服务的 URL 原样返回（逐字节不变）。"""
    for url in ("rtsp://127.0.0.1:8554/streamA/track1",
                "rtsp://127.0.0.1:8554/streamA"):
        assert normalize_target_endpoint(url, profile) == url


def test_userinfo_in_netloc_is_dropped(profile):
    """netloc 带 userinfo（user:pass@host）时取 host 部分。"""
    got = normalize_target_endpoint("rtsp://user:pw@10.0.0.9:554/x", profile)
    assert got == "rtsp://127.0.0.1:8554/x"


def test_empty_or_relative_url_untouched(profile):
    """空 URL / 相对 URL 原样返回（不硬造端点）。"""
    assert normalize_target_endpoint("", profile) == ""
    assert normalize_target_endpoint("/just/a/path", profile) == "/just/a/path"


def test_no_target_endpoint_declared_is_noop():
    """profile 未声明目标端点 → 不做任何改写（不猜端点）。"""
    url = "rtsp://10.0.0.9:554/x"
    assert normalize_target_endpoint(url, {}) == url


# ---------------------------------------------------------------------------
# 2. 资源段归一化
# ---------------------------------------------------------------------------
def test_unplayable_resource_is_replaced(profile):
    """★ 缺陷核心：不可播的资源名被换成该种子分配的可播资源。"""
    got = normalize_seed_resource(
        "rtsp://127.0.0.1:8554/isapi/streaming/channels/101",
        ["streamA", "streamB"], "streamA")
    assert got == "rtsp://127.0.0.1:8554/streamA"


def test_playable_resource_is_untouched(profile):
    """★ 幂等性：已可播的资源 URL 原样返回。"""
    url = "rtsp://127.0.0.1:8554/streamA/track1"
    assert normalize_seed_resource(url, ["streamA", "streamB"], "streamB") == url


def test_no_allowed_resources_means_noop(profile):
    """未声明可播集合 → 不做资源归一化（环境级约束缺省不生效）。"""
    url = "rtsp://127.0.0.1:8554/whatever"
    assert normalize_seed_resource(url, None, "streamA") == url
    assert normalize_seed_resource(url, [], "streamA") == url


def test_no_fallback_means_noop(profile):
    """没有兜底资源 → 不改写（宁可保留也不瞎猜）。"""
    url = "rtsp://127.0.0.1:8554/whatever"
    assert normalize_seed_resource(url, ["streamA"], "") == url


# ---------------------------------------------------------------------------
# 3. 两级串联（缺陷的完整场景）
# ---------------------------------------------------------------------------
def test_full_pipeline_normalizes_foreign_device_url(profile):
    """端点 + 资源两级串联：外部设备的 URL 被完全归正。"""
    url = "rtsp://10.11.26.98:554/isapi/streaming/channels/101"
    step1 = normalize_target_endpoint(url, profile)
    step2 = normalize_seed_resource(step1, ["streamA", "streamB"], "streamA")
    assert step2 == "rtsp://127.0.0.1:8554/streamA"


def test_full_pipeline_is_idempotent(profile):
    """两级串联对已正确的 URL 是 no-op（连续性硬不变式的保证）。"""
    url = "rtsp://127.0.0.1:8554/streamA/track1"
    step1 = normalize_target_endpoint(url, profile)
    step2 = normalize_seed_resource(step1, ["streamA", "streamB"], "streamB")
    assert step2 == url


def test_pipeline_uses_only_profile_and_allow_list(profile):
    """★ 不硬编码协议名/主机名/会话名：换 profile 即换行为。"""
    other = {"default_url": "sip://10.0.0.7:5060/"}
    got = normalize_target_endpoint("rtsp://10.11.26.98:554/x", other)
    assert got == "sip://10.0.0.7:5060/x"


# ---------------------------------------------------------------------------
# 4. 对本仓真实 RTSP profile 的回归（守住已发表语料的连续性）
# ---------------------------------------------------------------------------
def _rtsp_profile() -> dict:
    path = ROOT / "fused_hub" / "targets" / "rtsp" / "profile.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_real_rtsp_profile_endpoint_is_localhost():
    p = _rtsp_profile()
    scheme, netloc = target_endpoint(p)
    assert netloc == "127.0.0.1:8554"
    assert scheme == "rtsp"


def test_real_rtsp_profile_normalizes_foreign_host():
    """真实 profile 下，外部 IP 摄像机的端点被换掉。"""
    p = _rtsp_profile()
    got = normalize_target_endpoint(
        "rtsp://10.11.26.98:554/isapi/streaming/channels/101", p)
    assert got.startswith("rtsp://127.0.0.1:8554/")
    assert "10.11.26.98" not in got


# ---------------------------------------------------------------------------
# 5. 协议级开关（为什么 SIP 不参与端点归一化）
# ---------------------------------------------------------------------------
def test_endpoint_normalization_is_opt_in():
    """★ 默认关闭 → 不改变任何既有行为（历史语料逐字节不变）。"""
    assert endpoint_normalization_enabled({}) is False
    assert endpoint_normalization_enabled({"seedgen": {}}) is False


def test_endpoint_normalization_enabled_by_flag():
    assert endpoint_normalization_enabled(
        {"seedgen": {"target_endpoint_normalization": True}}) is True


def test_real_rtsp_profile_has_the_flag_on():
    """RTSP 需要归一化（Request-URI 决定请求目标）。"""
    assert endpoint_normalization_enabled(_rtsp_profile()) is True


def test_real_sip_profile_has_the_flag_off():
    """★ SIP **不得**归一化：URI domain 是逻辑实体标识、不决定路由。

    改写会破坏消息语义（且会丢掉 userinfo）⇒ 开关必须关闭。
    """
    p = json.loads(
        (ROOT / "fused_hub" / "targets" / "sip" / "profile.json")
        .read_text(encoding="utf-8"))
    assert endpoint_normalization_enabled(p) is False


def test_sip_uri_userinfo_is_preserved_by_parser():
    """SIP URI 形如 sip:user@host（无 //）—— 解析时不能吞掉 userinfo。"""
    from core.fused.downstream.target_env import _split_url

    scheme, netloc, path = _split_url("sip:alice@127.0.0.1:5060")
    assert scheme == "sip"
    assert netloc == "127.0.0.1:5060"
    assert path == ""


def test_sip_endpoint_mismatch_would_break_userinfo():
    """★ 记录"若对 SIP 归一化会发生什么"——这是必须关开关的原因。

    SIP URI 的 userinfo（alice）承载身份语义，端点归一化会把它连同
    host 一起替换掉 → 消息语义被破坏。故 SIP 必须显式排除。
    """
    from core.fused.downstream.target_env import _split_url

    scheme, netloc, _ = _split_url("sip:alice@10.0.0.9:5060")
    assert netloc == "10.0.0.9:5060"   # host 被正确取出
    # 归一化后的 URL 里 userinfo 已不在 netloc 中 —— 语义已丢
    assert "alice" not in netloc
