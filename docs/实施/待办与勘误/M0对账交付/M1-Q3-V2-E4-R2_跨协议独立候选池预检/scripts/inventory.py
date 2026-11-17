# -*- coding: utf-8 -*-
"""★ V2-E4-R2 §三/§四/§五：★ **跨协议来源盘点 + 三层隔离 + 容量设计**（★ 只读）。

★★ **键命名规范（★ 本轮教训）**：
  · ★ **内部键**：★ 一律不带 `★` 前缀（★ 展示时再加）
  · ★ **外部键**：★ 一律用**模块级常量**（★ 如 `FB_DOC`）⇒ ★ **杜绝与内部键混淆**
"""
import collections
import hashlib
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/r2"
OUTD.mkdir(parents=True, exist_ok=True)

# ══ 外部数据的键（★ 常量隔离）══
FB_DOC = "document"
FB_PROTO = "protocol"
FB_START = "chunk_start"
FB_TEXT = "chunk_text"
FB_ITEMS = "raw_items"
H2_DOC = "★ document_id"
H3_DOC = "★ document_id"
LED_DOC = "★ document"
QB_DOC = "★ 来源 RFC"

_RE_RFCNO = re.compile(r"Request for Comments:\s*(\d+)")
_RE_MONTH = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+(\d{4})\b")
# RFC 头部右侧对齐区（作者、机构、日期）以 2 个以上空格分隔
_SKIP_PREFIX = ("Status of this Memo", "Status of This Memo", "Internet-Draft",
                "Network Working Group", "Request for Comments", "Category:",
                "ISSN", "Obsoletes:", "Updates:", "Copyright", "Abstract",
                "Notice", "All Rights", "Distribution of this memo")
# 标题跨行时，第一行以这些词结尾
_TITLE_JOIN = ("for", "and", "or", "of", "the", "in", "with", "to", "a", "an")


def _left_part(text):
    """取冒号后或整行的左侧段（RFC 头部右侧对齐区以 2+ 空格分隔）。"""
    s = re.split(r"\s{2,}", text.strip())
    return s[0].strip() if s else ""


def _field(lines, key):
    """从头部取 key: value，值取左侧段（排除右侧对齐的作者/机构/日期）。"""
    for l in lines[:40]:
        if l.strip().startswith(key + ":"):
            return _left_part(l.split(":", 1)[1])
    return None


def head_meta(lines):
    """从 RFC 原文头部提取权威元数据。

    规则依据 RFC Editor 原文排版：
      左侧为 RFC 号、Category、Obsoletes、Updates；右侧对齐区为作者、机构、日期。
      正式标题为居中或缩进显示，可能跨两行。
    """
    rfc = None
    for l in lines[:40]:
        m = _RE_RFCNO.search(l)
        if m:
            rfc = m.group(1)
            break
    date = None
    for l in lines[:40]:
        m = _RE_MONTH.search(l)
        if m:
            date = f"{m.group(1)} {m.group(2)}"
            break
    title = ""
    ri = next((i for i, l in enumerate(lines[:40]) if _RE_RFCNO.search(l)), None)
    if ri is not None:
        cands = []
        for l in lines[ri + 1:40]:
            s = l.strip()
            if not s or len(s) > 120:
                continue
            # 右对齐的作者/机构/日期栏（缩进 >= 30）不是标题
            if len(l) - len(l.lstrip()) >= 30:
                continue
            if s.startswith(_SKIP_PREFIX):
                continue
            if len(s.split()) < 2:
                continue
            cands.append(s)
            if s.split()[-1].lower() not in _TITLE_JOIN:
                break
        if cands:
            title = " ".join(cands[:2]) if len(cands) > 1 else cands[0]
            title = re.sub(r"\s{2,}", " ", title)
    return {"rfc_number": rfc, "title": title,
            "category": _field(lines, "Category"),
            "obsoletes": _field(lines, "Obsoletes"),
            "updates": _field(lines, "Updates"),
            "date": date}


