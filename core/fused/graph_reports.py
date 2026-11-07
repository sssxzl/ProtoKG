# -*- coding: utf-8 -*-
"""core/fused/graph_reports.py —— Phase B2.5：**社区报告**（2026-11-08 新增）。

★ GraphRAG 的社区报告 = 「**跨段落的高层描述**」：
  微软原论文用它替代「chunk 向量 top-k」做检索 ⇒
  我们用它做**检索层的粗排**（细排仍是子图/精确事实）。

★ 本模块的三个特色：
  ① **带知识通道标注**（``owner_mix`` / ``class``）⇒ 社区视图能按 L1/L2 分层；
  ② **磁盘缓存**（键 = 社区成员 + 边的 hash）⇒ 同输入同输出（可复现）；
  ③ **LLM 不可用时不阻断**（降级为**确定性摘要**）。

★ 与知识通道台账（``core/knowledge_channels.py``）的关系：
  台账管「这条知识属不属于本次源集合」；本模块管「这个**社区**的构成如何」。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from core.fused.graph_ops import (community_class, community_owner_mix,
                                   detect_communities, merge_multidigraph,
                                   split_by_graph)

#: 社区报告的 prompt 版本（并入缓存键 ⇒ 改 prompt 必须升版）
COMMUNITY_REPORT_PROMPT_VERSION = "community-report-v1"


# ===========================================================================
# 社区摘要的**输入**构造
# ===========================================================================

def build_community_inputs(protocol: str) -> list[dict[str, Any]]:
    """从**已落盘的图**构造每个社区的摘要输入。

    Returns:
        ``[{"community_id":..., "members":[...], "edges":[...], "owner_mix":{...},
        "class":..., "facts":[...], "hash":...}, ...]``
    """
    from core.fused.graph_ops import read_graph
    nodes, edges = read_graph(protocol)
    sn, se = split_by_graph(nodes, edges, "semantic")
    mn, me = merge_multidigraph(sn, se)
    comms, algo = detect_communities(mn, me)
    by_id = {n["node_id"]: n for n in mn}

    out: list[dict[str, Any]] = []
    for i, members in enumerate(comms):
        mset = set(members)
        c_edges = [e for e in me
                   if e.get("from") in mset or e.get("to") in mset]
        mix = community_owner_mix(members, mn, me)
        # 社区内边的类型分布（报告的输入之一）
        edge_types: dict[str, int] = {}
        for e in c_edges:
            t = str(e.get("type"))
            edge_types[t] = edge_types.get(t, 0) + 1
        # 成员的事实摘要（节点名 + 类型 + 定义/取值线索）
        facts: list[str] = []
        for nid in members:
            n = by_id.get(nid)
            if not n:
                continue
            line = f"- [{n.get('type')}] {n.get('name')}"
            if n.get("definition"):
                line += f"：{str(n['definition'])[:80]}"
            elif n.get("syntax"):
                line += f"：{str(n['syntax'])[:80]}"
            facts.append(line)
        # 缓存键：成员 + 边 + prompt 版本 ⇒ 同输入同输出
        h = hashlib.sha256()
        h.update(COMMUNITY_REPORT_PROMPT_VERSION.encode("utf-8"))
        for nid in sorted(members):
            h.update(nid.encode("utf-8"))
        for e in sorted(c_edges, key=lambda x: (x.get("type", ""),
                                               x.get("from", ""),
                                               x.get("to", ""))):
            h.update(f"{e.get('type')}|{e.get('from')}|{e.get('to')}".encode())
        out.append({
            "community_id": f"c{i}",
            "members": list(members),
            "member_count": len(members),
            "edge_count": len(c_edges),
            "edge_types": dict(sorted(edge_types.items(), key=lambda kv: -kv[1])),
            "owner_mix": mix,
            "class": community_class(mix),
            "facts": facts,
            "algorithm": algo,
            "hash": h.hexdigest()[:16],
        })
    return out


# ===========================================================================
# 社区报告生成（LLM + 缓存 + 降级）
# ===========================================================================

_PROMPT_COMMUNITY = """你是协议规范分析助手。下面是某个协议知识图谱里的**一个社区**的成员清单。

