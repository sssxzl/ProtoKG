# -*- coding: utf-8 -*-
"""guard/verify_aspect_layout.py —— 批次 1.6 步 1 的**分布校验**。

判据（方案 §3.1.10.6 步 1）：
  ① 中枢文件**按 aspect 组织**；
  ② 旧布局自动降级读取（不破坏既有产物）；
  ③ ★ **默认路径逐字节不变** —— 新布局读出的 bundle 与旧布局读出的
     bundle **逐字节一致**（这是「步 1~5 全是加参数/加字段 ⇒ 默认路径逐字节
     不变」这条保证的机器可判定形式）。

用法::

    E:/app/Anaconda3/python.exe guard/verify_aspect_layout.py \
        --protocol rtsp --protocol sip --protocol smtp

本脚本**只读**中枢，不修改任何文件：它在 tmp 目录里用现有「按源分目录」
布局**重建**一份 aspect 布局，再分别读两种布局做对比。
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import paths                                    # noqa: E402
from core.fused.downstream.rag_seedgen import (           # noqa: E402
    assemble_bundle, load_fact_views,
)
from scripts.build_hub import (                            # noqa: E402
    RUNTIME_ENRICH_DIRS, _write_aspect_layout,
)


def _read_old_layout(root: Path) -> list[dict]:
    """★ 旧布局读法（**逐字节复刻**改动前的 `load_fact_views` 实现）。"""
    views: list[dict] = []
    if not root.is_dir():
        return views
    for jsonl in sorted(root.glob("*/facts/*.jsonl")):
        for line in jsonl.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                views.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return views


def _norm(obj):
    """稳定化：set → sorted list；tuple key → 字符串 key ⇒ 可逐字节比较。"""
    if isinstance(obj, dict):
        return {("|".join(map(str, k)) if isinstance(k, tuple) else str(k)): _norm(v)
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_norm(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_norm(v) for v in obj)
    return obj


def _dump(obj) -> str:
    """序列化（**保留 dict 插入序**）⇒ 可逐字节比较。

    ★ **不能用 sort_keys=True**：那会把 dict 的**键插入序**差异掩盖掉。
      实测教训：``methods`` / ``headers`` 是 dict，键插入序取决于 fact 的
      遍历序 ⇒ 键序一变，下游种子生成顺序就变 ⇒ 种子文件名全变
      （rtsp 58 条种子的 MD5 集合全变），而「内容」看起来完全一致。
    """
    return json.dumps(_norm(obj), ensure_ascii=False, default=str)


def _clone_layout(src_root: Path, dst_root: Path) -> None:
    """把「按源分目录」布局克隆到目标目录（**不含**新的顶层 facts/）。"""
    if dst_root.exists():
        shutil.rmtree(dst_root)
    for src_dir in sorted(p for p in src_root.iterdir() if p.is_dir()):
        facts_dir = src_dir / "facts"
        if not facts_dir.is_dir():
            continue
        out = dst_root / src_dir.name / "facts"
        out.mkdir(parents=True, exist_ok=True)
        # ★ D1 方案②：按 aspect 分桶 ⇒ 用 helper（避免重复读）
        for jsonl in paths.iter_source_fact_files_in(src_dir):
            shutil.copy2(jsonl, out / jsonl.name)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批次 1.6 步 1 分布校验")
    ap.add_argument("--protocol", action="append", default=None,
                    help="协议（可重复；默认 rtsp/sip/smtp 全查）")
    args = ap.parse_args(argv)
    protocols = args.protocol or ["rtsp", "sip", "smtp"]

    overall_ok = True
    tmp_root = Path(tempfile.mkdtemp(prefix="aspect_verify_"))
    try:
        for protocol in protocols:
            src_root = paths.per_source_root(protocol)
            if not src_root.is_dir():
                print(f"[{protocol}] 中枢目录不存在：{src_root} —— 跳过")
                overall_ok = False
                continue

            # ---- 在 tmp 里重建 aspect 布局（不改真实中枢）--------------------
            work = tmp_root / protocol
            _clone_layout(src_root, work)
            # ★ 克隆时要排除运行时富化目录（与真实构建一致）
            for d in RUNTIME_ENRICH_DIRS:
                shutil.rmtree(work / d, ignore_errors=True)

            original_root = paths.per_source_root
            try:
                paths.per_source_root = lambda p, _w=work: _w
                counts = _write_aspect_layout(protocol)
                new_views = load_fact_views(protocol)
            finally:
                paths.per_source_root = original_root

            old_views = _read_old_layout(work)

            # ---- 判据 ①：中枢文件按 aspect 组织 -----------------------------
            aspect_dir = work / "facts"
            aspect_files = sorted(p.name for p in aspect_dir.glob("*.jsonl"))
            ok_layout = bool(aspect_files) and all(
                (aspect_dir / f).is_file() for f in aspect_files)
            # 事实总数守恒
            ok_count = (len(old_views) == len(new_views))

            # ---- 判据 ②：内容集合一致（按 fact 身份比对）---------------------
            def _identity(v: dict) -> str:
                claims = v.get("all_claims") or []
                fids = sorted(c.get("fact_id") or "" for c in claims)
                fk = v.get("fact_key") or {}
                return f"{fk.get('subject')}|{fk.get('aspect')}|{','.join(fids)}"

            old_ids = [_identity(v) for v in old_views]
            new_ids = [_identity(v) for v in new_views]
            ok_set = sorted(old_ids) == sorted(new_ids)

            # ---- 判据 ③：bundle 逐字节一致（含 dict 键插入序）----------------
            old_bundle = assemble_bundle(list(old_views), protocol)
            new_bundle = assemble_bundle(list(new_views), protocol)
            old_dump = _dump(old_bundle)
            new_dump = _dump(new_bundle)
            ok_bundle = old_dump == new_dump
            # ★ 视图遍历序也必须一致（决定 methods/headers 的键插入序）
            ok_view_order = old_views == new_views

            # ---- 明细（便于人工审计差异）-------------------------------------
            print(f"\n=== {protocol} ===")
            print(f"  旧布局 facts 数: {len(old_views)}   新布局 facts 数: {len(new_views)}")
            print(f"  aspect 文件 ({len(aspect_files)}): {aspect_files}")
            print(f"  aspect 分布: {json.dumps(counts, ensure_ascii=False)}")
            print(f"  ① 按 aspect 组织: {'✅' if ok_layout else '❌'}")
            print(f"  ② 事实总数守恒:   {'✅' if ok_count else '❌'}")
            print(f"  ③ 内容集合一致:   {'✅' if ok_set else '❌'}")
            print(f"  ④ 视图遍历序一致: {'✅' if ok_view_order else '❌'}")
            print(f"  ⑤ bundle 逐字节（含键序）: {'✅' if ok_bundle else '❌'}")
            if not ok_bundle:
                # 打印第一处差异，便于定位
                for key in sorted(set(old_bundle) | set(new_bundle)):
                    a = _dump(old_bundle.get(key))
                    b = _dump(new_bundle.get(key))
                    if a != b:
                        print(f"     ✗ 差异桶 `{key}`:")
                        print(f"        旧: {a[:400]}")
                        print(f"        新: {b[:400]}")
            if not (ok_layout and ok_count and ok_set and ok_view_order
                    and ok_bundle):
                overall_ok = False
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    print("\n结论：" + ("✅ 可采信（步 1 分布校验通过）" if overall_ok
                       else "❌ 不可采信（见上方 ❌ 项）"))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
