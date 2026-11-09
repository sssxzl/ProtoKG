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

#: ★★ 模型链路产物的根（derived/model/）
#:   下辖四层（并列）：per_source（抽取）/ hub（中枢）/ graph（GraphRAG）/ seeds（消费）
#:   + 中间产物：spec / source / vuln / vuln_pattern_vectors / lane_a / source_blocks
MODEL_DIRNAME = "model"

#: ★★ 论文实验产物的根（derived/experiments/）
#:   rq3 / rq4 / semantic_gain / annotation / chatafl_analysis
#:   ★ 与「模型产物」**分开** ⇒ 一眼区分「模型」与「论文证据」
EXPERIMENTS_DIRNAME = "experiments"


def model_root() -> Path:
    """模型链路产物根 ``derived/model/``（四层 + 中间产物）。"""
    return derived_root() / MODEL_DIRNAME


def experiments_root() -> Path:
    """论文实验产物根 ``derived/experiments/``（RQ3/RQ4/标注/语义增益/对比分析）。"""
    return derived_root() / EXPERIMENTS_DIRNAME


def derived_root() -> Path:
    return PROJECT_ROOT / "derived"


def norms_path(protocol: str) -> Path:
    """v1 norms 产物 derived/model/spec/<protocol>/norms/norms.jsonl（rfc/traffic 源）。"""
    return model_root() / "spec" / protocol.lower() / "norms" / "norms.jsonl"


def source_blocks_cache(protocol: str) -> Path:
    """source 源检索缓存 derived/model/source_blocks/<protocol>.json。"""
    return model_root() / "source_blocks" / f"{protocol.lower()}.json"


#: ★★ 中枢根目录（2026-11-08 中枢重设计）
#:   derived/model/hub/<protocol>/  —— 结构化知识中枢（**独立角色**）
#:
#: ★ 为什么独立出来（诊断 P7）：``derived/model/per_source/`` 的语义是「**按源**分」
#:   （每源一个子目录：rfc/ traffic/ profile/ …），
#:   但批次 1.6 起中枢改成「按 aspect 统一存放」⇒ **跨源汇聚**的产物
#:   被放进了名为 per_source 的目录 ⇒ **目录名与内容语义相反**。
#:   ⇒ 中枢独立到 hub/，per_source/ 回归「各源中间产物」的本义。
HUB_DIRNAME = "hub"


def hub_root(protocol: str = "") -> Path:
    """中枢根 ``derived/model/hub/``（结构化知识中枢，**共用一套**）。

    ★ ★ **物理路径无协议层**（2026-11-08 中枢重设计，用户要求：
      「不要给每一个协议单独建立文件夹，共用一套机制」）。
      ★ 参数 ``protocol`` **保留但忽略** ⇒ 既有调用点与测试的
        monkeypatch（``lambda p: ...``）**继续可用** ⇒ 零改动兼容。
      ★ 协议隔离靠**记录内的 ``fact_key.protocol``**（读取端按它过滤）。
    """
    """中枢根 ``derived/model/hub/``（结构化知识中枢，**共用一套**）。

    ★ ★ **不按协议分目录**（2026-11-08 中枢重设计，用户要求）：
      中枢是「**按目标协议的知识分类**存储」的**通用机制** ⇒
      顶层只有**知识分类**（A~F），**协议是记录内的字段**
      （``fact_key.protocol`` / ``entity_id`` 的前缀）。
      ⇒ 换协议**不换机制** ⇒ 共用同一套落位/聚合/纯度/检索代码。
    ★ 代价：一次只处理**一个**协议 ⇒ 抽取前必须**清空**中枢
      （见 ``purge_hub``）⇒ 这正是「每次抽取清掉上一次」的实现。
    """
    return model_root() / HUB_DIRNAME


def hub_index_dir() -> Path:
    """中枢的跨分类索引目录 ``derived/model/hub/index/``。"""
    return hub_root() / "index"


def hub_class_dir(category: str) -> Path:
    """中枢的**分类目录** ``derived/model/hub/<category>/``。

    ★ ``category`` 取自 ``knowledge_slots.json`` 的分类 id
      （A_structure / B_interaction / …）。
    """
    return hub_root() / str(category)


#: ★★ GraphRAG **知识整理层**的根目录（与中枢**并列**，2026-11-08 重设计）
#:   derived/model/graph/  —— 结构化知识中枢的**上一层**：
#:   中枢（derived/model/hub/）= 知识**按分类**存储；
#:   图（derived/model/graph/）= 知识**按关系**整理（实体图 + 社区 + 报告）。
#:   ★ 两者**并列**（不是中枢的子目录）⇒ 层次清晰：
#:     derived/model/hub/      知识本体（分类存储）
#:     derived/model/graph/    关系视图（GraphRAG 整理层）
GRAPH_DIRNAME = "graph"


