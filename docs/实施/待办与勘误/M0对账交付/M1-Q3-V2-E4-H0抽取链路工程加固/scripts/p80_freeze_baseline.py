# -*- coding: utf-8 -*-
"""★ H0 §二：★ **冻结现有运行基线**（★ 只读，★ 不覆盖任何已有来源记录）。

★ 冻结：H1 156 / H2 52 / H3 23 / 两轮原始调用与缓存与统计 / V0V1V2 哈希 / 队列B 54 证据基线
★ ★ 所有新增审计数据单独落盘（★ 不覆盖已有记录）
"""
import hashlib
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/h0"
OUTD.mkdir(parents=True, exist_ok=True)
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-H0抽取链路工程加固")
DELIV.mkdir(parents=True, exist_ok=True)


def _sha(p):
    _p = pathlib.Path(p)
    return hashlib.sha256(_p.read_bytes()).hexdigest() if _p.is_file() else None


def _jl(p):
    _p = pathlib.Path(p)
    if not _p.is_file():
        return []
    return [json.loads(l) for l in _p.read_text(encoding="utf-8").splitlines()
            if l.strip()]


F = ROOT / "guard/_out"
E2 = F / "_n1c_v2/e2"
E4 = F / "_n1c_v2/e4"
PILOT = F / "_v2_e2_pilot"

