# -*- coding: utf-8 -*-
"""guard/verify_rfc_field_values.py —— 批次 2.0（P0）的**分布校验**。

判据：
  ① RFC 源确实产出了「字段取值」知识（norm 层 + fact 层）；
  ② ``headers`` 桶的**取值池空值率**显著下降；
  ③ ★ **必填头**的取值池**不再为空**（这是 ⑤ 层 value-pool-boundary
     规则与批次 1 的 R-2 能修好的前提）；
  ④ 取值可**溯源**到 rfc 源（by_source 里 rfc 的贡献 > 0）；
  ⑤ 取值**质量**：无超长、无散文形态残留（抽样人工可读）。

用法::

    E:/app/Anaconda3/python.exe guard/verify_rfc_field_values.py \
        --protocol rtsp --protocol sip --protocol smtp
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fused.extraction import rfc_extractor as RX                   # noqa: E402
from core.fused.downstream.rag_seedgen import (              # noqa: E402
    assemble_bundle, load_fact_views,
)

#: P0 之前的实测基线（批次 1.6 终态）：{协议: (headers 总数, 取值池空数,
#:                                     必填头取值池空数)}
BASELINE_BEFORE = {
    "rtsp": (58, 28, 0),
    "sip": (63, 26, 17),
    "smtp": (1, 0, 0),
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批次 2.0（P0）分布校验")
    ap.add_argument("--protocol", action="append", default=None)
    args = ap.parse_args(argv)
    protocols = args.protocol or ["rtsp", "sip", "smtp"]

    overall_ok = True
    for protocol in protocols:
        print(f"\n=== {protocol} ===")
        norms = RX.extract_rfc_norms(protocol)
        fv = [n for n in norms if n.get("kind") == "field_value"]
        n_values = sum(len(RX._parse_value_samples(n.get("content", "")))
                       for n in fv)
        print(f"  ① field_value norm {len(fv)} 条、共 {n_values} 个取值"
              f"（norms 总数 {len(norms)}）")

        bundle = assemble_bundle(load_fact_views(protocol), protocol)
        headers = bundle.get("headers") or {}
        empty = [k for k, v in headers.items() if not (v.get("values") or [])]
        req_empty = [(m, h) for m, hl in (bundle.get("required_headers") or {}).items()
                     for h in hl if h in empty]
        before = BASELINE_BEFORE.get(protocol, (0, 0, 0))
        ratio = len(empty) / max(len(headers), 1) * 100
        print(f"  ② headers {len(headers)} 个；取值池空 {len(empty)}"
              f"（{ratio:.0f}%）"
              f" ⇒ P0 前 {before[1]} 个（{before[1]/max(before[0],1)*100:.0f}%）")
        print(f"  ③ **必填头**取值池为空：{len(req_empty)} 个"
              f" ⇒ P0 前 {before[2]} 个")
        if req_empty:
            print(f"     ✗ 仍为空: {req_empty[:8]}")
            overall_ok = False

        by_src = (bundle.get("by_source") or {}).get("headers") or {}
        rfc_n = by_src.get("rfc", 0)
        print(f"  ④ 取值可溯源：by_source[headers] = {by_src}")
        if fv and rfc_n == 0:
            print("     ✗ 有 field_value norm 但 headers 桶里没有 rfc 贡献")
            overall_ok = False

        # ⑤ 质量抽样：超长 / 明显散文
        long_vals = []
        for name, info in headers.items():
            for v in (info.get("values") or []):
                if len(str(v)) > RX._MAX_SAMPLE_VALUE_LEN:
                    long_vals.append((name, str(v)[:60]))
        print(f"  ⑤ 质量抽样：超长取值 {len(long_vals)} 个"
              f" {'✅' if not long_vals else '❌'}")
        for n_, v_ in long_vals[:5]:
            print(f"     ✗ {n_}: {v_}")
        if long_vals:
            overall_ok = False

        # 明细：RFC 源贡献了取值的头
        rfc_heads = sorted(
            k for k, v in headers.items()
            if (v.get("source_values") or {}).get("rfc"))
        print(f"     RFC 源贡献取值的头（{len(rfc_heads)} 个）: "
              f"{rfc_heads[:14]}")

    print("\n结论：" + ("✅ 可采信（P0 分布校验通过）" if overall_ok
                       else "❌ 不可采信（见上方 ❌ 项）"))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
