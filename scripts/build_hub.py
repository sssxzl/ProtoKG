"""scripts/build_hub.py —— v2 中枢真实构建入口（Layer 2 单源抽取）。

用法::

    python scripts/build_hub.py --list-sources
    python scripts/build_hub.py --sources rfc --protocol rtsp
    python scripts/build_hub.py --sources rfc expert_note --protocol rtsp
    python scripts/build_hub.py --sources source --protocol smtp

产出::

    derived/per_source/<protocol>/<source>/facts/<source>.jsonl   v2 Fact (六元组, 单源)

★ 每次构建默认【清空】该协议上次实验的 facts（derived/per_source/<protocol>/），
  避免旧 facts 残留污染本次抽取/种子生成；用 --no-clean 可保留旧数据做增量抽取。

  ★★ 清理时机（2026-11-01 修复 P2-1）：清理发生在**质量闸通过之后**，
     顺序为「抽取 → 映射 → 质量闸 → 清理 → 写盘」。原先「先清理、后校验」，
     闸不通过时旧产物已被删、新产物未写入 ⇒ 该协议的 rfc facts 变成空
     （质量闸阻断构建变成「破坏知识库」）。现在闸不通过 = 保持原状并拒绝写入。

★ 幂等快照（A0.5）：产物按 build_id 写独立快照
  `derived/per_source/<protocol>/<source>/facts/snapshots/<build_id>/<source>.jsonl`，
  再原子切换到正式路径；清理时**保留** snapshots/ 目录，历史快照可回滚。

★ 与 v1 scripts/build_hub.py 的区别:
  - v1 走 core.fused.pipeline (v1 candidateization, 硬编码 rfc 系 + vuln 系);
  - 本脚本走 core.fused.norm (原生 norm → v2 Fact 映射, 基于 Layer 1 Profile)。

★ 只读保证:
  kb/ 全程只读; 仅读 derived/spec/<protocol>/norms/norms.jsonl (v1 extractor 产物);
  只写 derived/per_source/<protocol>/<source>/ (用户 2026-10-08 授权落盘)。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fused.norm import map_norm_to_facts                   # noqa: E402
from core.fused.expert_note import expert_note_to_facts         # noqa: E402
from core.fused.vuln import vuln_to_facts                       # noqa: E402
from core.fused.registry import load_registry                  # noqa: E402
from core.fused.validation import validate_fact                # noqa: E402
from core.fused.export import get_fact_view                    # noqa: E402
from core.fused.llm_ensemble import (                          # noqa: E402
    ENV_KEY as SEMANTIC_RULES_ENV_KEY,
    semantic_rules_enabled,
    set_semantic_rules_enabled,
)
from core import paths                                          # noqa: E402

#: v1 norms 产物路径（协议 × 源二维解耦：derived/spec/<protocol>/norms/norms.jsonl）
def _norms_path(protocol: str) -> Path:
    return paths.norms_path(protocol)

#: 五源 -> 底层 kb_source_type 集合 (与 v1 build_hub.py 对齐)
KNOWN_SOURCES = {
    "rfc": ("rfc",),
    "expert_note": ("expert_note", "expert_notes"),
    "traffic": ("traffic_pcap", "traffic_raw"),
    "vuln": ("vuln",),
    "source": ("source",),
}

#: 五源 -> kb 子目录名（协议 × 源二维：kb/<protocol>/<子目录>；与 core/paths.SOURCE_DIRS 一致）
KB_SOURCE_DIRS = {
    "rfc": "spec",
    "expert_note": "expert_note",
    "traffic": "数据流量",
    "vuln": "历史漏洞",
    "source": "协议实现源码",
}

#: 本次 build 各协议的幂等键（build_id）。A0.5：产物按 build_id 写独立快照
#: 再原子切换 —— 同输入两次 build 必须产出同一 build_id。
_LAST_BUILD_IDS: dict = {}


def scan_kb_sources() -> dict:
    """扫描 kb/<protocol>/ 目录，识别【实际存在】的知识源（按目录 + 数据量）。

    协议 × 源二维：kb/ 下每协议一个目录，协议目录下每源一个子目录。同时兼容旧的
    kb/<源>/ 单协议布局（尚未迁移时）。
    """
    result = {}
    kb = REPO_ROOT / "kb"
    for source, sub in KB_SOURCE_DIRS.items():
        files: list = []
        # 新结构 kb/<protocol>/<源>/
        for proto_dir in [p for p in kb.iterdir() if p.is_dir()]:
            d = proto_dir / sub
            if d.is_dir():
                files.extend(f for f in d.rglob("*") if f.is_file())
        # 旧结构 kb/<源>/（向后兼容）
        legacy = kb / sub
        if legacy.is_dir():
            files.extend(f for f in legacy.rglob("*") if f.is_file())
        if files:
            result[source] = {"dir": f"kb/<protocol>/{sub}", "files": len(files)}
    return result


def _remove_path(path: Path) -> None:
    """删除文件或目录（目录递归删）。路径不存在时静默跳过。

    Args:
        path: 待删除的文件或目录路径。
    """
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _clean_source_dir(source_dir: Path) -> None:
    """清空某源的产物目录，但**保留** `facts/snapshots/`（历史幂等快照）
    **与 `semantic/`（B-7 语义四库）**。

    ★ A0.5 修复（2026-11-01）：原先直接 `shutil.rmtree(source_dir)`，把
      `facts/snapshots/<build_id>/` 里的历史快照一并删掉 ⇒ 文档承诺的
      「可回滚到历史版本（F5）」根本无从谈起。

      现在：
        - **无快照**时行为不变（整目录删除）；
        - **有快照**时只删源目录下的其它全部内容，保留 `facts/snapshots/`。

    ★ B-9 追加（2026-11-02）：`semantic/`（规则库/候选库等**四库**）与
      facts 是**两套生命周期** —— facts 每次构建全量重写，四库由
      `--rules-only` 单独产出。若 facts 清理把 `semantic/` 一并删掉，
      语义规则库会在**任何一次**普通 rfc 构建后**静默消失** ⇒ 下游
      `rag_seedgen` 读不到规则。故把 `semantic/` 与 `facts/snapshots/`
      一并列为**保护区**。

    Args:
        source_dir: `derived/per_source/<protocol>/<source>/` 目录。
    """
    snap_dir = source_dir / "facts" / "snapshots"
    protected = {"facts", "semantic"}
    if not snap_dir.is_dir() and not (source_dir / "semantic").is_dir():
        shutil.rmtree(source_dir)
        return
    # 有快照/四库：保留 facts/ 与 semantic/，其余内容全删
    for child in source_dir.iterdir():
        if child.name in protected:
            continue
        _remove_path(child)
    facts_dir = source_dir / "facts"
    if not facts_dir.is_dir():
        return
    for child in facts_dir.iterdir():
        if child.name == "snapshots":
            continue
        _remove_path(child)


def _clean_per_source(protocol: str, sources: list[str] | None = None) -> None:
    """清空该协议**指定知识源**上次实验的 facts。

    ★★ 架构约束（2026-10-31 用户明确）：本模型**一次只处理一个知识库 ×
       一个知识源**。因此清理范围必须**精确到本次要处理的那个源**，
       绝不能连带清掉同协议的其他源。

       曾经的实现（清五源）导致：`build_hub.py --sources rfc --protocol rtsp`
       会把 rtsp 的 source/expert_note/vuln/traffic 一起删掉 → 依赖这些源
       的下游测试与种子生成全部失效（实测 22 个测试连带失败）。
       现在只清 `sources` 指定的源；`sources=None` 时清五源（仅供
       `--clean-all` 这类显式全量重建场景）。

    只删五源子目录（build_hub 自产的再生数据），**保留** boundary_probe 等
    运行时回写（oracle 探测回写的 legal_boundary 等非五源知识，属宝贵
    富化，不应被清空），不动 kb/ 与 fused_hub/targets/。

    ★ A0.5：保留各源的 `facts/snapshots/`（历史幂等快照），使回滚能力可用。
    """
    root = paths.per_source_root(protocol)
    if not root.is_dir():
        print(f"[清理] {protocol} 无历史 facts（{root} 不存在），跳过")
        return
    targets = list(sources) if sources else list(paths.SOURCES)
    cleaned: list[str] = []
    kept_snapshots: list[str] = []
    for source in targets:
        d = root / source
        if d.is_dir():
            has_snapshots = (d / "facts" / "snapshots").is_dir()
            _clean_source_dir(d)
            cleaned.append(source)
            if has_snapshots:
                kept_snapshots.append(source)
    if cleaned:
        print(f"[清理] 已清空 {protocol} 的 {len(cleaned)} 个源 facts: "
              f"{', '.join(cleaned)}")
    else:
        print(f"[清理] {protocol} 无待清理的源 facts，跳过")
    if kept_snapshots:
        print(f"[清理] 已保留 {protocol} 的历史幂等快照（snapshots/）: "
              f"{', '.join(kept_snapshots)}")


#: ★ 批次 1.6（步 0）：中枢「运行时回写目录」——**不清空**。
#:   `boundary_probe/` 是 oracle 探测回写的 **legal_boundary 等富化知识**，
#:   属**积累资产**而非「上次运行的抽取残留」
#:   （`tests/fused/test_build_hub_clean.py` 明确断言它必须保留）。
#:   ⇒ 「清空整个中枢」的对象 = **五源抽取产物（facts）+ 语义四库（semantic）**。
RUNTIME_ENRICH_DIRS: tuple[str, ...] = ("boundary_probe",)

#: ★ 批次 1.6（步 0）：语义四库在清空前的**仓库外备份目录**。
#:   规则库由 LLM 从 RFC 源产出 ⇒ **不能从 kb 重建**（需 120 次 LLM 调用）
#:   ⇒ 清空前必须留一份**可恢复**副本（这不是「归档到 derived/」，
#:   而是**备份**——用户明确否掉了 `derived/per_source_archive/<ts>/` 那种归档）。
SEMANTIC_BACKUP_ROOT = Path(r"E:\科研\想法idea\ProtoRAG_快照_20261102\semantic_backup")


def _backup_semantic_before_purge(protocol: str) -> str:
    """清空前把语义四库备份到**仓库外**（不可再生资产 ⇒ 必须可恢复）。"""
    root = paths.per_source_root(protocol)
    backups: list[str] = []
    for source_dir in sorted(root.glob("*/semantic")):
        if not source_dir.is_dir():
            continue
        dst = SEMANTIC_BACKUP_ROOT / protocol / source_dir.parent.name
        dst.mkdir(parents=True, exist_ok=True)
        for f in source_dir.glob("*.jsonl"):
            shutil.copy2(f, dst / f.name)
            # ★ 备份在**仓库外** ⇒ 不能用 relative_to(REPO_ROOT)
            backups.append(f"{protocol}/{source_dir.parent.name}/{f.name}")
    if backups:
        print(f"[清空] 语义四库已备份到仓库外（可恢复）: "
              f"{SEMANTIC_BACKUP_ROOT / protocol}  ({len(backups)} 个文件)")
    return SEMANTIC_BACKUP_ROOT / protocol and str(SEMANTIC_BACKUP_ROOT / protocol)


def _repo_rel(path) -> str:
    """把路径显示成「相对仓库根」；**在仓库外**时用绝对路径（不崩）。"""
    try:
        return str(Path(path).relative_to(REPO_ROOT))
    except ValueError:
        return str(path)
def _purge_hub_for_batch(protocol: str, *, purge_semantic: bool = True
                         ) -> list[str]:
    """★ 批次 1.6（步 0）：**清空整个中枢**（本协议的五源抽取产物）。

    ★ 与 :func:`_clean_per_source` 的区别（后者**不动**，签名与语义被测试锁定）：
      · 范围 = 该协议下的**全部五源**（不只是本次要构建的那一个）
      · 「清空」= 五源的 ``facts/``（**保留** ``facts/snapshots/`` 历史快照）
        + 语义四库 ``semantic/``（D-7 选项 A：中枢里的一切都是本次的）
      · **保留** :data:`RUNTIME_ENRICH_DIRS`（运行时回写的富化知识）
      · **直接清，不归档**（用户 2026-11-02 明确：清空不破坏多源复现，
        反而避免历史抽取记录影响本次；不必归档到 ``derived/per_source_archive/``）

    Returns:
        被清空的源名列表。
    """
    root = paths.per_source_root(protocol)
    if not root.is_dir():
        return []
    if purge_semantic:
        _backup_semantic_before_purge(protocol)
    purged: list[str] = []
    # ★ 骨架的物化产物也清（每次构建会重新物化 ⇒ 中枢里不留旧骨架）
    skel_dir = root / SKELETON_SOURCE_NAME
    if skel_dir.is_dir():
        shutil.rmtree(skel_dir, ignore_errors=True)
        purged.append(SKELETON_SOURCE_NAME)
    for source in paths.SOURCES:
        d = root / source
        if not d.is_dir():
            continue
        # 运行时富化目录：**不清**
        if source in RUNTIME_ENRICH_DIRS:
            continue
        # 语义四库（D-7 选项 A）：清掉，本次靠 --with-rules 重产
        # ★ **必须受 ``purge_semantic`` 开关控制**（否则 ``--no-purge``
        #   语义上"不清空"却仍把规则库删了 ⇒ 不可再生的规则静默丢失）
        sem = d / "semantic"
        if purge_semantic and sem.is_dir():
            shutil.rmtree(sem, ignore_errors=True)
        facts = d / "facts"
        if facts.is_dir():
            for child in facts.iterdir():
                if child.name == "snapshots":
                    continue
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)
                else:
                    child.unlink(missing_ok=True)
        purged.append(source)
    # 其它非五源目录（运行时富化）不动
    if purged:
        print(f"[清空] 已清空 {protocol} 中枢的五源抽取产物: {', '.join(purged)}"
              + ("（含语义四库）" if purge_semantic else ""))
    else:
        print(f"[清空] {protocol} 中枢无五源产物可清")
    return purged


def _write_source_manifest(protocol: str, sources: list[str],
                            build_ids: dict[str, str],
                            skeleton_count: int = 0) -> Path:
    """写中枢的**本次源集合**清单（``per_source/<协议>/sources.json``）。

    ★ 它是「本次实验的知识来源清单」的**唯一权威**：
      组装侧与消费端都据它判断「本次参与了哪些源」。
    """
    root = paths.per_source_root(protocol)
    root.mkdir(parents=True, exist_ok=True)
    doc = {
        "protocol": protocol,
        "source_set": sorted(sources),
        "build_ids": dict(build_ids),
        "built_at": datetime.now().astimezone().isoformat(),
        "purged_before_build": True,
        "runtime_enrich_dirs_kept": list(RUNTIME_ENRICH_DIRS),
        "skeleton": {
            "source": SKELETON_SOURCE_NAME,
            "fact_count": skeleton_count,
            "note": "协议骨架（状态机/消息实例/方法存在性/头取值/频次/配对）"
                    "由 source+traffic 源抽取后固化为入库资产，构建时物化进中枢"
                    "⇒ 单源调试时链路不断。",
        },
    }
    path = root / "sources.json"
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    try:
        shown = _repo_rel(path)
    except ValueError:
        shown = path          # ★ 路径在仓库外（如测试的 tmp_path）⇒ 不崩
    print(f"[清单] 本次源集合 {sorted(sources)} → {shown}")
    return path


#: ★ 批次 1.6：语义规则的来源候选（B-10 实验产物；发布进中枢的语义四库）。
SEMANTIC_RULE_SOURCES: tuple[str, ...] = (
    "derived/exp_semantic_gain/group_E1/rules.jsonl",
    "derived/exp_semantic_gain/group_E2/rules.jsonl",
)


def _republish_rules(protocol: str) -> None:
    """把 B-10 实验产出的规则**重新发布**进中枢的语义四库（D-7 选项 A）。

    ★ 为什么必须有这一步：语义四库由 LLM 从 RFC 源产出 ⇒ **不能从 kb 重建**
      ⇒ 「整个中枢全清」会**永久丢失**它 ⇒ 清空 + 重发必须**成对**执行。
    """
    from core.fused.downstream.rule_store import publish_rules
    rows: list[dict] = []
    for rel in SEMANTIC_RULE_SOURCES:
        p = REPO_ROOT / rel
        if not p.is_file():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict) and data.get("kind") == "semantic_rule":
                data = data.get("rule") or {}
            if isinstance(data, dict) and data.get("rule_id"):
                rows.append(data)
    if not rows:
        print("[规则] ★ 未找到可发布的规则产物（B-10 实验目录不存在）"
              "⇒ 本次中枢**不含**语义规则")
        return
    report = publish_rules(protocol, rows, replace=True)
    print(f"[规则] 已重新发布进中枢语义四库：权威 {report['authoritative']} 条 / "
          f"候选 {report['candidate']} 条 / 拒绝 {report['rejects']}")


#: ★ 批次 1.6（步 0.5）：中枢里的**骨架源目录名**。
#:   它不是 kb 里的知识源，而是「协议骨架」的物化位置。
SKELETON_SOURCE_NAME = "profile"


def _materialize_skeleton(protocol: str) -> int:
    """把 ``fused_hub/targets/<协议>/skeleton.json`` 物化进中枢的 ``profile/`` 源。

    ★ 为什么必须有：种子生成本质是「**状态机边的遍历**」
      ⇒ 只抽 RFC 源时 ``transitions`` 为 0 ⇒ **一条种子都生不出来**
      （实测：「!! 无状态机转移，无法生成种子」）。
    ★ 骨架是「**跨实验复用的协议结构**」，不是「本次抽取的结果」
      ⇒ 固化为**入库资产**，每次构建**重新物化**进中枢
      ⇒ 中枢自洽（里面的一切都是本次的）+ 单源调试时链路不断。
    ★ ``authority`` 改标 ``profile``：让「本次抽取的源」与「骨架」在
      ``available_sources`` 里**分得开**（否则骨架会带着 source/traffic 的
      authority 混进来，破坏「本次源集合」的语义）。
    """
    src = paths.target_profile_path(protocol) if hasattr(
        paths, "target_profile_path") else (
            REPO_ROOT / "fused_hub" / "targets" / protocol / "skeleton.json")
    if not src.is_file():
        print(f"[骨架] ★ {protocol} 无 skeleton.json（协议骨架缺失）"
              "⇒ 单源构建可能因无状态机而无法生成种子")
        return 0
    doc = json.loads(src.read_text(encoding="utf-8"))
    facts = doc.get("facts") or []
    if not facts:
        return 0
    for f in facts:
        for claim in (f.get("all_claims") or []):
            claim["authority"] = SKELETON_SOURCE_NAME
    dest_dir = paths.per_source_facts_dir(protocol, SKELETON_SOURCE_NAME)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{SKELETON_SOURCE_NAME}.jsonl"
    with dest.open("w", encoding="utf-8") as fh:
        for f in facts:
            fh.write(json.dumps(f, ensure_ascii=False) + "\n")
    try:
        shown = _repo_rel(dest)
    except ValueError:
        shown = dest          # ★ 路径在仓库外（如测试的 tmp_path）⇒ 不崩
    print(f"[骨架] 已物化 {len(facts)} facts → "
          f"{shown}（authority={SKELETON_SOURCE_NAME}）")
    return len(facts)


def _load_norms(protocol: str) -> list[dict]:
    """读 derived/spec/<protocol>/norms/norms.jsonl（v1 norms 产物）。

    容错：norms.jsonl 不存在时返回空列表（不 fail）。因为 source 源走 AutoSeeder、
    expert_note/vuln 源直接读 kb，都不依赖 norms；只有 rfc/traffic 源需要 norms，
    缺 norms 时它们自然映射 0 facts。
    """
    norms_path = _norms_path(protocol)
    if not norms_path.is_file():
        print(f"  [提示] norms.jsonl 不存在（{norms_path}），"
              f"rfc/traffic 源将映射 0 facts（source/expert_note/vuln 不受影响）")
        return []
    norms = []
    for line in norms_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            norms.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise SystemExit(f"norms.jsonl 解析失败: {exc}")
    return norms


def _build_source(source: str, norms: list[dict], registry,
                  protocol: str = "rtsp", constraints: bool = False,
                  vuln_llm: bool = False) -> tuple[list, int]:
    """对某源跑 v2 映射, 返回 (facts, skipped)。constraints=True 时 rfc 源额外抽语义约束；
    vuln_llm=True 时 vuln 源做 LLM 补全（Phase 2：trigger_sequence/mutation_hint）。"""
    if source == "expert_note":
        # 甲方案: 直接从 kb/<protocol>/expert_note JSON 映射, 不经过 norms.jsonl
        return expert_note_to_facts(protocol=protocol), 0
    if source == "vuln":
        # 甲方案: 直接从 kb/<protocol>/历史漏洞/*.json 结构化映射, 不经过 norms.jsonl。
        # vuln_llm 开启时额外用 LLM 补全漏洞模式（触发序列/变异提示），失败降级 rule 锚点。
        llm = None
        if vuln_llm:
            from core.llm import DeepSeekClient
            llm = DeepSeekClient()
        return vuln_to_facts(protocol=protocol, llm=llm), 0
    if source == "traffic":
        # traffic 源：从 kb/<protocol>/数据流量/*/ 的 client.log/rtsp.csv 确定性抽取
        # traffic norm（AutoSeeder 式 rule 部分，对齐 LLM-Boofuzz），再按 norm_id 去重
        # 映射 observed fact。不再依赖 norms.jsonl（v1 extractor 产物）。
        from core.fused.traffic_extractor import extract_traffic_norms
        from core.fused.traffic import traffic_norms_to_facts
        traffic_norms = extract_traffic_norms(protocol)
        return traffic_norms_to_facts(traffic_norms)
    if source == "rfc":
        # rfc 源：从 kb/<protocol>/spec/*.txt 确定性抽取 rfc norm（method/field/outcome），
        # 再映射 normative fact。不再依赖 norms.jsonl（v1 extractor 产物）。
        # --constraints 开启时额外抽取语义约束（借鉴 SemFuzz：构造约束+处理期望，
        # LLM 结构化；LLM 不可用则降级跳过，不影响结构抽取）。
        #
        # ★ A0.4：rfc 源走**质量闸**——① 构建质量闸（schema/重复ID/TOC残留）
        #   失败则**阻断构建**；② 离线评测（人工真值集）只作发布准入，缺真值集跳过。
        # ★ A0.5：产物按 build_id 写**独立快照**再原子切换，同输入两次 build 字节一致。
        from core.fused.rfc_extractor import (
            extract_rfc_norms, rfc_quality_report, compute_build_id,
            _load_rfc_config,
        )
        rfc_norms = extract_rfc_norms(protocol)
        if constraints:
            from core.fused.rfc_extractor import (extract_constraint_norms,
                                                  infer_structures)
            try:
                rfc_norms.extend(extract_constraint_norms(protocol))
                print(f"  [rfc] 约束抽取完成（共 {len(rfc_norms)} 条 norm 含约束）")
            except Exception as exc:  # noqa: BLE001
                print(f"  [rfc] 约束抽取失败，降级跳过: {exc}")
            try:
                struct_norms = infer_structures(protocol)
                rfc_norms.extend(struct_norms)
                print(f"  [rfc] 结构 LLM 兜底完成（补 {len(struct_norms)} 条方法/字段）")
            except Exception as exc:  # noqa: BLE001
                print(f"  [rfc] 结构 LLM 兜底失败，降级跳过: {exc}")
        facts = []
        skipped = 0
        for norm in rfc_norms:
            mapped = map_norm_to_facts(norm)
            if not mapped:
                skipped += 1
            else:
                facts.extend(mapped)

        # ---- A0.4 质量闸 ----
        cfg = _load_rfc_config(protocol)
        report = rfc_quality_report(protocol, facts=facts, norms=rfc_norms)
        print(f"  [rfc] 质量闸: norms={report.norm_count} facts={report.fact_count} "
              f"dup_fact_ids={report.dup_fact_ids} toc_pollution={report.toc_sourced_outcomes} "
              f"-> {'通过' if report.passed else '不通过'}")
        for issue in report.blocking_issues:
            print(f"  [rfc][阻断] {issue}")
        for warn in report.warnings:
            print(f"  [rfc][提示] {warn}")
        if not report.passed:
            raise SystemExit(
                f"[rfc] 质量闸未通过，构建中止（协议 {protocol}）："
                f"{'; '.join(report.blocking_issues)}")
        # ---- A0.5 幂等键 ----
        build_id = compute_build_id(protocol, rfc_norms, cfg)
        print(f"  [rfc] build_id={build_id}")
        _LAST_BUILD_IDS[protocol] = build_id
        return facts, skipped
    # source 源：AutoSeeder 方法（协议无关通用 query 检索 + LLM 状态转移分析，
    # 含字段级实例）。不再走 norms.jsonl 的正则 method 提取（ProtocolGPT 思路已弃用），
    # 也不再单独提取 header 清单（extract_header_facts 已移除，字段全集由字段级实例覆盖）。
    if source == "source":
        from core.fused.source_autoseeder import infer_source_facts
        facts = []
        facts.extend(infer_source_facts(protocol))
        return facts, 0
    # 其余源（rfc 等）走 norms.jsonl
    mapper = map_norm_to_facts
    types = KNOWN_SOURCES[source]
    facts = []
    skipped = 0
    for norm in norms:
        if norm.get("kb_source_type") not in types:
            continue
        mapped = mapper(norm)
        if not mapped:
            skipped += 1
        else:
            facts.extend(mapped)
    return facts, skipped


def _print_semantic_gate(label: str, rep) -> None:
    """打印 B-9 语义闸的**全部度量**（供人一眼核对，不做机器解析）。"""
    totals = dict(rep.semantic_rules_total or {})
    per = {k: v for k, v in totals.items() if k != "total"}
    print(f"  [{label}] 语义规则总数: {totals.get('total', 0)} 条"
          + (f"（分协议: {per}）" if per else ""))
    print(f"  [{label}] 可执行率: {rep.executable_rate:.4f} "
          f"（带 constraint 的规则 {rep.semantic_executable_rules} / "
          f"规则总数 {totals.get('total', 0)}）")
    print(f"  [{label}] 候选拒绝原因直方图: {rep.reject_reason_histogram}")
    print(f"  [{label}] `constraint is None` 计数: {rep.constraint_none_count}")
    print(f"  [{label}] `convertible=true` 计数: {rep.convertible_true_count}")
    print(f"  [{label}] gate_exercised（闸口是否真的被检验）: "
          f"{rep.gate_exercised}")
    print(f"  [{label}] 闸口说明: {rep.gate_note}")
    if rep.executable_rate_note:
        print(f"  [{label}] 可执行率口径: {rep.executable_rate_note}")
    for issue in rep.blocking_issues:
        print(f"  [{label}][阻断] {issue}")


def _run_rules_only(protocol: str, args) -> int:
    """`rules_only` 模式：**只产出语义规则与知识候选**（不产常规 facts/norms）。

    ★ 与 D-6 开关位（`PROTORAG_SEMANTIC_RULES`）**正交**（本模式**不改**它）：
      · D-6 管「**已落库的**语义规则是否参与生成」（下游 bundle / 种子生成）；
      · 本模式管「**是否产出**语义规则与候选」（构建侧）。
      本模式显式开启**产出**，但**绝不置位** D-6 ⇒ 全局默认仍是
      「语义规则不参与生成」，下游行为不变。

    ★ 三个闸在 `rules_only` 模式**同样生效**：
      ① 写盘**前**审内存产物（有违规 ⇒ 阻断，且**不落盘**）；
      ② 落盘后审**真实文件**（强制机制 4 针对的就是文件内容）；
      ③ 报告给出全部度量 + `gate_exercised` 自检。
    """
    from core.fused.rfc_extractor import (
        SEMANTIC_ROOT_ENV_KEY, audit_semantic_library, audit_semantic_rows,
        build_semantic_rules, save_semantic_library, semantic_candidate_row,
        semantic_quality_report, semantic_rule_row,
    )
    if args.semantic_root:
        os.environ[SEMANTIC_ROOT_ENV_KEY] = str(args.semantic_root)

    bundle = build_semantic_rules(protocol)
    print(f"  [rules-only] 约束候选 {bundle.candidate_total} 条 → "
          f"语义规则 {len(bundle.rules)} 条 / 知识候选 {len(bundle.candidates)} 条")
    print(f"  [rules-only] 已知字段集: {len(bundle.known_fields)} 个")

    # ---- 闸①：写盘**前**审内存产物（违规 ⇒ 阻断，且**不落盘**）----
    pre = audit_semantic_rows(
        protocol,
        [semantic_rule_row(r) for r in bundle.rules],
        [semantic_candidate_row(c) for c in bundle.candidates])
    pre_rep = semantic_quality_report(protocol, pre)
    _print_semantic_gate("rules-only/写盘前", pre_rep)
    if not pre_rep.passed:
        raise SystemExit(
            f"[rules-only] 语义规则闸未通过，构建中止（协议 {protocol}）："
            f"{'; '.join(pre_rep.blocking_issues)}")

    # ---- 落盘（**只写**语义四库，不写 facts/norms）----
    written = save_semantic_library(protocol, bundle.rules, bundle.candidates)
    print(f"  [rules-only] 规则库 -> {written['rules']}")
    print(f"  [rules-only] 候选库 -> {written['candidates']}")

    # ---- 闸②：审**落盘后的真实文件**（强制机制 4 的口径）----
    post = audit_semantic_library(protocol)
    post_rep = semantic_quality_report(protocol, post)
    _print_semantic_gate("rules-only/落盘后", post_rep)
    if not post_rep.passed:
        raise SystemExit(
            f"[rules-only] 语义规则闸未通过，构建中止（协议 {protocol}）："
            f"{'; '.join(post_rep.blocking_issues)}")

    print(f"[rules-only] 语义规则闸通过（协议 {protocol}）："
          f"规则 {post_rep.semantic_rules_total.get('total', 0)} 条 / "
          f"候选 {post_rep.semantic_candidates_total} 条")
    return 0


def _write_and_validate(source: str, facts, registry, protocol: str = "rtsp",
                         build_id: str | None = None) -> int:
    """落盘 get_fact_view jsonl + fail-closed 校验 (内存 + 落盘读回)。

    ★ A0.5：快照原子切换。
      产物先写到**独立快照目录**（`<dest_dir>/snapshots/<build_id>/`），
      再**复制**一份到正式路径 `<dest_dir>/<source>.jsonl`（同目录临时文件 +
      `os.replace` 原子切换）。
      好处：
        - 中途失败不会留下半截产物（正式路径仍是上一版完整文件）；
        - 并发 build 互不覆盖（各自写自己的快照，最后一次 replace 生效）；
        - 快照保留历史版本，可回滚（评审 F5「回退机制不完整」）。
      未提供 build_id 时退化为**直接写**（保持向后兼容）。

    ★ A0.5 修复（2026-11-01）：原先用 `os.replace(snap_file, dest)` —— 那是
      **搬移**语义，快照文件被搬到正式路径后 `snapshots/<build_id>/` 目录
      **永远是空的**（QA 实测三协议快照全空）⇒ 快照/回滚机制完全失效。
      现在改为**复制语义**：快照文件留在原处，另用 `shutil.copy2` 复制到
      同目录临时文件，再 `os.replace` 原子切换正式路径（原子性不变）。
    """
    dest_dir = paths.per_source_facts_dir(protocol, source)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{source}.jsonl"

    # 1. 内存 fail-closed
    failed_mem = 0
    for f in facts:
        try:
            validate_fact(f, registry)
        except Exception as exc:  # noqa: BLE001
            failed_mem += 1
            print(f"    [fail-closed] {f.fact_id}: {exc}")

    # 2. 落盘（先写快照，再原子切换）
    views = [get_fact_view(f) for f in facts]
    lines = [json.dumps(v, ensure_ascii=False) + "\n" for v in views]

    if build_id:
        snap_dir = dest_dir / "snapshots" / build_id
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_file = snap_dir / f"{source}.jsonl"
        with snap_file.open("w", encoding="utf-8") as fh:
            fh.writelines(lines)
        # ★ 复制（不是搬移）→ 快照内容留存，历史版本可回滚；
        #   正式路径仍走「临时文件 + os.replace」保证原子切换。
        tmp_file = dest_dir / f".{source}.jsonl.tmp"
        shutil.copy2(snap_file, tmp_file)
        os.replace(tmp_file, dest)
        # 记录本次 build_id（供回溯/回滚）
        (dest_dir / "current_build_id.txt").write_text(
            build_id + "\n", encoding="utf-8")
    else:
        with dest.open("w", encoding="utf-8") as fh:
            fh.writelines(lines)

    return failed_mem, dest


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="v2 中枢构建入口（**一次一个协议 x 一个知识源**）")
    parser.add_argument("--list-sources", action="store_true",
                        help="识别知识库中有哪几种知识源, 打印后退出")
    # ★★ 架构约束（2026-10-31 用户明确）：本模型**一次只处理一个知识库 ×
    #    一个知识源**。原 nargs="+" 允许多源，且清理时连带清掉其他源 → 改单值。
    # ★★ 批次 1.6（步 0）：恢复**多源**支持。
    #   2026-10-31 曾把它改成单值，理由是「清理时连带清掉其他源 ⇒ 22 个下游测试失效」。
    #   现在的解法不同：**清空整个中枢**（而不是「部分源清、部分源留」）⇒
    #   中枢里只有本次抽出的源 ⇒ 既不混杂历史、也不会让下游读到「缺失源的旧数据」。
    #   ⇒ `--sources` 恢复 nargs="+"，与模块 docstring 的用法示例一致。
    parser.add_argument("--sources", default=["rfc"], nargs="+",
                        choices=sorted(KNOWN_SOURCES),
                        help="本次处理的知识源（可多个；默认 rfc）。"
                             "例：--sources rfc expert_note")
    parser.add_argument("--no-purge", action="store_true",
                        help="★ 批次 1.6：**不清空**整个中枢（默认清空该协议的五源"
                             "抽取产物 + 语义四库）⇒ 增量/多源联合调试时保留其它源")
    parser.add_argument("--with-rules", action="store_true",
                        help="★ 批次 1.6（D-7 选项 A）：把**语义规则的发布**纳入"
                             "本批次 ⇒ 清空语义四库后重新发布（否则规则随清空消失，"
                             "而它**不能从 kb 重建**，需 LLM）")
    # ★★ 协议显式化：不传则报错，避免「默认 rtsp」的隐式误跑/批量。
    parser.add_argument("--protocol", required=True,
                        help="本次处理的目标协议（**单个**），如 rtsp / sip / smtp")
    parser.add_argument("--no-clean", action="store_true",
                        help="构建时不清空该协议该源的旧 facts（默认在**质量闸"
                             "通过后**清空**本次指定的源**，用于全量重建；"
                             "保留旧数据可做增量抽取）")
    parser.add_argument("--constraints", action="store_true",
                        help="rfc 源额外抽取语义约束（借鉴 SemFuzz 构造约束+处理期望，"
                             "LLM 结构化；需 DEEPSEEK_API_KEY，失败自动降级跳过）")
    parser.add_argument("--vuln-llm", action="store_true",
                        help="vuln 源额外 LLM 补全漏洞模式（Phase 2：trigger_sequence/mutation_hint）；"
                             "需 DEEPSEEK_API_KEY，失败自动降级为 rule 锚点)")
    # ★ D-6：语义规则参与生成的可关闭开关位（**默认关闭**）。
    #   本脚本是 Layer-2 构建脚本（不产 bundle）⇒ 这里只把开关位暴露到 CLI
    #   并让状态可见，不做别的语义规则处理。
    parser.add_argument("--enable-semantic-rules", action="store_true",
                        help="开启「语义规则参与生成」（D-6 开关位；**默认关闭**——"
                             "关闭时 bundle 的 semantic_rules 不参与任何生成）")
    # ★ B-9：rules_only 模式 —— **只产出语义规则与知识候选**。
    parser.add_argument("--rules-only", action="store_true",
                        help="**只产出语义规则与知识候选**（rules_only 模式）："
                             "写 <四库>/<协议>/rfc/semantic/{rules,candidates}.jsonl，"
                             "**不产出**常规 facts/norms；B-9 的三个闸同样生效。"
                             "⚠ 本模式**不改变** D-6 开关位（PROTORAG_SEMANTIC_RULES "
                             "保持默认关闭）")
    parser.add_argument("--semantic-root", default=None,
                        help="语义四库根目录覆盖（默认 "
                             "derived/per_source/<协议>/rfc/semantic/）。"
                             "用于把构建产物隔离到临时目录，避免污染 derived/")
    args = parser.parse_args(argv)

    # ★ D-6：开关置位（进程内 + 环境变量双保险）——默认**不置位**（保持关闭）。
    #   ⚠ `--rules-only` 模式**不改**这个开关位（rules_only 只管「产出」，
    #     D-6 管「已落库的规则是否参与生成」——两者正交）。
    if args.enable_semantic_rules and not args.rules_only:
        os.environ[SEMANTIC_RULES_ENV_KEY] = "1"
        set_semantic_rules_enabled(True)

    # ★ 批次 1.6：--sources 恢复多选（列表）
    sources = list(args.sources) if isinstance(args.sources, list) \
        else [args.sources]
    protocol = args.protocol

    # ---- 单协议语义：校验协议存在 ----
    known = {p.name for p in paths.kb_root().iterdir() if p.is_dir()}
    if protocol.lower() not in known:
        print(f"[错误] 协议 {protocol!r} 不在 kb/ 下（可用: "
              f"{', '.join(sorted(known))}）", file=sys.stderr)
        return 2

    # ---- ★ B-9：rules_only 模式（**只产语义规则与候选**，独立分支）----
    if args.rules_only:
        print(f"仓库根: {REPO_ROOT}")
        print(f"本次处理: 协议={protocol}  模式=rules_only"
              f"（**只产**语义规则与知识候选，不产 facts/norms）")
        print("语义规则参与生成(D-6): "
              f"{'开启' if semantic_rules_enabled() else '关闭'}"
              "（rules_only 模式**不改** D-6 开关位 PROTORAG_SEMANTIC_RULES）")
        if args.enable_semantic_rules:
            print("[提示] 本模式下 --enable-semantic-rules **不生效**"
                  "（rules_only 只管产出，不管下游是否参与生成）")
        print()
        return _run_rules_only(protocol, args)

    norms = _load_norms(protocol)
    registry = load_registry()

    if args.list_sources:
        print("知识库知识源识别结果（扫描 kb/ 目录，仅列出实际存在的源）:")
        found = scan_kb_sources()
        if not found:
            print("  （kb/ 目录下未发现任何知识源数据）")
        for src, info in found.items():
            print(f"  {src:14s} 目录={info['dir']:12s} 文件数={info['files']}")
        return 0

    print(f"仓库根: {REPO_ROOT}")
    print(f"本次处理: 协议={protocol}  知识源={', '.join(sources)}"
          f"  （单协议 x {'/'.join(sources)}）")
    print(f"中枢清空: {'否（--no-purge）' if args.no_purge else '是（整个中枢的五源产物）'}")
    # ★ D-6：把开关状态打进构建摘要 ⇒ 运行者一眼可见当前语义规则是否参与生成。
    print(f"语义规则参与生成: {'开启' if semantic_rules_enabled() else '关闭'}")
    print()

    # ★★ 顺序契约（2026-11-01 修复 P2-1，批次 1.6 保留并扩展）：
    #     抽取 → 映射 → **质量闸** → **清空整个中枢** → 写盘
    #   闸不通过时 `_build_source` 抛 SystemExit ⇒ **旧产物原封不动**
    #   （清空必须在**全部源**闸通过之后，否则阻断构建会把中枢清空）。
    #
    # 清掉上一次调用残留的幂等键，避免非 rfc 源误用上一次的 build_id。
    _LAST_BUILD_IDS.pop(protocol, None)

    # ---- ① 逐源独立抽取（每次一个源；各自过闸）-----------------------------
    pending: dict[str, tuple[list, str | None]] = {}
    build_ids: dict[str, str] = {}
    for source in sources:
        _LAST_BUILD_IDS.pop(protocol, None)
        facts, skipped = _build_source(source, norms, registry, protocol,
                                       constraints=args.constraints,
                                       vuln_llm=args.vuln_llm)
        build_id = _LAST_BUILD_IDS.pop(protocol, None)
        build_ids[source] = build_id or ""
        pending[source] = (facts, skipped, build_id)  # type: ignore[assignment]
        print(f"[{source}] 抽取完成：{len(facts)} Facts / skipped {skipped}")

    # ---- ② 全部源闸通过 ⇒ 清空整个中枢（★ 批次 1.6 步 0）------------------
    if not args.no_purge:
        _purge_hub_for_batch(protocol, purge_semantic=True)

    # ---- ③ 写盘（逐源；原子切换）------------------------------------------
    for source in sources:
        facts, skipped, build_id = pending[source]
        failed, dest = _write_and_validate(source, facts, registry, protocol,
                                           build_id=build_id)
        print(f"[{source}] 映射 {len(facts)} Facts / skipped {skipped} "
              f"(kind 未实现) / fail-closed 失败 {failed}")
        print(f"[{source}] -> {_repo_rel(dest)}")

    # ---- ③' 物化协议骨架（★ 单源调试时链路不断的前提）----------------------
    skeleton_count = _materialize_skeleton(protocol)

    # ---- ④ 语义规则纳入本批次（D-7 选项 A）----------------------------------
    if args.with_rules:
        _republish_rules(protocol)
    elif not args.no_purge:
        print("[规则] ★ 语义四库已随中枢清空而清空，且**未**指定 --with-rules "
              "⇒ 本次中枢**不含**语义规则（legal_boundary / response_expectation "
              "为空）。规则**不能从 kb 重建**（需 LLM）⇒ 需要时请加 --with-rules。")

    # ---- ⑤ 写本次源集合清单（唯一权威）-------------------------------------
    _write_source_manifest(protocol, sources, build_ids,
                            skeleton_count=skeleton_count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
