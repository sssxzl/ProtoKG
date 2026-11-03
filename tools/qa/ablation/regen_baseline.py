# -*- coding: utf-8 -*-
"""tools/qa/ablation/regen_baseline.py —— **重新生成种子语料基线**（可复跑）。

★ 为什么需要它：批次 2.5（F1/F3/F5/F6 + D20-丁+）改变了**默认行为**
  （语义规则按协议过滤 · 会话语义改走中枢 · ⑤ 层两段式底料 ·
  方法白名单按源决定 · 语义四库自动重发布）⇒ 语料必然变化
  ⇒ 历史基线失效 ⇒ 需要**一次性重标定**，且**过程必须可复现**。

★ 它做什么：
  ① 每个协议：``build_hub --sources rfc``（**纯 RFC 单源**，清空中枢后重建）
  ② 每个聚焦组 A/B/C/D：``seedgen --focus-group <组>`` ⇒ 收集种子 MD5 + 字典
  ③ 写 ``local/baseline_p0_seeds.md5``（逐条 MD5 清单）
     与 ``local/baseline_p0_summary.json``（条数 + 字典 token 摘要）

★ 只写这两个文件；**不动**代码、不动测试断言（那些由人工按实测值更新）。

用法::

    python tools/qa/ablation/regen_baseline.py                # 三协议四组
    python tools/qa/ablation/regen_baseline.py --protocols rtsp
    python tools/qa/ablation/regen_baseline.py --dry-run     # 只打印，不写盘
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for cand in [here.parent] + list(here.parents):
        if (cand / "core" / "paths.py").is_file():
            return cand
    return here.parents[3]


REPO = _repo_root()
PROTOCOLS = ("rtsp", "sip", "smtp")
GROUPS = ("A", "B", "C", "D")

MD5_HEADER = """# ProtoRAG 种子语料基线 —— 批次 2.5（F1/F3/F5/F6 + D20-丁+）之后
# 中枢态: 纯 RFC 单源（--sources rfc）+ 协议骨架 + 必填头物化 + 会话语义**不入中枢**
#          + 语义四库**自动重发布且按协议过滤** + 方法白名单**按源集合决定**
#          + ⑤ 层两段式底料（--base-corpus-from）
# 用途: 后续实验引用种子时的**逐字节对照**基准（md5sum -c 可直接校验）
# 格式: <md5>  <协议>/<分组>/<种子文件>
#
# ★ 重标定脚本: tools/qa/ablation/regen_baseline.py（可复跑）
# ★ 本基线是**纯 RFC 单源**口径 ⇒ 与「多源融合」语料不可混用
"""


def _run(cmd: list[str], log: Path) -> int:
    with log.open("w", encoding="utf-8") as fh:
        rc = subprocess.call(cmd, cwd=str(REPO), stdout=fh,
                             stderr=subprocess.STDOUT)
    return rc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--protocols", nargs="*", default=list(PROTOCOLS))
    ap.add_argument("--groups", nargs="*", default=list(GROUPS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out-root", default="out/baseline_regen")
    args = ap.parse_args(argv)

    out_root = REPO / args.out_root
    py = sys.executable
    md5_lines: list[str] = []
    summary_groups: dict[str, dict] = {}

    for proto in args.protocols:
        print(f"\n===== {proto}：构建纯 RFC 单源中枢 =====")
        build_log = out_root / f"{proto}.build.log"
        build_log.parent.mkdir(parents=True, exist_ok=True)
        rc = _run([py, "scripts/build_hub.py", "--protocol", proto,
                   "--sources", "rfc"], build_log)
        print(f"  build rc={rc}  日志: {build_log}")
        if rc != 0:
            print(f"  ★ 构建失败 ⇒ 跳过 {proto}")
            continue

        summary_groups[proto] = {}
        for group in args.groups:
            out = out_root / proto / group
            if out.exists():
                shutil.rmtree(out)
            log = out_root / f"{proto}.{group}.seedgen.log"
            rc = _run([py, "scripts/seedgen.py", "--protocol", proto,
                       "--focus-group", group, "--out", str(out),
                       "--manifest"], log)
            mf = out / "manifest.json"
            # ★ 注意：seedgen 的退出码 3 = 「种子数与**旧**标定值不符」，
            #   **manifest 仍然会写盘** ⇒ 不能因 rc!=0 就跳过（否则会漏收整组）。
            if not mf.is_file():
                print(f"  组{group}: seedgen rc={rc} ★ 无 manifest（真失败）")
                continue
            if rc != 0:
                print(f"  组{group}: seedgen rc={rc}（条数与旧标定值不符，"
                      f"manifest 已写 ⇒ 按实测收集）")
            doc = json.loads(mf.read_text(encoding="utf-8"))
            layers = Counter(s.get("layer_name") or "?"
                             for s in doc.get("seeds") or [])
            tokens = (doc.get("dictionary") or {}).get("token_count")
            summary_groups[proto][group] = {
                "seed_count": doc.get("seed_count"),
                "dict_tokens": tokens,
                "layers": dict(layers),
            }
            print(f"  组{group}: {doc.get('seed_count')} 条 / 字典 {tokens} token"
                  f" / {dict(layers)}")
            for s in doc.get("seeds") or []:
                md5_lines.append(f"{s.get('md5')}  {proto}/{group}/"
                                 f"{s.get('filename')}")

    if args.dry_run:
        print("\n=== 干跑：不写盘 ===")
        print(f"  将写入 {len(md5_lines)} 条 MD5")
        print(json.dumps(summary_groups, ensure_ascii=False, indent=2))
        return 0

    (REPO / "local" / "baseline_p0_seeds.md5").write_text(
        MD5_HEADER + "\n".join(md5_lines) + "\n", encoding="utf-8")
    summary = {
        "schema_version": "1.4",
        "note": "批次 2.5（F1/F3/F5/F6 + D20-丁+）之后的种子语料基线摘要",
        "hub_state": ("纯 RFC 单源（--sources rfc）+ 协议骨架 + 必填头物化 + "
                      "会话语义不入中枢 + 语义四库自动重发布且按协议过滤 + "
                      "方法白名单按源集合决定 + ⑤ 层两段式底料"),
        "regen_script": "tools/qa/ablation/regen_baseline.py",
        "generated_at": datetime.now().astimezone().isoformat(),
        "md5_manifest": "local/baseline_p0_seeds.md5",
        "groups": summary_groups,
    }
    (REPO / "local" / "baseline_p0_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    print(f"\n★ 已写入 local/baseline_p0_seeds.md5（{len(md5_lines)} 条）"
          f" 与 local/baseline_p0_summary.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
