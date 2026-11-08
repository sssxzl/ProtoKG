# -*- coding: utf-8 -*-
"""core/fused/hub_entities.py —— 中枢的**实体主表**与诊断矩阵（2026-11-08 新增）。

★ 解决诊断出的 **P2**（中枢没有实体概念 ⇒ 同一实体散在多个 aspect）
  与 **P3**（图与中枢各造名字 ⇒ 对不齐）。

★ 实体主表（``index/entities.jsonl``）：
  协议里有哪些**东西**（方法/字段/状态/消息/选项/定时器/角色…）。
  ★ **跨分类的唯一索引** ⇒ 事实/关系/规则/图全部引用同一 ``entity_id``。

★ 诊断矩阵：
  · **实体 × 分类矩阵** —— 谁在多个分类里重复、谁只在一个分类里（信息不全）；
  · **实体 × aspect 明细** —— 同一实体的属性散落在哪些 aspect。
"""
from __future__ import annotations

import collections
import json
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from core.fused.knowledge_slots import locate

#: 实体 id 的分隔符
_SEP = ":"


# ===========================================================================
# 实体 id 生成
# ===========================================================================

def entity_id(protocol: str, etype: str, name: str) -> str:
    """生成实体 id：``<protocol>:<type>:<规范化名>``。

    ★ **跨源稳定**：同一实体在任何源、任何构建里都是同一个 id
      ⇒ 图、事实、规则可互相对齐。
    """
    p = str(protocol or "").strip().lower()
    t = str(etype or "").strip().lower()
    n = re.sub(r"\s+", "_", str(name or "").strip()).lower()
    return f"{p}{_SEP}{t}{_SEP}{n}"


def parse_entity_id(eid: str) -> tuple[str, str, str]:
    """解析实体 id ⇒ ``(protocol, type, name)``。"""
    parts = str(eid or "").split(_SEP)
    if len(parts) < 3:
        return ("", "", str(eid or ""))
    protocol = parts[0]
    etype = parts[1]
    name = _SEP.join(parts[2:])
    return (protocol, etype, name)


# ===========================================================================
# 实体主表
# ===========================================================================

def build_entity_index(facts: Iterable[dict[str, Any]]
                       ) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
    """从一批 fact 构造**实体主表** + **实体 × aspect 明细**。

    Args:
        facts: fact 列表（每条含 ``fact_key``）。

    Returns:
        ``(entities, entity_aspects)``
        · ``entities``：实体主表（按 id 排序，**逐字节可复现**）；
        · ``entity_aspects``：``entity_id -> [aspect, ...]``。
    """
    ents: dict[str, dict[str, Any]] = {}
    ent_aspects: dict[str, list[str]] = collections.defaultdict(list)

    for f in facts:
        fk = f.get("fact_key") or {}
        subject = fk.get("subject") or {}
        etype = str(subject.get("type") or "").strip().lower()
        name = str(subject.get("name") or "").strip()
        aspect = str(fk.get("aspect") or "")
        protocol = str(fk.get("protocol") or "")

        # ---- 关系型实体：三元组 ⇒ 独立实体 ----
        quals = subject.get("qualifiers") or {}
        if etype == "relation" and quals:
            _mk_relation_entity(ents, protocol, quals, aspect)
            # 关系的**端点**也登记为实体（供图与检索引用）
            for _k, _v in quals.items():
                if isinstance(_v, dict) and _v.get("name"):
                    _mk_entity(ents, protocol, _v.get("type") or "entity",
                               _v.get("name"))
            continue

        if not name:
            continue
        eid = entity_id(protocol, etype, name)
        _mk_entity(ents, protocol, etype, name)
        if aspect and aspect not in ent_aspects[eid]:
            ent_aspects[eid].append(aspect)

    out = [ents[k] for k in sorted(ents)]
    for k in ent_aspects:
        ent_aspects[k] = sorted(ent_aspects[k])
    return out, dict(ent_aspects)


def _mk_entity(ents: dict[str, dict], protocol: str, etype: str,
               name: str) -> str:
    """登记（或更新）一个实体，返回 entity_id。"""
    eid = entity_id(protocol, etype, name)
    if eid not in ents:
        ents[eid] = {
            "entity_id": eid,
            "protocol": str(protocol or "").strip().lower(),
            "type": str(etype or "").strip().lower(),
            "name": str(name or "").strip(),
            "canonical_name": str(name or "").strip(),
            "aliases": [],
        }
    return eid


