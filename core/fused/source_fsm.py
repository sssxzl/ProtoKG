"""DEPRECATED（2026-10-19）：已被 core/fused/source_autoseeder.py（AutoSeeder 方法）替代。

core/fused/source_fsm.py —— 从协议实现源码推断状态机（LLM，ProtocolGPT 思路）。

协议无关引擎 + 协议 Profile：从 core.fused.protocol_patterns 读取协议的状态机信号
pattern（消息处理函数名 + 状态变量名），提取信号后 LLM 推断状态机。
设计（历史）: 引擎调用 get_pattern(protocol) 读取 protocol_patterns 配置…

设计依据: docs/设计/源码知识抽取设计.md（ProtocolGPT / STCFuzz 思路）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from core.fused.models import Subject, Value, Fact
from core.fused.source import _make_fact
from core.fused.protocol_patterns import get_pattern

#: 非消息类型的辅助函数（RTSP handleCmd_xxx 里的错误/内部回调），过滤掉
#: TODO: 后续可把各协议的非消息过滤集也移入 protocol_patterns.py
_NON_METHOD = {
    "afterLookup", "bad", "notFound", "notSupported", "redirect",
    "sessionNotFound", "unsupportedTransport", "withinSession",
}

#: 源码文件后缀白名单（实现 + 头文件），状态机信号也可能声明在头文件里
_SRC_EXTS = (".cpp", ".cc", ".cxx", ".c", ".hh", ".hpp", ".h")


def _extract_protocol_signals(src_dir: Path, protocol: str = "rtsp") -> dict:
    """从源码提取协议信号：命令处理函数名（消息类型）+ 状态变量名（状态线索）。

    协议无关：pattern 从 protocol_patterns.get_pattern(protocol) 读取，
    本函数不硬编码任何协议方法名/状态名。换协议只改 protocol_patterns.py。

    文件级粗筛用 fsm_marker（ProtocolGPT code_filter 思路）：只扫命中状态机
    标记的文件，跳过 IO/日志/工具等无关文件，降低 LLM 输入噪声。
    """
    pat = get_pattern(protocol)
    method_re = re.compile(pat["method_handler"])
    state_var_re = re.compile(pat["state_vars"])
    marker_re = re.compile(pat["fsm_marker"]) if pat.get("fsm_marker") else None

    files = sorted(f for f in src_dir.glob("*") if f.suffix in _SRC_EXTS)
    texts: list[str] = []
    for f in files:
        try:
            texts.append(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            texts.append("")

    # 文件级粗筛：只保留命中 fsm_marker 的状态机相关文件；
    # 若 marker 过严导致全不命中，回退全量（安全网，避免空结果）。
    if marker_re:
        kept = [t for t in texts if marker_re.search(t)]
        if kept:
            texts = kept

    methods: set[str] = set()
    state_hints: set[str] = set()
    for text in texts:
        for m in method_re.finditer(text):
            name = m.group(1)
            if "afterLookup" in name:
                continue
            base = name.split("_")[-1]
            if base in _NON_METHOD:
                continue
            methods.add(base)
        for m in state_var_re.finditer(text):
            state_hints.add(m.group(0))
    return {"methods": sorted(methods), "state_hints": sorted(state_hints)}


def _llm_infer_fsm(signals: dict, protocol: str = "rtsp") -> dict:
    """LLM 推断状态机：状态集合 + 状态转移（from --method--> to）。"""
    from core.llm import DeepSeekClient
    llm = DeepSeekClient()
    system = (
        "你是网络协议逆向专家，擅长从协议服务端实现的源码推断协议状态机（FSM）。\n"
        "给定「命令处理函数名（对应消息类型/方法）」和「状态相关变量名」，请推断：\n"
        "① 协议有哪些状态（state，用简洁英文，如 Init/Ready/Playing）；\n"
        "② 状态转移三元组（from_state --method--> to_state，method 用消息类型大写）。\n"
        "仅依据给定的方法名与状态变量名推断，不要引入任何协议特化的先验知识。"
        "只输出 JSON，不要解释。"
    )
    user = (
        f"协议 {protocol.upper()} 服务端源码提取的信号：\n"
        f"消息类型（方法）: {json.dumps(signals['methods'], ensure_ascii=False)}\n"
        f"状态变量名: {json.dumps(signals['state_hints'], ensure_ascii=False)}\n\n"
        "请输出 JSON：\n"
        '{"states": ["状态1", "状态2", ...], '
        '"transitions": [{"from": "状态A", "method": "方法", "to": "状态B"}, ...]}'
    )
    try:
        return llm.chat_json(system=system, user=user)
    except Exception:
        return {}


def infer_fsm_facts(protocol: str = "rtsp") -> list[Fact]:
    """Step2: 从协议实现源码推断状态机，产出 relation+target_state fact（transition）。"""
    src_dir = Path("kb") / "协议实现源码"
    signals = _extract_protocol_signals(src_dir, protocol)
    if not signals.get("methods"):
        return []
    result = _llm_infer_fsm(signals, protocol)
    facts: list[Fact] = []
    for t in result.get("transitions", []):
        src = (t.get("from") or "").strip()
        dst = (t.get("to") or "").strip()
        method = (t.get("method") or "").strip().upper()
        if not (src and dst and method):
            continue
        norm = {"protocol": protocol, "kb_source_type": "source",
                "source": "file:协议实现源码",
                "norm_id": f"source.fsm.{src}.{method}.{dst}"}
        facts.append(_make_fact(
            Subject(type="relation", name="transitions_to", qualifiers={
                "source": Subject(type="state", name=src),
                "target": Subject(type="state", name=dst),
                "method": Subject(type="method", name=method),
            }),
            Value(type="text", data=dst), norm, "协议实现源码", aspect="target_state"))
    return facts
