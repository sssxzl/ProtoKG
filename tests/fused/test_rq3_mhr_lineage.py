# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_mhr_lineage.py —— RQ3 血缘解析回归测试（v2）。

★ 覆盖 2026-10-24 架构复核发现的 P0 缺陷：
   崩溃文件名 `id:000000,sig:06,src:001325,op:havoc,rep:128` 中的
   `id:000000` 是**崩溃目录内**的编号，**不是队列 id**；
   真正的队列血缘在 `src:001325` 里。
   若拿崩溃的本地 id 去查队列的 orig_map/src_map → 会归因到**错误的种子**
   （C/D 组因队列 id 0..6 全是 L3 → MHR_C 会被虚报成 100%）。

新增于 v2；同时锁定 v2 的其余关键不变量：
   · V11：count(orig: 形式条目) == 初始种子数（污染探针）
   · 两种线格式自适应（纯文本 vs 4 字节长度前缀帧）
   · 宽松匹配（AFL 变异会破坏字段名）
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.rq3_mhr_patterns import (  # noqa: E402
    build_lineage_maps,
    detect_format,
    entry_kind,
    match_patterns,
    parse_entry_id,
    parse_orig_seed,
    parse_src_parents,
    resolve_root_seeds,
    split_messages,
)


# ===========================================================================
# 1. 命名形式解析
# ===========================================================================

def test_entry_kind_distinguishes_initial_and_derived():
    """`orig:` 形式 = 初始条目；`src:` 形式 = 派生条目。"""
    assert entry_kind("id:000000,orig:01_DESCRIBE+SETUP.raw") == "initial_copy"
    assert entry_kind("id:000050,src:000000,op:havoc,rep:128,+cov") == "derived"
    assert entry_kind("id:001325,src:001278+000001,op:splice,rep:4") == "derived"
    # 崩溃条目也是派生（它有 src: 字段）
    assert entry_kind("id:000000,sig:06,src:001325,op:havoc,rep:128") == "derived"


def test_parse_orig_seed_only_for_initial_entries():
    assert parse_orig_seed("id:000000,orig:01_DESCRIBE+SETUP.raw") == \
        "01_DESCRIBE+SETUP.raw"
    assert parse_orig_seed("id:000050,src:000000,op:havoc,rep:128") is None


def test_parse_src_parents_handles_splice_two_parents():
    """splice 崩溃/条目有 2 个父 → 必须都解析出来（多父口径）。"""
    assert parse_src_parents("id:000050,src:000000,op:havoc,rep:128") == [0]
    assert parse_src_parents("id:001325,src:001278+000001,op:splice,rep:4") == \
        [1278, 1]


# ===========================================================================
# 2. ★ P0 回归：崩溃归因必须沿 src: 父，不得用崩溃的本地 id
# ===========================================================================

def test_crash_local_id_must_not_be_used_as_queue_id():
    """★ 核心回归：崩溃的 `id:` 是崩溃目录内编号，不是队列 id。

    构造一个队列：id 0 = orig:AAA（会被误命中），id 5 = src:0（派生）。
    崩溃 `id:000000,sig:06,src:000005,...` 的本地 id=0 恰好会命中 orig:AAA，
    但真实血缘应沿 src:000005 → AAA。
    这里用「本地 id 命中错误条目」的方式构造可检出的差异。
    """
    queue = [
        "id:000000,orig:AAA.raw",          # 初始条目
        "id:000001,orig:BBB.raw",
        "id:000005,src:000001,op:havoc,rep:8",   # 派生自 BBB
    ]
    orig_map, src_map = build_lineage_maps(queue)

    crash = "id:000000,sig:06,src:000005,op:havoc,rep:8"
    # 崩溃的本地 id = 0（错，会指向 AAA）
    assert parse_entry_id(crash) == 0
    # 真实血缘：从 src 父 5 上溯
    roots = set()
    for p in parse_src_parents(crash):
        roots |= resolve_root_seeds(p, orig_map, src_map)
    assert roots == {"BBB.raw"}, "崩溃归因必须沿 src: 父上溯"


