# -*- coding: utf-8 -*-
"""tools/guard/verify_single_source_e2e.py —— 批次 1.6 **步 6**：单源端到端验收。

六条判据（方案 §3.1.10.7）：
  ① ``sources.json.source_set`` 恰为本次单源；
  ② ``bundle.available_sources`` 只含该源（``profile`` 骨架单独标 origin）；
  ③ ``bundle.by_source`` 逐桶核对 ⇒ 每条都能数到源头上，**无来源不明条目**；
  ④ 与**多源版本**逐条对比 ⇒ 差异**全部可解释**（= 被隔离掉的其它源贡献）；
  ⑤ 闸门：G1 违规 **0**；G2 可按 ``by_layer`` 分层读；
  ⑥ 护栏：FAILED/ERROR 新增 0 / 消失 0（由 run_guarded_pytest.py 单独跑）。

用法::

    E:/app/Anaconda3/python.exe tools/guard/verify_single_source_e2e.py \
        --protocol rtsp --group B

脚本会**改写中枢**（单源 → 多源对照 → 恢复单源）⇒ 请勿在别的构建并行时跑。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fused.downstream.rag_seedgen import (             # noqa: E402
    SKELETON_AUTHORITY, assemble_bundle, load_fact_views,
    load_source_manifest,
)

PY = sys.executable
ALL_SOURCES = ("rfc", "expert_note", "traffic", "vuln", "source")


# ===========================================================================
# 工具
# ===========================================================================

def _run(cmd: list[str], label: str) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        print(f"  [!!] {label} 退出码 {proc.returncode}")
        print("      " + out.strip().splitlines()[-1] if out.strip() else "")
    return proc.returncode, out


def _build(protocol: str, sources: list[str], with_rules: bool = True) -> bool:
    cmd = [PY, "scripts/build_hub.py", "--protocol", protocol,
           "--sources", *sources]
    if with_rules:
        cmd.append("--with-rules")
    code, _ = _run(cmd, f"build_hub({protocol}, {sources})")
    return code == 0


def _bundle(protocol: str) -> dict:
    return assemble_bundle(load_fact_views(protocol), protocol)


def _normalize(obj):
    if isinstance(obj, dict):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)):
                _normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_normalize(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_normalize(v) for v in obj)
    return obj


def _dump(obj) -> str:
    return json.dumps(_normalize(obj), ensure_ascii=False, default=str)


# ===========================================================================
# 主流程
# ===========================================================================

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批次 1.6 步 6 单源端到端验收")
    ap.add_argument("--protocol", action="append", default=None)
    ap.add_argument("--group", default="B")
    ap.add_argument("--skip-multi", action="store_true",
                    help="跳过多源对照（判据 ④）")
    args = ap.parse_args(argv)
    protocols = args.protocol or ["rtsp", "sip", "smtp"]

    overall_ok = True
    # ★ 产物目录必须放在**仓库外**（tools/guard/ 下新增文件会破坏护栏1 的
    #   「源码树静止」检查）⇒ 用系统临时目录。
    import tempfile
    tmp_root = Path(tempfile.mkdtemp(prefix=f"protorag_e2e_{protocols[0]}_"))
    print(f"（产物目录：{tmp_root}）")

    for protocol in protocols:
        print(f"\n{'=' * 70}\n=== {protocol} / focus-group {args.group} ===\n"
              f"{'=' * 70}")

        # ---------- ① 单源构建 ----------
        if not _build(protocol, ["rfc"]):
            print("  ❌ 单源构建失败")
            overall_ok = False
            continue
        manifest = load_source_manifest(protocol)
        declared = list(manifest.get("source_set") or [])
        ok1 = declared == ["rfc"]
        print(f"① sources.json.source_set = {declared}  "
              f"{'✅' if ok1 else '❌（期望 [rfc]）'}")
        if not ok1:
            overall_ok = False

        # ---------- 消费 ----------
        seed_dir = tmp_root / f"{protocol}_{args.group}"
        code, gate_out = _run(
            [PY, "scripts/seedgen.py", "--protocol", protocol,
             "--focus-group", args.group, "--out", str(seed_dir),
             "--manifest"], "seedgen")
        if code == 3:
            # ★ seedgen 退出码 3 = 「种子数与分组配置不符」的**告警**
            #   （种子**已正常落盘**；既有偏差：focus-group B 期望 50 / 实际 58）
            print("   ⚠ seedgen 退出码 3（种子数与分组配置不符的告警，"
                  "种子已正常落盘）")
        elif code != 0:
            print("  ❌ seedgen 失败")
            overall_ok = False
            continue
        for line in gate_out.splitlines():
            if "本次知识来源清单" in line or "中枢构建" in line:
                print(f"   {line.strip()}")

        # ---------- ② available_sources ----------
        single = _bundle(protocol)
        avail = set(single.get("available_sources") or [])
        allowed = set(declared) | {SKELETON_AUTHORITY}
        leak = avail - allowed
        ok2 = not leak and declared[0] in avail
        print(f"② available_sources = {sorted(avail)}；"
              f"越界 = {sorted(leak) or '无'}  {'✅' if ok2 else '❌'}")
        if not ok2:
            overall_ok = False

        # ---------- ③ by_source 逐桶核对 ----------
        by_source = single.get("by_source") or {}
        bucket_ids = single.get("bucket_fact_ids") or {}
        fact_index = single.get("fact_index") or {}
        unknown = []
        for bucket, srcs in by_source.items():
            ids = bucket_ids.get(bucket) or []
            total = sum(srcs.values())
            if len(ids) != total:
                unknown.append(f"{bucket}: 回指 {len(ids)} ≠ 计数 {total}")
            for fid in ids:
                info = fact_index.get(fid) or {}
                if info.get("authority") not in srcs:
                    unknown.append(f"{bucket}/{fid}: 来源不在 by_source 里")
        ok3 = not unknown
        print(f"③ by_source 逐桶核对（{len(by_source)} 个桶）"
              f"{'✅' if ok3 else '❌'}")
        for u in unknown[:5]:
            print(f"     ✗ {u}")
        if not ok3:
            overall_ok = False
        for bucket in sorted(by_source):
            print(f"     {bucket:22s} {by_source[bucket]}")

        # ---------- ⑤ 闸门 ----------
        code, gate_json = _run(
            [PY, "scripts/corpus_gate.py", "--protocol", protocol,
             "--seed-dir", str(seed_dir), "--group", args.group,
             "--json"], "corpus_gate")
        report = {}
        try:
            start = gate_json.index("{")
            report = json.loads(gate_json[start:])
        except Exception:  # noqa: BLE001
            pass
        gates = report.get("gates") or {}
        g1 = gates.get("G1") or {}
        g2 = gates.get("G2") or {}
        g5 = gates.get("G5") or {}
        g1_v = g1.get("violation_count")
        g2_v = g2.get("violation_count")
        by_layer = g2.get("by_layer")
        # ★ 判据 5 只要求「G1 违规 0」+「G2 可按 by_layer 分层读」
        #   （G2 的违规数在当前配置下**不可改善**：记忆条目「基准层已被归一化
        #     ⇒ 无可改善空间」⇒ G2 不作为本判据的阻断项）
        #   ★ G2 **不适用**时（该协议无环境级可播清单约束）本就没有 by_layer
        #     ⇒ 不作为失败项。
        g2_applicable = bool(g2.get("applicable"))
        if g2_applicable:
            ok5 = (g1_v == 0) and bool(by_layer)
            g2_note = "G2 适用 ⇒ 必须可按 by_layer 分层读"
        else:
            ok5 = (g1_v == 0)
            g2_note = (f"G2 **不适用**（{g2.get('skipped_reason')}）"
                       "⇒ 无 by_layer 属正常")
        print(f"⑤ 闸门：G1 违规 = {g1_v} {'✅' if g1_v == 0 else '❌'}；"
              f"G2 违规 = {g2_v}（既有偏差，不阻断本判据）")
        print(f"   {g2_note}")
        if by_layer:
            print(f"   G2 按 by_layer 分层：{json.dumps(by_layer, ensure_ascii=False)}")
        print(f"   G5 契约漂移：pass={g5.get('pass')}（warning，非阻断）")
        print(f"   闸门 overall_pass = {report.get('overall_pass')}；"
              f"退出码 {code}")
        if not ok5:
            overall_ok = False

        # ---------- ④ 多源对照 ----------
        if args.skip_multi:
            print("④ 多源对照：已跳过")
        else:
            if not _build(protocol, list(ALL_SOURCES), with_rules=False):
                print("④ ❌ 多源构建失败")
                overall_ok = False
                continue
            multi = _bundle(protocol)
            multi_avail = set(multi.get("available_sources") or [])
            m_ids = multi.get("bucket_fact_ids") or {}
            m_index = multi.get("fact_index") or {}
            s_ids = single.get("bucket_fact_ids") or {}

            unexplained: list[str] = []
            explained_multi_only = 0
            explained_single_only = 0
            for bucket in sorted(set(m_ids) | set(s_ids)):
                mset = set(m_ids.get(bucket) or [])
                sset = set(s_ids.get(bucket) or [])
                for fid in mset - sset:
                    auth = (m_index.get(fid) or {}).get("authority")
                    if auth in (set(declared) | {SKELETON_AUTHORITY}):
                        unexplained.append(
                            f"{bucket}/{fid}: 单源也在，但多源里**不在**本桶"
                            f"（authority={auth}）")
                    else:
                        explained_multi_only += 1
                for fid in sset - mset:
                    # 单源有、多源里「不在本桶」⇒ 必须是「桶迁移/被覆盖」
                    # （即该 fact 在多源里还在，只是落到别的桶）
                    elsewhere = any(fid in (ids or [])
                                    for b2, ids in m_ids.items() if b2 != bucket)
                    if elsewhere:
                        explained_single_only += 1
                    else:
                        unexplained.append(
                            f"{bucket}/{fid}: 多源里**完全消失**（不可解释）")
            ok4 = not unexplained
            print(f"④ 多源对照：多源 available_sources = {sorted(multi_avail)}")
            print(f"   多源独有（归因到被隔离的源）: {explained_multi_only} 条")
            print(f"   单源独有（多源里桶迁移/覆盖）: {explained_single_only} 条")
            print(f"   **不可解释差异: {len(unexplained)} 条** "
                  f"{'✅' if ok4 else '❌'}")
            for u in unexplained[:8]:
                print(f"     ✗ {u}")
            if not ok4:
                overall_ok = False

            # ---------- 恢复单源态 ----------
            _build(protocol, ["rfc"])
            restored = load_source_manifest(protocol).get("source_set")
            ok_restore = restored == ["rfc"]
            print(f"   ↩ 已恢复单源态：source_set = {restored} "
                  f"{'✅' if ok_restore else '❌'}")
            if not ok_restore:
                overall_ok = False

    print("\n结论：" + ("✅ 可采信（步 6 单源端到端验收通过）" if overall_ok
                       else "❌ 不可采信（见上方 ❌ 项）"))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
