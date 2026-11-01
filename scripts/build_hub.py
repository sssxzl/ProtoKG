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
    """清空某源的产物目录，但**保留** `facts/snapshots/`（历史幂等快照）。

    ★ A0.5 修复（2026-11-01）：原先直接 `shutil.rmtree(source_dir)`，把
      `facts/snapshots/<build_id>/` 里的历史快照一并删掉 ⇒ 文档承诺的
      「可回滚到历史版本（F5）」根本无从谈起。

      现在：
        - **无快照**时行为不变（整目录删除）；
        - **有快照**时只删源目录下的其它全部内容，保留 `facts/snapshots/`。

    Args:
        source_dir: `derived/per_source/<protocol>/<source>/` 目录。
    """
    snap_dir = source_dir / "facts" / "snapshots"
    if not snap_dir.is_dir():
        shutil.rmtree(source_dir)
        return
    # 有快照：保留 facts/snapshots/，其余内容全删
    for child in source_dir.iterdir():
        if child.name == "facts":
            continue
        _remove_path(child)
    facts_dir = source_dir / "facts"
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
    parser.add_argument("--sources", default="rfc",
                        choices=sorted(KNOWN_SOURCES),
                        help="本次处理的知识源（**单个**；默认 rfc）。"
                             "本模型一次只处理一个知识源，多源请分次调用。")
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
                             "需 DEEPSEEK_API_KEY，失败自动降级为 rule 锚点）")
    args = parser.parse_args(argv)

    source = args.sources
    protocol = args.protocol

    # ---- 单协议语义：校验协议存在 ----
    known = {p.name for p in paths.kb_root().iterdir() if p.is_dir()}
    if protocol.lower() not in known:
        print(f"[错误] 协议 {protocol!r} 不在 kb/ 下（可用: "
              f"{', '.join(sorted(known))}）", file=sys.stderr)
        return 2

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
    print(f"本次处理: 协议={protocol}  知识源={source}  （单协议 x 单源）")
    print()

    # ★★ 顺序契约（2026-11-01 修复 P2-1）：
    #     抽取 → 映射 → **质量闸** → **清理** → 写盘
    #   闸不通过时 `_build_source` 抛 SystemExit，**旧产物原封不动**
    #   （原先「先清理、后校验」⇒ 阻断构建反而把该协议的 rfc facts 删空）。
    #
    # 清掉上一次调用残留的幂等键，避免非 rfc 源误用上一次的 build_id。
    _LAST_BUILD_IDS.pop(protocol, None)

    facts, skipped = _build_source(source, norms, registry, protocol,
                                   constraints=args.constraints,
                                   vuln_llm=args.vuln_llm)

    # 质量闸通过后才清空**本次指定的源**的旧 facts，避免旧数据残留污染本次产物。
    # 只清这一个源 —— 同协议的其他源（source/expert_note/vuln/traffic）
    # 不受影响：它们是独立知识源、独立生命周期。
    if not args.no_clean:
        _clean_per_source(protocol, sources=[source])

    build_id = _LAST_BUILD_IDS.pop(protocol, None)
    failed, dest = _write_and_validate(source, facts, registry, protocol,
                                       build_id=build_id)
    print(f"[{source}] 映射 {len(facts)} Facts / skipped {skipped} "
          f"(kind 未实现) / fail-closed 失败 {failed}")
    print(f"[{source}] -> {dest.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
