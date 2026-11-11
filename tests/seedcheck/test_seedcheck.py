# -*- coding: utf-8 -*-
"""tests/seedcheck/test_seedcheck.py —— **种子校验层**的单元测试。

★ 覆盖
  ① V1 格式必假：每条判据都要能抓到（**唯一阻断级**⇒ 判错代价最大）
  ② V2 知识一致：缺必填头能抓到；**同构变体不报**（防误报）
  ③ V5 多样性：指标算得对（用构造数据）
  ④ 边界：空语料 / 无中枢数据时不崩

★ 为什么必须单测
  校验器**误报**会把好种子标成越界 ⇒ 误导投放；
  校验器**漏报**会让坏种子混进去 ⇒ 两者都要用单测钉住。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from seedcheck import v1_format, v2_knowledge, v3_env, v5_diversity   # noqa: E402
from seedcheck.knowledge import Knowledge                              # noqa: E402
from seedcheck.model import (LEVEL_COMPLIANT, LEVEL_EDGE, LEVEL_MALFORMED,
                              Report, SeedRecord, Violation)            # noqa: E402


# ===========================================================================
# 辅助
# ===========================================================================

def _seed(filename: str = "01_X.raw", raw: str = "") -> SeedRecord:
    rec = SeedRecord(filename=filename, raw_text=raw)
    norm = raw.replace("\r\n", "\n")
    for blk in [b for b in norm.split("\n\n") if b.strip()]:
        lines = [l for l in blk.split("\n") if l.strip()]
        if not lines:
            continue
        parts = lines[0].strip().split(" ")
        headers = {}
        for l in lines[1:]:
            s = l.strip()
            if ":" in s:
                k, v = s.split(":", 1)
                headers[k.strip()] = v.strip()
        rec.messages.append({"method": parts[0] if parts else "",
                             "uri": parts[1] if len(parts) > 1 else "",
                             "version": parts[2] if len(parts) > 2 else "",
                             "headers": headers})
    return rec


def _k(**kw) -> Knowledge:
    k = Knowledge(protocol="test")
    for key, val in kw.items():
        setattr(k, key, val)
    return k


# ===========================================================================
# ① V1 格式必假（唯一阻断级）
# ===========================================================================

def test_v1_empty_file_is_violation():
    vs = v1_format.check(_seed(raw=""))
    assert any(v.code == "empty_file" for v in vs)


def test_v1_missing_terminator():
    raw = "DESCRIBE rtsp://h/s RTSP/1.0\nCSeq: 1"      # 末尾无空行
    vs = v1_format.check(_seed(raw=raw))
    assert any(v.code == "no_terminator" for v in vs)


def test_v1_request_line_too_short():
    raw = "DESCRIBE\nCSeq: 1\n\n"                        # 首行只有 1 个字段
    vs = v1_format.check(_seed(raw=raw))
    assert any(v.code == "bad_request_line" for v in vs)


def test_v1_header_without_colon():
    raw = "DESCRIBE rtsp://h/s RTSP/1.0\nCSeq 1\n\n"    # 头行缺冒号
    vs = v1_format.check(_seed(raw=raw))
    assert any(v.code == "bad_header_line" for v in vs)


def test_v1_valid_seed_passes():
    raw = "DESCRIBE rtsp://h/s RTSP/1.0\r\nCSeq: 1\r\n\r\n"
    assert v1_format.check(_seed(raw=raw)) == []


# ===========================================================================
# ② V2 知识一致
# ===========================================================================

def test_v2_missing_required_header_detected():
    k = _k(required_headers={"SETUP": ["CSeq", "Transport"]},
           known_methods={"SETUP"})
    s = _seed(raw="SETUP rtsp://h/s/track1 RTSP/1.0\nCSeq: 1\n\n")
    vs = v2_knowledge.check(s, k)
    assert any(v.code == "missing_required_header" and "Transport" in v.message
               for v in vs)


def test_v2_unknown_method_detected():
    k = _k(known_methods={"DESCRIBE"})
    s = _seed(raw="FROB rtsp://h/s RTSP/1.0\nCSeq: 1\n\n")
    vs = v2_knowledge.check(s, k)
    assert any(v.code == "unknown_method" for v in vs)


def test_v2_missing_precondition_detected():
    k = _k(precondition={"PLAY": ["SETUP"]}, known_methods={"PLAY", "SETUP"})
    s = _seed(raw="PLAY rtsp://h/s RTSP/1.0\nCSeq: 1\n\n")
    vs = v2_knowledge.check(s, k)
    assert any(v.code == "missing_precondition" for v in vs)


def test_v2_missing_session_header_detected():
    k = _k(session_header={"PLAY": [{"header": "Session", "from_occurrence": 1}]},
           known_methods={"PLAY"})
    s = _seed(raw="PLAY rtsp://h/s RTSP/1.0\nCSeq: 1\n\n")
    vs = v2_knowledge.check(s, k)
    assert any(v.code == "missing_session_header" for v in vs)


def test_v2_isomorphic_variant_is_not_violation():
    """★ 规范域是**示例值**；同构但参数不同（端口号）**同样合法** ⇒ 不该报。"""
    k = _k(header_values={"Transport": ["RTP/AVP;unicast;client_port=46902-46903"]},
           known_methods={"SETUP"})
    s = _seed(raw="SETUP rtsp://h/s/track1 RTSP/1.0\n"
                  "CSeq: 1\nTransport: RTP/AVP;unicast;client_port=50000-50001\n\n")
    vs = v2_knowledge.check(s, k)
    assert not any(v.code == "value_outside_domain" for v in vs)


def test_v2_hex_session_id_is_isomorphic():
    """★ 十六进制会话 id（``000022B8``）vs 十进制规范值（``107518505``）⇒ 同构。"""
    k = _k(header_values={"Session": ["107518505"]}, known_methods={"PLAY"})
    s = _seed(raw="PLAY rtsp://h/s RTSP/1.0\nCSeq: 1\nSession: 000022B8\n\n")
    vs = v2_knowledge.check(s, k)
    assert not any(v.code == "value_outside_domain" for v in vs)


def test_v2_truly_wrong_value_is_violation():
    k = _k(header_values={"Transport": ["RTP/AVP;unicast"]}, known_methods={"SETUP"})
    s = _seed(raw="SETUP rtsp://h/s/track1 RTSP/1.0\n"
                  "CSeq: 1\nTransport: GARBAGE\n\n")
    vs = v2_knowledge.check(s, k)
    assert any(v.code == "value_outside_domain" for v in vs)


def test_v2_resource_extraction_skips_track_segment():
    """★ ``/mp3AudioTest/track1`` ⇒ 资源名是 ``mp3AudioTest``（不是 track1）。"""
    assert v2_knowledge._resource_of("rtsp://h:8554/mp3AudioTest/track1") == "mp3AudioTest"
    assert v2_knowledge._resource_of("rtsp://h:8554/mp3AudioTest") == "mp3AudioTest"


# ===========================================================================
# ③ V3 环境适配
# ===========================================================================

def test_v3_resource_unavailable_tagged():
    k = _k(env_resources={"live555": ["mp3AudioTest"]})
    s = _seed(raw="DESCRIBE rtsp://h:8554/otherStream RTSP/1.0\nCSeq: 1\n\n")
    vs = v3_env.check(s, k, "live555")
    assert any(v.code == "resource_unavailable" for v in vs)


def test_v3_skipped_without_env():
    k = _k(env_resources={"live555": ["mp3AudioTest"]})
    s = _seed(raw="DESCRIBE rtsp://h:8554/other RTSP/1.0\nCSeq: 1\n\n")
    assert v3_env.check(s, k, None) == []


# ===========================================================================
# ④ V5 多样性
# ===========================================================================

def test_v5_metrics_on_constructed_corpus():
    rep = Report(protocol="test")
    rep.metrics["layers"] = ["a", "b", "c"]
    s1 = _seed("1.raw", "DESCRIBE rtsp://h/s RTSP/1.0\nCSeq: 1\n\n")
    s2 = _seed("2.raw", "DESCRIBE rtsp://h/s RTSP/1.0\nCSeq: 1\n\n")   # 同内容
    s3 = _seed("3.raw", "PLAY rtsp://h/s RTSP/1.0\nCSeq: 1\n\n")
    m = v5_diversity.compute_metrics([s1, s2, s3], rep)
    assert m["seed_count"] == 3
    assert m["unique_content"] == 2
    assert m["unique_sequences"] == 2
    assert m["content_dup_rate"] > 0
    assert m["layer_coverage"] == 3


def test_v5_warns_on_high_duplication():
    rep = Report(protocol="test")
    rep.metrics["layers"] = ["a"]
    seeds = [_seed(f"{i}.raw", "DESCRIBE rtsp://h/s RTSP/1.0\nCSeq: 1\n\n")
             for i in range(5)]
    v5_diversity.compute_metrics(seeds, rep)
    vs = v5_diversity.check(seeds, rep)
    codes = {v.code for v in vs}
    assert "high_content_dup_rate" in codes
    assert "high_seq_dup_rate" in codes
    assert "first_method_concentrated" in codes


# ===========================================================================
# ⑤ 等级与报告
# ===========================================================================

def test_level_escalation():
    s = _seed(raw="DESCRIBE rtsp://h/s RTSP/1.0\nCSeq 1\n\n")
    s.add(Violation("V2", "x", "msg"))
    assert s.level == LEVEL_EDGE
    s.add(Violation("V1", "y", "msg"))
    assert s.level == LEVEL_MALFORMED


def test_report_groups_and_summary():
    rep = Report(protocol="test")
    s1 = _seed("1.raw")
    s2 = _seed("2.raw")
    s2.add(Violation("V2", "x", "msg"))
    rep.seeds = [s1, s2]
    txt = rep.summary_text()
    assert "种子校验" in txt
    assert rep.groups()[LEVEL_COMPLIANT] == 1
    assert rep.groups()[LEVEL_EDGE] == 1


def test_empty_corpus_does_not_crash():
    rep = Report(protocol="test")
    assert v5_diversity.compute_metrics([], rep) == {}
