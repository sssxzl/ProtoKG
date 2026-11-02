# -*- coding: utf-8 -*-
"""core/paths.py —— 统一路径解析：协议 × 源 二维解耦的唯一入口。

把「知识输入（kb）」「抽取中间产物（derived）」「目标配置（fused_hub/targets）」
的路径全部集中在这里，以 (protocol, source) 两个正交维度解析。

设计动机（对齐 Fuzz4All 的「配置驱动」+ 本项目的「协议×源二维解耦」）：
  - 协议维度差异 → 全部落在 fused_hub/targets/<protocol>/profile.json + kb/<protocol>/；
  - 知识源维度差异 → 落在五源抽取器（core/fused/{source_autoseeder,norm,expert_note,
    traffic,vuln}.py），各自独立；
  - 两者笛卡尔积：任何 (协议, 源) 组合都能解析出合法路径，换协议/换源零代码改动。

所有路径用绝对路径（基于项目根），不依赖进程 cwd（避免 cd 到别处后 kb/derived 相对
路径失效）。
"""
from __future__ import annotations

from pathlib import Path

#: 项目根（core/paths.py -> core -> <project>/）
PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: 五源 → kb 子目录名（源维度；与 scripts/build_hub.py 的 KB_SOURCE_DIRS 一致）
SOURCE_DIRS: dict[str, str] = {
    "rfc": "spec",
    "expert_note": "expert_note",
    "traffic": "数据流量",
    "vuln": "历史漏洞",
    "source": "协议实现源码",
}

#: 五源集合（顺序即 build_hub 默认处理顺序）
SOURCES: tuple[str, ...] = ("rfc", "expert_note", "traffic", "vuln", "source")


# ===========================================================================
# 知识输入（kb/<protocol>/<源目录>/）
# ===========================================================================

def kb_root() -> Path:
    return PROJECT_ROOT / "kb"


def kb_source_dir(protocol: str, source: str) -> Path:
    """kb/<protocol>/<源目录>/（该协议某源的知识输入目录）。"""
    sub = SOURCE_DIRS.get(source, source)
    return kb_root() / protocol.lower() / sub


# ===========================================================================
# 抽取中间产物（derived/...）
# ===========================================================================

def derived_root() -> Path:
    return PROJECT_ROOT / "derived"


def norms_path(protocol: str) -> Path:
    """v1 norms 产物 derived/spec/<protocol>/norms/norms.jsonl（rfc/traffic 源）。"""
    return derived_root() / "spec" / protocol.lower() / "norms" / "norms.jsonl"


def source_blocks_cache(protocol: str) -> Path:
    """source 源检索缓存 derived/source_blocks/<protocol>.json。"""
    return derived_root() / "source_blocks" / f"{protocol.lower()}.json"


def per_source_root(protocol: str) -> Path:
    """五源 facts 根 derived/per_source/<protocol>/（下面每源一个子目录）。"""
    return derived_root() / "per_source" / protocol.lower()


def per_source_facts_dir(protocol: str, source: str) -> Path:
    """五源 facts 输出 derived/per_source/<protocol>/<source>/facts/。"""
    return per_source_root(protocol) / source / "facts"


def per_source_aspect_facts_dir(protocol: str) -> Path:
    """★ 批次 1.6 步 1：**新布局** —— 中枢按 aspect 统一存放。

    derived/per_source/<protocol>/facts/<aspect>.jsonl

    设计意图（方案 §3.1.10.2）：「统一按中枢结构存放」= **按 aspect 落盘**；
    「源」退化为**事实内部的一个字段**（``all_claims[].authority``），
    不再作为目录层级。⇒ 中枢里**不按源分目录**，而按知识维度分文件。

    兼容期：旧的「按源分目录」布局 ``<protocol>/<source>/facts/<source>.jsonl``
    **仍然保留**（回退保险），读取端优先读本目录、缺失时自动降级读旧布局。
    """
    return per_source_root(protocol) / "facts"


def seeds_dir(protocol: str) -> Path:
    """种子输出 derived/seeds/<protocol>/。"""
    return derived_root() / "seeds" / protocol.lower()


# ===========================================================================
# 目标配置（fused_hub/targets/<protocol>/）
# ===========================================================================

def targets_root() -> Path:
    return PROJECT_ROOT / "fused_hub" / "targets"


def target_profile(protocol: str) -> Path:
    """fused_hub/targets/<protocol>/profile.json。"""
    return targets_root() / protocol.lower() / "profile.json"


def target_rfc_config(protocol: str) -> Path:
    """fused_hub/targets/<protocol>/rfc_config.json（rfc 源的协议专属抽取配置）。

    与 profile.json 分层：profile.json 是协议身份 + 通用段（allowed_methods /
    raw_format / seedgen …），rfc_config.json 只放**rfc 源抽取**需要的协议专属
    知识（章节号前缀 / 方法排除表 / 数值边界 / 期望响应词表），避免 profile 段膨胀。
    """
    return targets_root() / protocol.lower() / "rfc_config.json"


def target_resources(protocol: str) -> Path:
    """fused_hub/targets/<protocol>_streams.json（目标资源清单，如 RTSP 流名）。"""
    return targets_root() / f"{protocol.lower()}_streams.json"


def target_request_templates(protocol: str) -> Path:
    """fused_hub/targets/<protocol>_request_templates.json（真实请求模板）。"""
    return targets_root() / f"{protocol.lower()}_request_templates.json"


__all__ = [
    "PROJECT_ROOT",
    "SOURCE_DIRS",
    "SOURCES",
    "kb_root",
    "kb_source_dir",
    "derived_root",
    "norms_path",
    "source_blocks_cache",
    "per_source_root",
    "per_source_facts_dir",
    "per_source_aspect_facts_dir",
    "seeds_dir",
    "targets_root",
    "target_profile",
    "target_rfc_config",
    "target_resources",
    "target_request_templates",
]
