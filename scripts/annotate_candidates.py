# -*- coding: utf-8 -*-
"""scripts/annotate_candidates.py —— B 阶段人工标注集的**文件式标注工具 + 校验器**。

为什么是「文件式」而不是交互式
------------------------------
双人独立标注（roadmap §4.6 第 3 条）要求两名标注者**互不可见对方的标注**。
交互式终端天然做不到这一点（一个人得看着另一个人的屏幕/文件）。
文件式把「看题」和「答题」彻底分开：

    ① template  —— 从冻结候选生成**空白标注模板**（每人一份，互不可见）
    ② fill     —— 标注者在模板里填 4 个字段（人工做，本脚本不代劳）
    ③ validate —— 本脚本读回填好的文件并**逐条校验**（枚举合法性 + 交叉一致性）
    ④ kappa    —— 见 scripts/calc_cohen_kappa.py（两份文件 → Cohen's κ + 分歧率）

四个标注字段（roadmap §4.6 第 2 条）
------------------------------------
    ① has_normative_requirement : bool     该句是否含规范性要求
    ② modality                  : str      MUST / SHOULD / MAY / 无
    ③ operator                  : str      eq/ne/lt/gt/le/ge/in/present/absent/range / "不可"
    ④ expected_response_class   : str|null success/protocol_error/application_error/silence / null

★ 判定标准全部写在 ``docs/annotation_guide.md``。本脚本**只做机械校验**，
  **不做任何语义判断**、**不代填答案** —— 语义判断只能由人（或明确署名的模型轮次）做。

校验规则（validate）
--------------------
    R1 四字段齐全（缺一即报错）
    R2 modality ∈ {MUST, SHOULD, MAY, 无}
    R3 has_normative_requirement ∈ {True, False}（且必须是真正的 bool，不接受 "true"/1）
    R4 operator 非「不可」时必须属于 OPERATORS 词表
        （eq/ne/lt/gt/le/ge/in/present/absent/range）
    R5 expected_response_class 非空时必须 ∈ {success, protocol_error, application_error, silence}
    R6 交叉一致性：has_normative_requirement=False ⇒ modality 必为「无」
    R7 交叉一致性：has_normative_requirement=False ⇒ operator 必为「不可」
    R8 uncertain=True 时必须给 uncertain_reason（非空字符串）
    R9 candidate_id 必须存在于冻结集，且不得重复、不得缺漏
    R10 annotator 字段非空（保证「谁标的」可追溯 —— κ 计算与仲裁都要用）

用法
----
    python scripts/annotate_candidates.py template --out-dir derived/exp_semantic/truth \\
        --annotator A
    python scripts/annotate_candidates.py validate --annotations derived/exp_semantic/truth/rtsp.annotated.json
    python scripts/annotate_candidates.py template --out-dir /tmp/truth --annotator B --protocol rtsp

退出码
------
    ``0`` —— 全部通过；``1`` —— 校验失败（逐条列出问题）；``2`` —— 用法/环境错误
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

#: 可执行算子全集。**与 docs/rfc_source_bcd_roadmap.md §3.1 的 OPERATORS 逐项相等**
#: （新增算子必须同步改 core/fused/semantic.py 的 OPERATORS）。
OPERATORS: frozenset[str] = frozenset({
    "eq", "ne", "lt", "gt", "le", "ge", "in", "present", "absent", "range",
})

#: 规范性强度取值（含「无」）。
MODALITIES: frozenset[str] = frozenset({"MUST", "SHOULD", "MAY", "无"})

#: 期望响应类别（与 rfc_config.expected_response_classes 同集合）。
RESPONSE_CLASSES: frozenset[str] = frozenset({
    "success", "protocol_error", "application_error", "silence",
})

#: 「不可执行」的算子取值（指南要求填字符串 "不可"，不填 null）。
NOT_EXECUTABLE = "不可"

#: 标注记录必填字段。
REQUIRED_FIELDS: tuple[str, ...] = (
    "candidate_id", "has_normative_requirement", "modality",
    "operator", "expected_response_class", "annotator",
)

DEFAULT_FROZEN = Path("derived/exp_semantic/candidates_frozen.jsonl")
DEFAULT_GUIDE = Path("docs/annotation_guide.md")


# ---------------------------------------------------------------------------
# 读入
# ---------------------------------------------------------------------------
def load_frozen(path: Path) -> list[dict]:
    """读冻结候选集（jsonl）。"""
    if not path.is_file():
        raise FileNotFoundError(f"冻结候选集不存在: {path}")
    rows: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno} 不是合法 JSON: {exc}") from exc
    return rows


def load_annotations(path: Path) -> list[dict]:
    """读标注文件。接受两种形态：JSON 数组，或 ``{"annotations": [...]}`` 对象。"""
    if not path.is_file():
        raise FileNotFoundError(f"标注文件不存在: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("annotations") or data.get("items") or []
    if not isinstance(data, list):
        raise ValueError(f"{path} 顶层必须是数组或含 annotations 数组的对象")
    return data


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------
def validate_one(rec: dict, known_ids: set[str]) -> list[str]:
    """校验单条标注，返回问题列表（空 = 通过）。"""
    problems: list[str] = []
    cid = rec.get("candidate_id")

    # R1 字段齐全
    for field in REQUIRED_FIELDS:
        if field not in rec:
            problems.append(f"缺字段 `{field}`")
    if problems:
        return problems

    # R9 id 合法 + 不重复（重复由调用方检查）
    if not isinstance(cid, str) or cid not in known_ids:
        problems.append(f"candidate_id 未知: {cid!r}")

    # R3 has_normative_requirement 必须是真 bool
    hnr = rec["has_normative_requirement"]
    if not isinstance(hnr, bool):
        problems.append(
            f"has_normative_requirement 必须是 bool，实际是 {type(hnr).__name__} ({hnr!r})")

    # R2 modality
    modality = rec["modality"]
    if modality not in MODALITIES:
        problems.append(f"modality 非法: {modality!r}（允许: {sorted(MODALITIES)}）")

    # R4 operator
    operator = rec["operator"]
    if operator != NOT_EXECUTABLE and operator not in OPERATORS:
        problems.append(
            f"operator 非法: {operator!r}（必须是 {NOT_EXECUTABLE!r} 或 OPERATORS 之一）")

    # R5 expected_response_class
    erc = rec["expected_response_class"]
    if erc is not None and erc not in RESPONSE_CLASSES:
        problems.append(
            f"expected_response_class 非法: {erc!r}（允许 null 或 {sorted(RESPONSE_CLASSES)}）")

    # R10 annotator
    annotator = rec["annotator"]
    if not isinstance(annotator, str) or not annotator.strip():
        problems.append("annotator 必须是非空字符串")

    # R8 uncertain 需配 reason
    if rec.get("uncertain") is True:
        reason = rec.get("uncertain_reason")
        if not isinstance(reason, str) or not reason.strip():
            problems.append("uncertain=True 时必须给非空 uncertain_reason")

    # R6 / R7 交叉一致性
    if hnr is False:
        if modality != "无":
            problems.append(
                f"交叉不一致: has_normative_requirement=False 时 modality 必须是「无」，实际 {modality!r}")
        if operator != NOT_EXECUTABLE:
            problems.append(
                f"交叉不一致: has_normative_requirement=False 时 operator 必须是「不可」，实际 {operator!r}")

    return problems


def validate_all(annotations: list[dict], frozen: list[dict],
                 require_complete: bool = True) -> list[str]:
    """校验整份标注文件，返回问题列表（空 = 全部通过）。"""
    known_ids = {r["candidate_id"] for r in frozen}
    problems: list[str] = []

    seen: Counter = Counter()
    for i, rec in enumerate(annotations):
        if not isinstance(rec, dict):
            problems.append(f"第 {i + 1} 条不是对象")
            continue
        cid = rec.get("candidate_id", f"<第{i + 1}条>")
        for p in validate_one(rec, known_ids):
            problems.append(f"{cid}: {p}")
        seen[cid] += 1

    # R9 重复
    for cid, n in seen.items():
        if n > 1:
            problems.append(f"{cid}: candidate_id 重复 {n} 次")

    # R9 缺漏
    if require_complete:
        missing = sorted(known_ids - set(seen))
        if missing:
            problems.append(
                f"缺漏 {len(missing)} 条未标注（如 {missing[:3]}）")

    return problems


# ---------------------------------------------------------------------------
# 模板生成
# ---------------------------------------------------------------------------
def build_template(frozen: list[dict], annotator: str,
                   protocols: Optional[list[str]] = None,
                   split: str = "all") -> dict[str, list[dict]]:
    """按协议生成空白标注模板。

    模板里每条候选**只给题面**（candidate_id / protocol / text / source /
    span / section_path / subject_type），**不含任何答案字段的值** ——
    答案字段留空待填。``subject_type`` 给出是因为它是抽样分层标签、
    标注者需要知道题目属于哪类主体；但它**不是**答案的一部分。
    """
    out: dict[str, list[dict]] = {}
    for rec in frozen:
        proto = rec["protocol"]
        if protocols and proto not in protocols:
            continue
        if split != "all" and rec.get("split") != split:
            continue
        out.setdefault(proto, []).append({
            "candidate_id": rec["candidate_id"],
            "protocol": proto,
            "text": rec["text"],
            "source": rec.get("source"),
            "span_start": rec.get("span_start"),
            "span_end": rec.get("span_end"),
            "section_path": rec.get("section_path"),
            "subject_type": rec.get("subject_type"),
            "split": rec.get("split"),
            # ↓↓↓ 待填的四个字段（模板里为 null / 占位）↓↓↓
            "has_normative_requirement": None,
            "modality": None,
            "operator": None,
            "expected_response_class": None,
            "annotator": annotator,
            "uncertain": False,
            "uncertain_reason": None,
        })
    return out


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8", newline="\n")


# ---------------------------------------------------------------------------
# 指南泄漏自检
# ---------------------------------------------------------------------------
def check_guide_leaks(guide_path: Path, frozen: list[dict],
                      min_coverage: float = 0.5,
                      min_length: int = 45) -> tuple[list[str], list[str]]:
    """检查标注指南是否泄漏了冻结候选的原文。

    ★ 这是**防信息泄漏**的机械闸：指南里若出现某条**待标注**候选，
      标注者就能「照抄」，该条的标注就失去意义（roadmap §4.6 第 4 条的同类风险）。

    判据（**覆盖率**而非绝对长度 —— 后者会把「通用措辞」误判成泄漏）：

      L1 **逐字泄漏**：指南含某冻结候选的**完整**归一化原文 ⇒ 泄漏（必须为 0）
      L2 **近似泄漏**：覆盖率 ``L / len(候选) >= min_coverage`` **且**
         候选长度 ``>= min_length`` ⇒ 泄漏

    为什么 L2 要加长度下限：短候选（状态码表行、片段）天然与指南共享词汇 ——
    例如指南举了 ``|     "411"      ; Length Required`` 作表格行示例，
    冻结集里的 ``411            Length Required                  all`` 是**同一张表的
    另一行**，两者共享 ``Length Required`` 纯属表格词汇重合，不是答案泄漏。
    长度下限保证「覆盖率」只在候选足够长、因而覆盖率有判别力时才生效。

    返回 ``(problems, notes)``：``problems`` 是必须修的泄漏；
    ``notes`` 是短候选的低风险词汇重合（仅提示，不阻断）。
    """
    if not guide_path.is_file():
        return ([f"指南文件不存在: {guide_path}"], [])
    guide = _normalize_ws(guide_path.read_text(encoding="utf-8"))
    problems: list[str] = []
    notes: list[str] = []
    for rec in frozen:
        text = _normalize_ws(rec["text"])
        if not text:
            continue
        if text in guide:
            problems.append(f"L1 逐字泄漏: {rec['candidate_id']} | {text[:70]}")
            continue
        longest = _longest_common_substring(text, guide)
        coverage = longest / len(text) if text else 0.0
        if coverage < min_coverage:
            continue
        if len(text) >= min_length:
            problems.append(
                f"L2 近似泄漏(覆盖率 {coverage:.0%}, {longest}字符, 候选长 {len(text)}): "
                f"{rec['candidate_id']} | {text[:60]}")
        else:
            notes.append(
                f"短候选词汇重合(覆盖率 {coverage:.0%}, 候选长 {len(text)}): "
                f"{rec['candidate_id']} | {text[:50]}")
    return problems, notes


def _normalize_ws(text: str) -> str:
    """折叠连续空白为一个空格（表格对齐空格不构成「相同句子」）。"""
    return " ".join(text.split())


def _longest_common_substring(a: str, b: str) -> int:
    """求 a 在 b 中出现的最长连续子串长度（滚动数组 O(len(a)*len(b))）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
            else:
                cur[j] = 0
        prev = cur
    return best


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def cmd_template(args: argparse.Namespace) -> int:
    frozen = load_frozen(Path(args.frozen))
    protocols = [p.strip() for p in args.protocols.split(",")] if args.protocols else None
    templates = build_template(frozen, args.annotator, protocols, args.split)
    if not templates:
        print("[ERR] 没有匹配到候选", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    for proto, items in sorted(templates.items()):
        suffix = "" if args.split == "all" else f".{args.split}"
        path = out_dir / f"{proto}{suffix}.template.json"
        _write_json(path, {
            "_meta": {
                "annotator": args.annotator,
                "protocol": proto,
                "split": args.split,
                "count": len(items),
                "guide": "docs/annotation_guide.md",
                "note": "四个标注字段待填；判定标准见 docs/annotation_guide.md",
            },
            "annotations": items,
        })
        print(f"[OK] {proto}: {len(items)} 条 → {path}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    frozen = load_frozen(Path(args.frozen))
    paths = [Path(p) for p in (args.annotations or [])]
    paths += [Path(p) for p in (args.include or [])]
    if not paths:
        print("[ERR] 至少要指定 --annotations", file=sys.stderr)
        return 2
    annotations: list[dict] = []
    for path in paths:
        annotations.extend(load_annotations(path))

    # 覆盖性检查的范围 = 这些文件里出现过的 candidate_id 所属协议的**全部**冻结候选。
    # （一个协议的标注集通常拆成 <proto>.annotated.json + <proto>.holdout.json 两份，
    #   校验时须一起校验才谈得上「覆盖完整」。）
    protos = {a.get("protocol") for a in annotations if a.get("protocol")}
    scoped = [r for r in frozen if not protos or r["protocol"] in protos]

    problems = validate_all(annotations, scoped,
                             require_complete=not args.allow_partial)
    label = ", ".join(p.name for p in paths)
    if problems:
        print(f"[FAIL] {label}: {len(problems)} 个问题", file=sys.stderr)
        for p in problems[:args.max_problems]:
            print(f"  - {p}", file=sys.stderr)
        if len(problems) > args.max_problems:
            print(f"  ... 还有 {len(problems) - args.max_problems} 个问题",
                  file=sys.stderr)
        return 1
    dist = Counter((a["has_normative_requirement"], a["modality"],
                    a["operator"], a["expected_response_class"]) for a in annotations)
    n_unc = sum(1 for a in annotations if a.get("uncertain") is True)
    print(f"[OK] {label}: {len(annotations)} 条全部通过校验")
    print(f"     含规范要求: {sum(1 for a in annotations if a['has_normative_requirement'])}"
          f" / {len(annotations)}")
    print(f"     标注者: {sorted({a['annotator'] for a in annotations})}")
    print(f"     uncertain: {n_unc}")
    print(f"     组合分布: {len(dist)} 种")
    return 0


def cmd_check_guide(args: argparse.Namespace) -> int:
    frozen = load_frozen(Path(args.frozen))
    problems, notes = check_guide_leaks(Path(args.guide), frozen,
                                        args.min_coverage, args.min_length)
    for n in notes[:args.max_problems]:
        print(f"  [note] {n}")
    if problems:
        print(f"[FAIL] 指南泄漏检查: {len(problems)} 处", file=sys.stderr)
        for p in problems[:args.max_problems]:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"[OK] 指南无泄漏（检查 {len(frozen)} 条冻结候选，"
          f"覆盖率阈值 {args.min_coverage:.0%}，候选长度下限 {args.min_length}）")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    frozen = load_frozen(Path(args.frozen))
    ann = load_annotations(Path(args.annotations))
    print(f"标注 {len(ann)} 条（冻结集 {len(frozen)} 条）")
    for key, label in (("has_normative_requirement", "含规范要求"),
                       ("modality", "modality"),
                       ("operator", "operator"),
                       ("expected_response_class", "expected_response_class")):
        c = Counter(str(a.get(key)) for a in ann)
        print(f"  {label}: {dict(sorted(c.items()))}")
    n_unc = sum(1 for a in ann if a.get("uncertain") is True)
    print(f"  uncertain: {n_unc}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="B 阶段人工标注集工具（模板 / 校验 / 指南泄漏自检）")
    ap.add_argument("--frozen", default=str(DEFAULT_FROZEN), help="冻结候选集路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_tpl = sub.add_parser("template", help="生成空白标注模板")
    p_tpl.add_argument("--out-dir", required=True, help="模板输出目录")
    p_tpl.add_argument("--annotator", required=True, help="标注者标识（如 A / B）")
    p_tpl.add_argument("--protocols", default="", help="只生成指定协议（逗号分隔），默认全部")
    p_tpl.add_argument("--split", default="all", choices=["all", "train", "holdout"],
                       help="只生成指定切分，默认 all")
    p_tpl.set_defaults(func=cmd_template)

    p_val = sub.add_parser("validate", help="校验标注文件")
    p_val.add_argument("--annotations", required=True, nargs="+", help="标注文件路径（可多个）")
    p_val.add_argument("--include", action="append", default=[],
                       help="追加合并校验的文件（如该协议的 holdout 文件）")
    p_val.add_argument("--allow-partial", action="store_true",
                       help="允许缺漏（默认要求覆盖文件所涉协议的全部冻结候选）")
    p_val.add_argument("--max-problems", type=int, default=50, help="最多打印多少个问题")
    p_val.set_defaults(func=cmd_validate)

    p_leak = sub.add_parser("check-guide", help="检查指南是否泄漏冻结候选原文")
    p_leak.add_argument("--guide", default=str(DEFAULT_GUIDE), help="指南路径")
    p_leak.add_argument("--min-coverage", type=float, default=0.5,
                        help="判定为泄漏的覆盖率阈值（默认 0.5 = 50%%）")
    p_leak.add_argument("--min-length", type=int, default=45,
                        help="L2 近似泄漏判定的候选长度下限（短候选只提示不阻断）")
    p_leak.add_argument("--max-problems", type=int, default=50, help="最多打印多少处")
    p_leak.set_defaults(func=cmd_check_guide)

    p_st = sub.add_parser("stats", help="打印标注分布统计")
    p_st.add_argument("--annotations", required=True, help="标注文件路径")
    p_st.set_defaults(func=cmd_stats)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
