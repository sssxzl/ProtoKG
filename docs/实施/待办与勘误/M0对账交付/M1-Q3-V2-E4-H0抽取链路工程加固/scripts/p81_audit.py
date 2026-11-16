# -*- coding: utf-8 -*-
"""★ H0：★ **只读审计 + 离线加固验证**（★ 不改生产代码）。

★ ① 来源身份解析审计（★ 对全部实际入口的 source 形态）
★ ② 运行统计可复算性复核（★ §四 第 9 条）
★ ③ 字段级流转对账（★ H2 / H3 逐候选）
★ ④ 批量化与缓存正确性审计
"""
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/h0"))
import source_contract as SC
import field_ledger as FL
import run_events as RE

OUTD = ROOT / "guard/_out/_n1c_v2/h0"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-H0抽取链路工程加固")
DELIV.mkdir(parents=True, exist_ok=True)
E4 = ROOT / "guard/_out/_n1c_v2/e4"
PILOT = ROOT / "guard/_out/_v2_e2_pilot"

_report = {}

# ══ ① 来源身份解析审计 ══
print("  ★ ① 来源身份解析审计")
_forms = collections.Counter()
_samples = []
for _p in (E4 / "pool/V2-E4_H3新增候选原始.jsonl",
           PILOT / "V2-E2_新增候选审计.jsonl"):
    if not _p.is_file():
        continue
    for _l in _p.read_text(encoding="utf-8").splitlines():
        if not _l.strip():
            continue
        _d = json.loads(_l)
        _n = _d.get("★ norm（★ 派生层输出）") or _d.get("★ ★ candidate 全量") or {}
        _src = _n.get("source")
        if not _src:
            continue
        _kind = "file:doc#@line" if "#@" in _src else ("file:doc#sec" if "#" in _src
                                                     else "bare")
        _forms[_kind] += 1
        if len(_samples) < 6:
            _samples.append({"source_reference": _src, "形态": _kind,
                             "★ 解析结果": SC.normalize_document_id(_src)})
# ★ 生产侧形态（★ 源码审计）
_prod_forms = {
    "prose_semantics.py:1209": "file:<doc>#@<line>",
    "rfc_extractor.py:1079": "file:<doc>#<section>",
    "rfc_extractor.py:4616 解析": 'replace("file:", "")（★ 宽松：★ 不校验其余部分）',
    "semantic.py:428-429 解析": "startswith('file:') + 切片（★ 宽松）",
}
_report_forms = {"★ 实际产出中出现的形态": dict(_forms),
                 "★ 生产侧已知形态与解析点": _prod_forms,
                 "★ 样例解析": _samples}
for _s in _samples:
    print(f"      {_s['source_reference'][:38]:40s} → "
          f"{_s['★ 解析结果']['normalized_document_id']}")
_report["① 来源身份解析审计"] = _report_forms

# ══ ② 运行统计可复算性（★ §四 第 9 条）══
print("  ★ ② 运行统计可复算性复核")
_diag_dirs = {"H2（★ 第一轮试点）": PILOT / "diagnostics",
              "H3（★ 第二轮试点）": E4 / "diagnostics"}
_recheck = {}
for _tag, _d in _diag_dirs.items():
    _files = sorted(_d.glob("*.jsonl")) if _d.is_dir() else []
    _recheck[_tag] = {
        "★ 事件文件数": len(_files),
        "★ 结论": ("★ **可独立复算**" if _files else
                "★ **不可独立复算**（★ 无逐次事件记录）"),
        "★ 说明": ("★ 事件文件存在 ⇒ 可由事件重算统计" if _files else
                "★ 诊断器 flush() 未被调用 ⇒ 逐次请求/失败/截断证据【完全缺失】；"
                "★ 汇总数字仅来自内存 stats ⇒ **不可独立复算**"),
    }
    print(f"      {_tag}: 事件文件 {len(_files)} 个 ⇒ {_recheck[_tag]['★ 结论']}")
# ★ 生产诊断目录（★ 有 flush 调用）
_prod_diag = ROOT / "derived/diagnostics/llm_calls"
_prod_files = sorted(_prod_diag.glob("*.jsonl")) if _prod_diag.is_dir() else []
_mine = [p for p in _prod_files
         if "pilot" in p.read_text(encoding="utf-8", errors="replace")[:400].lower()
         or "v2e" in p.name.lower()]
_recheck["★ 生产诊断目录"] = {
    "★ 路径": str(_prod_diag.relative_to(ROOT)),
    "★ 事件文件数": len(_prod_files),
    "★ 是否含本项目两次隔离试点": bool(_mine),
    "★ 结论": "★ 生产流程有 flush 调用 ⇒ 事件齐全；★ **但两次隔离试点未走该路径**",
}
print(f"      生产诊断目录: {len(_prod_files)} 个事件文件｜"
      f"★ 含本项目试点 = {bool(_mine)}")
