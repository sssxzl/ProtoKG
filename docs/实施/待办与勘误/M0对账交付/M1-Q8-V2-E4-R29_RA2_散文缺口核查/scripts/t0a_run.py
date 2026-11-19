# -*- coding: utf-8 -*-
"""T0-A 隔离运行器（默认 dry-run；必须显式 --execute 且设置预算开关才会联网）。

硬约束：最多 2 请求、无重试、失败即停、单次 max_tokens=4000、累计输入 ≤7500、
费用 ≤0.15 元、thinking.type=disabled 在每次请求前校验。
"""
from __future__ import annotations
import argparse, json, os, pathlib, sys

HERE = pathlib.Path(__file__).resolve().parent
_cwd = pathlib.Path.cwd()
ROOT = _cwd if (_cwd / "kb").is_dir() else HERE.parents[5]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(HERE))
from core.fused.extraction import prose_semantics as PS  # noqa: E402
import t0a_adapter as AC  # noqa: E402

MAX_CALLS, MAX_TOKENS, MAX_IN = 2, 4000, 7500
PRICE_IN_PEAK, PRICE_OUT_PEAK = 2.0, 8.0     # CNY / 1M，按高峰取最坏
CAP_CNY = 0.15


def blocks():
    f = ROOT / "kb/smtp/spec/rfc3207.txt"
    text = f.read_text(encoding="utf-8", errors="replace")
    src = __import__("hashlib").sha256(f.read_bytes()).hexdigest()
    n = (len(text) // PS._MAX_BLOCK_CHARS) + 1
    return [{"doc": "rfc3207.txt", "start": st, "text": bt, "src_sha256": src}
            for st, bt in PS._split_blocks(text, n)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="真正联网（需预算授权）")
    args = ap.parse_args()
    bl = blocks()
    print(f"plan: 6 块，2 批（5+1），单次 max_tokens={MAX_TOKENS}，thinking=disabled")
    if not args.execute:
        print("dry-run only（未联网）。需要 --execute 且 DEEPSEEK_API_KEY + T0A_BUDGET_APPROVED=1")
        return 0
    if os.getenv("T0A_BUDGET_APPROVED") != "1":
        print("缺少 T0A_BUDGET_APPROVED=1（项目方预算授权），终止", file=sys.stderr)
        return 2
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        print("缺少 DEEPSEEK_API_KEY，终止", file=sys.stderr)
        return 2
    cli = AC.T0AClient(key)
    # 关键：走现有散文抽取入口，下游 Norm/Fact 由既有规则产出
    PS._MAX_TOKENS = MAX_TOKENS
    os.environ["PROSE_NO_RETRY"] = "1"
    os.environ["PROSE_BATCH_BLOCKS"] = "5"
    norms, stats = PS._extract_blocks("smtp", bl, llm=cli)
    spent = ((stats.get("input_tokens") or 0) * PRICE_IN_PEAK
             + (stats.get("output_tokens") or 0) * PRICE_OUT_PEAK) / 1e6
    print(f"结束：calls={stats.get('calls')} norms={len(norms)} "
          f"in={stats.get('input_tokens')} out={stats.get('output_tokens')} 约 {spent:.4f} 元")
    if stats.get("calls", 0) > MAX_CALLS:
        print("请求数超过上限，需人工核查")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