协议：{protocol}
社区包含 {n} 个实体，关联 {e} 条关系。

实体清单：
{facts}

请写一段**社区报告**，说明这个社区讲的是什么（2-4 句，中文）。
要求：
1. 说明这个社区覆盖了协议知识的哪个方面（如「会话建立相关的方法与头字段」）。
2. 点出成员之间的**典型关系**（如「哪些字段是该方法必须携带的」）。
3. **不要**逐个罗列实体名；不要编造清单里没有的信息。

输出 JSON：{{"summary": "<报告正文>"}}
"""


def _fallback_summary(item: dict[str, Any]) -> str:
    """**确定性摘要**（LLM 不可用时的降级，不编造内容）。"""
    et = item.get("edge_types") or {}
    rel = "、".join(f"{k}×{v}" for k, v in list(et.items())[:4]) or "无关联边"
    return (f"该社区含 {item.get('member_count', 0)} 个实体、"
            f"{item.get('edge_count', 0)} 条关系（{rel}）；"
            f"知识层级 {item.get('class', 'L1')}"
            f"（来源构成 {item.get('owner_mix') or {}}）。")


def generate_community_reports(protocol: str,
                                use_llm: bool = True,
                                llm: Any = None) -> list[dict[str, Any]]:
    """生成社区报告（LLM + 磁盘缓存 + 确定性降级）。

    ★ **不阻断**：LLM 不可用 / 调用失败 ⇒ 用确定性摘要（仍产出社区）。
    """
    from core.fused.source_retrieval import CACHE_DIR
    cache_file = CACHE_DIR / f"{protocol}.community_reports.json"
    cache: dict[str, Any] = {}
    try:
        if cache_file.is_file():
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        cache = {}
    if not isinstance(cache, dict):
        cache = {}

    if use_llm and llm is None:
        try:
            from core.llm import DeepSeekClient
            llm = DeepSeekClient()
        except Exception:                       # noqa: BLE001
            llm = None

    items = build_community_inputs(protocol)
    reports: list[dict[str, Any]] = []
    cache_dirty = False
    for item in items:
        h = item["hash"]
        summary = ""
        source = "fallback"
        if h in cache and isinstance(cache.get(h), str) and cache[h]:
            summary = cache[h]                       # ★ 命中缓存 ⇒ 不调 LLM
            source = "cache"
        elif llm is not None:
            try:
                r = llm.chat_json(
                    system="你输出 JSON。",
                    user=_PROMPT_COMMUNITY.format(
                        protocol=protocol.upper(),
                        n=item["member_count"], e=item["edge_count"],
                        facts="\n".join(item["facts"][:120])),
                    temperature=0.0, max_tokens=800)
                if isinstance(r, dict) and isinstance(r.get("summary"), str):
                    summary = r["summary"].strip()
                    source = "llm"
                    cache[h] = summary
                    cache_dirty = True
            except Exception:                   # noqa: BLE001
                summary = ""
        if not summary:
            summary = _fallback_summary(item)
            source = "fallback" if source != "cache" else source
        row = dict(item)
        row["summary"] = summary
        row["summary_source"] = source
        reports.append(row)

    if cache_dirty:
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(cache, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
        except OSError:
            pass
    return reports


def write_communities(protocol: str, reports: list[dict[str, Any]]) -> Path:
    """把社区报告落盘到 ``derived/per_source/<协议>/graph/communities.json``。"""
    from core.fused.graph_ops import graph_dir
    d = graph_dir(protocol)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "communities.json"
    p.write_text(json.dumps({
        "protocol": protocol,
        "prompt_version": COMMUNITY_REPORT_PROMPT_VERSION,
        "community_count": len(reports),
        "communities": reports,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


def read_communities(protocol: str) -> list[dict[str, Any]]:
    """读回落盘的社区报告。"""
    from core.fused.graph_ops import graph_dir
    p = graph_dir(protocol) / "communities.json"
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return data.get("communities") or []


__all__ = [
    "COMMUNITY_REPORT_PROMPT_VERSION",
    "build_community_inputs", "generate_community_reports",
    "write_communities", "read_communities",
]