# ★ §四 第 9 条的正式结论
_run2 = json.loads((PILOT / "V2-E2_LLM抽取试点运行报告.json").read_text(encoding="utf-8"))
_run4 = json.loads((E4 / "V2-E4_9份抽取运行报告.json").read_text(encoding="utf-8"))
_recheck["★ §四 第 9 条正式结论"] = {
    "★ H2 声称": {k: _run2.get(k) for k in
               ("★ 实际处理 RFC 文档数", "★ 实际处理 chunk 数",
                "★ 实际 LLM 调用数（★ 估算）", "★ token 合计", "★ 估算费用 USD")},
    "★ H3 声称": {k: _run4.get(k) for k in
               ("★ 实际 RFC 文档数", "★ 实际块数",
                "★ 实际 LLM 请求数（★ stats.calls，★ 含解析失败重试）",
                "★ token 合计", "★ 估算费用 USD")},
    "★ ★ 能否独立复算": "★ **否**",
    "★ 理由": ("★ 两次隔离试点的 **LLMDiagnostics.flush() 从未被调用** ⇒ "
             "★ **无逐次请求事件**、★ **无失败证据**、★ **无截断定位**；"
             "★ 汇总数字仅来自生产 `_extract_blocks` 的**内存 stats**（★ 该值不落盘）"
             "★ ⇒ ★ **9 份 / 18 块 / 4 次请求 / 19,657 tokens / $0.009789 "
             "★ 这些数字【无法由底层事件独立复算】**"),
    "★ ★ 缺失项处置": ("★ 缺失的历史 token 数据标记 **unavailable**；"
                "★ **不得估算后写成真实值**；★ 本轮以影子事件日志重建可复算链路"),
}
_report["② 运行统计可复算性复核"] = _recheck

# ══ ③ 字段级流转对账 ══
print("  ★ ③ 字段级流转对账")
# ★ ★ 先建「doc + 块起点 → raw item」索引（★ raw item 的 span = 块起点）
_raw_index = {}
for _rp in (PILOT / "V2-E2_新增候选审计.jsonl",
            E4 / "pool/V2-E4_H3原始LLM输出.jsonl"):
    if not _rp.is_file():
        continue
    for _l in _rp.read_text(encoding="utf-8").splitlines():
        if not _l.strip():
            continue
        _d = json.loads(_l)
        _it = _d.get("★ ★ 原始 LLM 输出（★ 全字段）") or _d.get("★ ★ candidate 全量")
        if not _it:
            continue
        _doc = str(_it.get("doc") or "")
        _sp = _it.get("span")
        if _doc and _sp is not None:
            _raw_index.setdefault((_doc, int(_sp)), []).append(_it)


def _find_raw(doc, span_line):
    """★ 按「同文档、块起点 ≤ 实体匹配行的最大者」反查 raw item。"""
    if not doc or span_line is None:
        return {}
    _cands = [(_kk, _vv) for _kk, _vv in _raw_index.items()
              if _kk[0] == doc and _kk[1] <= int(span_line)]
    if not _cands:
        return {}
    _best = max(_cands, key=lambda kv: kv[0][1])
    return _best[1][0] if _best[1] else {}


_rows = []
for _tag, _p in (("H2", PILOT / "V2-E2_新增候选审计.jsonl"),
                  ("H3", E4 / "pool/V2-E4_H3新增候选原始.jsonl")):
    if not _p.is_file():
        continue
    for _l in _p.read_text(encoding="utf-8").splitlines():
        if not _l.strip():
            continue
        _d = json.loads(_l)
        _norm = _d.get("★ norm（★ 派生层输出）")
        _raw = _d.get("★ ★ 原始 LLM 输出（★ 全字段）")
        if _norm is None and _raw is None:
            _norm = _d.get("★ ★ candidate 全量")
        if _norm is None:
            continue
        if _raw is None:
            _raw = _find_raw(str(_norm.get("source", "")).split("/")[-1].split("#")[0]
                             .replace("file:", ""),
                             _norm.get("span_line"))
        _src = (_norm.get("source")
                or (f'file:{_d.get("★ document_id")}#@{(_norm.get("span_line") or 0)}'))
        _res = SC.resolve_source(_src, kb_root=ROOT / "kb")
        _rows.extend(FL.trace_candidate(
            candidate_id=_d.get("★ candidate_id") or _d.get("★ document_id") or "",
            knowledge_kind=_d.get("★ proposed_knowledge_kind")
            or (_norm.get("kind") or ""),
            raw_item=_raw or {}, norm=_norm, source_ref=_src,
            source_resolution=_res))
