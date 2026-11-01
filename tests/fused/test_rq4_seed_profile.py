# -*- coding: utf-8 -*-
"""tests/fused/test_rq4_seed_profile.py —— RQ4 种子画像计算器的单元测试。

覆盖：
  1. **三个 AFLNet 分区器的逐字节忠实性**（RTSP 4 字节 / SMTP 2 字节 / SIP 方法边界）。
  2. **与 AFLNet 源码语义等价**的关键边界用例（空缓冲、单字节、终结符在末尾…）。
  3. 字典 token 统计（跳过空行与注释）。
  4. **种子目录纯净性**：非 .raw 文件必须被拒（AFLNet read_testcases 会把它们当种子）。
  5. rq4_verify_seeds 与 rq4_seed_profile 共用同一实现（防止两处漂移）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.rq4_seed_profile import (  # noqa: E402
    AFLNET_SIP_BOUNDARY_METHODS,
    count_dict_tokens,
    count_regions,
    count_rtsp_regions,
    count_sip_regions,
    count_smtp_regions,
    count_terminator_regions,
    profile_seed_dir,
)


# ---------------------------------------------------------------------------
# RTSP / SMTP：按终结符切分
# ---------------------------------------------------------------------------
def test_rtsp_terminator_is_four_bytes_crlfcrlf():
    """RTSP 分区器只认 4 字节 0D0A0D0A（\\r\\n\\r\\n）。"""
    # 一条 RTSP 消息以 \r\n\r\n 结束 → 1 个 region
    data = b"OPTIONS rtsp://x RTSP/1.0\r\nCSeq: 1\r\n\r\n"
    assert count_rtsp_regions(data) == 1
    # 两条消息 → 2 个 region
    two = data + b"DESCRIBE rtsp://x RTSP/1.0\r\nCSeq: 2\r\n\r\n"
    assert count_rtsp_regions(two) == 2


def test_rtsp_single_crlf_is_not_a_terminator():
    """只有单个 \\r\\n 不构成 RTSP 终结符 → 整条算 1 个 region。"""
    data = b"OPTIONS rtsp://x RTSP/1.0\r\nCSeq: 1\r\n"
    assert count_rtsp_regions(data) == 1


def test_smtp_terminator_is_two_bytes_crlf():
    """SMTP 分区器只认 2 字节 0D0A（\\r\\n）。"""
    data = b"EHLO x\r\nMAIL FROM:<a@b>\r\n"
    assert count_smtp_regions(data) == 2


def test_smtp_single_message_one_region():
    data = b"EHLO x\r\n"
    assert count_smtp_regions(data) == 1


def test_empty_buffer_zero_regions():
    """空输入 → 0 个 region（区别于"结构损坏兜底成 1"）。"""
    assert count_terminator_regions(b"", b"\x0d\x0a") == 0
    assert count_sip_regions(b"") == 0


def test_structurally_broken_buffer_falls_back_to_one_region():
    """无任何终结符 → AFLNet 兜底成 1 个 region（不是 0）。"""
    data = b"garbage-without-terminator"
    assert count_terminator_regions(data, b"\x0d\x0a\x0d\x0a") == 1
    assert count_terminator_regions(data, b"\x0d\x0a") == 1


def test_single_byte_buffer_is_one_region():
    """单字节缓冲（无终结符）→ 1 个 region（走 cur_end == buf_size-1 分支）。"""
    assert count_terminator_regions(b"X", b"\x0d\x0a") == 1
    assert count_sip_regions(b"X") == 1


# ---------------------------------------------------------------------------
# SIP：只有边界方法才开新消息
# ---------------------------------------------------------------------------
def test_sip_boundary_methods_start_new_regions():
    """REGISTER/INVITE/ACK/BYE 各开一个新 region。"""
    parts = []
    for method in AFLNET_SIP_BOUNDARY_METHODS:
        parts.append(f"{method} sip:x SIP/2.0\r\n".encode())
    data = b"".join(parts)
    assert count_sip_regions(data) == len(AFLNET_SIP_BOUNDARY_METHODS)


def test_sip_non_boundary_method_is_merged_into_previous():
    """★ 核心缺陷的复现：OPTIONS 开头 → 不开新 region（被并入前一条）。"""
    data = (b"REGISTER sip:x SIP/2.0\r\n"
            b"OPTIONS sip:x SIP/2.0\r\n"
            b"INVITE sip:y SIP/2.0\r\n")
    # REGISTER(1) + OPTIONS 被并入 → INVITE(2)
    assert count_sip_regions(data) == 2


def test_sip_all_boundary_methods_are_uppercase_exact():
    """小写方法名不被识别（AFLNet 逐字节比对，大小写敏感）。"""
    data = b"REGISTER sip:x SIP/2.0\r\nregister sip:y SIP/2.0\r\n"
    assert count_sip_regions(data) == 1


# ---------------------------------------------------------------------------
# 目录级画像
# ---------------------------------------------------------------------------
def test_profile_seed_dir_counts_files_and_regions(tmp_path):
    (tmp_path / "a.raw").write_bytes(b"REGISTER sip:x SIP/2.0\r\nINVITE sip:y SIP/2.0\r\n")
    (tmp_path / "b.raw").write_bytes(b"ACK sip:z SIP/2.0\r\n")
    prof = profile_seed_dir(tmp_path, "sip")
    assert prof["seed_files"] == 2
    assert prof["seed_regions"] == 3
    assert prof["dict_tokens"] == 0


def test_profile_seed_dir_ignores_non_raw_files(tmp_path):
    """★ 非 .raw 文件不计入画像（它们本就不该存在于种子目录）。"""
    (tmp_path / "a.raw").write_bytes(b"EHLO x\r\n")
    (tmp_path / "MANIFEST.md5").write_text("deadbeef *a.raw\n", encoding="utf-8")
    prof = profile_seed_dir(tmp_path, "smtp")
    assert prof["seed_files"] == 1
    assert prof["seed_regions"] == 1


def test_count_regions_dispatch_by_protocol():
    """count_regions 按协议分派到对应分区器。"""
    sip = b"REGISTER sip:x SIP/2.0\r\nINVITE sip:y SIP/2.0\r\n"
    assert count_regions(sip, "sip") == count_sip_regions(sip)
    rtsp = b"OPTIONS rtsp://x RTSP/1.0\r\n\r\n"
    assert count_regions(rtsp, "rtsp") == count_rtsp_regions(rtsp)
    smtp = b"EHLO x\r\nMAIL FROM:<a@b>\r\n"
    assert count_regions(smtp, "smtp") == count_smtp_regions(smtp)


# ---------------------------------------------------------------------------
# 字典 token 统计
# ---------------------------------------------------------------------------
def test_count_dict_tokens_skips_blank_and_comment(tmp_path):
    d = tmp_path / "x.dict"
    d.write_text('"OPTIONS"\n\n# comment\n"DESCRIBE"\n', encoding="utf-8")
    assert count_dict_tokens(d) == 2


def test_count_dict_tokens_none_and_missing(tmp_path):
    assert count_dict_tokens(None) == 0
    assert count_dict_tokens(tmp_path / "nope.dict") == 0


# ---------------------------------------------------------------------------
# 与 rq4_verify_seeds 共用实现（防漂移）
# ---------------------------------------------------------------------------
def test_verify_seeds_uses_same_region_implementation():
    """rq4_verify_seeds 里的 count_* 必须就是 rq4_seed_profile 里的那些函数。"""
    from scripts import rq4_verify_seeds

    assert rq4_verify_seeds.count_sip_regions is count_sip_regions
    assert rq4_verify_seeds.count_rtsp_regions is count_rtsp_regions


# ---------------------------------------------------------------------------
# 种子目录纯净性（防止污染 AFLNet 种子集）
# ---------------------------------------------------------------------------
def test_verify_dir_rejects_non_raw_files(tmp_path):
    """★ 非 .raw 文件存在 → verify_dir 必须报错（会被 AFLNet 当种子读进去）。"""
    from scripts.rq4_verify_seeds import VerifyError, verify_dir

    (tmp_path / "a.raw").write_bytes(b"EHLO x\r\n")
    (tmp_path / "MANIFEST.md5").write_text("x *a.raw\n", encoding="utf-8")
    with pytest.raises(VerifyError, match="非 .raw"):
        verify_dir(tmp_path, "smtp")


def test_verify_dir_accepts_pure_raw_dir(tmp_path):
    """纯 .raw 目录 → 通过（smtp 无额外断言）。"""
    from scripts.rq4_verify_seeds import verify_dir

    (tmp_path / "a.raw").write_bytes(b"EHLO x\r\nMAIL FROM:<a@b>\r\n")
    summary = verify_dir(tmp_path, "smtp")
    assert summary["seed_files"] == 1
