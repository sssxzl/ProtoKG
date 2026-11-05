# -*- coding: utf-8 -*-
"""交叉校验：RFC 源独立抽的「消息级必填头」 vs 骨架的「方法级必填头」。

★ 为什么做这个（★ F2 的重新定义）：
  原设想 F2 = 「用 RFC 源那份**替代**骨架那份 + 按消息级/方法级分层」。
  ★ **实测推翻了这个设想**：
    · 骨架的 `required_headers` 其实是**方法级**的（rtsp：SETUP 带 Transport、
      PLAY/PAUSE/TEARDOWN 带 Session、DESCRIBE/OPTIONS 只带 CSeq）⇒ **语义正确**，
      且取值池有真实值（不是空串）⇒ 不存在「报文带上本不该带的头」的问题；
    · RFC 源 LLM 抽的是**消息级**（所有请求都必带）⇒ 两者**层次互补，不是替代关系**；
    · 实测交集：RFC 抽到的 ⊆ 骨架并集，**零缺口** ⇒ 「替代/叠加」的**增量 = 0**。
  ⇒ ★★ F2 的真正价值不是「替代」，而是**独立复核**：
     RFC 源从 RFC 原文**独立**抽出的消息级必填头，与骨架那份**一致**（零缺口）
     ⇒ 证明骨架这一维**经得起 RFC 独立复核** ⇒ 这是「RFC 单源纯净度」的**正面证据**
     （而不是「骨架是污染源」的负面判断）。

★ 输出：
  · 交集 / RFC 独有（疑似误报）/ 骨架独有（方法级专属）
  · 判定：RFC 抽到的 ⊆ 骨架并集？（= 骨架与 RFC 语义一致）
  · 落盘 `local/required_headers_crosscheck.json`（论文可审计）

用法：E:/app/Anaconda3/python.exe local/_crosscheck_required_headers.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import paths                                      # noqa: E402
from core.fused.downstream import rag_seedgen as RS        # noqa: E402
from core.fused.rfc_extractor import infer_required_headers  # noqa: E402


def main() -> None:
    report: dict = {}
    print("=" * 82)
    print("交叉校验：RFC 源（消息级） ⊆ 骨架（方法级）？")
    print("=" * 82)
    for protocol in ("rtsp", "sip", "smtp"):
        views = RS.load_fact_views(protocol)
        if not views:
            continue
        b = RS.assemble_bundle(views, protocol)
        skel = b.get("required_headers") or {}
        skel_union = {h for hs in skel.values() for h in hs}
        rfc_msg = sorted({str(n.get("name", "")).strip()
                          for n in infer_required_headers(protocol)})
        rfc_set = set(rfc_msg)
        inter = sorted(rfc_set & skel_union)
        rfc_only = sorted(rfc_set - skel_union)
        skel_only = sorted(skel_union - rfc_set)
        # 骨架里哪些头是**方法级专属**（不在 RFC 源的消息级集合里）
        method_level = {}
        for m, hs in sorted(skel.items()):
            extra = [h for h in hs if h not in rfc_set]
            if extra:
                method_level[m] = extra
        print(f"\n── {protocol}")
        print(f"   RFC 源独立抽出（消息级）: {rfc_msg}")
        print(f"   骨架（方法级并集）      : {sorted(skel_union)}")
        print(f"   ★ 交集 {len(inter)} 个: {inter}")
        print(f"   ★ RFC 独有（疑似误报）: {rfc_only}")
        print(f"   ★ 骨架独有（方法级专属）: {skel_only}")
        if method_level:
            print(f"   方法级归属明细: {method_level}")
        verdict = ("一致（RFC 抽到的全部被骨架覆盖）" if not rfc_only
                   else f"有 {len(rfc_only)} 个 RFC 抽到的头不在骨架内")
        print(f"   ⇒ 判定：**{verdict}**")
        report[protocol] = {
            "rfc_message_level": rfc_msg,
            "skeleton_union": sorted(skel_union),
            "intersection": inter,
            "rfc_only_suspect": rfc_only,
            "skeleton_only_method_level": skel_only,
            "method_level_detail": method_level,
            "verdict": verdict,
            "rfc_subset_of_skeleton": not rfc_only,
        }
    p = Path(__file__).resolve().parent / "required_headers_crosscheck.json"
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已写入 {p}")


if __name__ == "__main__":
    main()