def graph_root(protocol: str = "") -> Path:
    """GraphRAG 整理层根 ``derived/model/graph/``（与中枢 ``derived/model/hub/`` **并列**）。

    ★ **无协议层**（与中枢一致）⇒ 图的记录带 ``protocol`` 字段，
      读写两端按它过滤 ⇒ 多协议可共存（护栏需要），生产单协议亦成立。
    """
    return model_root() / GRAPH_DIRNAME

def hub_facts_dir() -> Path:
    """中枢的 fact 目录（**过渡期**：按 aspect 落盘）。"""
    return hub_root() / "facts"


def purge_graph() -> list[str]:
    """**清空 GraphRAG 整理层**（``derived/model/graph/``）。

    ★ 与 ``purge_hub`` 配套：中枢重置时，图也要重置
    （否则图里留着上一个协议的知识 ⇒ 检索会串）。
    """
    import shutil
    root = graph_root()
    removed: list[str] = []
    if not root.is_dir():
        return removed
    for child in sorted(root.iterdir()):
        if child.name.startswith("_tmp"):
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            removed.append(child.name)
        except OSError:
            continue
    return removed

def purge_hub() -> list[str]:
    """**清空中枢**（每次抽取前调用）⇒ 落实「每次抽取清掉上一次」。

    ★ 中枢是**共用一套**（不按协议分目录）⇒ 一次只处理一个协议
      ⇒ 抽取前必须清空，否则会残留**上一个协议**的知识
      ⇒ 读取端会把它当成本次的 ⇒ **跨协议污染**。

    Returns:
        被清掉的相对路径（可审计）。
    """
    import shutil
    root = hub_root()
    removed: list[str] = []
    if not root.is_dir():
        return removed
    for child in sorted(root.iterdir()):
        if child.name.startswith("_tmp"):
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            removed.append(child.name)
        except OSError:
            continue
    return removed


def per_source_root(protocol: str) -> Path:
    """各源**中间产物**根 derived/model/per_source/<protocol>/（每源一个子目录）。

    ★ 2026-11-08（中枢重设计）：本目录**回归本义** —— 只放**各源自己的**
      中间产物（``rfc/facts/`` ``traffic/facts/`` ``profile/facts/`` …）。
      ⇒ 中枢本体（跨源汇聚）已迁到 ``derived/model/hub/<protocol>/``（见 ``hub_root``）。
    """
    return model_root() / "per_source" / protocol.lower()


def per_source_facts_dir(protocol: str, source: str) -> Path:
    """**某源**的中间产物 derived/model/per_source/<protocol>/<source>/facts/。

    ★ 中枢重设计后**位置不变**（它本来就是「各源」的东西）。
    """
    return per_source_root(protocol) / source / "facts"


def per_source_aspect_facts_dir(protocol: str) -> Path:
    """★ **中枢本体**的 fact 目录（按知识分类落盘的**过渡布局**）。

    2026-11-08（中枢重设计）：中枢已迁到 ``derived/model/hub/<protocol>/``；
    本函数保留为**过渡期**的 aspect 布局读写点（阶段 C 会换成按分类落盘）。

    ★ 批次 1.6 的布局意图（「统一按中枢结构存放」= 按 aspect 落盘；「源」退化为
      事实内部的 ``all_claims[].authority``）**仍然成立** ——
      本次只是把**物理位置**从中枢语义错误的 ``per_source/`` 移到 ``hub/``。
    """
    return hub_facts_dir()


def seeds_dir(protocol: str) -> Path:
    """种子输出 derived/model/seeds/<protocol>/。"""
    return model_root() / "seeds" / protocol.lower()


# ===========================================================================
# 目标配置（fused_hub/targets/<protocol>/）
# ===========================================================================

def targets_root() -> Path:
    return PROJECT_ROOT / "fused_hub" / "targets"


def target_profile(protocol: str) -> Path:
    """fused_hub/targets/<protocol>/profile.json。"""
    return targets_root() / protocol.lower() / "profile.json"


def target_skeleton(protocol: str) -> Path:
    """fused_hub/targets/<protocol>/skeleton.json（**协议骨架**）。

    ★ 批次 1.6 步 0.5 引入：协议骨架是「跨实验复用的协议结构」（消息实例 +
      目标状态 + 方法序列 + 取值枚举），不属于任何单一知识源 ⇒ 固化为
      **入库资产**，每次构建重新物化进中枢，保证单源构建时链路不断。

    ★ 批次 2.3：骨架内部的 facts 带**来源维度**（source / traffic），
      供消融实验按维度排除。
    """
    return targets_root() / protocol.lower() / "skeleton.json"


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
    "purge_hub",
    "purge_graph",
    "per_source_facts_dir",
    "per_source_aspect_facts_dir",
    "seeds_dir",
    "targets_root",
    "target_profile",
    "target_skeleton",
    "target_rfc_config",
    "target_resources",
    "target_request_templates",
]
