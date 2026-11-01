# -*- coding: utf-8 -*-
"""带**三道护栏**的全量 pytest 跑法 —— CI 与本机共用的标准验收跑法（可复现、可采信）。

本脚本是 ProtoRAG CI 的**验收闸门本体**：``.github/workflows/ci.yml`` 的
``guarded-pytest`` job 直接调用它。它解决三个已被实测踩到的坑：

  ① **并发写文件让数字漂移**：同一棵树连跑三次得 38 → 46 → 37。
     ⇒ 护栏1：跑前/跑后各存一次源码 mtime 快照，**diff 非空 ⇒ 本次结果不可采信**。
  ② **超时伪装成全绿**：pytest 被 kill 在打印 summary 之前时，`grep '^FAILED'` 拿到**空集**，
     与「真的 0 失败」在 grep 层面无法区分。
     ⇒ 护栏2：**summary 行必须存在**，否则判「本次运行无效」而不是「0 失败」。
  ③ **ERROR 有两种输出格式**，正则不同、不可混用：
       tb 头形态（--tb=short / 默认）：`_____ ERROR at setup of test_xxx _____`
       -rE 短摘要形态（--tb=no 时只有这个）：`ERROR tests/...::test_xxx - msg`
     ⇒ 本脚本**两种都认**。

★ 护栏4（抽取口径自检，2026-11-02 补上）
  summary 说「37 failed」，但从输出里只抽到 20 条 ⇒ **抽取口径坏了**，
  此时「与期望集比对」是拿残集在比，结论无效 ⇒ **直接判不可采信**。

★ 关于 ``-rfE``（务必保留）
  pytest 的 ``-r`` 是**覆盖**语义而非追加：写成 ``-rf -rE`` ⇒ 生效的只有 ``-rE``，
  **FAILED 行根本不输出** ⇒ 抽取恒为空集 ⇒ 「FAILED 集合比对」是空跑，
  永远判定「无漂移」——一个看起来在把关、实际上什么都不拦的假闸。
  ⇒ 必须写成**合并形式** ``-rfE``（f=失败、E=错误），两个报告都出。

用法
----
    python tools/qa/run_guarded_pytest.py                       # 全量 + 与基线期望集比对
    python tools/qa/run_guarded_pytest.py tests/fused/xxx.py    # 指定路径
    python tools/qa/run_guarded_pytest.py --no-compare         # 只跑，不比对期望集
    python tools/qa/run_guarded_pytest.py --out-dir <目录>      # 指定产物目录
    python tools/qa/run_guarded_pytest.py --repo-root <目录>    # 指定仓库根（默认自动推断）

退出码
------
    0 = 全部通过（护栏满足 + 与期望集一致）
    1 = 护栏被触发（树在动 / 无 summary 行 / 抽取口径不一致 / 期望集漂移）
        —— **本次结果不可采信**，CI job 即为红
    2 = 用法或环境错误（pytest 二进制缺失、目录不存在等）

★ 期望基线（"失败集合不漂移"闸门的锚点）
  基线文件**必须入库**（否则换台机器无处比对），位于 ``tools/qa/baseline/``：
    · ``expected_b_class_failed_ids.txt`` —— 预存 FAILED 集合，每行 ``<test_id>``
      （**带完整路径**，与 pytest 的 ``FAILED <path>::<name>`` 一致）
    · ``baseline_errors_pre_cleanup.txt`` —— 预存 ERROR 集合，每行 ``<test_name>``
      （**只有函数名**，因为 ERROR 的 tb 头形态不含路径）
  ⚠ 两份基线的**行格式刻意不同**（FAILED 带路径 / ERROR 不带路径），与 pytest 的
    两种输出形态一一对应 —— 不要"顺手统一"，那会让比对恒为漂移。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

#: 本脚本所在目录（tools/qa/）
HERE = Path(__file__).resolve().parent

#: 仓库根默认推断：tools/qa/run_guarded_pytest.py → 上两级 = 仓库根。
#: ★ **不硬编码绝对路径** —— 否则换机器/换 CI runner 就找不到仓库。
DEFAULT_REPO_ROOT = Path(__file__).resolve().parents[2]


def _force_utf8_stdio() -> None:
    """把 stdout/stderr 强制成 UTF-8（**errors="replace"**）。

    ★ 真实事故（2026-11-02 真机 CI，run 41357183519，Windows runner）：
      Windows 控制台默认是 **OEM 代码页**（charmap/cp936 等）⇒ 本脚本打印中文
      （第一行就是「== 仓库根：…」）时抛
      `UnicodeEncodeError: 'charmap' codec can't encode characters in position 3-6`
      ⇒ **脚本在第一行输出就崩了** ⇒ 护栏产物一个都没落盘
      ⇒ job 红，而日志里看不到任何闸门结论（只有一条编码错误）。
      ⇒ 修法：stdout/stderr 一律 reconfigure 成 UTF-8，且 `errors="replace"`
        —— 即便遇到不可编码字符也**只丢字符、不崩**（闸门必须永远能出结论）。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover —— 旧解释器/被替换的流
            pass


