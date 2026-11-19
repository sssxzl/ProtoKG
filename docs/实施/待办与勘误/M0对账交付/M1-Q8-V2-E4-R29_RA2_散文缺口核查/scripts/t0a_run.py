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


def batches():
    f = ROOT / "kb/smtp/spec/rfc3207.txt"
    text = f.read_text(encoding="utf-8", errors="replace")
    blocks = PS._split_blocks(text, (len(text) // PS._MAX_BLOCK_CHARS) + 1)
    out = []
    for part in (blocks[:5], blocks[5:]):
        body = "".join(f"\n\n===== [文档 rfc3207.txt]（起始行号 {st}）=====\n{bt}"
                       for st, bt in part)
        out.append(AC.build_payload("你是协议规范分析员。只输出 JSON。", PS._PROMPT + body))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="真正联网（需预算授权）")
    args = ap.parse_args()
    pays = batches()
    for p in pays:
        AC.assert_payload_ok(p, expect_max_tokens=MAX_TOKENS)
    print(f"plan: {len(pays)} 次请求，block={[len(p['messages'][1]['content']) for p in pays]} chars")
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
    spent, used_in = 0.0, 0
    for i, p in enumerate(pays, 1):
        if i > MAX_CALLS:
            break
        est_in = max(1, len(p["messages"][1]["content"]) // 4)
        if used_in + est_in > MAX_IN:
            print(f"输入预算不足（{used_in}+{est_in}>{MAX_IN}），停止"); break
        worst = est_in * PRICE_IN_PEAK / 1e6 + MAX_TOKENS * PRICE_OUT_PEAK / 1e6
        if spent + worst > CAP_CNY:
            print(f"费用预算不足（{spent:.4f}+{worst:.4f}>{CAP_CNY}），停止"); break
        try:
            out = cli.chat_json(system="你是协议规范分析员。只输出 JSON。",
                                user=p["messages"][1]["content"],
                                temperature=0.1, max_tokens=MAX_TOKENS)
        except Exception as exc:            # noqa: BLE001
            print(f"第 {i} 次请求失败：{type(exc).__name__}: {exc}；按规则停止，不重试")
            break
        meta = getattr(cli, "last_call_meta", {}) or {}
        used_in += int(meta.get("input_tokens") or est_in)
        spent += (int(meta.get("input_tokens") or est_in) * PRICE_IN_PEAK
                  + int(meta.get("output_tokens") or 0) * PRICE_OUT_PEAK) / 1e6
        if meta.get("finish_reason") == "length":
            print("finish_reason=length，结果截断，停止"); break
        print(f"请求 {i} ok：items={len(out.get('items') or [])} "
              f"in={meta.get('input_tokens')} out={meta.get('output_tokens')} 累计 {spent:.4f} 元")
        if int(meta.get("input_tokens") or est_in) > est_in * 1.5:
            print("实际计费量超预期 1.5 倍，停止，不发起下一次请求"); break
    print(f"结束：累计 {spent:.4f} 元，输入 {used_in} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
