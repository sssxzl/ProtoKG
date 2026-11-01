"""core/fused/source.py —— source 源（协议实现源码 method norm）→ v2 Fact 映射。

source 源现走 AutoSeeder（协议无关通用 query 检索 + LLM 状态转移分析, 见 core/fused/source_autoseeder.py）, 不再经 norms.jsonl 的正则 method 提取。
norm.content 形如：
    「liveMedia 服务端实现接收并处理 OPTIONS 方法（定义处 <path>:<line>）」

映射：method → definition（text，去「定义处」后缀的语义描述）+ epistemic=descriptive
      （源码实现是描述性陈述，非规范结论）。「定义处 path:line」提取为 evidence locator。

设计依据: local/layer2_extraction_methods.md §三 source 行（ProtocolGPT 借鉴，
           rule 抽固定字段，LLM 侧 RAG 推断状态机 —— 本模块只做 rule 部分）。
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from core.fused.models import (
    Subject, FactKey, ConditionAlways, Value, Fact, FactMetadata,
    Claim, Evidence, Scope,
)
from core.fused.canonical import (
    compute_fact_id, compute_claim_id, compute_evidence_id,
)

_LOC_PATTERN = re.compile(r"（定义处\s*(.+?)\s*）")


def _make_evidence(doc: str, source_id: str, quote: str, locator: Optional[str],
                   claim_id: str) -> Evidence:
    ev = Evidence(
        evidence_id="placeholder", claim_id=claim_id,
        source_type="source", source_id=source_id,
        document=doc, locator=locator, quote=quote,
        content_fingerprint="", extraction_fingerprint="",
    )
    eid = compute_evidence_id(ev)
    return Evidence(
        evidence_id=eid, claim_id=claim_id,
        source_type=ev.source_type, source_id=ev.source_id,
        document=ev.document, locator=ev.locator, quote=ev.quote,
        content_fingerprint=ev.content_fingerprint,
        extraction_fingerprint=ev.extraction_fingerprint,
    )


def _make_fact(subject: Subject, value: Value, norm: dict[str, Any],
               locator: Optional[str], aspect: str = "definition",
               protocol: str = "rtsp") -> Fact:
    # ★ protocol 从 norm 读（缺省用参数兜底），修复硬编码 rtsp——换协议时 fact 的
    # protocol 正确。本模块虽已被 source_autoseeder 替代（孤儿代码），但 source_fsm
    # 仍 import 此 _make_fact，保留参数化避免未来复用踩 protocol 坑。source_fsm 与
    # protocol_patterns 均已 DEPRECATED，三者构成孤岛（生产链路无调用方），仅
    # tests/fused/test_source.py 覆盖 source.py。
    fact_key = FactKey(protocol=norm.get("protocol", protocol), version="1.0",
                       subject=subject, aspect=aspect,
                       condition=ConditionAlways())
    fact_id = compute_fact_id(fact_key)
    tmp = Claim(claim_id="placeholder", fact_id=fact_id, value=value,
                epistemic_type="descriptive", authority="source",
                scope=Scope(), evidence=())
    cid = compute_claim_id(tmp)
    ev = _make_evidence(norm.get("source", ""), norm.get("norm_id", ""),
                        norm.get("content", ""), locator, cid)
    claim = Claim(claim_id=cid, fact_id=fact_id, value=value,
                  epistemic_type="descriptive", authority="source",
                  scope=Scope(), evidence=(ev,), confidence=None)
    return Fact(fact_id=fact_id, fact_key=fact_key, claims=(claim,),
                resolution=None, alignments=(),
                metadata=FactMetadata(created_at="2026-10-09", profile_version="rtsp-v1"))


def source_norm_to_facts(norm: dict[str, Any]) -> list[Fact]:
    """source method norm → [definition fact]（方法实现语义定义）。"""
    name = (norm.get("name", "") or "").strip()
    content = (norm.get("content", "") or "").strip()
    if not name or not content:
        return []
    m = _LOC_PATTERN.search(content)
    locator = m.group(1).strip() if m else None
    desc = _LOC_PATTERN.sub("", content).strip() or content
    return [_make_fact(
        Subject(type="method", name=name),
        Value(type="text", data=desc), norm, locator)]


# ===========================================================================
# Step1: 字段字面量提取（协议无关，从源码扫字符串字面量识别协议字段）
# ===========================================================================

_STRING_LITERAL = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')
#: header 行形态：字符串字面量里 "Transport:" / "Session:" / "Range:" 这样的 header 名+冒号
_HEADER_COLON = re.compile(r'"([A-Z][A-Za-z-]*):"')


def _looks_like_header(s: str) -> bool:
    """启发式判断字符串字面量是否是协议字段名（header 名）。

    协议字段名特征（文本协议通用：RTSP 的 Transport/Session/CSeq、SMTP 的
    HELO/MAIL/RCPT）：大写字母开头，仅含字母数字连字符，3~32 字符。
    排除路径（含 / \\）、URL、标点（: . ?）、含空格的日志/错误消息。
    """
    if not (3 <= len(s) <= 32):
        return False
    if not s[0].isupper():
        return False
    if not all(c.isalnum() or c == "-" for c in s):
        return False
    return True


def _scan_candidates(src_dir) -> list[str]:
    """扫描源码字符串字面量，返回候选字符串列表（含带冒号的 header 名 + 启发式预过滤）。"""
    candidates: set[str] = set()
    for f in sorted(src_dir.glob("*")):
        if f.suffix.lower() not in (".cpp", ".cc", ".c", ".hh", ".h"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # 1. 带冒号的 header 名（"Transport:" / "Session:" 等，最可靠的字段信号）
        for m in _HEADER_COLON.finditer(text):
            candidates.add(m.group(1))
        # 2. 无冒号的字符串字面量（启发式过滤）
        for m in _STRING_LITERAL.finditer(text):
            s = m.group(1)
            if _looks_like_header(s):
                candidates.add(s)
    return sorted(candidates)


def _llm_classify_headers(candidates: list[str]) -> list[str]:
    """用 LLM 从候选字符串中识别协议字段名（header），排除方法名/类名/传输值等噪音。

    协议无关：不硬编码任何协议字段，靠 LLM 的通用语义判断「哪些字符串是消息 header 字段名」。
    """
    from core.llm import DeepSeekClient
    llm = DeepSeekClient()
    system = (
        "你是网络协议逆向专家。给定从协议服务端实现源码中扫描到的字符串字面量列表，"
        "识别出其中【协议字段名】（即客户端请求/服务端响应消息中的 header 字段名）。\n"
        "必须排除：方法名/命令（如 DESCRIBE/SETUP/HELO）、C++ 类名（驼峰命名如 RTSPClient/ServerMediaSession）、"
        "传输协议或编码值（如 RTP/UDP/AVP/SAVP）、时间格式（如 YYYYMMDDTHHMMSSZ）、"
        "日志/错误消息。只输出真正的消息 header 字段名。"
    )
    user = (
        "候选字符串字面量（JSON 数组）：\n"
        + json.dumps(candidates, ensure_ascii=False)
        + "\n\n请输出 JSON，格式：{\"headers\": [\"字段名1\", \"字段名2\", ...]}。"
        "只保留你确认为消息 header 字段名的字符串。"
    )
    try:
        result = llm.chat_json(system=system, user=user)
        headers = result.get("headers", [])
        return [h for h in headers if isinstance(h, str) and h]
    except Exception:
        # LLM 失败则退回启发式结果（有噪音但不会漏）
        return candidates


def extract_header_facts(protocol: str = "rtsp", use_llm: bool = True) -> list[Fact]:
    """Step1: 从 kb/<protocol>/协议实现源码 提取协议字段（header fact）。

    流程（协议无关）：扫描源码字符串字面量 → 启发式预过滤 → LLM 判定协议字段名
    → 产出 Subject(type="header") + aspect="syntax" fact，进 bundle["headers"]。
    """
    from core import paths
    src_dir = paths.kb_source_dir(protocol, "source")
    candidates = _scan_candidates(src_dir)
    headers = _llm_classify_headers(candidates) if use_llm else candidates
    facts: list[Fact] = []
    for h in headers:
        norm = {"protocol": protocol, "kb_source_type": "source",
                "source": "file:协议实现源码", "norm_id": f"source.header.{h}"}
        facts.append(_make_fact(
            Subject(type="header", name=h),
            Value(type="pattern", data=h), norm, "协议实现源码",
            aspect="syntax", protocol=protocol))
    return facts