# ══ H1 / H2 / H3 ══
_h1 = _jl(ROOT / "guard/_out/m1_q3/p079/frozen_blocks.jsonl")
_h1_items = []
for _b in _jl(ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结/frozen_blocks.jsonl"):
    for _i, _it in enumerate(_b["raw_items"]):
        _h1_items.append(f"{_b['document']}@{_b['chunk_start']}#{_i}")
_h2 = _jl(PILOT / "V2-E2_新增候选审计.jsonl")
_h2_c = [r for r in _h2 if r.get("★ candidate 全量")]
_h3 = _jl(E4 / "pool/V2-E4_H3新增候选原始.jsonl")
_h3_raw = _jl(E4 / "pool/V2-E4_H3原始LLM输出.jsonl")

# ══ 两轮原始调用与缓存 ══
_diag2 = sorted((PILOT / "diagnostics").glob("*.jsonl")) if (PILOT / "diagnostics").is_dir() else []
_diag4 = sorted((E4 / "diagnostics").glob("*.jsonl")) if (E4 / "diagnostics").is_dir() else []
_calls2 = _jl(PILOT / "V2-E2_新增候选审计.jsonl")
_calls4 = _jl(E4 / "pool/V2-E4_调用记录.jsonl")
_run2 = json.loads((PILOT / "V2-E2_LLM抽取试点运行报告.json").read_text(encoding="utf-8"))
_run4 = json.loads((E4 / "V2-E4_9份抽取运行报告.json").read_text(encoding="utf-8"))

# ══ V0/V1/V2 哈希 ══
_v012 = {
    "V0": _sha(F / "_n1c/n2b0_tristate.py"),
    "V1": _sha(F / "_n1c/n2b0_tristate_v1.py"),
    "V2": _sha(F / "_n1c_v2/v2_knowledge_gate.py"),
}

# ══ 队列 B 54 证据基线 ══
_qb = _jl(ROOT / "docs/实施/待办与勘误/M0对账交付"
          / "M1-Q3-V2-E3队列B盲审发放与保留来源预案"
          / "V2-E3_原文与证据不可编辑字段基线.jsonl")

_baseline = {
    "★ 审计基线提交": "76aaadb",
    "★ H1（★ 历史候选）": {
        "★ 条数": len(_h1_items),
        "★ 来源文件": "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结/frozen_blocks.jsonl",
        "★ SHA256": _sha(ROOT / "docs/实施/待办与勘误/M0对账交付"
                         "/M1-Q2证据冻结/frozen_blocks.jsonl"),
        "★ 候选条数（★ 只读）": len(_h1)},
    "★ H2（★ 第一轮隔离试点）": {
        "★ 条数": len(_h2_c),
        "★ 来源文件": "guard/_out/_v2_e2_pilot/V2-E2_新增候选审计.jsonl",
        "★ SHA256": _sha(PILOT / "V2-E2_新增候选审计.jsonl"),
        "★ 运行统计文件": "V2-E2_LLM抽取试点运行报告.json",
        "★ 运行统计 SHA256": _sha(PILOT / "V2-E2_LLM抽取试点运行报告.json"),
        "★ 关键统计": {k: _run2.get(k) for k in
                   ("★ run_id", "★ 实际处理 RFC 文档数", "★ 实际处理 chunk 数",
                    "★ 实际 LLM 调用数（★ 估算）", "★ input tokens",
                    "★ output tokens", "★ token 合计", "★ 估算费用 USD")},
        "★ 诊断文件数": len(_diag2),
        "★ 诊断文件 SHA256": {p.name: _sha(p) for p in _diag2},
        "★ 缓存目录": "guard/_out/_v2_e2_pilot/cache/（★ 不入库）",
        "★ 缓存 SHA256": _sha(PILOT / "cache/DHCPv4.prose.json")},
    "★ H3（★ 第二轮隔离试点）": {
        "★ 候选条数": len(_h3), "★ 原始 LLM 输出条数": len(_h3_raw),
        "★ 来源文件": "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl",
        "★ SHA256": _sha(E4 / "pool/V2-E4_H3新增候选原始.jsonl"),
        "★ 原始输出 SHA256": _sha(E4 / "pool/V2-E4_H3原始LLM输出.jsonl"),
        "★ 运行统计文件": "V2-E4_9份抽取运行报告.json",
        "★ 运行统计 SHA256": _sha(E4 / "V2-E4_9份抽取运行报告.json"),
        "★ 关键统计": {k: _run4.get(k) for k in
                   ("★ run_id", "★ 实际 RFC 文档数", "★ 实际块数",
                    "★ 实际 LLM 请求数（★ stats.calls，★ 含解析失败重试）",
                    "★ input tokens", "★ output tokens", "★ token 合计",
                    "★ 估算费用 USD", "★ 复核调用（★ cache hit）")},
        "★ 诊断文件数": len(_diag4),
        "★ 诊断文件 SHA256": {p.name: _sha(p) for p in _diag4},
        "★ 缓存目录": "guard/_out/_n1c_v2/e4/cache/（★ 不入库）",
        "★ 缓存 SHA256": _sha(E4 / "cache/DHCPv4.prose.json")},
    "★ V0/V1/V2 哈希": _v012,
    "★ 队列 B 证据基线": {
        "★ 条数": len(_qb),
        "★ 来源文件": "docs/实施/待办与勘误/M0对账交付/M1-Q3-V2-E3队列B盲审发放与保留来源预案/V2-E3_原文与证据不可编辑字段基线.jsonl",
        "★ SHA256": _sha(ROOT / "docs/实施/待办与勘误/M0对账交付"
                         "/M1-Q3-V2-E3队列B盲审发放与保留来源预案"
                         "/V2-E3_原文与证据不可编辑字段基线.jsonl")},
}
(OUTD / "h0_baseline_frozen.json").write_text(
    json.dumps(_baseline, ensure_ascii=False, indent=2), encoding="utf-8")
print("  ★ 基线冻结：")
print(f"      H1 = {_baseline['★ H1（★ 历史候选）']['★ 条数']}"
      f"｜H2 = {len(_h2_c)}｜H3 = {len(_h3)}（★ raw {len(_h3_raw)}）"
      f"｜队列B = {len(_qb)}")
print(f"      V0/V1/V2 哈希：{ {k: v[:12] for k, v in _v012.items()} }")
print(f"      H2 诊断 {len(_diag2)} 个｜H3 诊断 {len(_diag4)} 个")
print(f"  ⇒ {OUTD/'h0_baseline_frozen.json'}")
