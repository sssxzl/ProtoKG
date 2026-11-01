# -*- coding: utf-8 -*-
"""compare/shallow_kb.py —— B 路：浅层知识库（PSG/RTSGen 式）。

复用 A 路的抽取（build_hub 产出的 v2 Fact）+ 分桶（assemble_bundle），
但**显式剥掉 provenance**（Epistemic / Evidence / Resolution），冲突静默抹平
（同 fact_key 下只保留首条 claim 的 value）。

与 A 路的唯一差异 = 知识表示层（有无 provenance 三要素）。
"""
from __future__ import annotations

from typing import Any, Optional

from core.fused.downstream.rag_seedgen import (
    load_fact_views,
    assemble_bundle,
    render_seed_prompt,
)
from compare.config import MODE_SHALLOW
from compare.interface import KnowledgeRepresentation

# provenance 相关字段（B 路剥掉，A 路保留）
_PROVENANCE_CLAIM_FIELDS = (
    "epistemic", "epistemic_type", "evidence", "authority",
    "confidence", "scope", "flags",
)


def strip_provenance(views: list[dict]) -> list[dict]:
    """把 fact view 退化为浅层知识：删 epistemic/evidence/resolution，冲突抹平。

    1) 每个 fact 只保留首条 claim 的 value（多源冲突静默覆盖）；
    2) 删掉 claim 上的认识论状态 / 证据 / 权威 / 置信度字段；
    3) 删掉 fact 级的 resolution（冲突消解结果）。
    """
    out: list[dict] = []
    for v in views:
        v = dict(v)
        claims = v.get("all_claims") or []
        if claims:
            first = dict(claims[0])
            for k in _PROVENANCE_CLAIM_FIELDS:
                first.pop(k, None)
            v["all_claims"] = [first]
        v.pop("resolution", None)
        out.append(v)
    return out


class ShallowKB(KnowledgeRepresentation):
    """B 路：结构化但无 provenance 的浅层知识库。"""

    name = MODE_SHALLOW

    def __init__(self, protocol: str, facts_root: Any,
                 resources: Optional[list] = None,
                 request_templates: Optional[dict] = None):
        self.protocol = protocol
        self.facts_root = facts_root
        self.resources = resources
        self.request_templates = request_templates
        self.bundle: Optional[dict] = None

    def prepare(self) -> None:
        views = load_fact_views(self.protocol, self.facts_root)
        views = strip_provenance(views)          # 关键：剥掉 provenance，冲突抹平
        self.bundle = assemble_bundle(views)

    def render_prompt(self, task: dict[str, Any]) -> tuple[str, str]:
        if self.bundle is None:
            raise RuntimeError("ShallowKB.prepare() 未调用")
        return render_seed_prompt(
            self.bundle,
            protocol=task.get("protocol", self.protocol),
            n_seeds=task.get("n_seeds", 20),
            resources=task.get("resources") or self.resources,
            request_templates=task.get("request_templates") or self.request_templates,
        )