_force_utf8_stdio()

#: 期望集（基线锚点）—— 随仓库入库
DEFAULT_EXPECT_FAILED = HERE / "baseline" / "expected_b_class_failed_ids.txt"
DEFAULT_EXPECT_ERRORS = HERE / "baseline" / "baseline_errors_pre_cleanup.txt"

#: 源码 mtime 快照范围（这些路径的变动会让结果不可比）
SNAPSHOT_GLOBS = [
    "tests/fused/*.py", "tests/*.py",
    "core/fused/*.py", "core/fused/downstream/*.py", "core/*.py",
    "scripts/*.py",
]

#: pytest 的 summary 行有多种形态（实测）：
#:   `= 37 failed, 1163 passed, 20 errors in 92.61s =`
#:   `= 20 errors in 0.60s =`                 ← 只有 error 时**不打印** failed/passed
#:   `= 1163 passed in 60.1s =`               ← 无失败无 error 时
#:   `= 5 skipped in 1.0s =`
#: ⇒ 不能用固定的三段正则；改为「先定位 summary 行，再在行内分别取各计数」。
SUMMARY_LINE_RE = re.compile(r"^=+.*\bin [\d.]+s.*=+\s*$", re.M)
COUNT_FAILED_RE = re.compile(r"(\d+)\s+failed")
COUNT_PASSED_RE = re.compile(r"(\d+)\s+passed")
COUNT_ERRORS_RE = re.compile(r"(\d+)\s+errors?")
COUNT_SKIPPED_RE = re.compile(r"(\d+)\s+skipped")
FAILED_RE = re.compile(r"^FAILED\s+(\S+)", re.M)
ERROR_TB_RE = re.compile(r"ERROR at setup of ([^\s]+)")
ERROR_SUMMARY_RE = re.compile(r"^ERROR\s+(\S+)", re.M)


def _snapshot(root: Path) -> dict:
    """跑前/跑后各取一次源码 mtime 快照（用于检测并发编辑污染）。"""
    out: dict[str, str] = {}
    for pat in SNAPSHOT_GLOBS:
        for p in sorted(root.glob(pat)):
            try:
                out[str(p.relative_to(root))] = f"{p.stat().st_mtime_ns}"
            except OSError:
                pass
    return out


def _find_pytest() -> str:
    """找可用的 pytest 解释器。

    优先本机固定路径（团队约定的 Anaconda），否则退到**当前解释器**
    ``sys.executable`` —— 在 Linux / GitHub Actions 上就是 runner 自己的 python，
    这正是期望行为。
    """
    for cand in (r"E:\app\Anaconda3\python.exe", sys.executable):
        if cand and Path(cand).is_file():
            return cand
    return ""


def _read_expected(path: Path) -> list[str]:
    """读期望集文件（去空白行、去重、保持排序）。"""
    return sorted({ln.strip() for ln in
                   path.read_text(encoding="utf-8").splitlines() if ln.strip()})


