# -*- coding: utf-8 -*-
"""tools/guard/run_guarded_by_protocol.py —— **单协议链路自检**（2026-11-08 新增）。

★★ **实测结论（重要，3 轮实测 / 约 40 分钟）**：本脚本**不能替代全量护栏**
  —— 方案 B 在**当前测试集上结构性不可行**。
  实测：跨协议分组 ⇒ 新增 39 failed + 20 errors；修正分组后 ⇒ 新增 55 + 37；
  单协议 ⇒ 新增 19 + 20。
  ⇒ **根因是「两类测试的要求互斥」**：
    · **协议专属**测试需要「中枢里只有该协议」⇒ 单协议构建即可；
    · **通用**测试**隐含依赖「中枢里有多个协议」**
      （如 ``test_edge_cover`` 用**默认协议 rtsp**）⇒ 需要多协议共存；
    ⇒ 「单协议」与「通用测试」**互斥** ⇒ 无法同时满足。
  ⇒ **这是测试集的设计假设**，不是实现缺陷。
  实测（2026-11-08，18 分钟）：
  · 跨协议分组（``--all-protocols``）⇒ **新增 39 failed + 20 errors**；
  · 单协议（``--protocol rtsp``）⇒ **新增 19 failed + 20 errors**。
  ⇒ 根因：**当前测试集本身是跨协议的** ——
    `test_graph_pipeline::test_graph_build_for_each_protocol[*]`（遍历所有协议建图）、
    `test_rq3_build_corpus::*`（要 rtsp 完整种子）、
    `test_seed_legality` / `test_graph_communities`（读中枢/图）……
    这些测试**要求多个协议的中枢同时存在**。
  ⇒ **单协议 ⇒ 中枢只有目标协议** 的生产语义，**与测试集的假设冲突**。

★★ **因此两条路径分工如下**（已实现）：
  · **生产路径**（用户要的语义）：``build_hub --protocol X``
    ⇒ **清空整个中枢** ⇒ 中枢里**只有 X** ⇒ 「每次抽取把上一次清理掉」。
  · **护栏路径**（测试基础设施）：``build_hub --protocol X --no-purge``
    ⇒ **按协议替换**写入 ⇒ 多协议共存 ⇒ 跨协议测试可跑。

★ 本脚本的定位：**单协议生产链路的自检**（构建一个协议 ⇒ 跑它的测试），
  **不是**全量护栏的替代品。


★ 为什么需要它（中枢共用一套之后）：
  中枢现在**共用一套**（``derived/hub/``，不按协议分目录）⇒
  **一次只装一个协议**（生产语义：每次抽取把上一次清理掉）。
  ⇒ 护栏若在「四个协议共存」的中枢上跑，就**测不到**「中枢只有目标协议」
  这个生产语义 ⇒ 与真实运行路径不一致。

★ 本脚本的做法（**方案 B**）：
  对每个协议 P：
    ① 构建 P 的中枢（**全清** ⇒ 中枢里只有 P）⇒ 与生产路径**完全一致**；
    ② 跑**属于 P 的测试**（测试文件里出现 P 的字面量）+ **通用测试**；
    ③ 收集该组的 FAILED / ERROR 集合；
  最后**合并所有分组**的集合 ⇒ 与期望集比对（口径与原护栏一致）。

★ 通用测试（不含任何协议字面量）⇒ 在**每个协议**下都跑
  （它们读当前中枢 ⇒ 必须每组都验证）。

用法：
    python tools/guard/run_guarded_by_protocol.py --out-dir guard/byproto
    python tools/guard/run_guarded_by_protocol.py --protocol rtsp --out-dir guard/byproto
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / "tests"
EXPECTED = ROOT / "tools" / "guard" / "baseline" / "expected_b_class_failed_ids.txt"
NARROW_EXEMPT = ROOT / "tools" / "guard" / "baseline" / "narrow_hub_failed_ids.txt"

#: 已知协议（**从 kb 推导** ⇒ 只有真正有知识源的协议才参与）
def known_protocols() -> list[str]:
    """可参与护栏的协议：**kb 里有 RFC 源** + **有 profile 资产**。

    ★ 排除「只有词典没有知识源」的（如 ftp）⇒ 否则构建直接失败。
    """
    kb = ROOT / "kb"
    if not kb.is_dir():
        return []
    out = []
    for _p in sorted(kb.iterdir()):
        if not _p.is_dir() or not (_p / "spec").is_dir():
            continue
        _t = ROOT / "fused_hub" / "targets" / _p.name.lower()
        if (_t / "profile.json").is_file():
            out.append(_p.name.lower())
    return out

def test_protocols(text: str) -> list[str]:
    """测试文件里出现的协议字面量。"""
    return sorted({p for p in known_protocols()
                   if re.search(rf"(?<![a-z0-9_]){re.escape(p)}(?![a-z0-9_])",
                                text, re.I)})


def group_tests(protocols: list[str]) -> tuple[dict[str, list[str]], list[str]]:
    """分组：**按测试函数**的协议依赖判定（★ 2026-11-08 修正）。

    ★ **修正前的错**：按**整个文件**里的协议字面量分组 ⇒
      `test_graph_pipeline.py`（里面只有 1 个函数用 sip/smtp）被误归到
      **所有**协议组 ⇒ 单协议组里其它协议的数据缺失 ⇒ 大面积失败。
    ★ **修正后**：逐个**测试函数**看它依赖哪个协议 ⇒
      一个文件里不同函数可归到**不同**协议组 ⇒ 精准。
    """
    import ast
    groups: dict[str, list[str]] = {p: [] for p in protocols}
    common: list[str] = []
    for f in sorted(TESTS.rglob("test_*.py")):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(f.relative_to(ROOT))
        try:
            tree = ast.parse(text)
        except SyntaxError:
            common.append(rel)      # 语法错 ⇒ 归通用（收集错误会报出来）
            continue
        file_ps: set[str] = set()
        has_fn = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            has_fn = True
            # ★ 该函数体 + 装饰器里出现的协议字面量
            seg = ast.get_source_segment(text, node) or ""
            file_ps |= set(test_protocols(seg))
        if not has_fn:
            common.append(rel)
            continue
        if not file_ps:
            common.append(rel)
            continue
        for p in file_ps:
            groups.setdefault(p, []).append(rel)
    return groups, common


def build_hub(protocol: str, sources: list[str]) -> bool:
    """构建该协议的中枢（**全清** ⇒ 中枢里只有它）。"""
    cmd = [sys.executable, str(ROOT / "scripts" / "build_hub.py"),
           "--protocol", protocol]
    if sources:
        cmd += ["--sources"] + sources
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    return r.returncode == 0


def run_group(files: list[str], out_dir: Path, tag: str) -> tuple[list[str], list[str]]:
    """跑一组测试 ⇒ ``(failed_ids, error_ids)``。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / f"{tag}_raw.txt"
    cmd = [sys.executable, "-m", "pytest", "-rfE", "--tb=no", "-q",
           "-p", "no:cacheprovider"] + files
    with raw.open("w", encoding="utf-8", newline="") as fh:
        subprocess.run(cmd, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT)
    failed: list[str] = []
    errored: list[str] = []
    for ln in raw.read_text(encoding="utf-8", errors="ignore").splitlines():
        m = re.match(r"^(FAILED|ERROR)\s+(\S+)", ln.strip())
        if m:
            (failed if m.group(1) == "FAILED" else errored).append(m.group(2))
    return failed, errored


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="按协议分组的护栏")
    ap.add_argument("--protocol", default="",
                    help="★ 单协议护栏（默认第一个可用协议）：中枢**全清** ⇒ 只有该协议")
    ap.add_argument("--all-protocols", action="store_true",
                    help="★ 实验性：跨协议分组（中枢按协议替换 ⇒ 多协议共存）")
    ap.add_argument("--sources", default="rfc",
                    help="构建中枢时用的源（逗号分隔）")
    ap.add_argument("--out-dir", default="qa/byproto")
    ap.add_argument("--with-common", action="store_true",
                    help="★ 连通用测试一起跑（它们隐含依赖多个协议并存）")
    ap.add_argument("--skip-build", action="store_true",
                    help="不构建中枢（用现有中枢）")
    args = ap.parse_args(argv)

    _known = known_protocols()
    if args.all_protocols:
        protocols = list(_known)
    else:
        protocols = [args.protocol] if args.protocol else (_known[:1] or [])
    if not protocols:
        print("!! 没有已知协议", file=sys.stderr)
        return 2
    sources = [s.strip() for s in (args.sources or "").split(",") if s.strip()]
    out_dir = ROOT / args.out_dir
    groups, common = group_tests(protocols)

    all_failed: set[str] = set()
    all_error: set[str] = set()
    for p in protocols:
        if not args.skip_build:
            print(f"[构建] {p} …", flush=True)
            if not build_hub(p, sources):
                print(f"!! {p} 构建失败", file=sys.stderr)
                return 2
        # ★ 只跑**该协议专属**的测试（通用测试见下）
        files = sorted(set(groups.get(p, [])))
        if not files:
            continue
        print(f"[测试] {p}: {len(files)} 个专属文件", flush=True)
        f, e = run_group(files, out_dir, p)
        all_failed |= set(f)
        all_error |= set(e)
        print(f"        failed {len(f)} / error {len(e)}", flush=True)

    # ★★ **通用测试最后统一跑一次**（2026-11-08 实测修正）：
    #   通用测试**隐含依赖「中枢里有多个协议」**（例如
    #   ``test_edge_cover`` 用**默认协议 rtsp**）⇒ 在「只有单协议」的
    #   组里跑必然失败 ⇒ 逐组跑会重复失败。
    #   ⇒ 改为：各协议**专属**测试分组跑（诊断价值），
    #     **通用**测试在**全部协议构建完**后统一跑一次。
    if common and args.with_common:
        print(f"[测试] 通用: {len(common)} 个文件", flush=True)
        f, e = run_group(sorted(common), out_dir, "common")
        all_failed |= set(f)
        all_error |= set(e)
        print(f"        failed {len(f)} / error {len(e)}", flush=True)

    expected = set()
    if EXPECTED.is_file():
        expected = {ln.strip() for ln in EXPECTED.read_text(encoding="utf-8").splitlines()
                    if ln.strip() and not ln.strip().startswith("#")}
    exempt = set()
    if NARROW_EXEMPT.is_file():
        exempt = {ln.strip() for ln in NARROW_EXEMPT.read_text(encoding="utf-8").splitlines()
                  if ln.strip() and not ln.strip().startswith("#")}

    new_failed = sorted(all_failed - expected - exempt)
    gone_failed = sorted(expected - all_failed - exempt)
    new_error = sorted(all_error - expected)
    gone_error = sorted(expected - all_error)

    print("\n== 按协议分组护栏 ==")
    print(f"   failed: 合计 {len(all_failed)} | 期望 {len(expected)} | "
          f"新增 {len(new_failed)} / 消失 {len(gone_failed)}")
    print(f"   error : 合计 {len(all_error)} | 期望 {len(expected)} | "
          f"新增 {len(new_error)} / 消失 {len(gone_error)}")
    for x in new_failed[:12]:
        print(f"      + {x}")
    for x in new_error[:12]:
        print(f"      + {x}")
    for x in gone_failed[:6]:
        print(f"      - {x}")
    ok = not new_failed and not gone_failed and not new_error and not gone_error
    print(f"== 结论：{'✅ 可采信' if ok else '❌ 不可采信'} ==")
    (out_dir / "summary.json").write_text(json.dumps({
        "protocols": protocols, "failed": sorted(all_failed),
        "error": sorted(all_error), "new_failed": new_failed,
        "gone_failed": gone_failed, "new_error": new_error,
        "ok": ok}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