def _mk_relation_entity(ents: dict[str, dict], protocol: str,
                        quals: dict[str, Any], aspect: str) -> str:
    """关系型实体：``source--method-->target`` ⇒ 一个独立实体。"""
    src = quals.get("source") or {}
    tgt = quals.get("target") or {}
    mth = quals.get("method") or {}
    s_name = str(src.get("name") or "")
    t_name = str(tgt.get("name") or "")
    m_name = str(mth.get("name") or "")
    rel_name = f"{s_name}--{m_name}-->{t_name}" if m_name else \
        f"{s_name}-->{t_name}"
    eid = entity_id(protocol, "relation", rel_name)
    if eid not in ents:
        ents[eid] = {
            "entity_id": eid,
            "protocol": str(protocol or "").strip().lower(),
            "type": "relation",
            "name": rel_name,
            "canonical_name": rel_name,
            "aliases": [],
            "participants": [
                {"role": "source",
                 "entity_id": entity_id(protocol, src.get("type") or "state",
                                       s_name)},
                {"role": "via",
                 "entity_id": entity_id(protocol, mth.get("type") or "method",
                                       m_name)},
                {"role": "target",
                 "entity_id": entity_id(protocol, tgt.get("type") or "state",
                                       t_name)},
            ],
        }
    return eid


# ===========================================================================
# 诊断矩阵
# ===========================================================================

def entity_category_matrix(facts: Iterable[dict[str, Any]]
                           ) -> dict[str, Any]:
    """**实体 × 分类矩阵**（诊断 P2：谁在多个分类里重复）。

    Returns:
        ``{"entities": N, "by_entity": {eid: [category, ...]},
           "cross_category": N, "single_category": N,
           "by_category": {category: N}}``
    """
    ent_aspects: dict[str, list[str]] = collections.defaultdict(list)
    for f in facts:
        fk = f.get("fact_key") or {}
        subject = fk.get("subject") or {}
        etype = str(subject.get("type") or "").strip().lower()
        name = str(subject.get("name") or "").strip()
        aspect = str(fk.get("aspect") or "")
        protocol = str(fk.get("protocol") or "")
        if etype == "relation":
            quals = subject.get("qualifiers") or {}
            src = quals.get("source") or {}
            tgt = quals.get("target") or {}
            mth = quals.get("method") or {}
            rel_name = (f"{src.get('name','')}--{mth.get('name','')}"
                        f"-->{tgt.get('name','')}")
            eid = entity_id(protocol, "relation", rel_name)
        else:
            if not name:
                continue
            eid = entity_id(protocol, etype, name)
        cat = (locate(aspect, etype) or ("", ""))[0]
        if cat and cat not in ent_aspects[eid]:
            ent_aspects[eid].append(cat)

    by_cat: dict[str, int] = collections.Counter()
    for cats in ent_aspects.values():
        for c in cats:
            by_cat[c] += 1
    multi = {k: sorted(v) for k, v in ent_aspects.items() if len(v) > 1}
    return {
        "entities": len(ent_aspects),
        "by_entity": {k: sorted(v) for k, v in sorted(ent_aspects.items())},
        "cross_category": len(multi),
        "single_category": len(ent_aspects) - len(multi),
        "by_category": dict(sorted(by_cat.items())),
        "cross_category_detail": {k: v for k, v in sorted(multi.items())},
    }


def entity_aspect_detail(facts: Iterable[dict[str, Any]]
                          ) -> dict[str, list[str]]:
    """**实体 × aspect 明细**（同一实体的属性散落在哪些 aspect）。"""
    _ents, detail = build_entity_index(facts)
    return detail


# ===========================================================================
# 落盘
# ===========================================================================

def write_entity_index(protocol: str, entities: list[dict[str, Any]]
                       ) -> Path:
    """把实体主表落盘到 ``<中枢根>/index/entities.jsonl``。"""
    from core.paths import hub_index_dir
    d = hub_index_dir(protocol)
    d.mkdir(parents=True, exist_ok=True)
    p = d / "entities.jsonl"
    with p.open("w", encoding="utf-8", newline="") as f:
        for e in sorted(entities, key=lambda x: x.get("entity_id") or ""):
            f.write(json.dumps(e, ensure_ascii=False) + "\n")
    return p


def load_facts(protocol: str) -> list[dict[str, Any]]:
    """读回某协议的**全部 fact**（从现有中枢布局）。"""
    from core import paths
    out: list[dict[str, Any]] = []
    d = paths.per_source_aspect_facts_dir(protocol)
    if not d.is_dir():
        return out
    for p in sorted(d.glob("*.jsonl")):
        if p.name.startswith("_"):
            continue
        for ln in p.read_text(encoding="utf-8").splitlines():
            if ln.strip():
                try:
                    out.append(json.loads(ln))
                except json.JSONDecodeError:
                    continue
    return out


__all__ = [
    "entity_id", "parse_entity_id", "build_entity_index",
    "entity_category_matrix", "entity_aspect_detail",
    "write_entity_index", "load_facts",
]
