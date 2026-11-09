#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成 M2 真人标注工作包（117 条待标）。

★ 产出三件东西（都在 `local/annotation_workpack/`）：
  ① `标注工作包.md`     —— 给人的**逐条工作单**（题面 + 溯源 + 填写指引）
  ② `待标注模板.json`   —— 可直接填的 JSON（字段与 truth 完全一致 ⇒ 填完即用）
  ③ `标注进度表.md`     —— 勾选式进度表（便于分批推进 + 交接）

★ 设计原则：
  · **题面只给候选句本身**（与 holdout 口径一致：标注者只看 text，不看 RFC 上下文）
  · **溯源信息单独给**（section_path / source / spec_version）—— 便于复核，但不参与判定
  · **不泄漏答案**：本脚本**不输出**任何规则/模型产出 ⇒ 标注不受实现影响
  · 与既有校验器对齐：填完用 ``scripts/annotate_candidates.py validate`` 直接校验

用法：
    E:/app/Anaconda3/python.exe scripts/gen_annotation_workpack.py
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TRUTH_DIR = ROOT / "derived" / "exp_semantic" / "truth"
FROZEN = ROOT / "derived" / "exp_semantic" / "candidates_frozen.jsonl"
OUT_DIR = ROOT / "local" / "annotation_workpack"

PROTOCOL_LABEL = {"rtsp": "RTSP（RFC 2326）", "sip": "SIP（RFC 3261）",
                  "smtp": "SMTP（RFC 5321/5322）"}

#: 判定选项（与 ``docs/工具/人工标注指南.md`` §2~§5 一致）。
OPTIONS = {
    "has_normative_requirement": "是 / 否（这条候选句本身是否含规范性约束）",
    "modality": "MUST / SHOULD / MAY / 无",
    "operator": "eq / ne / lt / gt / le / ge / in / present / absent / range / 不可",
    "expected_response_class": "success / protocol_error / application_error / silence / null",
}


def _load_truth() -> list[dict]:
    rows: list[dict] = []
    for f in sorted(TRUTH_DIR.glob("*.json")):
        for item in json.loads(f.read_text(encoding="utf-8")):
            item["_src_file"] = f.name
            rows.append(item)
    return rows


