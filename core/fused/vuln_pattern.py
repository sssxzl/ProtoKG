# -*- coding: utf-8 -*-
"""core/fused/vuln_pattern.py —— 漏洞模式（vuln_pattern）识别与抽取（Layer 2，规则部分）。

借鉴 GLMFuzz（QRS 2025）「漏洞知识引导的协议 fuzzing」：把历史漏洞结构化成一个
「可检索的漏洞模式」（触发序列 + 触发字段 + 边界动作 + 变异提示），供知识中枢存储
与下游种子生成消费。

本模块是「漏洞模式」的唯一真源（避免第二真源）：
  - action 分类（_CWE_ACTION / _COND_KEYWORD_ACTION / _extract_cwes）
  - 触发流提取（_STREAM_HINT_MAP / _CRASH_STREAMS / _extract_stream_hints）
  - 字段归一化（_FIELD_ALIAS / _normalize_field）
  - 边界参数（BoundaryParam / _ACTION_BOUNDARY）
strategy.py（下游漏洞导向）与 boundary_probe.py（源 B）复用本模块，不各自维护。

Phase 1 只做 rule 抽取（零 LLM）：trigger_sequence 仅方法锚点、mutation_hint 仅
触发条件原文；Phase 2 用 LLM 补全完整触发消息序列与变异提示。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from core import paths

# ===========================================================================
# 1. 字段名归一化（把中文/口语字段名映射到标准头字段名）
# ===========================================================================

_FIELD_ALIAS = {
    "transport header": "Transport",
    "transport": "Transport",
    "授权头": "Authorization",
    "认证字段": "Authorization",
    "authorization": "Authorization",
    "传输参数": "Transport",
    "序列号": "CSeq",
    "cseq": "CSeq",
    "响应": "response",
    "content-length": "Content-Length",
    "content_length": "Content-Length",
    "client_port": "client_port",
    "interleaved": "interleaved",
    "track": "track",
    "digest": "Digest",
    "nonce": "nonce",
    "username": "username",
    "realm": "realm",
    "uri": "uri",
    "session": "Session",
    "range": "Range",
}


def normalize_field(field_name: str) -> str:
    """字段名归一化（大小写不敏感，中文别名映射 + 剥尾部 header/头 字样）。

    实测 trigger_field 常带 " header" / " 头" 后缀（如 "Transport header"、
    "Authorization header"），先按原样查别名表，未命中再剥后缀重查。
    """
    if not field_name:
        return ""
    key = str(field_name).strip()
    low = key.lower()
    if low in _FIELD_ALIAS:
        return _FIELD_ALIAS[low]
    # 剥尾部 " header" / " 头" 字样（对齐 vuln_rules_design.md §3.2 归一化规则）
    stripped = re.sub(r"\s+(header|头)$", "", key, flags=re.IGNORECASE).strip()
    low2 = stripped.lower()
    if low2 in _FIELD_ALIAS:
        return _FIELD_ALIAS[low2]
    return key


def _normalize_field(field_name: str) -> str:  # 向后兼容别名
    return normalize_field(field_name)


# ===========================================================================
# 2. 漏洞「触发流」提取（隐患：漏洞针对特定流，如 Matroska/Ogg/MP3）
# ===========================================================================

# 漏洞文本关键词 → 资源清单流名（按关键词长度降序，长词优先匹配）
_STREAM_HINT_MAP = [
    ("mpeg-2 transport stream", ["mpeg2TransportStreamTest"]),
    ("mpeg2 transport stream", ["mpeg2TransportStreamTest"]),
    ("transport stream", ["mpeg2TransportStreamTest"]),
    ("mpeg-1/2", ["mpeg1or2AudioVideoTest", "mpeg1or2ESVideoTest"]),
    ("mpeg1or2", ["mpeg1or2AudioVideoTest", "mpeg1or2ESVideoTest"]),
    ("mpeg-4", ["mpeg4ESVideoTest"]),
    ("mpeg4", ["mpeg4ESVideoTest"]),
    ("matroska", ["matroskaFileTest"]),
    ("h.264", ["h264ESVideoTest"]),
    ("h264", ["h264ESVideoTest"]),
    ("h.265", ["h265ESVideoTest"]),
    ("h265", ["h265ESVideoTest"]),
    ("webm", ["webmFileTest"]),
    ("opus", ["opusFileTest"]),
    ("vob", ["vobTest"]),
    ("amr", ["amrAudioTest"]),
    ("aac", ["aacAudioTest"]),
    ("adts", ["aacAudioTest"]),
    ("ac-3", ["ac3AudioTest"]),
    ("ac3", ["ac3AudioTest"]),
    ("wav", ["wavAudioTest"]),
    ("mp3", ["mp3AudioTest"]),
    ("ogg", ["oggFileTest"]),
    ("mkv", ["matroskaFileTest"]),
    ("dv ", ["dvVideoTest"]),
    ("mpeg", ["mpeg1or2AudioVideoTest", "mpeg1or2ESVideoTest"]),
]

# 实测会导致 testOnDemandRTSPServer 完整会话崩溃的流（dry run 会被 afl-fuzz 拒绝）。
# 即便漏洞文本提到这些流，也不能用——否则种子在 dry run 阶段直接崩溃。
_CRASH_STREAMS = {"amrAudioTest", "aacAudioTest", "ac3AudioTest"}


def extract_stream_hints(text: str, protocol: str = "rtsp") -> list[str]:
    """从漏洞文本（condition + description）提取「触发流」流名（映射来自 profile 的 vuln 段）。

    只返回不在 crash_streams 里的流；命中多个关键词时按出现顺序去重。
    无命中返回 []（调用方自行回退安全流）。
    """
    if not text:
        return []
    cfg = _load_vuln_config(protocol)
    t = text.lower()
    found: list[str] = []
    for keyword, streams in cfg["stream_hints"]:
        if keyword in t:
            for s in streams:
                if s not in cfg["crash_streams"] and s not in found:
                    found.append(s)
    return found


def _extract_stream_hints(text: str, protocol: str = "rtsp") -> list[str]:  # 向后兼容别名
    """向后兼容别名（当前无调用点）。protocol 透传，避免误用退化 RTSP。"""
    return extract_stream_hints(text, protocol)


def crash_streams(protocol: str = "rtsp") -> set[str]:
    """返回该协议的「崩溃流」集合（dry run 会被 afl-fuzz 拒绝的流）。

    供下游（如 run_seedgen_e2e 的资源清单过滤）直接取协议特定的崩溃流，
    替代硬编码 RTSP 的 _CRASH_STREAMS。缺 profile 配置时回退 RTSP 硬编码默认。
    """
    return _load_vuln_config(protocol)["crash_streams"]


# ===========================================================================
# 3. action 分类：漏洞 → 边界动作（CWE 编号 + 触发条件关键词）
# ===========================================================================

# CWE 编号 → 动作（权威，命中即用）
_CWE_ACTION = {
    "476": "empty_edge",     # 空指针解引用
    "121": "long_value",     # 栈缓冲区溢出
    "120": "long_value",     # 缓冲区溢出
    "122": "long_value",     # 堆缓冲区溢出
    "787": "long_value",     # 越界写
    "125": "long_value",     # 越界读
    "119": "long_value",     # 内存边界不恰当
    "190": "int_edge",       # 整数溢出
    "189": "int_edge",       # 数值错误
    "416": "uaf_seq",        # 释放后使用
    "401": "lifecycle_seq",  # 内存泄漏/生命周期
    "617": "assert_seq",     # 可达断言
    "400": "many_params",    # 资源消耗
    "307": "replay_seq",     # 认证尝试限制
    "22": "path_edge",       # 路径遍历
    "287": "auth_edge",      # 认证不恰当
    "306": "auth_edge",      # 认证缺失
    "94": "inject_edge",     # 代码注入
}

# 触发条件关键词 → 动作（比 CWE 更具体，覆盖「序列型」漏洞）
_COND_KEYWORD_ACTION = [
    ((("连续两次", "同一 track", "同 track", "同一track"),), "double_setup"),
    ((("interleaved", "RTP/AVP/TCP", "RTP-over-RTSP"),), "interleave_seq"),
    ((("绝对时间", "clock=", "seek"),), "abs_time_seek"),
    ((("大量 client_port", "多个 client_port", "client_port 字段"),), "many_params"),
    ((("第二连接", "第二个连接", "second connection", "另一个连接"),), "multi_session"),
    ((("超长", "过长", "long", "length", "溢出"),), "long_value"),
    ((("为空", "空值", "空指针", "空引用", "NULL", "null"),), "empty_edge"),
    ((("重放", "反复", "重复发送", "大量请求", "多次"),), "replay_seq"),
    ((("绝对",),), "abs_time_seek"),
]


def _extract_cwes(cwe_str: str) -> list[str]:
    """从 cwe 字符串抽取全部 CWE 编号（如 'CWE-119 ...; CWE-189 ...' -> ['119','189']）。"""
    return re.findall(r"CWE-(\d+)", cwe_str or "")


def classify_action(cwe_str: str, condition: str, description: str) -> str:
    """把漏洞的 CWE + 触发条件 + 描述，识别成边界动作（action）。

    规则（两层）：
      1. 触发条件关键词 → 更具体的序列型动作（优先级高于 CWE，先匹配）
      2. CWE 编号 → 权威动作（条件没命中才用）
    其余回退 "default"。
    """
    cwes = _extract_cwes(cwe_str)
    text = f"{condition} {description}"

    action = "default"
    # 第一层：条件关键词（更具体，序列型漏洞）
    for keyword_groups, act in _COND_KEYWORD_ACTION:
        for kws in keyword_groups:
            if any(kw.lower() in text.lower() for kw in kws):
                action = act
                break
        if action != "default":
            break
    # 第二层：CWE 编号（条件没命中才用）
    if action == "default":
        for c in cwes:
            if c in _CWE_ACTION:
                action = _CWE_ACTION[c]
                break
    return action


# ===========================================================================
# 4. 边界参数（action → 边界维度 + 合法域 + 非法域）
# ===========================================================================

@dataclass
class BoundaryParam:
    """一个漏洞的边界参数：边界在哪个维度、合法域、非法域（触发点）。"""
    dim: str            # 边界维度名
    action: str         # 来源 action
    legal_desc: str     # 合法域描述
    illegal_desc: str   # 非法域描述（触发点）


# action → 边界参数（源 B：漏洞知识驱动）
_ACTION_BOUNDARY: dict[str, BoundaryParam] = {
    "double_setup": BoundaryParam(
        dim="track_number", action="double_setup",
        legal_desc="对不同 track 分别 SETUP（track1≠track2，多轨会话）",
        illegal_desc="对同一 track 连续两次 SETUP（track1==track1，触发 Matroska UAF）",
    ),
    "interleave_seq": BoundaryParam(
        dim="transport_switch", action="interleave_seq",
        legal_desc="会话内传输方式保持一致（全 interleaved 或全普通）",
        illegal_desc="interleaved 与普通 SETUP 之间切换（触发 UAF）",
    ),
    "uaf_seq": BoundaryParam(
        dim="re_setup_after_teardown", action="uaf_seq",
        legal_desc="SETUP → TEARDOWN（终止会话，不重建）",
        illegal_desc="TEARDOWN 后再 SETUP（重建引用已释放资源，触发 UAF）",
    ),
    "lifecycle_seq": BoundaryParam(
        dim="session_rebuild", action="lifecycle_seq",
        legal_desc="建立会话 → 终止会话（不重建）",
        illegal_desc="终止会话后重建（触发 UAF）",
    ),
    "assert_seq": BoundaryParam(
        dim="repeated_setup_play", action="assert_seq",
        legal_desc="单次 SETUP + PLAY",
        illegal_desc="多次重复 SETUP/PLAY（触发断言）",
    ),
    "replay_seq": BoundaryParam(
        dim="cseq_dup", action="replay_seq",
        legal_desc="CSeq 递增",
        illegal_desc="连续相同 CSeq（触发重放）",
    ),
}


def _load_vuln_config(protocol: str) -> dict:
    """从 profile.json 读 vuln 段，返回协议特定漏洞知识（缺失回退硬编码默认）。

    通用层保留 CWE→action（_CWE_ACTION，跨协议通用漏洞类型）+ 通用触发关键词 +
    字段归一化框架；协议特定漏洞知识（流名映射、崩溃流、UAF 边界）归 profile 的
    vuln 段，换协议从 profile 提供（缺失回退 RTSP 硬编码默认，向后兼容）。
    """
    cfg = {
        "stream_hints": list(_STREAM_HINT_MAP),
        "crash_streams": set(_CRASH_STREAMS),
        "action_boundary": dict(_ACTION_BOUNDARY),
    }
    prof = paths.target_profile(protocol)
    if not prof.exists():
        return cfg
    try:
        import json
        data = json.loads(prof.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return cfg
    vuln = data.get("vuln")
    if not isinstance(vuln, dict):
        return cfg
    sh = vuln.get("stream_hints")
    if isinstance(sh, list):
        hints = []
        for item in sh:
            if (isinstance(item, list) and len(item) == 2
                    and item[0] and isinstance(item[1], list)):
                hints.append((str(item[0]), [str(s) for s in item[1]]))
        if hints:
            cfg["stream_hints"] = hints
    cs = vuln.get("crash_streams")
    if isinstance(cs, list):
        cfg["crash_streams"] = {str(x) for x in cs}
    ab = vuln.get("action_boundary")
    if isinstance(ab, dict):
        for action, b in ab.items():
            if isinstance(b, dict) and b.get("dim"):
                cfg["action_boundary"][str(action)] = BoundaryParam(
                    dim=str(b["dim"]), action=str(action),
                    legal_desc=str(b.get("legal", "")),
                    illegal_desc=str(b.get("illegal", "")))
    return cfg


def boundary_for_action(action: str, protocol: str = "rtsp") -> Optional[BoundaryParam]:
    """action → 边界参数；未映射的 action 返回 None（边界来自 profile 的 vuln 段）。"""
    return _load_vuln_config(protocol)["action_boundary"].get(action)


# ===========================================================================
# 5. 漏洞模式抽取（rule 部分，零 LLM）
# ===========================================================================

def _field_values(field_value) -> list[str]:
    """trigger.field.value 可能是 str / list / None，统一成归一化后的 list[str]。"""
    if field_value is None:
        return []
    if isinstance(field_value, list):
        return [normalize_field(x) for x in field_value
                if normalize_field(x)]
    s = normalize_field(field_value)
    return [s] if s else []


def extract_vuln_pattern(entry: dict, protocol: str = "rtsp") -> Optional[dict]:
    """从单个 CVE JSON 抽取漏洞模式（rule 部分，零 LLM）。

    返回 vuln_pattern dict（无 method/field 锚点或 scope!=seedgen 返回 None）：

      {
        "action":           "double_setup",              # 边界动作
        "trigger_sequence": ["SETUP", "PLAY"],           # 触发消息序列（Phase 1 仅方法锚点）
        "trigger_field":    "track",                     # 触发字段（归一化，可空）
        "boundary":         {dim, legal, illegal} | None,  # 边界参数（仅已映射 action）
        "cwe":              "CWE-416 (释放后使用)",
        "streams":          ["matroskaFileTest"],        # 触发流
        "mutation_hint":    "多个 SETUP 和 PLAY 命令",    # 变异提示（Phase 1 仅条件原文）
      }
    """
    if entry.get("scope") != "seedgen":
        return None
    trig = entry.get("trigger", {}) or {}
    mval = (trig.get("method") or {}).get("value") or []
    methods = [str(m).strip() for m in (mval if isinstance(mval, list) else [mval])
               if str(m).strip()]
    fields = _field_values((trig.get("field") or {}).get("value"))
    condition = str((trig.get("condition") or {}).get("value") or "").strip()
    desc = str(entry.get("description_raw") or "").strip()
    cwe = str(entry.get("cwe_avd") or "").strip()

    # 必须有 method 或 field 锚点
    if not methods and not fields:
        return None

    action = classify_action(cwe, condition, desc)
    boundary = boundary_for_action(action, protocol)

    return {
        "action": action,
        "trigger_sequence": methods,              # Phase 1 仅方法锚点（Phase 2 LLM 补全）
        "trigger_field": fields[0] if fields else "",
        "boundary": {
            "dim": boundary.dim,
            "legal": boundary.legal_desc,
            "illegal": boundary.illegal_desc,
        } if boundary is not None else None,
        "cwe": cwe,
        "streams": extract_stream_hints(f"{condition} {desc}", protocol),
        "mutation_hint": condition,               # Phase 1 仅条件原文（Phase 2 LLM 补全）
    }


# ===========================================================================
# 6. LLM 补全（Phase 2）：trigger_sequence + mutation_hint
# ===========================================================================

_PROMPT_TRIGGER_SEQUENCE = """你是 {protocol} 协议漏洞分析专家。
给定一条历史漏洞的「触发方法锚点 + 触发条件 + 描述」，推断触发该漏洞的完整请求消息序列
（含前置方法，用协议方法名列表表示，如 ["DESCRIBE","SETUP","SETUP"]）。

