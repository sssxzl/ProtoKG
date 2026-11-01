# -*- coding: utf-8 -*-
"""scripts/calc_cohen_kappa.py —— 两名标注者的 **Cohen's κ + 分歧率**计算。

为什么需要它
------------
roadmap §4.6 第 3 条把「双人独立标注 → 计算 Cohen's κ → κ < 0.6 则重标并修订
标注指南 → 分歧由第三人仲裁」定为**硬流程**，且 §4.7 明确要求「κ 与分歧率入报告」
（评审 R12）。没有 κ 就没有「这份标注集靠得住」这个结论。

★ **本脚本只算数，不改标注。**
  若某协议 κ < 0.6，脚本**只报告、不修正** —— 是否重标、是否修订指南，
  由项目负责人裁决（roadmap §4.6 第 3 条）。这一点是刻意的：
  「为了让 κ 好看而调整标注」正是这份标注集最需要防的失败模式。

四个字段分别算 κ（不是一个合并 κ）
----------------------------------
κ 是**逐字段**算的：``has_normative_requirement`` / ``modality`` / ``operator`` /
``expected_response_class``。理由：四个字段的难度差异极大
（``has_normative_requirement`` 是二分类、几乎无歧义；``operator`` 十一分类、
大量条目都是「不可」、但边界最 fuzzy）。合并成一个 κ 会把「某个字段一致」
掩盖成「整体一致」，掩盖掉真正需要修订指南的那个字段。

另外单独报一个**整条一致率**（四个字段全同）与 **分歧明细**
（列出每条分歧的字段与双方取值），供仲裁使用。

κ 的定义（名义变量，2 标注者）
------------------------------
    po = 两标注者实际一致的比例
    pe = 偶然一致的比例 = Σ_k (A_k/N) · (B_k/N)
    κ  = (po - pe) / (1 - pe)

    ★ **退化情形**：若两标注者都只用了**同一个**类别（pe == 1），
      κ 的分母为 0，数学上未定义。此时：
        · 若 po == 1（完全一致）⇒ 记 κ = 1.0（约定值，并在报告中注明）
        · 否则 ⇒ 记 κ = 0.0（最大分歧），并注明「类别分布退化，κ 不可靠」
      这不是「算不出来」，而是「一致率没有信息量」—— 必须显式报出来，
      不能悄悄返回一个好看的数字。

用法
----
    python scripts/calc_cohen_kappa.py --a A.json --b B.json
    python scripts/calc_cohen_kappa.py --a A.json --b B.json --show-disagreements
    python scripts/calc_cohen_kappa.py --a A.json --b B.json --json

退出码
------
    ``0`` —— 计算完成（**无论 κ 高低**）
    ``1`` —— 用法/输入错误
    ★ 刻意**不因 κ 低而返回非 0**：κ 低是需要**报告**的事实，不是脚本错误。
      若要接 CI 闸，用 ``--fail-below`` 显式开启。
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

#: 参与 κ 计算的四个字段。
FIELDS: tuple[str, ...] = (
    "has_normative_requirement", "modality", "operator", "expected_response_class",
)

#: roadmap §4.6 第 3 条的阈值：κ < 0.6 ⇒ 重标并修订指南。
KAPPA_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# 输入
# ---------------------------------------------------------------------------
def load_annotations(path: Path) -> dict[str, dict]:
    """读标注文件 ⇒ ``{candidate_id: record}``。"""
    if not path.is_file():
        raise FileNotFoundError(f"标注文件不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("annotations") or data.get("items") or []
    if not isinstance(data, list):
        raise ValueError(f"{path} 顶层必须是数组或含 annotations 数组的对象")
    out: dict[str, dict] = {}
    for i, rec in enumerate(data):
        if not isinstance(rec, dict):
            raise ValueError(f"{path} 第 {i + 1} 条不是对象")
        cid = rec.get("candidate_id")
        if not isinstance(cid, str):
            raise ValueError(f"{path} 第 {i + 1} 条缺 candidate_id")
        out[cid] = rec
    return out


def _key(value: Any) -> str:
    """把字段值转成可比较的字符串键（``None`` → ``"<null>"``）。"""
    if value is None:
        return "<null>"
    if value is True:
        return "True"
    if value is False:
        return "False"
    return str(value)


# ---------------------------------------------------------------------------
# κ
# ---------------------------------------------------------------------------
def cohen_kappa(labels_a: list[str], labels_b: list[str]) -> dict:
    """计算 Cohen's κ。

    返回：``{"kappa": float|None, "po": float, "pe": float, "n": int,
    "degenerate": bool, "note": str}``
    """
    n = len(labels_a)
    if n == 0:
        return {"kappa": None, "po": 0.0, "pe": 0.0, "n": 0,
                "degenerate": True, "note": "空样本"}
    if len(labels_b) != n:
        raise ValueError("两份标注长度不同")

    agree = sum(1 for x, y in zip(labels_a, labels_b) if x == y)
    po = agree / n
    ca, cb = Counter(labels_a), Counter(labels_b)
    pe = sum((ca[k] / n) * (cb.get(k, 0) / n) for k in ca)

    if abs(1.0 - pe) < 1e-12:
        # 类别分布退化：双方都只用了一个类别 ⇒ κ 无定义
        degenerate = True
        if po >= 1.0:
            kappa, note = 1.0, "双方类别分布退化（pe=1），完全一致 ⇒ κ 约定为 1.0"
        else:
            kappa, note = 0.0, "双方类别分布退化（pe=1），κ 无定义 ⇒ 约定为 0.0（一致率无信息量）"
    else:
        degenerate = False
        kappa = (po - pe) / (1.0 - pe)
        note = ""
    return {"kappa": kappa, "po": po, "pe": pe, "n": n,
            "degenerate": degenerate, "note": note}


def compare(ann_a: dict[str, dict], ann_b: dict[str, dict],
            only_common: bool = True) -> dict:
    """比较两份标注。

    ``only_common=True``（默认）：只在**双方都标注了**的 candidate_id 上计算
    —— 这是 κ 的正确口径（比较的是同一批题上的两份答卷）。
    """
    common = sorted(set(ann_a) & set(ann_b))
    only_a = sorted(set(ann_a) - set(ann_b))
    only_b = sorted(set(ann_b) - set(ann_a))
    if only_common:
        ids = common
    else:
        ids = sorted(set(ann_a) | set(ann_b))

    per_field: dict[str, dict] = {}
    for field in FIELDS:
        la = [_key(ann_a[i].get(field)) for i in ids if i in ann_a]
        lb = [_key(ann_b[i].get(field)) for i in ids if i in ann_b]
        per_field[field] = cohen_kappa(la, lb)

    # 整条一致率（四字段全同）
    both = [i for i in ids if i in ann_a and i in ann_b]
    full_agree = sum(
        1 for i in both
        if all(_key(ann_a[i].get(f)) == _key(ann_b[i].get(f)) for f in FIELDS))
    exact = {
        "n": len(both),
        "agree": full_agree,
        "rate": (full_agree / len(both)) if both else 0.0,
    }

    # 分歧明细
    disagreements: list[dict] = []
    for i in both:
        diffs = []
        for f in FIELDS:
            va, vb = ann_a[i].get(f), ann_b[i].get(f)
            if _key(va) != _key(vb):
                diffs.append({"field": f, "a": va, "b": vb})
        if diffs:
            disagreements.append({
                "candidate_id": i,
                "protocol": ann_a[i].get("protocol") or ann_b[i].get("protocol"),
                "text": ann_a[i].get("text") or ann_b[i].get("text"),
                "diff_fields": [d["field"] for d in diffs],
                "diffs": diffs,
                "a_uncertain": ann_a[i].get("uncertain") is True,
                "b_uncertain": ann_b[i].get("uncertain") is True,
            })

    return {
        "n_common": len(common),
        "n_only_a": len(only_a),
        "n_only_b": len(only_b),
        "only_a_ids": only_a,
        "only_b_ids": only_b,
        "per_field": per_field,
        "exact": exact,
        "disagreements": disagreements,
        "disagreement_rate": 1.0 - exact["rate"],
    }


# ---------------------------------------------------------------------------
# 报告
# ---------------------------------------------------------------------------
def _fmt(v: Optional[float]) -> str:
    return "n/a" if v is None else f"{v:.3f}"


def render_report(result: dict, a_name: str, b_name: str,
                  show_disagreements: bool = False) -> str:
    lines: list[str] = []
    lines.append("=" * 74)
    lines.append(f"Cohen's κ —— 标注者 {a_name} vs {b_name}")
    lines.append("=" * 74)
    lines.append(f"共同标注条目: {result['n_common']}"
                 f"   (仅 A 有: {result['n_only_a']}, 仅 B 有: {result['n_only_b']})")
    lines.append("")
    lines.append(f"{'字段':<32}{'κ':>9}{'一致率po':>11}{'偶然pe':>9}{'n':>7}")
    lines.append("-" * 74)
    for field, st in result["per_field"].items():
        flag = "  ⚠退化" if st["degenerate"] else ""
        lines.append(f"{field:<32}{_fmt(st['kappa']):>9}{st['po']:>11.3f}"
                     f"{st['pe']:>9.3f}{st['n']:>7}{flag}")
        if st["note"]:
            lines.append(f"    └ {st['note']}")
    lines.append("-" * 74)
    ex = result["exact"]
    lines.append(f"{'整条一致（四字段全同）':<30}{ex['rate']:>11.3f}"
                 f"   ({ex['agree']}/{ex['n']})")
    lines.append(f"{'整条分歧率':<32}{result['disagreement_rate']:>9.3f}")
    lines.append("")

    # 阈值判定（只报告，不修改）
    below = [(f, st["kappa"]) for f, st in result["per_field"].items()
             if st["kappa"] is not None and st["kappa"] < KAPPA_THRESHOLD]
    lines.append(f"阈值判定（roadmap §4.6 第 3 条，κ < {KAPPA_THRESHOLD} ⇒ 重标并修订指南）:")
    if below:
        for f, k in below:
            lines.append(f"  ⚠ {f}: κ = {k:.3f} < {KAPPA_THRESHOLD} —— **需上报负责人裁决**")
    else:
        lines.append(f"  ✓ 全部字段 κ ≥ {KAPPA_THRESHOLD}")
    lines.append("")

    if result["disagreements"]:
        lines.append(f"分歧条目: {len(result['disagreements'])} 条"
                     f"（占共同条目 {len(result['disagreements']) / max(1, result['n_common']):.1%}）")
    else:
        lines.append("分歧条目: 0 条")

    if show_disagreements and result["disagreements"]:
        lines.append("")
        lines.append("-" * 74)
        lines.append("分歧明细（供第三人仲裁）")
        lines.append("-" * 74)
        for d in result["disagreements"]:
            lines.append(f"[{d['candidate_id']}] ({d.get('protocol')}) "
                         f"{str(d.get('text'))[:64]}")
            for df in d["diffs"]:
                lines.append(f"    {df['field']}: A={df['a']!r}  B={df['b']!r}")
            if d["a_uncertain"] or d["b_uncertain"]:
                lines.append(f"    (uncertain: A={d['a_uncertain']} B={d['b_uncertain']})")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="计算两名标注者的 Cohen's κ 与分歧率")
    ap.add_argument("--a", required=True, help="标注者 A 的标注文件")
    ap.add_argument("--b", required=True, help="标注者 B 的标注文件")
    ap.add_argument("--name-a", default="A", help="标注者 A 的名字（报告用）")
    ap.add_argument("--name-b", default="B", help="标注者 B 的名字（报告用）")
    ap.add_argument("--show-disagreements", action="store_true", help="打印分歧明细")
    ap.add_argument("--json", action="store_true", help="输出 JSON（机器可读）")
    ap.add_argument("--fail-below", type=float, default=None,
                    help=f"若任一字段 κ 低于此值则退出码 1（默认不启用；"
                         f"roadmap 阈值 {KAPPA_THRESHOLD}）")
    args = ap.parse_args(argv)

    try:
        ann_a = load_annotations(Path(args.a))
        ann_b = load_annotations(Path(args.b))
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"[ERR] {exc}", file=sys.stderr)
        return 1

    result = compare(ann_a, ann_b)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(render_report(result, args.name_a, args.name_b, args.show_disagreements))

    if args.fail_below is not None:
        below = [f for f, st in result["per_field"].items()
                 if st["kappa"] is not None and st["kappa"] < args.fail_below]
        if below:
            print(f"\n[FAIL] 字段 κ 低于 {args.fail_below}: {below}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