def _load_frozen() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in FROZEN.read_text(encoding="utf-8").splitlines():
        if line.strip():
            c = json.loads(line)
            out[c["candidate_id"]] = c
    return out


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    truth = _load_truth()
    frozen = _load_frozen()
    pending = [t for t in truth if t.get("pending") is True]

    # ── ① 可填模板（字段与 truth 一致 + _answer 槽位）────────────────
    template = []
    for t in pending:
        template.append({
            "candidate_id": t["candidate_id"],
            "protocol": t["protocol"],
            "text": t["text"],
            "has_normative_requirement": None,
            "modality": None,
            "operator": None,
            "expected_response_class": None,
            "uncertain": None,
            "uncertain_reason": None,
            "annotator": None,
        })

    # ── ② 工作单 Markdown ──────────────────────────────────────────
    md: list[str] = []
    md.append("# M2 人工标注工作包（117 条待标）\n")
    md.append("> 生成脚本：`scripts/gen_annotation_workpack.py`（可重复运行，内容确定）\n")
    md.append("> 标注规范：**`docs/工具/人工标注指南.md`**（判定标准、边界规则、正反例）\n")
    md.append("> ⚠️ **标注前请完整读一遍指南**，尤其 §2.3 / §3.3 / §4.3 / §5.4 的边界规则。\n")
    md.append("\n---\n")
    md.append("\n## 一、怎么用这份工作包\n")
    md.append("\n### 1.1 标注流程\n")
    md.append("\n1. 读 `docs/工具/人工标注指南.md`（判定标准 + 边界规则）。\n")
    md.append("2. 打开 `待标注模板.json`，逐条填写 4 个判定字段（见 §1.2）。\n")
    md.append("3. 填完后回填到 `derived/exp_semantic/truth/<协议>.{annotated,holdout}.json`：\n")
    md.append("   保持条目顺序与 `candidate_id` 不变，把 `pending` 改为 `false`、"
              "`annotator` 填你的代号。\n")
    md.append("4. 校验：`E:/app/Anaconda3/python.exe scripts/annotate_candidates.py validate "
              "--annotations <你填的文件> --include <对应的 holdout 文件>`\n")
    md.append("5. 全部标完后算 κ（需**第二名**独立标注者 B 的文件）：\n")
    md.append("   `E:/app/Anaconda3/python.exe scripts/calc_cohen_kappa.py --a <A 的文件> "
              "--b <B 的文件> --show-disagreements`\n")
    md.append("\n### 1.2 每条要填的 4 个字段\n")
    for k, v in OPTIONS.items():
        md.append(f"\n- **`{k}`** —— {v}\n")
    md.append("\n另有两个可选字段：\n")
    md.append("\n- **`uncertain`** —— 拿不准填 `true`（布尔）\n")
    md.append("- **`uncertain_reason`** —— 拿不准的原因（如「响应类别不可判定」）\n")
    md.append("\n### 1.3 三条最容易出错的地方（指南原文摘要）\n")
    md.append("\n1. **只看候选句本身**。原文没写规范性动词 ⇒ `has_normative_requirement = 否`。"
              "不要凭「这看起来像条约束」来判。\n")
    md.append("2. **不要从协议常识倒推**。特别是 `expected_response_class`："
              "原文没说违反后会怎样，就填 `null`。\n")
    md.append("3. **拿不准就标 `uncertain = true`**，不要硬猜。"
              "不确定的条目进入仲裁清单，是资产不是负担。\n")
    md.append("\n---\n")

    by_proto: dict[str, list[dict]] = {}
    for t in pending:
        by_proto.setdefault(t["protocol"], []).append(t)

    md.append("\n## 二、逐条工作单\n")
    idx = 0
    for proto in ("rtsp", "sip", "smtp"):
        items = by_proto.get(proto, [])
        if not items:
            continue
        md.append(f"\n### {PROTOCOL_LABEL.get(proto, proto)}（{len(items)} 条）\n")
        for t in items:
            idx += 1
            fz = frozen.get(t["candidate_id"], {})
            md.append(f"\n#### [{idx}] `{t['candidate_id']}`\n")
            md.append(f"\n**题面（只依据这段文本判定）**：\n")
            md.append(f"\n```\n{t['text'].strip()}\n```\n")
            # 溯源（供复核，不参与判定）
            src_bits = []
            if fz.get("section_path"):
                src_bits.append("章节：" + " > ".join(str(x) for x in fz["section_path"]))
            if fz.get("source"):
                src_bits.append(f"来源：`{fz['source']}`")
            if fz.get("spec_version"):
                src_bits.append(f"规范：{fz['spec_version']}")
            if src_bits:
                md.append(f"\n溯源（**仅供定位核对，不作为判定依据**）：{'　'.join(src_bits)}\n")
            md.append(f"\n**填写**：`has_normative_requirement` = ___　"
                      f"`modality` = ___　`operator` = ___　"
                      f"`expected_response_class` = ___\n")

    (OUT_DIR / "标注工作包.md").write_text("\n".join(md), encoding="utf-8")

    # ── ③ 可填模板 JSON ────────────────────────────────────────────
    (OUT_DIR / "待标注模板.json").write_text(
        json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ── ④ 进度表 ──────────────────────────────────────────────────
    prog: list[str] = ["# M2 标注进度表\n",
                       "\n> 勾选式进度追踪（分批推进时更新）。\n",
                       "\n| # | candidate_id | 协议 | 切分 | 已标 | 标注者 | 备注 |",
                       "|---:|---|---|---|:-:|---|---|"]
    idx = 0
    for t in pending:
        idx += 1
        split = "holdout" if "holdout" in t["_src_file"] else "train"
        prog.append(f"| {idx} | `{t['candidate_id']}` | {t['protocol']} | {split} "
                    f"| ☐ | | |")
    prog.append(f"\n**合计 {idx} 条**（已标 3 条沿用旧轮，见 `docs/工具/人工标注现状.md` §0.3）\n")
    (OUT_DIR / "标注进度表.md").write_text("\n".join(prog), encoding="utf-8")

    # ── 汇总 ────────────────────────────────────────────────────────
    print(f"✔ 工作包已生成 → {OUT_DIR}")
    print(f"  待标条目 = {len(pending)}")
    for proto in ("rtsp", "sip", "smtp"):
        print(f"    {proto:5s} {len(by_proto.get(proto, [])):3d} 条")
    print(f"  产出：标注工作包.md / 待标注模板.json / 标注进度表.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
