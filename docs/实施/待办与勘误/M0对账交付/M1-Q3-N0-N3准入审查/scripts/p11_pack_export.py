# -*- coding: utf-8 -*-
"""★ N1.1：★ 把标注包导出为**人工可用的表格 + 审核说明 + 汇总脚本**。

★ 输出（★ 全部进入交付目录 ⇒ 便于人工填写与回填）：
  · `N1_人工标注表.csv`   —— 50 行 × 9 个待标注字段（★ 可直接编辑）
  · `N1_人工标注表.md`    —— 同内容的可读版（含原文上下文）
  · `N1_审核说明.md`      —— 标注规则（★ 含 evidence_insufficient 的用法）
  · `n1_汇总脚本.py`      —— ★ 人工回填后的统计脚本
★ ★ **本阶段不产生任何标签** ⇒ ★ 真实语义标签必须由独立人工提供
"""
import csv
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = ROOT / "guard/_out/n1"
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
DELIV.mkdir(parents=True, exist_ok=True)

packs = [json.loads(l) for l in
         (OUT / "n1_annotation_pack.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()]

FIELDS = ["subject", "action", "object", "strength", "polarity",
          "condition", "exception", "evidence_support", "final_label"]

# ══ CSV ══
with (DELIV / "N1_人工标注表.csv").open("w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["sample_id", "分组", "protocol", "document", "chunk_id",
                "raw_span", "entity", "normative_subject", "action", "object",
                "strength", "polarity", "condition",
                "★原文上下文", "★待标注:subject", "★待标注:action",
                "★待标注:object", "★待标注:strength", "★待标注:polarity",
                "★待标注:condition", "★待标注:exception",
                "★待标注:evidence_support", "★待标注:final_label",
                "审核者", "审核者2", "仲裁", "备注"])
    for p in packs:
        _c = p["★ 原文上下文"]
        _ctx = "\n".join(f"{c['line']}: {c['text']}" for c in _c)
        _f = p["★ 候选字段"]
        w.writerow([
            p["★ sample_id"], p["★ 分组"], p["protocol"], p["document"],
            p["chunk_id"], p["★ 原始位置"]["raw_span"],
            _f["entity"], _f["normative_subject"], _f["action"], _f["object"],
            _f["strength"], _f["polarity"], _f["condition"], _ctx,
            "", "", "", "", "", "", "", "", "", "", "", "", "", ""])

# ══ Markdown ══
md = ["# N1 独立人工语义复核表（★ 50 条）", "",
      "> ★ 请逐条填写「★待标注」各列；★ **允许 `evidence_insufficient`**；",
      "> ★ **不要**参考任何模型判定；★ 本表**不含** L2 结论。", "",
      "**字段说明**：`evidence_support` ∈ {supported, partially_supported, "
      "contradicted, evidence_insufficient}；",
      "`final_label` ∈ {valid_confirmed, valid_rejection, false_rejection, "
      "false_confirmation, pending_insufficient_evidence, uncertain_requires_human}", "",
      "---", ""]
for p in packs:
    md.append(f"## {p['★ sample_id']}　（分组 {p['★ 分组']}｜"
              f"{p['protocol']}/{p['document']}｜chunk {p['chunk_id']}）")
    md.append("")
    md.append(f"**候选字段**：`entity={p['★ 候选字段']['entity']}`　"
              f"`subject={p['★ 候选字段']['normative_subject']}`　"
              f"`action={p['★ 候选字段']['action']}`　"
              f"`object={p['★ 候选字段']['object']}`　"
              f"`strength={p['★ 候选字段']['strength']}`　"
              f"`polarity={p['★ 候选字段']['polarity']}`")
    md.append("")
    md.append("**原文上下文**：")
    md.append("")
    md.append("```")
    for c in p["★ 原文上下文"]:
        md.append(f"{c['line']}: {c['text']}")
    md.append("```")
    md.append("")
    md.append("**候选原始文本**：")
    md.append("")
    md.append("```")
    md.append(f"meaning  : {p['★ 候选原始文本']['meaning']}")
    md.append(f"constraint: {p['★ 候选原始文本']['constraint']}")
    md.append("```")
    md.append("")
    md.append("**待标注**：`subject=` `action=` `object=` `strength=` `polarity=` "
              "`condition=` `exception=` `evidence_support=` `final_label=` "
              "`审核者=` `备注=`")
    md.append("")
    md.append("---")
    md.append("")
(DELIV / "N1_人工标注表.md").write_text("\n".join(md), encoding="utf-8")

# ══ 审核说明 ══
RULES = """# N1 独立人工语义复核 · 审核说明

## 一、这是什么

★ 对 **50 条** RFC 规范抽取候选做**独立人工语义判定**，★ 建立本项目目前**唯一缺失**的
「人工语义质量基线」。

★ ★ **本表不含任何模型判定结论**（★ 已做泄漏检查：0 处）⇒ ★ 请勿参考其他材料推断。

## 二、怎么标

### 2.1 逐字段标注（9 项）

| 字段 | 判定依据 |
|---|---|
| `subject` | ★ 原文中的**义务承担者**；★ 若原文用指代（This field / It），★ 写出**解析后的实际承担者**，★ 并在备注注明是代词 |
| `action` | ★ 原文中的**行为动词**（include / contain / MUST NOT use …） |
| `object` | ★ 原文中的**行为对象**（★ 跨行时写完整） |
| `strength` | ★ MUST / MUST NOT / SHALL / SHOULD / SHOULD NOT / MAY / REQUIRED / RECOMMENDED |
| `polarity` | ★ positive / negative（★ SHOULD NOT ⇒ **negative + strength=SHOULD**） |
| `condition` | ★ 原文中的条件/前提；★ 无则填 `null`；★ ★ **条件不得写成动作** |
| `exception` | ★ 原文中的例外/排除；★ 无则填 `null` |
| `evidence_support` | ★ `supported` / `partially_supported` / `contradicted` / `evidence_insufficient` |
| `final_label` | ★ 见下表 |

### 2.2 `final_label` 取值（★ 单选）

| 取值 | 含义 |
|---|---|
| `valid_confirmed` | ★ 候选的义务**确实存在于原文**，★ 且六个字段都被原文支持 ⇒ **应被确认** |
| `valid_rejection` | ★ 候选**不应被确认**（原文不支持该义务 / 字段与原文不符 / 只是描述性知识） |
| `false_rejection` | ★ 原文**确实支持**该义务，★ 但被拒收 ⇒ **误拒** |
| `false_confirmation` | ★ 被确认，但原文**不支持**该义务 ⇒ **误确认** |
| `pending_insufficient_evidence` | ★ 原文证据不足，★ 无法判定 ⇒ **保持待审** |
| `uncertain_requires_human` | ★ 你本人也无法确定 ⇒ **需要仲裁** |

### 2.3 ★ 允许并鼓励 `evidence_insufficient`

★ **不要被迫做二元判断**。★ 若原文上下文不足以判定字段，写 `evidence_insufficient`，
★ `final_label` 填 `pending_insufficient_evidence`。
★ ★ **这是本轮最重要的质量信号之一**：★ 若大量样本落在 evidence_insufficient，
★ 说明**候选本身缺少必要字段证据**，★ 而不是审核者不努力。

## 三、复核流程

1. ★ 单人首标：★ 逐条填写
2. ★ **高风险样本（分组 K）建议双人独立标注**：★ 第 2 列填入第二审核者，★ **不要互看**
3. ★ 分歧仲裁：★ 两人 `final_label` 不同 ⇒ ★ 填「仲裁」列，★ 写仲裁结论
4. ★ 分歧率会单独统计

## 四、随机样本 vs 风险样本

★ **分组 R（30 条）** = ★ 分层随机抽样 ⇒ ★ 可用于估计总体
★ **分组 K（20 条）** = ★ 风险富集 ⇒ ★ **不可**用于估计总体错误率
★ ⇒ ⇒ **两者必须分开统计**

## 五、回填方式

★ 直接编辑 `N1_人工标注表.csv` 的 ★待标注 列（★ 也可编辑 md 版），
★ 回填后运行：`python n1_汇总脚本.py N1_人工标注表.csv`
★ ⇒ 输出正确确认比例 / false confirmation / false rejection / 六字段支持率 /
★ ★ **指代主体错误率** / **双审一致性与分歧**

## 六、★ 约束

★ ★ 标签必须由**独立人工**提供
★ ★ 不得用另一个 LLM 模拟人工审核
★ ★ 不得用模型辅助结论冒充人工确认
★ ★ 不得为了得到某个结论而调整判定
"""
(DELIV / "N1_审核说明.md").write_text(RULES, encoding="utf-8")

# ══ 汇总脚本 ══
SUM = '''# -*- coding: utf-8 -*-
"""★ N1.3：★ 人工标签回填后的统计（★ **随机样本与风险样本分开**）。"""
import collections
import csv
import json
import pathlib
import sys

FIELDS = ["subject", "action", "object", "strength", "polarity",
          "condition", "exception", "evidence_support", "final_label"]
LABEL_MAP = {
    "valid_confirmed": "confirmed", "valid_rejection": "rejected",
    "false_rejection": "rejected", "false_confirmation": "confirmed",
    "pending_insufficient_evidence": "pending",
    "uncertain_requires_human": "pending",
}


def main(csv_path):
    rows = list(csv.DictReader(pathlib.Path(csv_path).open(encoding="utf-8-sig")))
    out = {}
    for grp in ("R", "K"):
        _rs = [r for r in rows if r["sample_id"].startswith(grp + "-")]
        if not _rs:
            continue
        _lab = [r["★待标注:final_label"].strip() for r in _rs]
        _done = [x for x in _lab if x]
        _c = collections.Counter(_done)
        _ev = collections.Counter(r["★待标注:evidence_support"].strip()
                                  for r in _rs if r["★待标注:evidence_support"].strip())
        _field_sup = {}
        for f in FIELDS[:7]:
            _vals = [r["★待标注:" + f].strip() for r in _rs
                     if r["★待标注:" + f].strip()]
            _field_sup[f] = {
                "filled": len(_vals),
                "★ 非 null/无 的比例": round(
                    sum(1 for v in _vals if v.lower() not in ("null", "none", "无", "-"))
                    / max(1, len(_vals)), 3) if _vals else None,
            }
        # ★ 双审一致性
        _pairs = [r for r in _rs if r["审核者"].strip() and r["审核者2"].strip()]
        _agree = sum(1 for r in _pairs
                     if r["★待标注:final_label"].strip()
                     == r.get("★待标注:final_label_2", "").strip())
        out[grp] = {
            "样本数": len(_rs), "已标注": len(_done),
            "★ 标签分布": dict(_c),
            "★ evidence_support 分布": dict(_ev),
            "★ 正确确认比例（valid_confirmed / 已标注）": round(
                _c.get("valid_confirmed", 0) / max(1, len(_done)), 3),
            "★ false confirmation 比例": round(
                _c.get("false_confirmation", 0) / max(1, len(_done)), 3),
            "★ false rejection 比例": round(
                _c.get("false_rejection", 0) / max(1, len(_done)), 3),
            "★ 证据不足比例": round(
                _c.get("pending_insufficient_evidence", 0) / max(1, len(_done)), 3),
            "★ 六字段支持率": _field_sup,
            "★ 双审样本数": len(_pairs),
            "★ 双审一致率": round(_agree / max(1, len(_pairs)), 3) if _pairs else None,
            "★ 双审分歧样本": [r["sample_id"] for r in _pairs
                          if r["★待标注:final_label"].strip()
                          != r.get("★待标注:final_label_2", "").strip()],
        }
    out["★ 说明"] = ("★ R（随机分层）可用于估计总体；★ K（风险富集）**不可**用于估计总体"
                     "★ ⇒ 两者分开统计")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "N1_人工标注表.csv")
'''
(DELIV / "n1_汇总脚本.py").write_text(SUM, encoding="utf-8")

print(f"  ★ 已导出：")
for _n in ("N1_人工标注表.csv", "N1_人工标注表.md", "N1_审核说明.md", "n1_汇总脚本.py"):
    _p = DELIV / _n
    print(f"      {_n}（{_p.stat().st_size:,} 字节）")
