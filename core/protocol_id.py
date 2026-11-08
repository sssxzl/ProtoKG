# -*- coding: utf-8 -*-
"""core/protocol_id.py —— **目标协议识别**（2026-11-08 新增）。

★ 用户要求（中枢重设计）：
  「每次运行前对目标协议进行识别（可以通过调用 LLM 进行判断），
    然后传参给我这个项目模型」
  ⇒ 本模块把「**自然语言/目录/文件名 ⇒ 协议名**」这件事**独立出来**，
    识别结果作为**参数**传给中枢构建 / 建图 / 种子生成。

★ 两级策略（**规则优先，LLM 兜底**）：
  ① **规则**：已知协议的**特征词**（全名/别名/典型报文特征）匹配
     ⇒ 零成本、确定、可复现；
  ② **LLM**：规则无法判定时 ⇒ 把候选集 + 输入交给 LLM 判断
     ⇒ 应对「描述性输入」（如「那个用 UDP 做地址分配的协议」）。

★ **协议清单从资产目录推导**（``fused_hub/targets/<协议>/``）
  ⇒ 加协议只加资产，不改本文件。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

#: 已知协议的**特征词**（协议无关的通用机制；协议清单从资产目录推导）
#: ★ 这里只放**别名与典型特征**（识别用），不是协议知识
_ALIASES: dict[str, tuple[str, ...]] = {
    "rtsp": ("rtsp", "real time streaming protocol", "实时流传输协议",
             "rtsp/1.0", "setup play teardown"),
    "sip": ("sip", "session initiation protocol", "会话初始协议",
            "sip/2.0", "invite register subscribe"),
    "smtp": ("smtp", "simple mail transfer protocol", "简单邮件传输协议",
             "ehlo mail rcpt", "smtp/1."),
    "dhcpv4": ("dhcp", "dhcpv4", "dynamic host configuration protocol",
               "动态主机配置协议", "dhcpdiscover", "dhcpoffer", "dhcpack",
               "bootp"),
    "ftp": ("ftp", "file transfer protocol", "文件传输协议"),
}


def known_protocols() -> list[str]:
    """**已知协议清单**（从资产目录 ``fused_hub/targets/<协议>/`` 推导）。"""
    from core import paths
    root = paths.PROJECT_ROOT / "fused_hub" / "targets"
    if not root.is_dir():
        return []
    out = []
    for d in sorted(root.iterdir()):
        if not d.is_dir():
            continue
        if (d / "profile.json").is_file():
            out.append(d.name.lower())
    return out


def _norm(text: str) -> str:
    """归一：小写 + 折叠空白。"""
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def identify_by_rules(text: str) -> list[tuple[str, int]]:
    """规则识别 ⇒ ``[(协议, 命中数), ...]``（按命中数降序）。

    ★ 判据：协议名/别名在输入里**作为词**出现；
      或命中「协议名 + 特征词」的组合。
    """
    t = _norm(text)
    if not t:
        return []
    scores: dict[str, int] = {}
    for proto, aliases in _ALIASES.items():
        hit = 0
        for al in aliases:
            a = _norm(al)
            if not a:
                continue
            if re.search(r"(?<![a-z0-9])" + re.escape(a) + r"(?![a-z0-9])", t):
                hit += 2 if a == proto else 1
        if hit:
            scores[proto] = hit
    # 资产目录里存在才算数（避免识别到未配置的协议）
    known = set(known_protocols())
    scored = [(p, s) for p, s in scores.items() if p in known]
    if not scored:
        scored = sorted(scores.items(), key=lambda kv: -kv[1])
    return sorted(scored, key=lambda kv: -kv[1])


def identify_by_llm(text: str, candidates: Optional[list[str]] = None,
                    llm: Any = None) -> Optional[str]:
    """LLM 识别（规则无结果时的兜底）。

    ★ **无 LLM / 调用失败 ⇒ 返回 None**（不臆造）。
    ★ 输出必须是候选集里的协议名，否则视为无效。
    """
    cands = list(candidates or known_protocols())
    if not cands or not str(text or "").strip():
        return None
    if llm is None:
        try:
            from core.llm import DeepSeekClient
            llm = DeepSeekClient()
        except Exception:                       # noqa: BLE001
            return None
    try:
        res = llm.chat_json(
            system="你输出 JSON。",
            user=("下面是一段协议相关的描述。请判断它指的是哪个协议，"
                  "只从候选列表里选一个。\n"
                  f"候选：{', '.join(cands)}\n"
                  f"描述：{str(text)[:800]}\n"
                  '输出 JSON：{"protocol": "<候选之一>"}'),
            temperature=0.0, max_tokens=200)
    except Exception:                           # noqa: BLE001
        return None
    if not isinstance(res, dict):
        return None
    got = str(res.get("protocol") or "").strip().lower()
    return got if got in {str(c).lower() for c in cands} else None


def identify_protocol(text: str, *, use_llm: bool = True,
                      llm: Any = None) -> dict[str, Any]:
    """**目标协议识别**（规则优先 + LLM 兜底）。

    Returns:
        ``{"protocol": "dhcpv4" | "", "method": "rule"|"llm"|"",
           "scores": [...], "candidates": [...], "note": str}``
        ★ ``protocol`` 为空串 ⇒ **无法判定**（不猜）。
    """
    scores = identify_by_rules(text)
    if scores:
        best = scores[0]
        if len(scores) == 1 or best[1] > scores[1][1]:
            return {"protocol": best[0], "method": "rule", "scores": scores,
                    "candidates": known_protocols(),
                    "note": f"规则命中（{best[1]} 分）"}
    if use_llm:
        got = identify_by_llm(text, llm=llm)
        if got:
            return {"protocol": got, "method": "llm", "scores": scores,
                    "candidates": known_protocols(),
                    "note": "规则未唯一命中 ⇒ LLM 判定"}
    return {"protocol": "", "method": "", "scores": scores,
            "candidates": known_protocols(),
            "note": "无法判定（规则未命中且 LLM 不可用/无效）"}


def identify_from_path(path: str | Path) -> str:
    """从目录/文件路径里识别协议（如 ``kb/dhcpv4/spec/rfc2131.txt``）。"""
    p = Path(str(path))
    for part in reversed([x.lower() for x in p.parts]):
        if part in _ALIASES:
            return part
    stem = re.sub(r"[^a-z0-9]+", "", p.stem.lower())
    for proto in known_protocols():
        if re.sub(r"[^a-z0-9]+", "", proto) in stem:
            return proto
    return ""


__all__ = [
    "known_protocols", "identify_by_rules", "identify_by_llm",
    "identify_protocol", "identify_from_path",
]