- 触发方法锚点: {methods}
- 触发条件: {condition}
- 漏洞描述: {description}

只输出 JSON（不要解释）：
{{"sequence": ["METHOD1", "METHOD2", ...]}}
若无法推断，输出 {{"sequence": []}}。"""


_PROMPT_MUTATION_HINT = """你是 {protocol} 协议漏洞分析专家。
给定一条历史漏洞的「CWE 类型 + 触发条件 + 描述」，提炼一句「变异提示」——该漏洞靠什么
字段/序列的哪类变异触发（供 fuzzer 定向变异）。

- CWE: {cwe}
- 触发条件: {condition}
- 漏洞描述: {description}

只输出 JSON（不要解释）：
{{"hint": "一句话变异提示"}}"""


def infer_trigger_sequence(protocol: str, methods: list[str], condition: str,
                           description: str, llm) -> list[str]:
    """LLM 补全触发消息序列（含前置方法）。失败返回 []（调用方保留 rule 锚点）。"""
    try:
        r = llm.chat_json(
            system="你输出 JSON。",
            user=_PROMPT_TRIGGER_SEQUENCE.format(
                protocol=protocol.upper(),
                methods=", ".join(methods) or "(无)",
                condition=condition or "(无)",
                description=(description or "")[:500]),
            temperature=0.2, max_tokens=500)
        if isinstance(r, dict):
            seq = r.get("sequence") or []
            return [str(m).strip().upper() for m in seq if str(m).strip()]
    except Exception:
        pass
    return []


def infer_mutation_hint(protocol: str, cwe: str, condition: str,
                        description: str, llm) -> str:
    """LLM 提炼变异提示。失败返回 ""（调用方保留 rule 的条件原文）。"""
    try:
        r = llm.chat_json(
            system="你输出 JSON。",
            user=_PROMPT_MUTATION_HINT.format(
                protocol=protocol.upper(),
                cwe=cwe or "(无)",
                condition=condition or "(无)",
                description=(description or "")[:500]),
            temperature=0.2, max_tokens=300)
        if isinstance(r, dict):
            return (r.get("hint") or "").strip()
    except Exception:
        pass
    return ""


def complete_vuln_pattern(entry: dict, protocol: str = "rtsp", llm=None) -> Optional[dict]:
    """rule 抽取 + LLM 补全 trigger_sequence / mutation_hint（Phase 2）。

    llm 为 None 或 LLM 调用失败时，返回 rule 抽取的锚点模式（降级不丢失）。
    """
    pat = extract_vuln_pattern(entry, protocol)
    if pat is None or llm is None:
        return pat
    seq = infer_trigger_sequence(protocol, pat["trigger_sequence"],
                                 pat["mutation_hint"],
                                 entry.get("description_raw", ""), llm)
    if seq:
        pat["trigger_sequence"] = seq
    hint = infer_mutation_hint(protocol, pat["cwe"], pat["mutation_hint"],
                               entry.get("description_raw", ""), llm)
    if hint:
        pat["mutation_hint"] = hint
    return pat


__all__ = [
    "BoundaryParam",
    "normalize_field",
    "extract_stream_hints",
    "crash_streams",
    "classify_action",
    "boundary_for_action",
    "extract_vuln_pattern",
    "infer_trigger_sequence",
    "infer_mutation_hint",
    "complete_vuln_pattern",
    # 供 strategy/boundary_probe 复用的原始表（向后兼容）
    "_FIELD_ALIAS",
    "_STREAM_HINT_MAP",
    "_CRASH_STREAMS",
    "_CWE_ACTION",
    "_COND_KEYWORD_ACTION",
    "_ACTION_BOUNDARY",
]