def test_crash_attribution_via_src_parents_matches_manual_walk():
    """7 个真实崩溃（RQ1.2 基线组）→ 全部应归到同一组根种子。"""
    queue = [
        "id:000000,orig:aac.raw",
        "id:000001,orig:ac3.raw",
        "id:000649,orig:mpg.raw",
        "id:001278,src:000000,op:havoc,rep:2",
        "id:001325,src:001278+000001,op:splice,rep:4",
    ]
    orig_map, src_map = build_lineage_maps(queue)
    crashes = [
        "id:000000,sig:06,src:001325,op:havoc,rep:128",
        "id:000001,sig:06,src:001325,op:havoc,rep:8",
        "id:000005,sig:06,src:001325+000649,op:splice,rep:64",
    ]
    seen = {}
    for c in crashes:
        roots = set()
        for p in parse_src_parents(c):
            roots |= resolve_root_seeds(p, orig_map, src_map)
        seen[c] = frozenset(roots)
    # 前 2 个崩溃共享 src 父 001325 → 归因一致
    assert seen[crashes[0]] == seen[crashes[1]] == frozenset({"aac.raw", "ac3.raw"})
    # 第 3 个是 splice（父 001325 + 000649）→ 多父并集，额外含 mpg.raw
    assert seen[crashes[2]] == frozenset({"aac.raw", "ac3.raw", "mpg.raw"})
    # ★ 关键：三者都不等于「按本地 id 查队列」的结果（那会得到 aac/ac3/mpg 三个不同值）
    assert len(set(seen.values())) == 2


# ===========================================================================
# 3. V11 不变量：orig: 形式条目数 == 初始种子数（污染探针）
# ===========================================================================

def test_v11_orig_form_count_equals_initial_seed_count():
    """★ 污染探针：ChatAFL 增强会把 orig: 形式条目数顶到 1344。

    RQ1.2 实测：50 / 7 / 1344 —— 精确等于各自的初始种子数。
    """
    cases = [
        (["id:000000,orig:01.raw", "id:000001,orig:02.raw",
          "id:000002,src:000000,op:havoc,rep:1"], 2),
        (["id:000000,orig:01.raw"], 1),
        ([f"id:{i:06d},src:000000,op:havoc,rep:{i}" for i in range(30)], 0),
    ]
    for entries, expect in cases:
        orig_map, src_map = build_lineage_maps(entries)
        assert len(orig_map) == expect


# ===========================================================================
# 4. 两种线格式自适应
# ===========================================================================

def test_detect_format_text_vs_length_prefixed():
    """纯文本（种子/队列）与 4 字节长度前缀帧（崩溃样本）必须区分开。"""
    text = b"DESCRIBE rtsp://127.0.0.1/x RTSP/1.0\r\nCSeq: 1\r\n\r\n"
    assert detect_format(text) == "text"

    import struct
    payload = b"SETUP rtsp://127.0.0.1/x/track1 RTSP/1.0\r\nCSeq: 1\r\n\r\n"
    framed = struct.pack("<I", len(payload)) + payload
    assert detect_format(framed) == "frame"
    assert split_messages(framed) == [payload]


def test_split_messages_falls_back_to_crlf():
    text = b"A\r\n\r\nB\r\n\r\n"
    msgs = split_messages(text)
    assert len(msgs) == 2
    assert msgs[0] == b"A\r\n\r\n"


# ===========================================================================
# 5. 宽松匹配（AFL 变异会破坏字段名）
# ===========================================================================

def test_match_patterns_tolerates_mutated_field_names():
    """★ 实测：AFL 把 SETUP 变异成 SETUdioTerack1、Transport 变异成 Trans\\x7fort。

    严格匹配在真实崩溃上命中 0 → 宽松匹配是必需的。
    """
    # track 号被插垃圾
    mutated = b"SETUdioTerack1 RTSP/1.0\r\nCSeq: 1\r\n\r\n" \
              b"SETUdioTerack1 RTSP/1.0\r\nCSeq: 2\r\n\r\n"
    hits = match_patterns(mutated, session_values=["000022B8"])
    assert hits["P1"], "被变异的 track 号仍应被识别为 P1"

    # Transport 键名被破坏，但参数名还在
    mutated2 = b"Trans\x7fort: RTP/AVP/TCP;unicast;interleaved=0-1\r\n\r\n" \
               b"Transport: RTP/AVP;unicast;client_port=50000-50001\r\n\r\n"
    hits2 = match_patterns(mutated2, session_values=["000022B8"])
    assert hits2["P3"], "被变异的 Transport 键名仍应被识别为 P3"


def test_match_patterns_detects_trigger_session_value():
    hits = match_patterns(
        b"TEARDOWN rtsp://127.0.0.1/x/ RTSP/1.0\r\nSession: 000022B8\r\n\r\n",
        session_values=["000022B8"])
    assert hits["P2"]
