# -*- coding: utf-8 -*-
"""scripts/run_pipeline.py —— **统一入口**：识别协议 → 建模 → 出种子（2026-11-08 新增）。

★ 用户要求：「每次运行前对目标协议进行识别（可以通过调用 LLM 进行判断），
  然后传参给我这个项目模型」。

★ 流程：
  ① **协议识别**：``core.protocol_id.identify_protocol``（规则优先 + LLM 兜底）
     —— 输入可以是协议名、别名、目录、文件，或**自然语言描述**；
  ② **中枢重置**：``paths.purge_hub()`` ⇒ 「每次抽取把上一次清理掉」；
  ③ **建中枢**：``build_hub --protocol X --sources ...`` ⇒ 中枢里只有 X；
  ④ **建图**：``build_graph --protocol X``；
  ⑤ **出种子**：``seedgen --protocol X``；
  ⑥ **报告**：协议、源集合、各阶段产物规模。

用法：
    python scripts/run_pipeline.py --target "DHCPv4"
    python scripts/run_pipeline.py --target "kb/dhcpv4/spec/rfc2131.txt"
    python scripts/run_pipeline.py --target "用 UDP 做地址分配的协议" --use-llm
    python scripts/run_pipeline.py --target rtsp --skip-seeds
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _run(cmd: list[str], *, title: str) -> bool:
    """跑一个子命令（**透传输出** ⇒ 用户能看到进度）。"""
    print(f"\n===== {title} =====", flush=True)
    print(f"$ {' '.join(cmd)}", flush=True)
    r = subprocess.run(cmd, cwd=str(ROOT))
    ok = r.returncode == 0
    print(f"----- {title}: {'OK' if ok else f'失败（退出码 {r.returncode}）'} -----",
          flush=True)
    return ok


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="统一入口：识别目标协议 → 重置中枢 → 建中枢 → 建图 → 出种子")
    ap.add_argument("--target", required=True,
                    help="目标协议：协议名 / 别名 / 路径 / 自然语言描述")
    ap.add_argument("--sources", default="rfc",
                    help="本次参与的知识源（逗号分隔）")
    ap.add_argument("--use-llm", action="store_true",
                    help="★ 规则无法唯一判定时**用 LLM 判定**")
    ap.add_argument("--skip-graph", action="store_true", help="跳过建图")
    ap.add_argument("--skip-seeds", action="store_true", help="跳过出种子")
    ap.add_argument("--seed-out", default="", help="种子输出目录（默认 derived/seeds/<协议>/）")
    ap.add_argument("--dry-run", action="store_true", help="只识别，不执行")
    args = ap.parse_args(argv)

    # ── ① 协议识别 ────────────────────────────────────────────────
    from core.protocol_id import identify_from_path, identify_protocol
    target = str(args.target).strip()
    hit = identify_from_path(target)
    if hit:
        ident = {"protocol": hit, "method": "path", "scores": [],
                 "candidates": [], "note": f"从路径识别：{target}"}
    else:
        ident = identify_protocol(target, use_llm=args.use_llm)
    print("== ① 协议识别 ==")
    print(f"   输入: {target}")
    print(f"   结果: {ident.get('protocol') or '(未判定)'} "
          f"[{ident.get('method') or '-'}] {ident.get('note', '')}")
    if not ident.get("protocol"):
        print("!! 无法判定目标协议 ⇒ 请显式写协议名（rtsp / sip / smtp / dhcpv4）",
              file=sys.stderr)
        return 2
    proto = ident["protocol"]

    if args.dry_run:
        print("\n（--dry-run：只识别，不执行后续步骤）")
        return 0

    # ── ② 中枢重置（每次抽取把上一次清理掉）────────────────────────
    from core import paths
    print("\n== ② 中枢重置 ==")
    removed = paths.purge_hub()
    print(f"   中枢已清空: {', '.join(removed) if removed else '(空)'}")
    # ★ GraphRAG 整理层**一并重置**（图是从中枢投影出来的
    #   ⇒ 留着旧图就会带着上一个协议的知识去检索）。
    _g = paths.purge_graph()
    print(f"   图已清空: {', '.join(_g) if _g else '(空)'}")

    sources = [s.strip() for s in (args.sources or "").split(",") if s.strip()]

    # ── ③ 建中枢 ─────────────────────────────────────────────────
    py = sys.executable
    cmd = [py, str(ROOT / "scripts" / "build_hub.py"), "--protocol", proto]
    if sources:
        cmd += ["--sources"] + sources
    if not _run(cmd, title=f"③ 建中枢（{proto}｜源={sources or '默认'}）"):
        return 1

    # ── ④ 建图 ───────────────────────────────────────────────────
    if not args.skip_graph:
        if not _run([py, str(ROOT / "scripts" / "build_graph.py"),
                     "--protocol", proto], title=f"④ 建图（{proto}）"):
            return 1

    # ── ⑤ 出种子 ─────────────────────────────────────────────────
    if not args.skip_seeds:
        cmd = [py, str(ROOT / "scripts" / "seedgen.py"), "--protocol", proto]
        if args.seed_out:
            cmd += ["--out", args.seed_out]
        if not _run(cmd, title=f"⑤ 出种子（{proto}）"):
            return 1

    # ── ⑥ 报告 ───────────────────────────────────────────────────
    print("\n== ⑥ 本次运行报告 ==")
    from core.fused.downstream.rag_seedgen import load_fact_views
    views = load_fact_views(proto)
    print(f"   协议: {proto}（识别方式：{ident.get('method')}）")
    print(f"   源集合: {sources or '(默认)'}")
    print(f"   中枢事实数: {len(views)}")
    hub = paths.hub_root()
    for rel in ("facts", "graph", "sources.json"):
        p = hub / rel
        if p.exists():
            print(f"   产物: derived/hub/{rel}")
    print("\n★ 中枢里**只有**本次协议的信息（每次抽取已重置）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
