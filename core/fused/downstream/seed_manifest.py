# -*- coding: utf-8 -*-
"""core/fused/downstream/seed_manifest.py —— 种子 manifest 构建与读写。

manifest 是 RQ3「变异命中率归因」与「论文可溯源」的数据基础：
每条种子记录 filename / MD5 / 生成分层 / 漏洞接近度分数 / 组内排名 /
生成器 / 描述 / 合法-非法端 / 漏洞模式标签 / 资源流 / 方法序列。

设计约束（对齐技术方案 §2.5）：
  · 文件名与 manifest **零漂移**：由 `plan_seed_filenames` 统一产出，
    落盘文件名与 manifest.filename 天然对齐。
  · 跨组归因**以 MD5 为主键**、rank 为组内变量；不依赖文件名/rank 做跨组主键。
  · `legal_illegal` 判定**必须先判 illegal**（"illegal(同 track)" 含子串 legal）。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.models import SeedCorpus

from .rag_seedgen import plan_seed_filenames
from .selector import seed_layer, vuln_proximity_score

#: manifest 的 schema 版本
SCHEMA_VERSION = "1.0"

#: 漏洞模式标签（与 MHR_A 的 P1–P4 判定一一对应）
PATTERN_TAGS: tuple[str, ...] = ("P1", "P2", "P3", "P4")

#: 漏洞模式 → 关键词映射（用于从 description 解析 pattern_tags）
_ACTION_TAG_RULES: tuple[tuple[str, str], ...] = (
    ("double_setup", "P1"),
    ("interleave_seq", "P3"),
    ("uaf_seq", "P4"),
    ("lifecycle_seq", "P4"),
)

#: 触发字段 → 漏洞模式标签映射（字段型漏洞）
_FIELD_TAG_RULES: dict[str, str] = {
    "Session": "P2",
    "interleaved": "P3",
    "client_port": "P3",
    "Transport": "P3",
    "track": "P1",
}


def classify_legal_illegal(description: str) -> str:
    """判定种子的合法/非法端：`illegal` / `legal` / `n/a`。

    ★ **必须先判 illegal**：描述 "…illegal(同 track)" 里含子串 "legal"，
    顺序反了会把非法端全部误判成合法端。

    Args:
        description: 种子描述文本。

    Returns:
        "illegal" / "legal" / "n/a"。
    """
    d = (description or "").lower()
    if "illegal" in d:
        return "illegal"
    if "legal" in d:
        return "legal"
    return "n/a"


def classify_pattern_tags(seed: SeedCorpus) -> list[str]:
    """解析种子瞄准的漏洞模式标签（P1–P4 子集）。

    规则（对齐技术方案 §2.5.2）：
      · description/action 含 `double_setup` → P1（同 track 双 SETUP）
      · description/action 含 `interleave_seq` → P3（Transport 切换）
      · description/action 含 `uaf_seq` / `lifecycle_seq` → P4（会话重建序列）
      · 字段型（vuln-field）且 trigger_field == Session → P2（触发 Session 值）
      · 字段型且 trigger_field ∈ {interleaved, client_port, Transport} → P3
      · 字段型且 trigger_field == track → P1

    Args:
        seed: 待解析的种子。

    Returns:
        排序后的标签列表（无匹配时为空列表）。
    """
    desc = (seed.description or "").lower()
    gb = (seed.generated_by or "").lower()
    tags: set = set()
    for keyword, tag in _ACTION_TAG_RULES:
        if keyword in desc or keyword in gb:
            tags.add(tag)
    # 字段型漏洞：从描述里解析出触发字段名（如 "vuln-field empty_edge Session …"）
    if "vuln-field" in desc:
        field = _extract_trigger_field(desc)
        tag = _FIELD_TAG_RULES.get(field)
        if tag:
            tags.add(tag)
    return sorted(tags)


def _extract_trigger_field(desc: str) -> str:
    """从 "vuln-field <维度> <字段> …" 描述里抽出触发字段名（大小写不敏感）。

    描述文本在判定前已被转成小写，故查表也必须小写，
    否则 "Transport" 会被漏判成未知字段。
    """
    parts = desc.split()
    if "vuln-field" not in parts:
        return ""
    idx = parts.index("vuln-field")
    # 触发字段名紧随维度名之后（维度名形如 empty_edge / long_value）
    for token in parts[idx + 1:]:
        low = token.lower()
        for known in _FIELD_TAG_RULES:
            if low == known.lower():
                return known
        if low.startswith(("legal", "illegal")):
            break
    return ""


def _md5_of(path: Path) -> str:
    """文件的 MD5（32 位小写 hex）。"""
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def build_manifest(seeds: list, out_dir, *,
                   protocol: str = "rtsp",
                   group: Optional[str] = None,
                   seedgen_cfg: Optional[dict] = None,
                   dictionary: Optional[dict] = None,
                   generated_at: Optional[str] = None,
                   base_count: Optional[int] = None) -> dict:
    """构建 manifest 字典（不落盘）。

    Args:
        seeds: 已排序、已落盘的种子列表（顺序即 rank）。
        out_dir: 种子落盘目录（用于读取实际文件计算 MD5 与字节数）。
        protocol: 协议名。
        group: 聚焦组名（A/B/C/D）；None 表示非分组模式。
        seedgen_cfg: 记录本次生成参数（focus_group / layers / order / dict_kind…）。
        dictionary: 字典元信息（path / token_count / md5）。
        generated_at: ISO 8601 时间戳；None 时取当前时间。
        base_count: 基准层条数（P2-5：文件名宽度按它算 ⇒ 基准层文件名稳定）。

    Returns:
        manifest 字典（可直接 json.dump）。
    """
    out = Path(out_dir)
    names = plan_seed_filenames(seeds, base_count=base_count)
    entries: list = []
    for idx, (seed, name) in enumerate(zip(seeds, names), start=1):
        path = out / name
        raw = path.read_bytes() if path.exists() else b""
        layer, layer_name = seed_layer(seed)
        entries.append({
            "index": idx,
            "rank": idx,
            "filename": name,
            "md5": hashlib.md5(raw).hexdigest(),
            "bytes": len(raw),
            "layer": layer,
            "layer_name": layer_name,
            "generated_by": seed.generated_by or "",
            "score": vuln_proximity_score(seed),
            "description": seed.description or "",
            "legal_illegal": classify_legal_illegal(seed.description),
            "pattern_tags": classify_pattern_tags(seed),
            "stream": (seed.selected_url or "").rstrip("/").split("/")[-1],
            "methods": list(seed.target_methods),
            "group": group or "",
        })
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "protocol": protocol,
        "group": group or "",
        "generated_at": generated_at or datetime.now().astimezone().isoformat(),
        "seedgen": dict(seedgen_cfg or {}),
        "dictionary": dict(dictionary or {}),
        "seed_count": len(entries),
        "seeds": entries,
    }
    # ★ P0-4：⑤（action-seq 变异层）的条数**单独记账**，**不受 G5 契约约束**
    #   （契约条数是**基准层**的约定）。
    #   ★ **条件性添加**：只有真的存在 ⑤ 种子时才写这两个键
    #     ⇒ ⑤ 关闭时 manifest **逐字节不变**（回滚手段必须成立）。
    mutation_count = sum(1 for e in entries if e.get("layer") == "L5")
    if mutation_count:
        manifest["mutation_count"] = mutation_count
        manifest["base_seed_count"] = len(entries) - mutation_count
    return manifest


def write_manifest(manifest: dict, path) -> Path:
    """把 manifest 落盘（UTF-8，不转义中文，缩进 2）。

    Args:
        manifest: build_manifest 的返回值。
        path: 目标文件路径（父目录自动创建）。

    Returns:
        写入的路径。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")
    return p


def read_manifest(path) -> dict:
    """读取 manifest 文件。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


__all__ = ["SCHEMA_VERSION", "PATTERN_TAGS", "classify_legal_illegal",
           "classify_pattern_tags", "build_manifest", "write_manifest",
           "read_manifest"]
