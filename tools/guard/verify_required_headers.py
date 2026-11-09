# -*- coding: utf-8 -*-
"""tools/guard/verify_required_headers.py —— 批次 1.6 **步 4** 的**分布校验**。

判据（方案 §3.1.10.6 步 4）：
  ① bundle 的 ``required_headers`` 与 profile.json 的**等价**（物化前后不变）；
  ② ``available_sources`` 含 ``profile`` 但 **origin 单独标注**；
  ③ 中枢里**确实有**物化的必填头事实（或明确记录「该协议走兼容期回退」）。

用法::

    E:/app/Anaconda3/python.exe tools/guard/verify_required_headers.py \
        --protocol rtsp --protocol sip --protocol smtp
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core import paths                                      # noqa: E402
from core.fused.downstream.rag_seedgen import (             # noqa: E402
    assemble_bundle, load_fact_views,
)


def _profile_required_headers(protocol: str) -> dict:
    prof = paths.target_profile(protocol)
    if not prof.is_file():
        return {}
    data = json.loads(prof.read_text(encoding="utf-8"))
    return {k: sorted(set(v)) for k, v in
            ((data.get("seedgen") or {}).get("required_headers") or {}).items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="批次 1.6 步 4 分布校验")
    ap.add_argument("--protocol", action="append", default=None)
    args = ap.parse_args(argv)
    protocols = args.protocol or ["rtsp", "sip", "smtp"]

    overall_ok = True
    for protocol in protocols:
        print(f"\n=== {protocol} ===")
        expected = _profile_required_headers(protocol)
        views = load_fact_views(protocol)
        if not views:
            print("  中枢为空 —— 跳过")
            overall_ok = False
            continue
        bundle = assemble_bundle(list(views), protocol)

        # ① 等价性
        got = bundle.get("required_headers") or {}
        eq_ok = got == expected
        print(f"  ① required_headers 与 profile.json 等价: "
              f"{'✅' if eq_ok else '❌'}"
              f"（profile {len(expected)} 个方法 / bundle {len(got)} 个方法）")
        if not eq_ok:
            only_exp = {k: v for k, v in expected.items() if got.get(k) != v}
            print(f"       ✗ 差异: {json.dumps(only_exp, ensure_ascii=False)}")
            overall_ok = False

        # ② available_sources + origin 分列
        avail = bundle.get("available_sources") or []
        origin = (bundle.get("bucket_origin") or {}).get("required_headers")
        has_profile = "profile" in avail
        if expected:
            # 该协议**有**必填头清单 ⇒ 必须已物化（origin 标 facts）
            origin_ok = bool(origin) and origin.get("facts") is True
            print(f"  ② available_sources={avail}；"
                  f"required_headers origin={origin}")
            print(f"     含 profile: {'✅' if has_profile else '❌'}   "
                  f"origin 标注 facts: {'✅' if origin_ok else '❌'}")
            if not (has_profile and origin_ok):
                overall_ok = False
        else:
            # 该协议**没有**必填头清单 ⇒ 无需物化，origin 应为全 False
            origin_ok = bool(origin) and not origin.get("facts") \
                and not origin.get("profile")
            print(f"  ② available_sources={avail}；"
                  f"required_headers origin={origin}")
            print(f"     含 profile: {'✅' if has_profile else '❌'}   "
                  f"无必填头清单 ⇒ origin 应为全 False: "
                  f"{'✅' if origin_ok else '❌'}")
            if not (has_profile and origin_ok):
                overall_ok = False

        # ③ 中枢里确实有物化事实（否则应明确是兼容期回退）
        materialized = [v for v in views
                        if (v.get("fact_key") or {}).get("aspect")
                        == "required_headers"]
        if expected:
            mat_ok = len(materialized) == len(expected)
            print(f"  ③ 中枢里的必填头事实 {len(materialized)} 条 "
                  f"（profile {len(expected)} 个方法）"
                  f" {'✅' if mat_ok else '❌'}")
            if not mat_ok:
                overall_ok = False
        else:
            print(f"  ③ 该协议 profile.json 无 required_headers "
                  f"⇒ 走兼容期回退（中枢里 {len(materialized)} 条物化事实）"
                  f" {'✅' if not materialized else '❌'}")
            if materialized:
                overall_ok = False

        # 明细
        for method in sorted(got):
            print(f"     {method:16s} {got[method]}")

    print("\n结论：" + ("✅ 可采信（步 4 分布校验通过）" if overall_ok
                       else "❌ 不可采信（见上方 ❌ 项）"))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
