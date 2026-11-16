# -*- coding: utf-8 -*-
"""★ V2-E4：★ **恢复首次真实调用的统计**（★ 缓存命中重跑会把 token/calls 归零）。

★ ★ 真实调用（★ 首次，★ cache miss）：
    run_id = v2e4-9doc-20261116-193838
    RFC 9 ｜块 18 ｜请求 4 ｜重试 0 ｜失败 0
    input 4455 ｜output 15202 ｜合计 19657 ｜费用 USD 0.009789 ｜耗时 150.7s
★ ★ 复核调用（★ cache hit）：★ 请求 0 ｜token 0 ⇒ **不计入预算**
"""
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/e4"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4队列B审核启动与保留抽取")

REAL = {
    "run_id": "v2e4-9doc-20261116-193838",
    "★ 实际 RFC 文档数": 9, "★ 实际块数": 18,
    "★ 批量化": "★ 一次调用传 18 块 ⇒ 生产 _BATCH_BLOCKS=5 ⇒ 约 3 批",
    "★ 实际 LLM 请求数（★ stats.calls，★ 含解析失败重试）": 4,
    "★ 重试数 / 失败数": [0, 0],
    "★ input tokens": 4455, "★ output tokens": 15202,
    "★ token 合计": 19657, "★ 估算费用 USD": 0.009789,
    "★ 耗时秒": 150.7,
}

_p = OUTD / "V2-E4_9份抽取运行报告.json"
_s = json.loads(_p.read_text(encoding="utf-8"))
_cur_req = _s.get("★ 实际 LLM 请求数（★ stats.calls，★ 含解析失败重试）")
_cur_tok = _s.get("★ token 合计")
if _cur_req == 0 and _cur_tok == 0:
    # ★ 本次是缓存命中复核 ⇒ 恢复首次真实统计并标注
    _s.update(REAL)
    _s["★ ★ 复核调用说明"] = (
        "★ 本次重跑为【缓存命中复核】（★ 请求 0 / token 0），★ **不计入预算**；"
        "★ 上表为【首次真实调用】的统计（★ cache miss，★ run_id "
        f"{REAL['run_id']}）")
    _s["★ 首次真实调用 run_id"] = REAL["run_id"]
    _s["★ 复核调用（★ cache hit）"] = {"★ 请求数": 0, "★ token": 0}
    _p.write_text(json.dumps(_s, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  ★ 已恢复首次真实调用的统计（★ 缓存命中重跑归零已修正）")
else:
    print("  ★ 当前报告已是真实调用统计（★ 无需恢复）")
for _k in ("★ 实际 LLM 请求数（★ stats.calls，★ 含解析失败重试）", "★ token 合计",
           "★ 估算费用 USD", "★ 各限额是否未超"):
    print(f"      {_k}: {_s.get(_k)}")
print(f"  ⇒ {_p}")
