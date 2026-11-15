# -*- coding: utf-8 -*-
"""★ N1-R：★ 生成**双阶段盲审**标注包（★ A / B 两份独立文件）+ 修订说明。

★ 盲审原则：
  · ★ 人工文件**不含**任何模型状态（L2 verdict / final_state / 旧结论 / Agent 推荐）
  · ★ A 与 B 得到**同一批样本**但**各自独立**的文件（★ 含完整标签列，★ 非仅姓名列）
  · ★ 模型状态**单独**放在 `n1r_model_state.jsonl`（★ 汇总阶段才读取）
"""
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "guard/_out/n1r"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
DELIV.mkdir(parents=True, exist_ok=True)

packs = [json.loads(l) for l in
         (OUT / "n1r_restored_packs.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()]

# ★ 人工需填写的标签列（★ 每位审核者一份完整列）
LABEL_COLS = [
    ("subject", "义务承担者（★ 指代须写出解析后的实际承担者）"),
    ("action", "行为动词"),
    ("object", "行为对象（★ 跨行须完整）"),
    ("strength", "MUST/MUST NOT/SHALL/SHOULD/SHOULD NOT/MAY/REQUIRED/…"),
    ("polarity", "positive / negative"),
    ("condition", "★ 原文中的条件（★ 无则填 null；★ **不得**填整条 constraint）"),
    ("exception", "★ 原文中的例外（★ 无则填 null）"),
    ("evidence_support", "supported / partially_supported / contradicted / evidence_insufficient"),
    ("final_label", "valid_confirmed / valid_rejection / false_rejection / "
              "false_confirmation / pending_insufficient_evidence / uncertain_requires_human"),
]

HEAD = [
    "sample_id", "分组", "protocol", "document", "rfc_sha256",
    "chunk_id", "chunk_start", "chunk_end_estimate", "chunk_hash",
    "★ 原始 source_span", "★ 绝对锚点行", "★ 与 chunk 关系",
    "★ entity（LLM 候选）", "★ normative_subject（LLM 候选）",
    "★ action（LLM 候选）", "★ object（LLM 候选）", "★ strength（LLM 候选）",
    "★ polarity（LLM 候选，★ 原始无此字段）", "★ condition（LLM 候选，★ 原始无此字段）",
    "★ exception（LLM 候选，★ 原始无此字段）",
    "★ LLM meaning（★ 生成文本，★ 非 RFC 原文）",
    "★ LLM constraint（★ 生成文本，★ 非 RFC 原文）",
    "★ 推导 polarity（★ 供核对）", "★ 锚点行原文（RFC 原文）",
    "★ RFC 原文上下文（锚点 ±6 行）", "★ 原始 evidence_context（绝对行号原文）",
]
# ★ 审核者 A 的标签列
HEAD_A = HEAD + [f"★ A:{c}" for c, _ in LABEL_COLS] + \
    ["★ A:审核者", "★ A:备注"]
HEAD_B = HEAD + [f"★ B:{c}" for c, _ in LABEL_COLS] + \
    ["★ B:审核者", "★ B:备注"]


def _g(p, *keys):
    """★ 容错取键（★ 键名带不同后缀说明 ⇒ 统一兼容）。"""
    for k in keys:
        if k in p:
            return p[k]
    for k in p:
        if any(x in k for x in keys):
            return p[k]
    return ""


def _norm(s):
    """★ 字段内换行转标记（★ 避免 CSV 混合行尾）★ + 统一 LF。"""
    return str(s or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ⏎ ")


def _row(p, tag):
    _ctx = " ⏎ ".join(f"{c['line']}: {_norm(c['text'])}"
                      for c in _g(p, "RFC 原文上下文"))
    _ectx = " ⏎ ".join(f"{c['line']}: {_norm(c['text'])}"
                       for c in _g(p, "原始 evidence_context"))
    _f = p["★ LLM 原始候选字段"]
    _base = [
        p["sample_id"], p["分组"], p["protocol"], p["document"], p["rfc_sha256"],
        p["chunk_id"], p["chunk_start"], p["chunk_end_estimate"], p["chunk_hash"],
        _g(p, "原始 source_span"), _g(p, "绝对锚点行"),
        _g(p, "与 chunk 关系"),
        _f["entity"], _f["normative_subject"], _f["action"], _f["object"],
        _f["strength"], _f["polarity"] or "", _f["condition"] or "", _f["exception"] or "",
        _g(p, "LLM 原始 meaning"), _g(p, "LLM 原始 constraint"),
        _g(p, "推导 polarity"), _g(p, "锚点行原文"),
        _ctx, _ectx,
    ]
    if tag == "A":
        _base = [_norm(_v) if isinstance(_v, str) else _v for _v in _base]
    return _base + [""] * len(LABEL_COLS) + ["", ""]


for _tag, _head, _name in (("A", HEAD_A, "N1_盲审标注表_A.csv"),
                           ("B", HEAD_B, "N1_盲审标注表_B.csv")):
    with (DELIV / _name).open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(_head)
        for p in packs:
            w.writerow(_row(p, _tag))
    print(f"  ★ {_name}：{len(packs)} 行 × {len(_head)} 列")

# ★ 仲裁表（★ 两阶段后使用）
with (DELIV / "N1_仲裁表.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f, lineterminator="\n")
    w.writerow(["sample_id", "分组", "★ A:final_label", "★ B:final_label",
                "★ 是否分歧", "★ 仲裁结论", "★ 仲裁者", "★ 仲裁理由"])
    for p in packs:
        w.writerow([p["sample_id"], p["分组"], "", "", "", "", "", ""])

# ★ ★ 模型状态**单独**存放（★ 汇总阶段才读取 ⇒ ★ 盲审阶段不可见）
_model = []
for p in packs:
    _model.append({"sample_id": p["sample_id"], "分组": p["分组"],
                    "★ 模型状态（★ 盲审阶段不可见）": None})
(OUT / "n1r_model_state.jsonl").write_text(
    "\n".join(json.dumps(m, ensure_ascii=False) for m in _model) + "\n",
    encoding="utf-8")

# ★ Markdown（★ 含完整证据，★ 供人阅读）
md = ["# N1-R 人工盲审标注表（★ 50 条 · 修订版）", "",
      "> ★ 本表**不含**任何模型状态；★ A / B 各自独立填写；",
      "> ★ 字段含义见 `N1_审核说明.md`。", "", "---", ""]
for p in packs:
    _f = p["★ LLM 原始候选字段"]
    md.append(f"## {p['sample_id']}　（分组 {p['分组']}）")
    md.append("")
    md.append(f"**来源**：`{p['protocol']}/{p['document']}`｜RFC SHA256 `{p['rfc_sha256'][:16]}…`")
    md.append(f"**位置**：chunk `{p['chunk_id']}`（行 {p['chunk_start']}~{p['chunk_end_estimate']}）"
              f"｜原始 source_span **{p['★ 原始 source_span（★ 绝对行号）']}**"
              f"｜绝对锚点行 **{p['★ 绝对锚点行（= 原始 span，★ 绝对行号）']}**")
    md.append(f"**与 chunk 关系**：{p['★ 与 chunk 关系']}")
    md.append("")
    md.append("**LLM 原始候选字段**（★ 生成内容，★ 非 RFC 原文）："
              f"`entity={_f['entity']}` `subject={_f['normative_subject']}` "
              f"`action={_f['action']}` `object={_f['object']}` "
              f"`strength={_f['strength']}`")
    md.append("")
    md.append(f"**LLM meaning**（★ 非原文）：`{p['★ LLM 原始 meaning（★ 生成文本，★ 非 RFC 原文）']}`")
    md.append("")
    md.append(f"**LLM constraint**（★ 非原文）：`{p['★ LLM 原始 constraint（★ 生成文本，★ 非 RFC 原文）']}`")
    md.append("")
    md.append(f"**推导 polarity**（★ 供核对）：{p['★ 推导 polarity（★ 供人工核对）']}"
              f"（{p['★ polarity 来源']}）")
    md.append("")
    md.append("**锚点行原文（RFC 原文）**：")
    md.append("")
    md.append("```")
    md.append(_g(p, "锚点行原文"))
    md.append("```")
    md.append("")
    md.append("**RFC 原文上下文（锚点 ±6 行）**：")
    md.append("")
    md.append("```")
    for c in p["★ RFC 原文上下文（锚点 ±6 行）"]:
        md.append(f"{c['line']}: {c['text']}")
    md.append("```")
    md.append("")
    md.append("**原始 evidence_context（绝对行号原文）**：")
    md.append("")
    md.append("```")
    for c in p["★ 原始 evidence_context（绝对行号原文）"]:
        md.append(f"{c['line']}: {c['text']}")
    md.append("```")
    md.append("")
    md.append("**待标注**：" + "　".join(f"`{c}=`" for c, _ in LABEL_COLS))
    md.append("")
    md.append("---")
    md.append("")
(DELIV / "N1_盲审标注表.md").write_text("\n".join(md), encoding="utf-8")
print(f"  ★ N1_盲审标注表.md：{len(packs)} 条")
print(f"  ★ N1_仲裁表.csv：{len(packs)} 行")
print(f"  ★ 模型状态单独存放（★ 盲审阶段不可见）：guard/_out/n1r/n1r_model_state.jsonl")