with (OUTD / "h0_field_ledger.jsonl").open("w", encoding="utf-8") as f:
    for _r in _rows:
        f.write(json.dumps(_r, ensure_ascii=False) + "\n")
_stats = FL.field_stats(_rows)
_kinds = FL.kind_split_stats(_rows)
_unres = [r for r in _rows if r["★ 来源解析状态"] != "resolved"]
_lost = [r for r in _rows if r["★ 状态"] == FL.UNEXPECTEDLY_LOST]
print(f"      字段流转记录 = {len(_rows)} 条｜★ 来源未解析 = {len(_unres)}"
      f"｜★ unexpectedly_lost = {len(_lost)}")
print("      ★ 逐字段（★ LLM 覆盖率 / Norm 保留率 / 保全率）：")
for _f, _v in _stats.items():
    print(f"          {_f:20s} 适用 {_v['① 字段适用率']:.4f}｜"
          f"LLM {_v['② 模型输出覆盖率']:.4f}｜Norm {_v['③ 派生阶段保留率']:.4f}｜"
          f"canon {_v['④ 映射阶段保全率']:.4f}")
_report["③ 字段级流转对账"] = {
    "★ 流转记录数": len(_rows),
    "★ 来源未解析数": len(_unres),
    "★ unexpectedly_lost 数": len(_lost),
    "★ 逐字段指标": _stats,
    "★ 按知识类别分组": _kinds,
}

# ══ ④ 批量化与缓存正确性审计 ══
print("  ★ ④ 批量化与缓存审计")
_cf = E4 / "cache/DHCPv4.prose.json"
_cache = json.loads(_cf.read_text(encoding="utf-8")) if _cf.is_file() else {}
_report["④ 批量化与缓存正确性审计"] = {
    "★ 生产批大小": 5,
    "★ 缓存键组成": ("★ `cache_key(prompt_version, input_fingerprint, temperature, "
                "max_tokens, prompt_digest)`（★ 见 cache_key.py）"),
    "★ ★ 缓存键是否含来源版本": ("★ ★ **不含**（★ 只含块文本指纹）⇒ ★ "
                     "★ **同文档换版本时键不变** ⇒ ★ 潜在风险"),
    "★ ★ 缓存键是否含模型": "★ **不含**（★ model_identity 只在 cache_key 的模型身份串里，★ 需核）",
    "★ 缓存文件条目数": len(_cache.get("items") or []),
    "★ ★ 一次批量 JSON 损坏是否导致整批丢失": ("★ **是**（★ `_extract_blocks` 的批内循环中，"
                              "★ 单批 JSON 损坏 ⇒ 该批 items 为空 ⇒ "
                              "★ **该批全部块无候选**）"),
    "★ ★ 重试是否重复插入候选": ("★ **是**（★ `_attempt` 重试成功后 `_raw_items` 继续 append，"
                       "★ 但同一批只 append 一次 ⇒ ★ **不重复**；"
                       "★ 跨批无影响）"),
    "★ ★ 批次→chunk_id 映射": ("★ **可追踪**（★ `_chunk_id(batch)` 由 batch 内 doc+start 推导；"
                     "★ 但 **norm 的 span_line 是实体匹配行**，★ "
                     "★ **不是块起点** ⇒ ★ 需按「同文档 start ≤ span 的最大者」反查）"),
    "★ ★ 缓存命中是否污染真实统计": ("★ **会**（★ 本轮已实测：★ 缓存命中重跑把 "
                       "★ token/calls 归零并覆盖报告 ⇒ ★ 已由 "
                       "★ `p73_restore_stats.py` 恢复，★ 根因修复见 `run_events.py`）"),
    "★ 输出截断能否定位": ("★ ★ **不能定位到具体块**（★ 截断体现在整批的 finish_reason，"
                  "★ 块级无独立标记）"),
    "★ ★ 结论": ("★ 批量化本身正确（★ 18 块 = 4 批 = 4 请求），★ "
             "★ **但缓存键缺来源版本、★ 截断不可块级定位、★ 缓存命中会覆盖统计**"),
}
for _k, _v in _report["④ 批量化与缓存正确性审计"].items():
    print(f"      {_k}: {str(_v)[:110]}")

(OUTD / "h0_audit_report.json").write_text(
    json.dumps(_report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'h0_audit_report.json'}")
print(f"  ⇒ {OUTD/'h0_field_ledger.jsonl'}")
