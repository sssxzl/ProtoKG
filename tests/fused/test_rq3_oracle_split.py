# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_oracle_split.py —— `_oracle.py` 的格式自适应切分契约。

技术方案 v2 §4.1.1 的要求：
  · **纯文本种子**的切分行为**逐字节不变**（回归断言）
  · **长度前缀帧**（`/out/replayable-crashes/*`）被正确切分，**全部帧精确消费文件长度**
  · 长度前缀帧的负载可达 16417 B → 上限不能取 4096（会把真实崩溃样本误判为纯文本）
"""
from __future__ import annotations

import importlib.util
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _load_oracle():
    """加载 `tools/qa/_oracle.py`（非包模块，用 importlib 载入）。"""
    spec = importlib.util.spec_from_file_location(
        "rq3_oracle_mod", ROOT / "tools" / "qa" / "_oracle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ORACLE = _load_oracle()


def _msg(method: str, url: str, cseq: int = 1) -> bytes:
    """构造一条 RTSP 消息字节。"""
    return (f"{method} {url} RTSP/1.0\r\n"
            f"CSeq: {cseq}\r\n\r\n").encode()


def _frames(payloads: list) -> bytes:
    """构造 4 字节长度前缀帧格式。"""
    out = b""
    for p in payloads:
        out += struct.pack("<I", len(p)) + p
    return out


def _legacy_split(data: bytes) -> list:
    """v1 的纯文本切分实现（回归对照）。"""
    sep = b"\r\n\r\n"
    msgs: list = []
    rest = data
    while True:
        idx = rest.find(sep)
        if idx == -1:
            if rest.strip():
                msgs.append(rest)
            break
        msgs.append(rest[:idx + len(sep)])
        rest = rest[idx + len(sep):]
    return msgs


# ===========================================================================
# 纯文本：行为逐字节不变
# ===========================================================================

def test_pure_text_split_unchanged():
    """★ 纯文本切分与 v1 实现逐条相同（回归红线）。"""
    content = _msg("DESCRIBE", "rtsp://127.0.0.1/s") + \
        _msg("SETUP", "rtsp://127.0.0.1/s/track1", 2) + \
        _msg("PLAY", "rtsp://127.0.0.1/s/", 3)
    assert ORACLE.split_messages(content) == _legacy_split(content)
    assert len(ORACLE.split_messages(content)) == 3


def test_real_seed_files_unchanged():
    """★ 真实语料种子：切分结果与 v1 完全一致（逐条断言）。"""
    seeds = ROOT / "derived" / "experiments" / "rq3" / "C" / "seeds"
    if not seeds.is_dir():
        pytest.skip("语料未生成")
    files = sorted(seeds.glob("*.raw"))
    if not files:
        pytest.skip("语料为空")
    for f in files:
        data = f.read_bytes()
        assert ORACLE.split_messages(data) == _legacy_split(data), \
            f"{f.name} 的切分结果变了"


def test_empty_data():
    """空数据 → 空列表。"""
    assert ORACLE.split_messages(b"") == []


# ===========================================================================
# 长度前缀帧
# ===========================================================================

def test_frame_format_split():
    """★ 长度前缀帧被正确切分。"""
    payloads = [_msg("DESCRIBE", "rtsp://127.0.0.1/s"),
                _msg("SETUP", "rtsp://127.0.0.1/s/track1", 2)]
    data = _frames(payloads)
    msgs = ORACLE.split_messages(data)
    assert len(msgs) == 2
    assert msgs[0].startswith(b"DESCRIBE")
    assert msgs[1].startswith(b"SETUP")


def test_frame_large_payload():
    """★ 大负载帧（> 4096）仍被正确切分。

    真实崩溃样本实测负载可达 16417 B；若上限取 4096 → 该样本会被误判为纯文本
    → 重放输入与 AFL 原始输入不一致 → 重放结论不严格成立。
    """
    big = b"X" * 20000
    data = _frames([big, b"tail"])
    msgs = ORACLE.split_messages(data)
    assert len(msgs) == 2
    assert msgs[0] == big
    assert msgs[1] == b"tail"


def test_frame_exact_consumption():
    """★ 帧必须精确消费文件长度（否则回退纯文本分支）。"""
    data = _frames([b"abc"]) + b"TRAILING"
    # 未精确消费 → 走纯文本分支（不是帧）
    msgs = ORACLE.split_messages(data)
    assert len(msgs) == 1
    assert msgs[0] == data


def test_frame_zero_length_rejected():
    """零长度帧被拒绝（n <= 0）。"""
    data = struct.pack("<I", 0) + b"abc"
    assert ORACLE.split_messages(data) == _legacy_split(data)


def test_frame_text_looking_payload():
    """帧负载是 RTSP 文本时也能正确切分。"""
    payloads = [_msg("TEARDOWN", "rtsp://127.0.0.1:8554/wavAudioTest"),
                _msg("SETUP", "rtsp://127.0.0.1:8554/wavAudioTest/track1", 2)]
    data = _frames(payloads)
    msgs = ORACLE.split_messages(data)
    assert len(msgs) == 2
    assert msgs[0].startswith(b"TEARDOWN")
