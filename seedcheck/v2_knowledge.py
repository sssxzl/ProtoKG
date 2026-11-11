# -*- coding: utf-8 -*-
"""seedcheck/v2_knowledge.py —— **V2 知识一致**（判据全部来自中枢）。

★ 处置：**只打标，不阻断**
  「违反协议」恰恰是 fuzzing 最有价值的输入面（服务器可能报错、可能崩溃）
  ⇒ 丢弃它等于主动扔掉可能触发解析缺陷的输入 ⇒ 与 fuzzing 目的矛盾。

★ 6 项检查（判据来源全部是中枢维度 ⇒ 协议知识一变，口径自动跟着变）
  ┌────────────────────────┬──────────────────────────────┐
  │ 检查                    │ 判据来源（中枢维度）            │
  ├────────────────────────┼──────────────────────────────┤
  │ 必填头齐全              │ required_header_by_method      │
  │                        │ required_header_global        │
  │ 方法存在                │ existence（method 主体）        │
  │ 前置链有序              │ precondition                   │
  │ 会话语义（第 N 次起带头） │ session_header                 │
  │ URI 形态                │ url_template                   │
  │ 取值合法                │ value_enum_spec（规范取值域）    │
  └────────────────────────┴──────────────────────────────┘
"""
from __future__ import annotations

import re

from .knowledge import Knowledge
from .model import SeedRecord, Violation


def _value_pattern(v: str) -> str:
    """把值里的**数字**归一（``client_port=46902-46903`` → ``client_port=<N>-<N>``）。

    ★ 用途：规范域抽到的是**示例值** ⇒ 种子用**同构但参数不同**的值（端口号、
      会话 id…）**同样合法** ⇒ 归一后比对才能区分「合法变体」与「真越界」。
    """
    # 归一「**含数字的 token**」整体（不只纯数字）
    #   · ``107518505``      ⇒ ``<N>``
    #   · ``000022B8``（十六进制会话 id）⇒ ``<N>``（若只归一纯数字会留下 ``<N>B8`` ⇒ 比不上）
    #   · ``RTP/AVP``（无数字）⇒ 原样
    return re.sub(r"\b(?=\w*\d)\w+\b", "<N>", str(v))


def _resource_of(uri: str) -> str:
    """从 URI 取资源名（末段；``/trackN`` 归到它的流）。"""
    if not uri:
        return ""
    path = uri.split("://", 1)[-1]
    path = path.split("/", 1)[1] if "/" in path else ""
    segs = [s for s in path.split("/") if s]
    if not segs:
        return ""
    # ★ 2026-11-11 修正：末段若是 ``trackN`` ⇒ 资源名是**它前面那段**（流名）
    #   （``/mp3AudioTest/track1`` ⇒ ``mp3AudioTest`` ⇒ 不是 ``track1``）
    if len(segs) >= 2 and segs[-1].lower().startswith("track"):
        return segs[-2]
    return segs[0]


def _required_for(k: Knowledge, method: str) -> list[str]:
    """某方法的必填头（方法级 + 全局级）。"""
    heads = list(k.required_headers.get(method) or [])
    heads += list(k.required_headers.get("*") or [])
    heads += list(k.required_headers.get("__global__") or [])
    return sorted({str(h) for h in heads})


def check(seed: SeedRecord, k: Knowledge) -> list[Violation]:
    """V2 检查 ⇒ 违规列表（打标）。"""
    out: list[Violation] = []
    fn = seed.filename

    # ---- 逐报文 ----
    seen_methods: list[str] = []
    for i, m in enumerate(seed.messages, 1):
        meth = m.get("method", "")
        uri = m.get("uri", "")
        headers = {str(k).lower(): str(v) for k, v in (m.get("headers") or {}).items()}
        seen_methods.append(meth)

        # ① 必填头齐全
        need = _required_for(k, meth)
        missing = [h for h in need if h.lower() not in headers]
        if missing:
            out.append(Violation(
                "V2", "missing_required_header",
                f"第 {i} 个报文（{meth}）缺必填头：{', '.join(missing)}",
                fn, meth, f"required_header_by_method[{meth}]"))

        # ② 方法存在性
        if k.known_methods and meth and meth not in k.known_methods:
            out.append(Violation(
                "V2", "unknown_method",
                f"第 {i} 个报文的方法 {meth} 不在已知方法集合里",
                fn, meth, "existence（method 主体）"))

        # ③ URI 的**资源段** ∈ 协议档案声明的资源清单
        #   ★ 2026-11-11 修正：原判据「URI 含模板占位符名」**不成立**
        #     （``{stream}`` 已被替换成实际资源名 ⇒ 占位符名不会出现在 URI 里）
        #   ⇒ 改为可比对的判据：**资源段 ∈ resources_file 的资源清单**
        if k.resources and uri:
            res = _resource_of(uri)
            if res and res not in set(k.resources):
                out.append(Violation(
                    "V2", "unknown_resource",
                    f"第 {i} 个报文（{meth}）的 URI 资源段 {res} 不在协议资源清单里",
                    fn, res, "profile.resources_file"))

        # ④ 取值合法（值 ∈ 规范取值域）
        #   ★ 2026-11-11 修正：**同构变体**不算违规
        #     规范域抽到的是**示例值**（如 ``client_port=46902-46903``）
        #     而种子用 ``client_port=50000-50001``（**同样合法**）
        #     ⇒ 直接判「不在域内」会产生大量**误报**
        #   ⇒ 改为：把数字归一（``46902`` → ``<N>``）后比对 ⇒ 结构相同 ⇒ 视为同构变体
        for hname, hval in headers.items():
            domain = k.domain_of(hname)
            if not domain or not hval:
                continue
            if hval in domain:
                continue
            pat = _value_pattern(hval)
            if any(_value_pattern(x) == pat for x in domain):
                # 同构变体（端口号/会话 id 等参数不同）⇒ **合法**，不报违规
                continue
            out.append(Violation(
                "V2", "value_outside_domain",
                f"第 {i} 个报文的头 {hname} 的值不在规范取值域内：{hval[:40]}",
                fn, hname, f"value_enum_spec[{hname}]（{len(domain)} 个合法值）"))

    # ---- 跨报文 ----
    # ⑤ 前置链有序
    for i, meth in enumerate(seen_methods):
        pres = k.precondition.get(meth) or []
        if not pres:
            continue
        prior = set(seen_methods[:i])
        missing_pre = [p for p in pres if p not in prior]
        if missing_pre:
            out.append(Violation(
                "V2", "missing_precondition",
                f"第 {i + 1} 个报文（{meth}）的前置方法未出现：{', '.join(missing_pre)}",
                fn, meth, f"precondition[{meth}]"))

    # ⑥ 会话语义（第 N 次出现起要带某头）
    counts: dict[str, int] = {}
    for i, m in enumerate(seed.messages, 1):
        meth = m.get("method", "")
        counts[meth] = counts.get(meth, 0) + 1
        nth = counts[meth]
        headers = {str(k).lower(): str(v) for k, v in (m.get("headers") or {}).items()}
        for rule in (k.session_header.get(meth) or []):
            if not isinstance(rule, dict):
                continue
            hname = str(rule.get("header") or "")
            from_nth = int(rule.get("from_occurrence") or 1)
            if not hname or nth < from_nth:
                continue
            if hname.lower() not in headers:
                out.append(Violation(
                    "V2", "missing_session_header",
                    f"第 {i} 个报文（{meth} 第 {nth} 次）应带会话头 {hname}",
                    fn, hname, f"session_header[{meth}].from_occurrence={from_nth}"))
    return out
