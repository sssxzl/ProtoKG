# -*- coding: utf-8 -*-
"""★ V2-E4-R1：★ **H3 23 条候选的人工盲审包生成器（★ XLSX）**。

★ ★ 三份 XLSX：★ 审核者 A / 审核者 B / 第三方仲裁
★ ★ **★ 绝不向盲审者透露**：★ V2 类型预测、★ 当前路由、★ H2A 的三点判断、
★   ★ 开发集标准答案、★ 另一审核者答案、★ 已知误分类原因
★ ★ 候选命题文本与候选声称的结构化字段【必须提供】（★ 审核对象），★ 但 kind/route【不提供】
★ ★ 0 次 LLM；★ 不改 H3 候选；★ 不改 V0/V1/V2
"""
from __future__ import annotations

import collections
import hashlib
import html
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/r1"
OUTD.mkdir(parents=True, exist_ok=True)
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R1_H3候选人工盲审")
DELIV.mkdir(parents=True, exist_ok=True)

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill, Protection
from openpyxl.utils import get_column_letter
from openpyxl.workbook.defined_name import DefinedName
from openpyxl.worksheet.datavalidation import DataValidation

H3 = [json.loads(l) for l in
      (ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3新增候选原始.jsonl")
      .read_text(encoding="utf-8").splitlines() if l.strip()]
RAW = [json.loads(l) for l in
       (ROOT / "guard/_out/_n1c_v2/e4/pool/V2-E4_H3原始LLM输出.jsonl")
       .read_text(encoding="utf-8").splitlines() if l.strip()]
_rawidx = {}
for _r in RAW:
    _it = _r["★ ★ 原始 LLM 输出（★ 全字段）"]
    _rawidx.setdefault((_it.get("doc"), int(_it.get("span") or 0)), []).append(_it)


def _find_raw(doc, span):
    if not span:
        return {}
    _c = [(k, v) for k, v in _rawidx.items() if k[0] == doc and k[1] <= int(span)]
    return max(_c, key=lambda kv: kv[0][1])[1][0] if _c else {}


# ══ 中性稳定 ID（★ 按冻结清单顺序；★ 不泄露任何预测）══
_items = []
for _i, _c in enumerate(sorted(H3, key=lambda z: (z["★ document_id"],
                                                 int((z["★ source_span"] or [0])[0]),
                               z["★ candidate_id"])), start=1):
    _n = _c["★ norm（★ 派生层输出）"]
    _sl = int(_n.get("span_line") or 0)
    _raw = _find_raw(_c["★ document_id"], _sl)
    _lo, _hi = _c["★ source_span"]
    _pp = ROOT / f'kb/{_c["★ protocol"]}/spec/{_c["★ document_id"]}'
    _L = _pp.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _evidence = " ".join(_L[_lo - 1:_hi])
    _items.append({
        "★ 审核ID": f"H3-{_i:02d}",
        "★ RFC 文档": _c["★ document_id"],
        "★ 协议": _c["★ protocol"],
        "★ RFC SHA256": _c["★ source_sha256"],
        "★ chunk_id": _c["★ chunk_id"],
        "★ 证据跨度（行号）": f"{_lo}-{_hi}",
        "★ 证据原文（RFC 逐行）": _evidence,
        "★ 候选命题（constraint 文本）": str(_n.get("constraint") or ""),
        "★ 候选含义（meaning 文本）": str(_n.get("meaning") or ""),
        "★ 候选声称的主体": str(_raw.get("normative_subject") or ""),
        "★ 候选声称的动作": str(_raw.get("action") or ""),
        "★ 候选声称的对象": str(_raw.get("object") or ""),
        "★ 候选声称的强度": str(_raw.get("strength") or ""),
        "★ 候选声称的极性": str(_raw.get("polarity") or ""),
        "★ 候选声称的条件": str(_raw.get("condition") or ""),
        "★ 候选声称的例外": str(_raw.get("exception") or ""),
        "★ 候选声称的主体解析状态": str(_n.get("subject_status") or ""),
        "★ 候选锚点行号": str(_sl),
        "★ 锚点行原文": str(_L[_sl - 1]) if 1 <= _sl <= len(_L) else "",
    })

# ══ 枚举（★ 全部含 unknown / uncertain / not_applicable / unresolved）══
ENUMS = {
    "是否存在目标知识": ["yes", "no", "uncertain"],
    "原文是否支持候选命题": ["yes", "no", "uncertain", "not_applicable"],
    "source_content_kind": ["non_protocol_metadata", "protocol_syntax",
                            "protocol_registry_or_enumeration",
                            "protocol_descriptive_semantics",
                            "normative_rule_candidate", "mixed_or_uncertain"],
    "knowledge_kind": ["non_protocol_metadata", "protocol_syntax",
                       "protocol_registry_or_enumeration",
                       "protocol_descriptive_semantics",
                       "normative_rule_candidate", "mixed_or_uncertain"],
    "rule_eligibility": ["eligible", "ineligible", "uncertain",
                         "not_applicable"],
    "evidence_sufficiency": ["sufficient", "partial", "insufficient",
                              "not_applicable"],
    "抽取完整性": ["full", "partial", "cross_sentence_missing",
                   "cross_section_missing", "not_applicable"],
    "规范强度": ["MUST", "SHALL", "SHOULD", "MAY", "REQUIRED", "RECOMMENDED",
                 "unknown", "not_applicable"],
    "极性": ["positive", "negative", "unknown", "not_applicable"],
    "目标路由": ["rule_channel", "structured_channel", "metadata_channel",
                 "descriptive_channel", "pending_review", "not_applicable"],
    "最终裁定状态": ["agreed", "arbitrated", "unresolved"],
}
REVIEW_COLS = [
    ("★ 原文是否支持候选命题", "是否存在目标知识"),
    ("★ 是否属于目标协议知识", "是否存在目标知识"),
    ("★ source_content_kind", "source_content_kind"),
    ("★ knowledge_kind", "knowledge_kind"),
    ("★ rule_eligibility", "rule_eligibility"),
    ("★ evidence_sufficiency", "evidence_sufficiency"),
    ("★ 规范义务主体", None),
    ("★ 规范义务动作", None),
    ("★ 规范义务对象", None),
    ("★ 规范强度", "规范强度"),
    ("★ 极性", "极性"),
    ("★ 条件", None),
    ("★ 例外", None),
    ("★ 抽取完整性", "抽取完整性"),
    ("★ RFC 原文证据是否充分", "evidence_sufficiency"),
    ("★ 人工认为正确的 V2 目标路由", "目标路由"),
    ("★ 审核理由（必填）", None),
    ("★ 审核者 ID（匿名编号）", None),
    ("★ 审核日期", None),
]
IDENTITY_COLS = ["★ 审核ID", "★ RFC 文档", "★ 协议", "★ RFC SHA256",
                 "★ chunk_id", "★ 证据跨度（行号）", "★ 证据原文（RFC 逐行）",
                 "★ 候选命题（constraint 文本）", "★ 候选含义（meaning 文本）",
                 "★ 候选声称的主体", "★ 候选声称的动作", "★ 候选声称的对象",
                 "★ 候选声称的强度", "★ 候选声称的极性", "★ 候选声称的条件",
                 "★ 候选声称的例外", "★ 候选声称的主体解析状态",
                 "★ 候选锚点行号", "★ 锚点行原文"]
# ★ 文本型列（★ 禁日期/科学计数法/标识符截断）
TEXT_COLS = set(IDENTITY_COLS) | {"★ 审核理由（必填）", "★ 审核者 ID（匿名编号）",
                                  "★ 审核日期", "★ 规范义务主体", "★ 规范义务动作",
                                  "★ 规范义务对象", "★ 条件", "★ 例外"}
LOCK_COLS = set(IDENTITY_COLS)


def _txt(ws, row, col, value):
    """★ 写入文本单元格（★ 强制文本格式 + 防公式注入）。"""
    _c = ws.cell(row=row, column=col)
    _c.value = "" if value is None else str(value)
    _c.number_format = "@"
    try:
        _c.data_type = "s"
        _c.quotePrefix = True
    except Exception:
        pass
    return _c


def _add_enum_sheet(wb):
    """★ 隐藏的枚举 sheet + 命名区域（★ 规避内联列表 255 字符上限）。"""
    _es = wb.create_sheet("_枚举")
    _names = {}
    for _i, (_k, _v) in enumerate(ENUMS.items(), start=1):
        _es.cell(row=1, column=_i, value=_k)
        for _j, _item in enumerate(_v, start=2):
            _es.cell(row=_j, column=_i, value=_item)
        _rng = f"_枚举!${get_column_letter(_i)}$2:${get_column_letter(_i)}${len(_v)+1}"
        _alias = f"ENUM_{re.sub(r'[^A-Za-z0-9]', '_', _k)}"
        _names[_alias] = _rng
        try:
            wb.defined_names.add(DefinedName(_alias, attr_text=_rng))
        except Exception:
            pass
    _es.sheet_state = "hidden"
    return _names


def _apply_dv(ws, col, alias, first_row, last_row):
    _dv = DataValidation(type="list", formula1=f"={alias}", allow_blank=True,
                         showDropDown=False)
    _dv.error = "★ 请从下拉列表中选择（★ 不得自由输入未知值）"
    _dv.errorTitle = "★ 取值不在允许集合内"
    ws.add_data_validation(_dv)
    _dv.add(f"{get_column_letter(col)}{first_row}:{get_column_letter(col)}{last_row}")
    return _dv


def build_review_xlsx(path, *, reviewer, with_arbitration=False):
    """★ 生成一份盲审 XLSX（★ 审核者 A / B）。"""
    wb = openpyxl.Workbook()
    # ── Sheet 1：说明 ──
    ws0 = wb.active
    ws0.title = "说明"
    _lines = [
        ["H3 候选人工盲审 · 审核说明"],
        [""],
        ["【这是什么】", "★ 23 条由抽取器自动生成的候选（★ 来源于 DHCPv4 的 9 份 RFC）"],
        ["【你要做什么】", "★ 逐条判断：原文是否支持该候选、它属于哪类知识、是否适用规范规则通道"],
        ["【四维判定】", "source_content_kind / knowledge_kind / rule_eligibility / evidence_sufficiency"],
        ["【重要】", "★ 表中【候选命题】与【候选声称的字段】是【待核对象】，★ 不是结论"],
        ["【重要】", "★ 不适用的规范字段请选 not_applicable 或留空，★ 不要强行填写"],
        ["【强度】", "★ 原文没明确给出强度时选 unknown，★ 不要凭推测写 MUST"],
        ["【SHOULD NOT】", "★ 强度选 SHOULD 且极性选 negative"],
        ["【无 BCP14 关键词】", "★ 没有 MUST/SHALL 大写词也可能是规范义务，★ 请依据原文判断"],
        ["【多条命题】", "★ 一条候选若含多个独立命题，★ 请在【补充知识】表新增行"],
        ["【保存】", "★ ★ 请保存为 .xlsx（★ 不要另存为 CSV；★ 仓库要求 UTF-8）"],
        ["【禁止】", "★ 不得查看另一审核者的答案 ｜★ 不得使用模型辅助生成标注"],
        ["【编号】", "★ 用匿名编号（如 REV-01 / ARB-01），★ 填入【审核者 ID】列"],
    ]
    for _r in _lines:
        ws0.append(_r)
    ws0.column_dimensions["A"].width = 18
    ws0.column_dimensions["B"].width = 96
    ws0["A1"].font = Font(bold=True, size=14)
    for _i in range(3, len(_lines) + 1):
        ws0.cell(row=_i, column=1).font = Font(bold=True)
        ws0.cell(row=_i, column=2).alignment = Alignment(wrap_text=True,
                                                        vertical="top")
    # ── Sheet 2：机器身份（★ 冻结 + 保护）──
    ws1 = wb.create_sheet("机器身份")
    ws1.append(IDENTITY_COLS)
    for _c in ws1[1]:
        _c.font = Font(bold=True, color="FFFFFF")
        _c.fill = PatternFill("solid", fgColor="44546A")
    for _r, _it in enumerate(_items, start=2):
        for _ci, _col in enumerate(IDENTITY_COLS, start=1):
            _txt(ws1, _r, _ci, _it.get(_col, ""))
        for _ci, _col in enumerate(IDENTITY_COLS, start=1):
            ws1.cell(row=_r, column=_ci).protection = Protection(locked=True)
    for _ci in range(1, len(IDENTITY_COLS) + 1):
        ws1.column_dimensions[get_column_letter(_ci)].width = \
            62 if _ci in (7, 8, 9) else 20
    ws1.freeze_panes = "B2"
    # ── Sheet 3：人工审核（★ 可填 + 下拉）──
    ws2 = wb.create_sheet("人工审核")
    _cols = ["★ 审核ID"] + [c for c, _ in REVIEW_COLS]
    ws2.append(_cols)
    for _c in ws2[1]:
        _c.font = Font(bold=True, color="FFFFFF")
        _c.fill = PatternFill("solid", fgColor="2F5597")
    for _r, _it in enumerate(_items, start=2):
        _txt(ws2, _r, 1, _it["★ 审核ID"])
        ws2.cell(row=_r, column=1).protection = Protection(locked=True)
        for _ci in range(2, len(_cols) + 1):
            _cc = ws2.cell(row=_r, column=_ci)
            _cc.number_format = "@"
            _cc.protection = Protection(locked=False)
    for _ci, _col in enumerate(_cols, start=1):
        ws2.column_dimensions[get_column_letter(_ci)].width = \
            34 if _ci >= 2 else 12
    ws2.freeze_panes = "B2"
    # ── Sheet 4：补充知识（★ 一候选多命题）──
    ws3 = wb.create_sheet("补充知识")
    _scols = ["★ 审核ID", "★ 补充命题序号", "★ 补充命题（原文约束文本）",
              "★ 补充命题所在行号", "★ source_content_kind", "★ knowledge_kind",
              "★ rule_eligibility", "★ evidence_sufficiency", "★ 主体", "★ 动作",
              "★ 对象", "★ 强度", "★ 极性", "★ 条件", "★ 例外",
              "★ 审核理由（必填）"]
    ws3.append(_scols)
    for _c in ws3[1]:
        _c.font = Font(bold=True, color="FFFFFF")
        _c.fill = PatternFill("solid", fgColor="548235")
    for _r in range(2, 2 + len(_items) * 2):
        _txt(ws3, _r, 1, "")
        ws3.cell(row=_r, column=1).protection = Protection(locked=False)
        for _ci in range(2, len(_scols) + 1):
            _cc = ws3.cell(row=_r, column=_ci)
            _cc.number_format = "@"
            _cc.protection = Protection(locked=False)
    for _ci in range(1, len(_scols) + 1):
        ws3.column_dimensions[get_column_letter(_ci)].width = \
            30 if _ci >= 3 else 14
    # ── 枚举 + 下拉 ──
    _names = _add_enum_sheet(wb)
    _alias_by_col = {}
    for _ci, (_col, _enum) in enumerate(REVIEW_COLS, start=2):
        if _enum:
            _alias_by_col[_ci] = f"ENUM_{re.sub(r'[^A-Za-z0-9]', '_', _enum)}"
            _apply_dv(ws2, _ci, _alias_by_col[_ci], 2, len(_items) + 1)
    _smap = {"★ source_content_kind": "ENUM_source_content_kind",
             "★ knowledge_kind": "ENUM_knowledge_kind",
             "★ rule_eligibility": "ENUM_rule_eligibility",
             "★ evidence_sufficiency": "ENUM_evidence_sufficiency",
             "★ 强度": "ENUM_规范强度",
             "★ 极性": "ENUM_极性"}
    for _ci, _col in enumerate(_scols, start=1):
        if _col in _smap:
            _apply_dv(ws3, _ci, _smap[_col], 2, len(_items) * 2 + 1)
    # ── 保护（★ 身份/证据 sheet 锁定；★ 人工 sheet 仅身份列锁定）──
    ws0.protection.sheet = True
    ws0.protection.password = "protokg-h3"
    ws1.protection.sheet = True
    ws1.protection.password = "protokg-h3"
    ws2.protection.sheet = True
    ws2.protection.password = "protokg-h3"
    ws3.protection.sheet = True
    ws3.protection.password = "protokg-h3"
    wb.save(path)
    return path


def build_arbitration_xlsx(path):
    """★ 第三方仲裁表（★ 不预填任何结论）。"""
    wb = openpyxl.Workbook()
    ws0 = wb.active
    ws0.title = "说明"
    for _r in [
        ["H3 候选 · 第三方仲裁表"],
        [""],
        ["【何时用】", "★ 仅在 A 与 B 出现**实质分歧**时使用"],
        ["【仲裁范围】", "★ 知识存在性 / 知识类型 / 规范效力 / 关键字段 / 证据支持"],
        ["【禁止】", "★ 不得直接复制 A 或 B 的答案而无理由"],
        ["【必须填】", "★ 匿名审核者 ID + 审核日期 + 仲裁理由 + 最终裁定状态"],
        ["【unresolved】", "★ 无法解决时保留 unresolved，★ 不得强制形成确定真值"],
    ]:
        ws0.append(_r)
    ws0.column_dimensions["A"].width = 16
    ws0.column_dimensions["B"].width = 84
    ws1 = wb.create_sheet("仲裁记录")
    _cols = ["★ 审核ID", "★ RFC 文档", "★ 证据跨度（行号）", "★ 候选命题（constraint 文本）",
             "★ A:知识类型", "★ B:知识类型", "★ 仲裁后知识类型",
             "★ A:rule_eligibility", "★ B:rule_eligibility",
             "★ 仲裁后rule_eligibility", "★ A:证据充分性", "★ B:证据充分性",
             "★ 仲裁后证据充分性", "★ 具体分歧", "★ 原文证据（行号+摘录）",
             "★ 最终裁定状态", "★ 仲裁者 ID（匿名编号）", "★ 审核日期",
             "★ 仲裁理由"]
    ws1.append(_cols)
    for _c in ws1[1]:
        _c.font = Font(bold=True, color="FFFFFF")
        _c.fill = PatternFill("solid", fgColor="833C00")
    for _r, _it in enumerate(_items, start=2):
        _txt(ws1, _r, 1, _it["★ 审核ID"])
        _txt(ws1, _r, 2, _it["★ RFC 文档"])
        _txt(ws1, _r, 3, _it["★ 证据跨度（行号）"])
        _txt(ws1, _r, 4, _it["★ 候选命题（constraint 文本）"])
        for _ci in range(5, len(_cols) + 1):
            _cc = ws1.cell(row=_r, column=_ci)
            _cc.number_format = "@"
            _cc.protection = Protection(locked=False)
    for _ci in range(1, len(_cols) + 1):
        ws1.column_dimensions[get_column_letter(_ci)].width = \
            40 if _ci in (4, 15) else 18
    ws1.freeze_panes = "B2"
    _names = _add_enum_sheet(wb)
    _apply_dv(ws1, 7, "ENUM_knowledge_kind", 2, len(_items) + 1)
    _apply_dv(ws1, 10, "ENUM_rule_eligibility", 2, len(_items) + 1)
    _apply_dv(ws1, 13, "ENUM_evidence_sufficiency", 2, len(_items) + 1)
    _apply_dv(ws1, 16, "ENUM_最终裁定状态", 2, len(_items) + 1)
    ws0.protection.sheet = True
    ws0.protection.password = "protokg-h3"
    ws1.protection.sheet = True
    ws1.protection.password = "protokg-h3"
    wb.save(path)
    return path


# ══ 生成 ══
print("  ★ 生成 XLSX")
_pa = build_review_xlsx(DELIV / "H3_23候选_审核者A_盲审模板.xlsx", reviewer="A")
_pb = build_review_xlsx(DELIV / "H3_23候选_审核者B_盲审模板.xlsx", reviewer="B")
_pr = build_arbitration_xlsx(DELIV / "H3_23候选_第三方仲裁模板.xlsx")
for _p in (_pa, _pb, _pr):
    print(f"      {_p.name}｜{_p.stat().st_size} bytes｜"
          f"sha256={hashlib.sha256(_p.read_bytes()).hexdigest()[:16]}")

# ══ 机器基线 JSONL ══
_baseline = OUTD / "h3_machine_baseline.jsonl"
with _baseline.open("w", encoding="utf-8") as f:
    for _it in _items:
        _c = next(c for c in H3 if c["★ document_id"] == _it["★ RFC 文档"]
                  and f'{c["★ source_span"][0]}-{c["★ source_span"][1]}'
                  == _it["★ 证据跨度（行号）"])
        f.write(json.dumps({
            "★ 审核ID": _it["★ 审核ID"],
            "★ candidate_id": _c["★ candidate_id"],
            "★ norm_id": _c["★ norm（★ 派生层输出）"].get("norm_id"),
            "★ chunk_id": _c["★ chunk_id"],
            "★ document_id": _it["★ RFC 文档"],
            "★ protocol": _it["★ 协议"],
            "★ source_sha256": _it["★ RFC SHA256"],
            "★ source_span": _c["★ source_span"],
            "★ evidence_text": _it["★ 证据原文（RFC 逐行）"],
            "★ evidence_text_sha256": hashlib.sha256(
                _it["★ 证据原文（RFC 逐行）"].encode()).hexdigest(),
            "★ candidate_proposition": _it["★ 候选命题（constraint 文本）"],
            "★ candidate_meaning": _it["★ 候选含义（meaning 文本）"],
            "★ candidate_claimed_fields": {
                "subject": _it["★ 候选声称的主体"], "action": _it["★ 候选声称的动作"],
                "object": _it["★ 候选声称的对象"], "strength": _it["★ 候选声称的强度"],
                "polarity": _it["★ 候选声称的极性"], "condition": _it["★ 候选声称的条件"],
                "exception": _it["★ 候选声称的例外"]},
            "★ run_id": _c["★ run_id"], "★ model": _c["★ model"],
            "★ prompt_digest": _c["★ prompt_digest"],
            "★ schema_version": _c["★ schema_version"],
        }, ensure_ascii=False) + "\n")
print(f"  ★ 机器基线：{len(_items)} 条｜sha256="
      f"{hashlib.sha256(_baseline.read_bytes()).hexdigest()[:16]}")

# ══ 只读 HTML 证据包 ══
_h = ["<!DOCTYPE html><html lang='zh-CN'><head><meta charset='utf-8'>",
      "<title>H3 23 候选 · 只读 RFC 证据包</title><style>",
      "body{font-family:Consolas,'Microsoft YaHei',monospace;margin:24px;line-height:1.55}",
      "h2{font-size:15px;margin:22px 0 6px;padding:6px 10px;background:#eef3fa;border-left:4px solid #3a6ea5}",
      ".m{color:#555;font-size:12px}.p{background:#fffbe6;border:1px solid #e0c97a;padding:8px 12px;margin:10px 0}",
      "table.ln{border-collapse:collapse;width:100%;margin:6px 0 12px}",
      "table.ln td{padding:1px 8px;font-size:12.5px;vertical-align:top}",
      "td.no{width:54px;color:#888;text-align:right;background:#f6f6f6}",
      "tr.ev td{background:#fff6d8;font-weight:600}.q{background:#eef7ee;padding:6px 10px;margin:4px 0}",
      "</style></head><body>",
      "<h1>H3 · 23 条候选的只读 RFC 证据包</h1>",
      "<div class='p'><b>给审核者：</b>本包是<b>只读</b>的 RFC 原文证据。"
      "<br>① 请在 <code>H3_23候选_审核者X_盲审模板.xlsx</code> 的【人工审核】表填写。"
      "<br>② 本包<b>不含</b>任何机器类型预测、路由结果或另一审核者答案。"
      "<br>③ 候选命题与候选声称的字段是<b>待核对象</b>，不是结论。</div>"]
for _it in _items:
    _doc = _it["★ RFC 文档"]
    _pp = ROOT / f'kb/{_it["★ 协议"]}/spec/{_doc}'
    _L = _pp.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _lo, _hi = [int(x) for x in _it["★ 证据跨度（行号）"].split("-")]
    _h.append(f"<h2>{html.escape(_it['★ 审核ID'])}</h2>")
    _h.append(f"<div class='m'>{html.escape(_doc)} ｜ 行 {_lo}–{_hi} ｜ "
              f"sha256 <code>{_it['★ RFC SHA256'][:16]}…</code></div>")
    _h.append(f"<div class='q'><b>候选命题（待核）：</b>"
              f"{html.escape(_it['★ 候选命题（constraint 文本）']) or '<i>（空）</i>'}<br>"
              f"<b>候选含义（待核）：</b>{html.escape(_it['★ 候选含义（meaning 文本）'])}</div>")
    _h.append("<table class='ln'>")
    for _i in range(max(1, _lo - 6), min(len(_L), _hi + 6) + 1):
        _cls = "ev" if _lo <= _i <= _hi else ""
        _h.append(f"<tr class='{_cls}'><td class='no'>{_i}</td>"
                  f"<td>{html.escape(_L[_i-1]) or '&nbsp;'}</td></tr>")
    _h.append("</table>")
_h.append("</body></html>")
_hp = DELIV / "H3_23候选_只读RFC证据包.html"
_hp.write_text("\n".join(_h), encoding="utf-8")
print(f"  ★ 只读证据包：{_hp.name}｜sha256="
      f"{hashlib.sha256(_hp.read_bytes()).hexdigest()[:16]}")
(OUTD / "_items.json").write_text(json.dumps(_items, ensure_ascii=False, indent=2),
                                encoding="utf-8")
print(f"  ⇒ {DELIV}")
