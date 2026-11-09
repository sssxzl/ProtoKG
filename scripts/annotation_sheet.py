# -*- coding: utf-8 -*-
"""把「待标候选」导出成人工标注用的 Excel 表，并能把填好的表**导回**标注 JSON。

为什么需要它
------------
`derived/exp_semantic/truth/*.json` 是**机器格式**（每条一个 JSON 对象），
人要在里面填 117 条不现实。本脚本提供一条**可审计的双向通道**：

    export  truth/*.json  ──►  xlsx（人填）
    import  xlsx（人填完） ──►  truth_b/<proto>.{annotated,holdout}.json

★ 纪律（与 `docs/人工标注指南.md` §8 一致）：
  - 表里**只给题面 + 空答案格**，不预填任何判定，避免引导标注者；
  - `candidate_id` / `text` 由冻结集原样抄出，**不做任何清洗**（半句也照抄）；
  - 导出是可复现的：同一份 frozen + truth ⇒ 同一行序、同一内容。

用法
----
    PY="E:/app/Anaconda3/python.exe"
    $PY scripts/annotation_sheet.py export --xlsx derived/exp_semantic/标注表_117条待标.xlsx
    $PY scripts/annotation_sheet.py import --xlsx <填好的.xlsx> \
        --out-dir derived/exp_semantic/truth_b --annotator B

填写约定（也在表内「填写须知」写明）
------------------------------------
- 四个判定列：`是否含规范要求` / `规范强度` / `算子` / `期望响应类别`，均带下拉；
- `期望响应类别` **留空按 `null` 处理**（判不出来就是 null，是绝大多数情况）
  —— import 时会打印实际由「留空」折算为 null 的条数，便于审计；
- `不确定` 留空按「否」处理；填「是」时**必须**在 `不确定原因` 写一句话；
- 两个派生约束由 import 强制（与标注器 R6/R7 一致）：
  `是否含规范要求`=否 ⇒ 强度必为「无」、算子必为「不可」。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from openpyxl import Workbook, load_workbook              # noqa: E402
from openpyxl.formatting.rule import CellIsRule            # noqa: E402
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: E402
from openpyxl.utils import get_column_letter               # noqa: E402
from openpyxl.worksheet.datavalidation import DataValidation  # noqa: E402

TRUTH_DIR = REPO / "derived" / "exp_semantic" / "truth"
FROZEN = REPO / "derived" / "exp_semantic" / "candidates_frozen.jsonl"

#: 词表 —— 与 `scripts/annotate_candidates.py` 的 MODALITIES / OPERATORS /
#: RESPONSE_CLASSES 逐项相等（有测试守）。
MODALITIES = ("MUST", "SHOULD", "MAY", "无")
OPERATORS = ("eq", "ne", "lt", "gt", "le", "ge", "in", "present", "absent",
             "range", "不可")
RESPONSE_CLASSES = ("null", "success", "protocol_error", "application_error",
                    "silence")
YN = ("是", "否")

#: 表头（顺序即列序）。`★` 标记的四列是**唯一**要填的判定列。
COLS: tuple[tuple[str, str, int], ...] = (
    # (键, 表头, 列宽)
    ("idx", "序号", 5),
    ("candidate_id", "candidate_id", 19),
    ("protocol", "协议", 6),
    ("split", "切分", 8),
    ("subject_type", "主体类型", 12),
    ("text", "候选文本（判定唯一依据，逐字照抄 RFC 抽取结果）", 78),
    ("has_normative_requirement", "★是否含规范要求\n（是/否）", 14),
    ("modality", "★规范强度\n（MUST/SHOULD/MAY/无）", 15),
    ("operator", "★算子\n（eq…range/不可）", 16),
    ("expected_response_class", "★期望响应类别\n（留空=null）", 18),
    ("uncertain", "不确定\n（是/否）", 10),
    ("uncertain_reason", "不确定原因（不确定=是 时必填一句话）", 34),
    ("note", "备注（可选，不进 JSON）", 22),
    ("section_no", "章节号（仅溯源）", 9),
    ("section_path", "章节路径（仅溯源）", 30),
    ("spec_version", "规范版本（仅溯源）", 12),
)

HEADER_ROW = 3
FIRST_DATA_ROW = HEADER_ROW + 1

_THIN = Side(style="thin", color="D0D5DD")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_FILL_HDR = PatternFill("solid", fgColor="1F3864")     # 深蓝灰
_FILL_TITLE = PatternFill("solid", fgColor="D9E2F3")   # 浅蓝
_FILL_HOLDOUT = PatternFill("solid", fgColor="FCE4D6")  # 浅橙
_FILL_MISSING = PatternFill("solid", fgColor="FFF2CC")  # 浅黄（未填）


# ---------------------------------------------------------------------------
# 读取待标集
# ---------------------------------------------------------------------------
def load_frozen(path: Path = FROZEN) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rec = json.loads(line)
            out[rec["candidate_id"]] = rec
    return out


def pending_rows(truth_dir: Path, frozen: dict[str, dict],
                 only_pending: bool = True) -> list[dict]:
    """跨 6 个 truth 文件收集待标条目，按协议→切分→id 稳定排序。

    Args:
        only_pending: True（默认）只取 ``pending: true`` 的条目 —— 用于**续标**；
            False 取**全部 120 条** —— 用于给「第二标注者」出空白表
            （B 轮必须看不到 A 的任何判定，所以不能只给 117 条）。
    """
    rows: list[dict] = []
    for f in sorted(truth_dir.glob("*.json")):
        split = "holdout" if f.stem.endswith(".holdout") else "train"
        proto = f.name.split(".")[0]
        for rec in json.loads(f.read_text(encoding="utf-8")):
            if only_pending and not rec.get("pending"):
                continue
            cid = rec["candidate_id"]
            if cid not in frozen:
                raise SystemExit(f"[FATAL] {cid} 不在冻结集内 ⇒ 候选池与标注集失联")
            base = frozen[cid]
            if base["text"] != rec["text"]:
                raise SystemExit(f"[FATAL] {cid} 的 text 与冻结集不一致")
            rows.append({**base, "split": split, "protocol": proto})
    order = {"rtsp": 0, "sip": 1, "smtp": 2}
    rows.sort(key=lambda r: (order.get(r["protocol"], 9),
                             r["split"] != "train", r["candidate_id"]))
    return rows


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------
def _style_header(ws, ncol: int) -> None:
    for c in range(1, ncol + 1):
        cell = ws.cell(row=HEADER_ROW, column=c)
        cell.fill = _FILL_HDR
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.alignment = Alignment(horizontal="center", vertical="center",
                                   wrap_text=True)
        cell.border = _BORDER
    ws.row_dimensions[HEADER_ROW].height = 42


def build_workbook(rows: list[dict]) -> Workbook:
    wb = Workbook()
    ws = wb.active
    ws.title = "标注表"
    ncol = len(COLS)

    # ---- 标题行 ----
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
    t = ws.cell(row=1, column=1)
    t.value = (f"ProtoRAG B 阶段人工标注表 · 共 {len(rows)} 条 · "
               "判定只依据「候选文本」一列，不得翻 RFC 上下文或任何实现产物"
               "（本表不含任何既往判定）")
    t.font = Font(bold=True, size=12, color="1F3864")
    t.fill = _FILL_TITLE
    t.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 24

    # ---- 标注者 / 日期（import 会读这两格）----
    ws.cell(row=2, column=1, value="标注者").font = Font(bold=True)
    ws.cell(row=2, column=2, value="").fill = _FILL_MISSING
    ws.cell(row=2, column=3, value="日期").font = Font(bold=True)
    ws.cell(row=2, column=4, value="").fill = _FILL_MISSING
    hint = ws.cell(row=2, column=6,
                   value="填写须知见「填写须知」页；下拉列请直接选，不要手打。"
                         "「期望响应类别」留空 = null。")
    hint.font = Font(italic=True, size=9, color="7F7F7F")

    # ---- 表头 ----
    for i, (_k, title, width) in enumerate(COLS, start=1):
        ws.cell(row=HEADER_ROW, column=i, value=title)
        ws.column_dimensions[get_column_letter(i)].width = width
    _style_header(ws, ncol)

    # ---- 数据行 ----
    for n, rec in enumerate(rows):
        r = FIRST_DATA_ROW + n
        path = rec.get("section_path") or []
        vals = {
            "idx": n + 1,
            "candidate_id": rec["candidate_id"],
            "protocol": rec["protocol"],
            "split": rec["split"],
            "subject_type": rec.get("subject_type"),
            "text": rec["text"],
            "has_normative_requirement": None,
            "modality": None,
            "operator": None,
            "expected_response_class": None,
            "uncertain": None,
            "uncertain_reason": None,
            "note": None,
            "section_no": rec.get("section_no"),
            "section_path": " › ".join(str(p) for p in path),
            "spec_version": rec.get("spec_version"),
        }
        for i, (k, _t, _w) in enumerate(COLS, start=1):
            cell = ws.cell(row=r, column=i, value=vals.get(k))
            cell.border = _BORDER
            cell.font = Font(size=10)
            if k == "text":
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            elif k in ("candidate_id", "section_path", "uncertain_reason", "note"):
                cell.alignment = Alignment(vertical="top", wrap_text=True)
            else:
                cell.alignment = Alignment(horizontal="center", vertical="top")
        # holdout 视觉提示（只染「切分」一格，避免整行花）
        if rec["split"] == "holdout":
            ws.cell(row=r, column=4).fill = _FILL_HOLDOUT
        # 估算行高：文本列宽 78 ⇒ 约 60 个字符/行
        ws.row_dimensions[r].height = max(16, min(96, 14 * (len(rec["text"]) // 60 + 1)))

    last = FIRST_DATA_ROW + len(rows) - 1

    # ---- 下拉 ----
    def _dv(values: tuple[str, ...], col_letter: str, prompt: str) -> None:
        dv = DataValidation(type="list", formula1='"%s"' % ",".join(values),
                            allow_blank=True, showDropDown=False)
        dv.error = "只能从下拉里选"
        dv.errorTitle = "取值非法"
        dv.prompt = prompt
        dv.promptTitle = "可选值"
        ws.add_data_validation(dv)
        dv.add(f"{col_letter}{FIRST_DATA_ROW}:{col_letter}{last}")

    _dv(YN, "G", "这句话里有没有对实现者的规范性要求？")
    _dv(MODALITIES, "H", "MUST NOT→MUST；SHOULD NOT→SHOULD；无要求→无")
    _dv(OPERATORS, "I", "不可执行填「不可」；不要因为读不懂就填「不可」")
    _dv(RESPONSE_CLASSES, "J", "原文没说违规后会怎样 ⇒ 留空（=null）")
    _dv(YN, "K", "拿不准就填「是」，并在右侧写一句原因")

    # ---- 未填高亮（是否含规范要求 为空）----
    ws.conditional_formatting.add(
        f"G{FIRST_DATA_ROW}:G{last}",
        CellIsRule(operator="equal", formula=['""'], fill=_FILL_MISSING))

    ws.freeze_panes = f"C{FIRST_DATA_ROW}"
    ws.auto_filter.ref = f"A{HEADER_ROW}:{get_column_letter(ncol)}{last}"
    ws.sheet_view.zoomScale = 90

    _add_guide_sheet(wb)
    _add_stats_sheet(wb, rows, last)
    return wb


def _add_guide_sheet(wb: Workbook) -> None:
    """判定规则速查（摘自 docs/人工标注指南.md，**不含任何候选的答案**）。"""
    ws = wb.create_sheet("填写须知")
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 58

    ws.merge_cells("A1:C1")
    c = ws.cell(row=1, column=1, value="填写须知 · 四字段判定速查"
                                      "（完整版见 docs/人工标注指南.md）")
    c.font = Font(bold=True, size=12, color="1F3864")
    c.fill = _FILL_TITLE
    ws.row_dimensions[1].height = 24

    blocks: list[tuple[str, list[tuple[str, str, str]]]] = [
        ("字段一 has_normative_requirement（是/否）", [
            ("判定问题", "这句话里，有没有对「实现者 / 收发双方」提出的规范性要求？", ""),
            ("判「是」", "出现 RFC 2119 全大写关键词（MUST / MUST NOT / SHALL / "
                        "REQUIRED / SHOULD / SHOULD NOT / RECOMMENDED / MAY / OPTIONAL）",
             "或同义强制措辞 / 祈使式的小写 must、should"),
            ("判「否」", "纯描述性、事实陈述、举例、ABNF 文法行、表格行、"
                        "RFC 2119 元叙述", "小写 must 只描述「判断动作」时也判否"),
            ("半句", "只按 text 里**实际出现**的内容判；出现 MUST 就判「是」", ""),
            ("拿不准", "标 uncertain=是 并写一句原因 —— 不要默认判「否」", ""),
        ]),
        ("字段二 modality（MUST / SHOULD / MAY / 无）", [
            ("MUST", "MUST / MUST NOT / SHALL / SHALL NOT / REQUIRED / is prohibited",
             "★ MUST NOT 归 MUST，方向由 operator 表达"),
            ("SHOULD", "SHOULD / SHOULD NOT / RECOMMENDED / NOT RECOMMENDED", ""),
            ("MAY", "MAY / MAY NOT / OPTIONAL", "MAY = 可选，不是「弱化的 MUST」"),
            ("无", "字段一判「否」时必须填「无」", "校验器强制"),
            ("多强度词", "取最强的那一个", ""),
        ]),
        ("字段三 operator（eq/ne/lt/gt/le/ge/in/present/absent/range/不可）", [
            ("前提", "要「可执行」必须同时有：明确约束对象 + 明确比较关系 + 明确操作数",
             "三者缺一 ⇒ 不可"),
            ("eq / ne", "等于 / 不等于某个确定值", "MUST NOT be X ⇒ ne"),
            ("lt / gt / le / ge", "less than / more than / at most·no more than / "
                                  "at least·no less than", ""),
            ("in / range", "one of {...} / between X and Y", ""),
            ("present / absent", "MUST contain·be present / MUST NOT contain·be omitted",
             "★ 看否定的是「存在」还是「取值」"),
            ("判「不可」", "无规范要求；没有操作数；约束对象不明；操作数在 text 外；"
                          "时序/状态/行为要求；ABNF/表格行", "不要因读不懂就填「不可」"),
        ]),
        ("字段四 expected_response_class（留空=null / success / protocol_error / "
         "application_error / silence）", [
            ("判定问题", "如果这条约束被违反，接收方会怎么回应？", ""),
            ("null（最常见）", "原文只规定「必须做什么」，没说「不这么做会怎样」", "留空即可"),
            ("protocol_error", "原文明确给出 4xx / 5xx、命令未实现、报文非法", ""),
            ("application_error", "协议格式正确但语义被拒（鉴权失败 / 对象不存在 / 权限不足）", ""),
            ("silence", "明确说丢弃 / 不响应 / 忽略", ""),
            ("success", "明确说接受 / 照办 / 正常处理", ""),
            ("★ 禁止", "**不要从协议常识倒推**（如「SMTP 通常回 250」）",
             "倒推会让 F1 虚高，是这份标注集最需要防的污染"),
        ]),
        ("标注纪律（直接决定标注集有没有用）", [
            ("只用 text", "不要翻 RFC 上下文补全句子 —— holdout 与训练集同口径", ""),
            ("不看实现产物", "不查 profile.json / allowed_methods / derived/per_source/ / "
                            "core/fused/ 的规则表", "否则 F1 变成「自己抄自己」"),
            ("不猜", "标不准就 uncertain=是，会进第三人仲裁清单", "这不是失败"),
            ("不调标准", "不要为了让下游好看而放宽或收紧", "κ 低是要报告的事实"),
        ]),
    ]

    r = 3
    for title, items in blocks:
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=3)
        cell = ws.cell(row=r, column=1, value=title)
        cell.font = Font(bold=True, size=11, color="FFFFFF")
        cell.fill = _FILL_HDR
        cell.alignment = Alignment(vertical="center")
        ws.row_dimensions[r].height = 20
        r += 1
        for a, b, c3 in items:
            for j, v in enumerate((a, b, c3), start=1):
                cell = ws.cell(row=r, column=j, value=v)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                cell.border = _BORDER
                cell.font = Font(size=10, bold=(j == 1))
            ws.row_dimensions[r].height = max(16, 14 * (max(len(b), len(c3)) // 55 + 1))
            r += 1
        r += 1

    ws.freeze_panes = "A3"


def _add_stats_sheet(wb: Workbook, rows: list[dict], last: int) -> None:
    ws = wb.create_sheet("进度统计")
    ws.column_dimensions["A"].width = 26
    for col in "BCDE":
        ws.column_dimensions[col].width = 12

    ws.merge_cells("A1:E1")
    c = ws.cell(row=1, column=1, value="进度与分布（左侧计数为公式，随填表自动更新）")
    c.font = Font(bold=True, size=12, color="1F3864")
    c.fill = _FILL_TITLE
    ws.row_dimensions[1].height = 24

    import collections
    ws.cell(row=3, column=1, value="待标总数").font = Font(bold=True)
    ws.cell(row=3, column=2, value=len(rows))
    ws.cell(row=4, column=1, value="已填条数").font = Font(bold=True)
    ws.cell(row=4, column=2, value=f"=COUNTA('标注表'!G{FIRST_DATA_ROW}:G{last})")
    ws.cell(row=5, column=1, value="剩余").font = Font(bold=True)
    ws.cell(row=5, column=2, value="=B3-B4")
    ws.cell(row=6, column=1, value="完成率").font = Font(bold=True)
    ws.cell(row=6, column=2, value="=IF(B3=0,0,B4/B3)").number_format = "0.0%"
    ws.cell(row=7, column=1, value="判「是」的条数").font = Font(bold=True)
    ws.cell(row=7, column=2,
            value=f"=COUNTIF('标注表'!G{FIRST_DATA_ROW}:G{last},\"是\")")
    ws.cell(row=8, column=1, value="标 uncertain 的条数").font = Font(bold=True)
    ws.cell(row=8, column=2,
            value=f"=COUNTIF('标注表'!K{FIRST_DATA_ROW}:K{last},\"是\")")

    # 分布表
    r = 10
    ws.cell(row=r, column=1, value="分布").font = Font(bold=True, size=11)
    r += 1
    for j, h in enumerate(("维度", "取值", "条数", "其中 holdout", "其中 train"), start=1):
        cell = ws.cell(row=r, column=j, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _FILL_HDR
        cell.alignment = Alignment(horizontal="center")
    r += 1

    dims = (("协议", "protocol", ("rtsp", "sip", "smtp")),
            ("切分", "split", ("train", "holdout")),
            ("主体类型", "subject_type",
             ("method", "field", "status", "message_type")))
    for label, key, vals in dims:
        for v in vals:
            n = sum(1 for x in rows if str(x.get(key)) == v)
            ho = sum(1 for x in rows if str(x.get(key)) == v and x["split"] == "holdout")
            ws.cell(row=r, column=1, value=label).border = _BORDER
            ws.cell(row=r, column=2, value=v).border = _BORDER
            ws.cell(row=r, column=3, value=n).border = _BORDER
            ws.cell(row=r, column=4, value=ho).border = _BORDER
            ws.cell(row=r, column=5, value=n - ho).border = _BORDER
            r += 1
    # 交叉表提示
    cross = collections.Counter((x["protocol"], x["split"]) for x in rows)
    r += 1
    ws.cell(row=r, column=1, value="协议 × 切分明细").font = Font(bold=True, size=11)
    r += 1
    for j, h in enumerate(("协议", "train", "holdout", "合计"), start=1):
        cell = ws.cell(row=r, column=j, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = _FILL_HDR
        cell.alignment = Alignment(horizontal="center")
    r += 1
    for p in ("rtsp", "sip", "smtp"):
        tr, ho = cross[(p, "train")], cross[(p, "holdout")]
        for j, v in enumerate((p, tr, ho, tr + ho), start=1):
            ws.cell(row=r, column=j, value=v).border = _BORDER
        r += 1
    ws.freeze_panes = "A3"


def cmd_export(args: argparse.Namespace) -> int:
    frozen = load_frozen()
    rows = pending_rows(Path(args.truth_dir), frozen,
                        only_pending=not getattr(args, "include_labeled", False))
    wb = build_workbook(rows)
    out = Path(args.xlsx)
    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"[OK] 导出 {len(rows)} 条 → {out}")
    import collections
    print("     协议×切分:", dict(collections.Counter(
        (r["protocol"], r["split"]) for r in rows)))
    return 0


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------
def _norm(v) -> str:
    return "" if v is None else str(v).strip()


def cmd_import(args: argparse.Namespace) -> int:
    wb = load_workbook(args.xlsx, data_only=True)
    ws = wb["标注表"]

    sheet_annotator = _norm(ws.cell(row=2, column=2).value)
    annotator = args.annotator or sheet_annotator
    if not annotator:
        print("[FAIL] 没拿到标注者：请填表内 B2 或用 --annotator 指定",
              file=sys.stderr)
        return 1

    header = [ws.cell(row=HEADER_ROW, column=i).value for i in range(1, len(COLS) + 1)]
    keys = [k for k, _t, _w in COLS]
    col_of = {k: i + 1 for i, k in enumerate(keys)}
    if header[1] != "candidate_id":        # 轻量表头校验，防拿错表
        print("[FAIL] 表头不符：第 2 列应为 candidate_id", file=sys.stderr)
        return 1

    frozen = load_frozen()
    records: list[dict] = []
    problems: list[str] = []
    n_blank_as_null = n_blank_uncertain = 0
    seen: set[str] = set()

    row = FIRST_DATA_ROW
    while True:
        cid = _norm(ws.cell(row=row, column=col_of["candidate_id"]).value)
        if not cid:
            break
        if cid not in frozen:
            problems.append(f"第{row}行 {cid}: 不在冻结集")
            row += 1
            continue
        if cid in seen:
            problems.append(f"第{row}行 {cid}: candidate_id 重复")
        seen.add(cid)

        yn = _norm(ws.cell(row=row, column=col_of["has_normative_requirement"]).value)
        mod = _norm(ws.cell(row=row, column=col_of["modality"]).value)
        op = _norm(ws.cell(row=row, column=col_of["operator"]).value)
        erc = _norm(ws.cell(row=row, column=col_of["expected_response_class"]).value)
        unc = _norm(ws.cell(row=row, column=col_of["uncertain"]).value)
        reason = _norm(ws.cell(row=row, column=col_of["uncertain_reason"]).value)

        if yn not in ("是", "否"):
            problems.append(f"第{row}行 {cid}: 是否含规范要求 未填或非「是/否」")
            row += 1
            continue
        has = yn == "是"
        if not unc:
            n_blank_uncertain += 1
        if not erc:
            n_blank_as_null += 1
        erc_val = None if erc in ("", "null") else erc

        rec = {
            "candidate_id": cid,
            "protocol": frozen[cid]["protocol"],
            "text": frozen[cid]["text"],
            "has_normative_requirement": has,
            "modality": mod or (None if has else "无"),
            "operator": op or (None if has else "不可"),
            "expected_response_class": erc_val,
            "uncertain": unc == "是",
            "uncertain_reason": reason or None,
            "annotator": annotator,
            "pending": False,
        }
        records.append(rec)
        row += 1

    # 复用标注器自带的 10 条校验规则（与手工流程同口径）
    try:
        from scripts.annotate_candidates import validate_one  # type: ignore
    except Exception:                                         # noqa: BLE001
        sys.path.insert(0, str(REPO / "scripts"))
        from annotate_candidates import validate_one          # type: ignore
    known = set(frozen)
    for rec in records:
        for p in validate_one(rec, known):
            problems.append(f"{rec['candidate_id']}: {p}")

    if problems:
        print(f"[FAIL] 校验未通过，共 {len(problems)} 条问题（前 30 条）：",
              file=sys.stderr)
        for p in problems[:30]:
            print("   -", p, file=sys.stderr)
        return 1

    # 按协议 × 切分落盘
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    buckets: dict[tuple[str, str], list[dict]] = {}
    for rec in records:
        split = next((x["split"] for x in [frozen[rec["candidate_id"]]]), "train")
        buckets.setdefault((rec["protocol"], split), []).append(rec)
    for (proto, split), recs in sorted(buckets.items()):
        name = f"{proto}.annotated.json" if split == "train" else f"{proto}.holdout.json"
        (out_dir / name).write_text(
            json.dumps(recs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n")
        print(f"[OK] {out_dir / name}  {len(recs)} 条")

    print(f"[OK] 标注者={annotator}；共 {len(records)} 条；"
          f"留空折算为 null：{n_blank_as_null} 条；"
          f"不确定留空按「否」：{n_blank_uncertain} 条")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="标注表的导出/回收")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("export", help="truth/*.json 的 pending 条目 → xlsx")
    e.add_argument("--xlsx", required=True)
    e.add_argument("--truth-dir", default=str(TRUTH_DIR))
    e.add_argument("--include-labeled", action="store_true",
                   help="连同已标条目一起导出（全部 120 条）—— "
                        "给第二标注者出空白表时用，避免其只见 117 条")
    e.set_defaults(func=cmd_export)

    i = sub.add_parser("import", help="填好的 xlsx → 标注 JSON")
    i.add_argument("--xlsx", required=True)
    i.add_argument("--out-dir", required=True)
    i.add_argument("--annotator", default=None)
    i.set_defaults(func=cmd_import)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