def main() -> int:
    ap = argparse.ArgumentParser(description="带三道护栏的全量 pytest 验收跑法")
    ap.add_argument("paths", nargs="*", default=["tests/"], help="要跑的路径（默认 tests/）")
    ap.add_argument("--repo-root", default=str(DEFAULT_REPO_ROOT),
                    help="仓库根目录（默认由脚本位置自动推断：tools/qa/ 上两级）")
    ap.add_argument("--out-dir", default=str(DEFAULT_REPO_ROOT / "_ci_artifacts"),
                    help="产物目录（默认 <仓库根>/_ci_artifacts/；"
                         "**不写进源码目录**，避免污染 tools/qa/）")
    ap.add_argument("--expect-failed", default=str(DEFAULT_EXPECT_FAILED),
                    help="期望 FAILED 集（基线文件）")
    ap.add_argument("--expect-errors", default=str(DEFAULT_EXPECT_ERRORS),
                    help="期望 ERROR 集（基线文件）")
    ap.add_argument("--no-compare", action="store_true", help="不与期望集比对")
    ap.add_argument("--extra", default="", help="追加给 pytest 的参数（空格分隔）")
    args = ap.parse_args()

    root = Path(args.repo_root).resolve()
    if not root.is_dir():
        print(f"★ 用法/环境错误：仓库根不存在 {root}", file=sys.stderr)
        return 2
    if not (root / "tests").is_dir():
        print(f"★ 用法/环境错误：{root} 下没有 tests/，仓库根不对", file=sys.stderr)
        return 2

    py = _find_pytest()
    if not py:
        print("★ 用法/环境错误：找不到 pytest 解释器", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / "_guarded_raw.txt"
    before_snap = out_dir / "_guarded_before.txt"
    after_snap = out_dir / "_guarded_after.txt"
    result_json = out_dir / "_guarded_result.json"

    targets = args.paths or ["tests/"]
    for t in targets:
        if not (root / t).exists():
            print(f"★ 用法/环境错误：路径不存在 {t}", file=sys.stderr)
            return 2

    # ★ `-r` 是 **覆盖** 语义（不是追加）：`-rf -rE` ⇒ 生效的是 `-rE`，
    #   **FAILED 行根本不会输出** ⇒ 抽取恒为空集 ⇒ 「FAILED 集合比对」是空跑。
    #   ⇒ 必须写成**合并形式** `-rfE`（f=失败、E=错误），两个报告都出。
    cmd = [py, "-m", "pytest", *targets, "-q", "-p", "no:cacheprovider",
           "--tb=no", "-rfE"]
    if args.extra:
        cmd += args.extra.split()

    print(f"== 仓库根：{root}")
    print(f"== 解释器：{py}")
    print("== 护栏1：跑前快照 ==")
    before = _snapshot(root)
    before_snap.write_text("\n".join(f"{k} {v}" for k, v in sorted(before.items())),
                           encoding="utf-8")
    print(f"   快照 {len(before)} 个源码文件 → {before_snap.name}")

    print(f"== 跑 pytest：{' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root),
                       encoding="utf-8", errors="replace", timeout=3600)
    raw.write_text((r.stdout or "") + "\n" + (r.stderr or ""), encoding="utf-8")
    out = r.stdout or ""

    print("== 护栏1：跑后快照 ==")
    after = _snapshot(root)
    after_snap.write_text("\n".join(f"{k} {v}" for k, v in sorted(after.items())),
                          encoding="utf-8")
    changed = sorted(k for k in set(before) | set(after)
                     if before.get(k) != after.get(k))
    tree_stable = not changed
    if tree_stable:
        print("   ✅ 树静止（源码 mtime 无变化）")
    else:
        print(f"   ⚠️ 树在测量期间被改动 {len(changed)} 个文件：")
        for c in changed[:20]:
            print(f"      {c}")
        print("      ⇒ 本次结果**不可采信**（并发编辑污染）")

    # ---- 护栏2：summary 行必须存在 ----
    #  ⚠ pytest 的 summary 行**形态多样**（见 SUMMARY_LINE_RE 注释），
    #    必须逐个计数分别取，不能用固定三段正则 —— 否则「只有 error」的运行会被误判为「无 summary」。
    sm = SUMMARY_LINE_RE.search(out)
    summary_present = bool(sm)
    failed_n = passed_n = errors_n = skipped_n = None
    if summary_present:
        line = sm.group(0)
        mf, mp, me, msk = (COUNT_FAILED_RE.search(line), COUNT_PASSED_RE.search(line),
                           COUNT_ERRORS_RE.search(line), COUNT_SKIPPED_RE.search(line))
        failed_n = int(mf.group(1)) if mf else 0
        passed_n = int(mp.group(1)) if mp else 0
        errors_n = int(me.group(1)) if me else 0
        skipped_n = int(msk.group(1)) if msk else 0
        print(f"== 护栏2：summary 行存在 ✅ {failed_n} failed / {passed_n} passed / "
              f"{errors_n} errors" + (f" / {skipped_n} skipped" if skipped_n else ""))
    else:
        print("== 护栏2：★ 无 summary 行 ⇒ 本次运行无效（可能被 kill / 超时），"
              "**不得当成 0 失败**")

    # ---- 抽取 FAILED / ERROR 集合（两种 ERROR 格式都认） ----
    failed_ids = sorted(set(FAILED_RE.findall(out)))
    err_ids = set(ERROR_TB_RE.findall(out))
    if not err_ids:
        err_ids = set(ERROR_SUMMARY_RE.findall(out))
    err_ids = sorted({e.split("::")[-1] for e in err_ids})

    print()
    print("== 抽取结果 ==")
    print(f"   FAILED {len(failed_ids)} 条   ERROR {len(err_ids)} 条")

    # ---- 与期望集比对 ----
    drift = {}
    if not args.no_compare:
        for label, ids, exp_path in (
                ("failed", failed_ids, Path(args.expect_failed)),
                ("errors", err_ids, Path(args.expect_errors))):
            if not exp_path.is_file():
                print(f"   （跳过 {label} 比对：期望集 {exp_path.name} 不存在）")
                continue
            exp = _read_expected(exp_path)
            added = sorted(set(ids) - set(exp))
            removed = sorted(set(exp) - set(ids))
            drift[label] = {"expected": len(exp), "actual": len(ids),
                            "added": added, "removed": removed}
            print(f"   {label}: 期望 {len(exp)} / 实测 {len(ids)} | "
                  f"新增 {len(added)} / 消失 {len(removed)}")
            for x in added[:10]:
                print(f"      + {x}")
            for x in removed[:10]:
                print(f"      - {x}")

    ok = tree_stable and summary_present and not any(
        d.get("added") or d.get("removed") for d in drift.values())

    # ---- 护栏4：抽取口径自检 ----
    #  ★ summary 说有 N 条失败，但只抽到 M 条 ⇒ 口径坏了，
    #    此时「与期望集比对」是拿空集/残集在比，结论无效 ⇒ 直接判不可采信。
    extract_consistent = True
    if failed_n is not None and len(failed_ids) != failed_n:
        extract_consistent = False
        print(f"   ❌ FAILED 抽取口径不一致：summary={failed_n} vs 抽取={len(failed_ids)}"
              f" ⇒ 本次结果不可采信")
    if errors_n is not None and len(err_ids) != errors_n:
        extract_consistent = False
        print(f"   ❌ ERROR 抽取口径不一致：summary={errors_n} vs 抽取={len(err_ids)}"
              f" ⇒ 本次结果不可采信")
    if not extract_consistent:
        ok = False

    result = {
        "repo_root": str(root),
        "targets": targets, "command": cmd,
        "tree_stable": tree_stable, "changed_files": changed,
        "summary_present": summary_present,
        "failed": failed_n, "passed": passed_n, "errors": errors_n,
        "skipped": skipped_n,
        "failed_ids": failed_ids, "error_ids": err_ids,
        "extract_consistent": extract_consistent,
        "drift": drift, "verdict": "TRUSTWORTHY" if ok else "NOT_TRUSTWORTHY",
    }
    result_json.write_text(json.dumps(result, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print()
    print(f"== 结论：{'✅ 可采信' if ok else '❌ 本次结果不可采信'} ==")
    print(f"   原始输出: {raw}")
    print(f"   结果 json: {result_json}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