def jl(path):
    return [json.loads(l) for l in
            pathlib.Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


docs = {}
for proto in ("sip", "rtsp", "smtp", "DHCPv4"):
    d = ROOT / "kb" / proto / "spec"
    if not d.is_dir():
        continue
    for f in sorted(d.glob("*.txt")):
        b = f.read_bytes()
        L = b.decode("utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        docs[(proto, f.name)] = {"path": str(f.relative_to(ROOT)), "lines": len(L),
                                 "sha256": hashlib.sha256(b).hexdigest(),
                                 "bytes": len(b), "meta": head_meta(L)}

blocks = jl(ROOT / "docs/实施/待办与勘误/M0对账交付"
             / "M1-Q2证据冻结/frozen_blocks.jsonl")
h1_docs = {b[FB_DOC] for b in blocks}
win = {}
for b in blocks:
    n = str(b.get(FB_TEXT) or "").count("\n") + 1
    s = int(b[FB_START])
    win.setdefault(b[FB_DOC], []).append((s, s + n - 1, len(b.get(FB_ITEMS) or [])))
h2_docs = {r[H2_DOC] for r in
           jl(ROOT / "guard/_out/_v2_e2_pilot/V2-E2_新增候选审计.jsonl") if r.get(H2_DOC)}
h3_docs = {r[H3_DOC] for r in
           jl(ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl")}
dev_docs = {json.loads(l).get(LED_DOC) for l in
            (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl")
            .read_text(encoding="utf-8").splitlines() if l.strip()}
qb_docs = {g[QB_DOC] for g in
           jl(ROOT / "docs/实施/待办与勘误/M0对账交付"
              / "M1-Q3-V2-E4-B1队列B人工真值验收/B1_人工真值冻结清单.jsonl")
           if g.get(QB_DOC)}

rows = []
for (proto, name), d in sorted(docs.items()):
    m = d["meta"]
    in_h1, in_h2, in_h3 = name in h1_docs, name in h2_docs, name in h3_docs
    in_dev, in_qb = name in dev_docs, name in qb_docs
    roles = []
    if in_dev:
        roles.append("A 开发集（N1-B/N1-C/V2 调优）")
    if in_h1:
        roles.append("B 历史独立（H1 候选）")
    if in_h2:
        roles.append("B 历史独立（H2 试点）")
    if in_h3:
        roles.append("B 历史独立（H3）")
    if in_qb:
        roles.append("B 队列B 片段来源")
    independent = not roles
    wins = win.get(name, [])
    covered = sum(e - s + 1 for s, e, _ in wins)
    rows.append({
        "protocol": proto, "document": name,
        "rfc_number": m["rfc_number"], "title": m["title"],
        "category": m["category"], "date": m["date"],
        "obsoletes": m["obsoletes"], "updates": m["updates"],
        "source_sha256": d["sha256"], "bytes": d["bytes"],
        "total_lines": d["lines"], "window_blocks": len(wins),
        "window_covered_lines": covered,
        "unexposed_lines": d["lines"] - covered,
        "unexposed_ratio": round((d["lines"] - covered) / max(1, d["lines"]), 4),
        "in_h1": in_h1, "in_h2": in_h2, "in_h3": in_h3,
        "in_dev_set": in_dev, "in_queue_b_source": in_qb,
        "independence_roles": (" ｜ ".join(roles) if roles
                               else "C 文档级独立（未参与任何开发/历史独立）"),
        "independence_level": ("★ 文档级独立（C 类）" if independent
                                else "★ 已参与既有集合（★ 不可作 C 类）"),
        "recomputable": "★ SHA256 + 行号映射均已登记 ✔",
        "metadata_source": "★ RFC 原文自带头部（★ 零网络、★ 可复算）",
    })

print("  ★ 跨协议 RFC 来源盘点（★ 元数据取自 RFC 原文头部）：")
for r in rows:
    if r["protocol"] in ("sip", "rtsp", "smtp"):
        print(f"      {r['protocol']:6s} {r['document']:14s} RFC{r['rfc_number']}"
              f"｜{str(r['title'])[:42]}")
        print(f"             Cat={r['category']}｜Date={r['date']}"
              f"｜Obsoletes={r['obsoletes']}｜Updates={r['updates']}")
        print(f"             行 {r['total_lines']}｜窗口覆盖 {r['window_covered_lines']}"
              f"｜未暴露 {r['unexposed_lines']}（{r['unexposed_ratio']:.1%}）"
              f"｜{r['independence_level']}")

cap = {}
for proto in ("sip", "rtsp", "smtp"):
    sub = [r for r in rows if r["protocol"] == proto]
    indep = [r for r in sub if r["independence_level"].startswith("★ 文档级独立")]
    cap[proto] = {
        "rfc_count": len(sub),
        "independent_rfc_count": len(indep),
        "independent_documents": [r["document"] for r in indep],
        "total_lines": sum(r["total_lines"] for r in sub),
        "exposed_lines": sum(r["window_covered_lines"] for r in sub),
        "unexposed_lines": sum(r["unexposed_lines"] for r in sub),
        "block_capacity_100lines": (
            0 if not indep else
            (sum(r["unexposed_lines"] for r in indep) - 10 * len(indep)) // 100),
        "max_per_document": 6,
        "expected_candidate_capacity": len(indep) * 2 * 2,
        "expected_knowledge_types": "★ 规范规则 / 协议语法 / 注册值 / 描述性 / 非协议元数据",
        "actual_capacity_after_exclusion": len(indep),
        "plan_vs_actual": "★ 计划见《受控LLM抽取预算申请》；★ 实际产出待授权后统计",
    }
print()
print("  ★ 三协议候选容量设计：")
for p, v in cap.items():
    print(f"      {p:6s} RFC {v['rfc_count']}｜文档级独立 {v['independent_rfc_count']}"
          f"｜未暴露行 {v['unexposed_lines']}｜可选块 ~{v['block_capacity_100lines']}"
          f"｜预计候选 ~{v['expected_candidate_capacity']}")

(OUTD / "r2_inventory.json").write_text(json.dumps({
    "rfc_rows": rows, "capacity": cap,
    "sets": {"h1_docs": sorted(h1_docs), "h2_docs": sorted(h2_docs),
             "h3_docs": sorted(h3_docs), "dev_docs": sorted(dev_docs),
             "queue_b_source_docs": sorted(qb_docs)}},
    ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'r2_inventory.json'}")
