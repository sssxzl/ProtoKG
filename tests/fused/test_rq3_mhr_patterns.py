# -*- coding: utf-8 -*-
"""tests/fused/test_rq3_mhr_patterns.py —— 变异命中率判定规则的行为契约（v2）。

固化技术方案 **v2** §5 的规则：
  · **命名形式**分类：`orig:` = 初始副本 / `src:` = 派生（MD5 降为交叉校验）
  · **血缘沿 `src:` 链上溯**（splice 多父、防环、深度上限 64）
  · **格式自适应切分**（纯文本 `\r\n\r\n` / 4 字节长度前缀帧）
  · **去噪 + 宽松匹配**（严格规则在真实崩溃样本上命中 0 → 宽松是必需）
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.rq3_mhr_patterns import (  # noqa: E402
    MAX_LINEAGE_DEPTH, MSG_SEP, PATTERNS,
    build_lineage_maps, classify_entry, denoise, detect_format, entry_kind,
    match_patterns, normalize_name, parse_entry_id, parse_orig,
    parse_orig_seed, parse_src_parents, resolve_root, resolve_root_seeds,
    split_messages, summarize_hits,
)


def _msg(method: str, url: str, cseq: int = 1) -> bytes:
    """构造一条 RTSP 消息字节（纯文本线格式）。"""
    return (f"{method} {url} RTSP/1.0\r\n"
            f"CSeq: {cseq}\r\n\r\n").encode()


def _frames(payloads: list) -> bytes:
    """构造 4 字节长度前缀帧格式的数据。"""
    out = b""
    for p in payloads:
        out += struct.pack("<I", len(p)) + p
    return out


# ===========================================================================
# 格式自适应切分（v2 §5.3.0）
# ===========================================================================

def test_split_text_format():
    """纯文本按 \\r\\n\\r\\n 切分。"""
    content = _msg("DESCRIBE", "rtsp://127.0.0.1/s") + \
        _msg("SETUP", "rtsp://127.0.0.1/s/track1", 2)
    msgs = split_messages(content)
    assert len(msgs) == 2
    assert msgs[0].startswith(b"DESCRIBE")
    assert msgs[1].startswith(b"SETUP")


def test_split_frame_format():
    """★ 长度前缀帧格式被正确识别并切分。"""
    payloads = [_msg("DESCRIBE", "rtsp://127.0.0.1/s"),
                _msg("SETUP", "rtsp://127.0.0.1/s/track1", 2)]
    data = _frames(payloads)
    msgs = split_messages(data)
    assert len(msgs) == 2
    assert msgs[0].startswith(b"DESCRIBE")
    assert detect_format(data) == "frame"


def test_detect_format_text_not_frame():
    """纯文本不得被误判为帧格式。"""
    data = _msg("DESCRIBE", "rtsp://127.0.0.1/s")
    assert detect_format(data) == "text"


def test_split_frame_large_payload():
    """★ 大负载帧（> 4096）仍被正确识别（v2 伪码的 4096 上限会误判）。"""
    big = b"X" * 20000
    data = _frames([big, b"tail"])
    msgs = split_messages(data)
    assert len(msgs) == 2
    assert msgs[0] == big
    assert detect_format(data) == "frame"


def test_split_frame_incomplete_falls_back():
    """帧未精确消费文件长度 → 回退纯文本分支。"""
    data = _frames([b"abc"]) + b"TRAILING"
    msgs = split_messages(data)
    assert detect_format(data) == "text"
    assert len(msgs) == 1


def test_split_empty():
    """空内容 → 空列表。"""
    assert split_messages(b"") == []
    assert detect_format(b"") == "text"


# ===========================================================================
# 去噪（v2 §5.3.2）
# ===========================================================================

def test_denoise_removes_control_bytes():
    """控制字符与 0xff 类字节被替换为空格。"""
    raw = b"Transport: Trans\x7fort\r\n"
    clean = denoise(raw)
    assert b"\x7f" not in clean
    assert b"Trans ort" in clean


def test_denoise_keeps_line_endings():
    """★ \\r / \\n / \\t 必须保留（它们是消息行分隔符，剔除会让切分失效）。"""
    raw = b"DESCRIBE rtsp://127.0.0.1:8554/s RTSP/1.0\r\nCSeq: 1\r\n\r\n"
    assert denoise(raw) == raw


# ===========================================================================
# P1–P4 宽松判定（v2 §5.3.2）
# ===========================================================================

def test_p1_double_setup_same_track():
    """同一 track 的 SETUP 出现 ≥ 2 次 → P1 命中。"""
    content = (_msg("DESCRIBE", "rtsp://127.0.0.1/s") +
               _msg("SETUP", "rtsp://127.0.0.1/s/track1", 2) +
               _msg("SETUP", "rtsp://127.0.0.1/s/track1", 3))
    assert match_patterns(content)["P1"] is True


def test_p1_not_hit_on_different_tracks():
    """不同 track → P1 不命中。"""
    content = (_msg("DESCRIBE", "rtsp://127.0.0.1/s") +
               _msg("SETUP", "rtsp://127.0.0.1/s/track1", 2) +
               _msg("SETUP", "rtsp://127.0.0.1/s/track2", 3))
    assert match_patterns(content)["P1"] is False


def test_p1_loose_tolerates_mutated_method():
    """★ 宽松匹配：容忍 `SETUdioTerack1` 这类被变异破坏的方法名。"""
    content = (b"SETUdioTerack1 rtsp://127.0.0.1/s/track1 RTSP/1.0\r\nCSeq: 1\r\n\r\n"
               b"SETUdioTerack1 rtsp://127.0.0.1/s/track1 RTSP/1.0\r\nCSeq: 2\r\n\r\n")
    assert match_patterns(content)["P1"] is True


def test_p1_loose_tolerates_mutated_track_key():
    """★ 宽松匹配：容忍 track 键名被破坏（`terack1`）。"""
    content = (b"SETUP rtsp://127.0.0.1/s/terack1 RTSP/1.0\r\nCSeq: 1\r\n\r\n"
               b"SETUP rtsp://127.0.0.1/s/terack1 RTSP/1.0\r\nCSeq: 2\r\n\r\n")
    assert match_patterns(content)["P1"] is True


def test_p2_trigger_session():
    """`Session: 000022B8` → P2 命中。"""
    content = b"DESCRIBE rtsp://127.0.0.1/s RTSP/1.0\r\nSession: 000022B8\r\n\r\n"
    assert match_patterns(content)["P2"] is True


def test_p2_loose_bare_value():
    """★ 宽松匹配：键名被破坏时，裸值也应命中。"""
    content = b"DESCRIBE rtsp://127.0.0.1/s RTSP/1.0\r\n000022B8\r\n\r\n"
    assert match_patterns(content)["P2"] is True


def test_p2_not_hit_other_session():
    """非触发值的 Session → P2 不命中。"""
    content = b"DESCRIBE rtsp://127.0.0.1/s RTSP/1.0\r\nSession: 12345\r\n\r\n"
    assert match_patterns(content)["P2"] is False


def test_p2_uses_session_whitelist():
    """P2 用**白名单**判定（可传入触发值集合）。"""
    content = b"DESCRIBE rtsp://127.0.0.1/s RTSP/1.0\r\nSession: 000022B8\r\n\r\n"
    assert match_patterns(content, session_values=["other"])["P2"] is False
    assert match_patterns(content, session_values=["000022B8"])["P2"] is True


def test_p3_transport_switch():
    """同时含 interleaved 与 client_port → P3 命中。"""
    content = (b"SETUP rtsp://127.0.0.1/s/track1 RTSP/1.0\r\n"
               b"Transport: RTP/AVP;unicast;interleaved=0-1\r\n"
               b"Transport: RTP/AVP;unicast;client_port=50000-50001\r\n\r\n")
    assert match_patterns(content)["P3"] is True


def test_p3_loose_tolerates_mutated_transport_key():
    """★ 宽松匹配：容忍 `Trans\\x7fort`（键名被破坏，只匹配参数名）。"""
    content = (b"SETUP rtsp://127.0.0.1/s/track1 RTSP/1.0\r\n"
               b"Trans\x7fort: RTP/AVP;unicast;interleaved=0-1\r\n"
               b"Trans\x7fort: RTP/AVP;unicast;client_port=50000-50001\r\n\r\n")
    assert match_patterns(content)["P3"] is True


def test_p4_setup_teardown_setup_same_track():
    """SETUP … TEARDOWN … SETUP 且同 track → P4 命中。"""
    content = (_msg("SETUP", "rtsp://127.0.0.1/s/track1", 1) +
               _msg("TEARDOWN", "rtsp://127.0.0.1/s/", 2) +
               _msg("SETUP", "rtsp://127.0.0.1/s/track1", 3))
    assert match_patterns(content)["P4"] is True


def test_p4_not_hit_different_track():
    """两 SETUP 的 track 不同 → P4 不命中。"""
    content = (_msg("SETUP", "rtsp://127.0.0.1/s/track1", 1) +
               _msg("TEARDOWN", "rtsp://127.0.0.1/s/", 2) +
               _msg("SETUP", "rtsp://127.0.0.1/s/track2", 3))
    assert match_patterns(content)["P4"] is False


def test_patterns_on_frame_format():
    """帧格式的崩溃样本也能做模式判定。"""
    payloads = [_msg("SETUP", "rtsp://127.0.0.1/s/track1", 1),
                _msg("SETUP", "rtsp://127.0.0.1/s/track1", 2)]
    hits = match_patterns(_frames(payloads))
    assert hits["P1"] is True


# ===========================================================================
# 命名形式分类（v2 §5.2.1 / §5.3.1）
# ===========================================================================

def test_entry_kind_by_naming_form():
    """★ v2：按命名形式分类（orig: = 初始 / src: = 派生）。"""
    assert entry_kind("id:000000,orig:01_A.raw") == "initial_copy"
    assert entry_kind("id:000007,src:000000,op:havoc,rep:64") == "derived"
    assert entry_kind("id:000000,sig:06,src:001325,op:havoc,rep:128") == "derived"


def test_entry_kind_differs_from_md5():
    """★ v2：内容与种子相同但命名形式为 src: → 仍判 derived（按命名形式）。"""
    e = classify_entry("id:000007,src:000000,op:havoc,rep:64",
                       "same-as-seed", b"x", {"same-as-seed"})
    assert e["kind"] == "derived"
    assert e["md5_in_seeds"] is True


def test_normalize_name_windows_ads():
    """★ Windows/NTFS 的 `:` → U+F03A 陷阱必须被还原。"""
    win = "id\uf03a000000,sig\uf03a06,src\uf03a001325,op\uf03ahavoc"
    assert normalize_name(win).startswith("id:000000")
    assert entry_kind(win) == "derived"
    assert parse_entry_id(win) == 0
    assert parse_src_parents(win) == [1325]


def test_parse_orig_seed():
    """orig: 后的种子文件名。"""
    assert parse_orig_seed("id:000000,orig:01_DESCRIBE+SETUP.raw") == \
        "01_DESCRIBE+SETUP.raw"
    assert parse_orig_seed("id:000007,src:000000,op:havoc") is None


def test_parse_orig_backward_compat_alias():
    """★ 向后兼容：v1 的 `parse_orig` 必须仍可导入且行为一致。

    （QA-2026-10-24 P0-2：v2 重构时旧名被移除 → 整个测试套件收集失败。）
    """
    assert parse_orig is parse_orig_seed
    assert parse_orig("id:000000,orig:01_DESCRIBE+SETUP.raw") == \
        "01_DESCRIBE+SETUP.raw"
    assert parse_orig("id:000007,src:000000,op:havoc") is None


def test_parse_src_parents():
    """src: 父 id 列表（splice 有 2 个）。"""
    assert parse_src_parents("id:000007,src:000000,op:havoc,rep:64") == [0]
    assert parse_src_parents("id:000005,src:001325+000649,op:splice") == \
        [1325, 649]
    assert parse_src_parents("id:000000,orig:x.raw") == []


# ===========================================================================
# 血缘上溯（v2 §5.2.2）
# ===========================================================================

def _lineage_fixture():
    """构造一条含 splice 多父的血缘链。

    id:0 = orig:A
    id:1 = orig:B
    id:2 = src:0            (havoc from A)
    id:3 = src:1            (havoc from B)
    id:4 = src:2+3          (splice → 多父)
    """
    entries = [
        "id:000000,orig:A.raw",
        "id:000001,orig:B.raw",
        "id:000002,src:000000,op:havoc,rep:4",
        "id:000003,src:000001,op:havoc,rep:8",
        "id:000004,src:000002+000003,op:splice,rep:2",
    ]
    return build_lineage_maps(entries)


def test_build_lineage_maps():
    """血缘映射：orig_map 与 src_map。"""
    om, sm = _lineage_fixture()
    assert om == {0: "A.raw", 1: "B.raw"}
    assert sm == {2: [0], 3: [1], 4: [2, 3]}


def test_resolve_root_seeds_single_parent():
    """单父链上溯到唯一根。"""
    om, sm = _lineage_fixture()
    assert resolve_root_seeds(2, om, sm) == {"A.raw"}


def test_resolve_root_seeds_splice_multi_parent():
    """★ splice 多父 → 根集合 > 1。"""
    om, sm = _lineage_fixture()
    assert resolve_root_seeds(4, om, sm) == {"A.raw", "B.raw"}


def test_resolve_root_seeds_cycle_safe():
    """★ 成环时不无限递归（防环）。"""
    om = {}
    sm = {1: [2], 2: [1]}
    assert resolve_root_seeds(1, om, sm) == set()


def test_resolve_root_seeds_depth_limit():
    """★ 深度上限：超限归 unattributed（返回空集）。"""
    om = {}
    sm = {i: [i + 1] for i in range(200)}
    assert resolve_root_seeds(0, om, sm, max_depth=MAX_LINEAGE_DEPTH) == set()


def test_resolve_root_maps_layer():
    """解析根 + 层归属（多父时 L3 优先）。"""
    om, sm = _lineage_fixture()
    mf = {"A.raw": {"layer": "L3", "filename": "A.raw"},
          "B.raw": {"layer": "L1", "filename": "B.raw"}}
    root, layer, n_roots = resolve_root("id:000004,src:000002+000003,op:splice",
                                        om, sm, mf, {})
    assert layer == "L3"
    assert n_roots == 2


def test_resolve_root_unattributed():
    """完全 unresolved → unattributed。"""
    om, sm = _lineage_fixture()
    root, layer, n_roots = resolve_root("id:000099,src:000098,op:havoc",
                                        om, sm, {}, {})
    assert root is None
    assert layer == "unknown"


def test_resolve_root_nn_prefix_fallback():
    """兜底：NN_ 序号前缀反查 manifest。"""
    om = {0: "07_B.raw"}
    sm = {}
    mf = {}
    mi = {"07": {"layer": "L2", "filename": "07_B.raw"}}
    root, layer, _n = resolve_root("id:000000,orig:07_B.raw", om, sm, mf, mi)
    assert root == "07_B.raw"
    assert layer == "L2"


# ===========================================================================
# 汇总
# ===========================================================================

def test_summarize_hits():
    """汇总：池化比率 + P1–P4 分布。"""
    entries = [
        {"kind": "derived", "hits": {"P1": True, "P2": False, "P3": False,
                                     "P4": False}, "hit_any": True},
        {"kind": "derived", "hits": {"P1": False, "P2": True, "P3": False,
                                     "P4": False}, "hit_any": True},
        {"kind": "derived", "hits": {"P1": False, "P2": False, "P3": False,
                                     "P4": False}, "hit_any": False},
        {"kind": "initial_copy", "hits": {"P1": True, "P2": False,
                                          "P3": False, "P4": False},
         "hit_any": True},
    ]
    s = summarize_hits(entries)
    assert s["n_total"] == 4
    assert s["n_initial"] == 1
    assert s["n_derived"] == 3
    assert s["n_hit"] == 2
    assert s["mhr_a"] == pytest.approx(200.0 / 3)
    assert s["pattern_counts"] == {"P1": 1, "P2": 1, "P3": 0, "P4": 0}


def test_summarize_hits_empty_derived():
    """derived 为空 → mhr_a 为 None（不是 0）。"""
    s = summarize_hits([{"kind": "initial_copy", "hits": {}, "hit_any": False}])
    assert s["n_derived"] == 0
    assert s["mhr_a"] is None
