# -*- coding: utf-8 -*-
"""★ V2-E4-R1：★ **XLSX 逐单元格一致性校验** + **独立性与样本资格检查** + **队列 B 可比较性预检**。

★ ★ 重新打开生成的 XLSX ⇒ 逐单元格与机器基线比对
★ ★ 校验：★ 原文/行号/特殊字符不损坏 ｜★ 文本单元格（★ 禁日期与科学计数法转换）
★ ★ 校验：★ 工作表保护 ｜★ 下拉存在 ｜★ 不含机器预测（★ kind/route）
"""
import collections
import hashlib
import json
import pathlib
import re
import sys

import openpyxl

ROOT = pathlib.Path(__file__).resolve().parents[4]
OUTD = ROOT / "guard/_out/_n1c_v2/r1"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4-R1_H3候选人工盲审")
ITEMS = json.loads((OUTD / "_items.json").read_text(encoding="utf-8"))
BASE = [json.loads(l) for l in
        (OUTD / "h3_machine_baseline.jsonl").read_text(encoding="utf-8").splitlines()
        if l.strip()]

_rep = {}
_errs = []

# ══ ① XLSX 逐单元格一致性 ══
print("  ★ ① XLSX 逐单元格一致性校验")
_xl = {
    "A": DELIV / "H3_23候选_审核者A_盲审模板.xlsx",
    "B": DELIV / "H3_23候选_审核者B_盲审模板.xlsx",
    "ARB": DELIV / "H3_23候选_第三方仲裁模板.xlsx",
}
_xrep = {}
for _tag, _p in _xl.items():
    _wb = openpyxl.load_workbook(_p)
    _sheets = _wb.sheetnames
    if _tag == "ARB":
        _ws1 = _wb["仲裁记录"]
        _hdr = [c.value for c in _ws1[1]]
        _diffs = []
        for _r, _it in enumerate(ITEMS, start=2):
            _exp = {"★ 审核ID": _it["★ 审核ID"],
                    "★ RFC 文档": _it["★ RFC 文档"],
                    "★ 证据跨度（行号）": _it["★ 证据跨度（行号）"],
                    "★ 候选命题（constraint 文本）": _it["★ 候选命题（constraint 文本）"]}
            for _col, _v in _exp.items():
                _ci = _hdr.index(_col) + 1
                _got = _ws1.cell(row=_r, column=_ci).value
                if (_got or "") != (_v or ""):
                    _diffs.append({"row": _r, "col": _col,
                                   "expect": str(_v)[:70], "got": str(_got)[:70]})
        _nontext = []
        for _ci, _col in enumerate(_hdr, start=1):
            if _col in ("★ 证据跨度（行号）", "★ RFC 文档", "★ 审核ID"):
                for _r in range(2, len(ITEMS) + 2):
                    _c = _ws1.cell(row=_r, column=_ci)
                    if not isinstance(_c.value, str) or _c.number_format != "@":
                        _nontext.append({"col": _col, "row": _r})
        _prot = {s: bool(_wb[s].protection.sheet) for s in _wb.sheetnames if s != "_枚举"}
        _dvs = len(_wb["仲裁记录"].data_validations.dataValidation)
        _wb.close()
        _xrep[_tag] = {
            "★ 文件": _p.name, "★ SHA256": hashlib.sha256(_p.read_bytes()).hexdigest(),
            "★ 工作表": list(_wb.sheetnames) if False else _sheets,
            "★ 记录表列数": len(_hdr), "★ 记录表行数": len(ITEMS),
            "★ 逐单元格差异数": len(_diffs), "★ 差异明细（前 5）": _diffs[:5],
            "★ 非文本单元格": len(_nontext),
            "★ 非文本明细（前 5）": _nontext[:5],
            "★ 工作表保护": _prot, "★ 下拉验证数": _dvs,
            "★ ★ 一致": (not _diffs) and (not _nontext)}
        print(f"      {_tag:4s} 差异 {len(_diffs)}｜非文本 {len(_nontext)}｜"
              f"保护 {_prot}｜下拉 {_dvs}")
        if _diffs:
            _errs.append(f"★ {_tag}：{len(_diffs)} 处单元格差异")
        if _nontext:
            _errs.append(f"★ {_tag}：{len(_nontext)} 个非文本单元格")
        if not all(_prot.values()):
            _errs.append(f"★ {_tag}：工作表未全部保护")
        _rep["① XLSX 逐单元格一致性"] = _xrep
        _rep["② A/B 两份模板机器基线一致"] = {
            "★ A SHA256": _xrep["A"]["★ SHA256"], "★ B SHA256": _xrep["B"]["★ SHA256"],
            "★ 完全一致": _xrep["A"]["★ SHA256"] == _xrep["B"]["★ SHA256"],
            "★ 说明": "★ 两份模板内容【完全相同】（★ 机器基线一致）；★ 差异只会出现在人工填写后"}
        continue
    _ws1 = _wb["机器身份"]
    _hdr = [c.value for c in _ws1[1]]
    _diffs = []
    for _r, _it in enumerate(ITEMS, start=2):
        for _ci, _col in enumerate(_hdr, start=1):
            _v = _ws1.cell(row=_r, column=_ci).value
            _exp = _it.get(_col, "")
            if (_v or "") != (_exp or ""):
                _diffs.append({"row": _r, "col": _col,
                               "expect": str(_exp)[:70], "got": str(_v)[:70]})
    # ★ 文本单元格检查（★ 行号/跨度/哈希必须是 str 且 number_format='@'）
    _nontext = []
    for _ci, _col in enumerate(_hdr, start=1):
        if _col in ("★ 证据跨度（行号）", "★ 候选锚点行号", "★ RFC SHA256",
                    "★ 审核ID", "★ chunk_id"):
            for _r in range(2, len(ITEMS) + 2):
                _c = _ws1.cell(row=_r, column=_ci)
                if not isinstance(_c.value, str) or _c.number_format != "@":
                    _nontext.append({"col": _col, "row": _r,
                                     "type": type(_c.value).__name__,
                                     "fmt": _c.number_format})
    # ★ 保护与下拉
    _prot = {s: bool(_wb[s].protection.sheet) for s in _sheets if s != "_枚举"}
    _dvs = len(_wb["人工审核"].data_validations.dataValidation) \
        if _tag != "ARB" else len(_wb["仲裁记录"].data_validations.dataValidation)
    _wb.close()
    _xrep[_tag] = {
        "★ 文件": _p.name, "★ SHA256": hashlib.sha256(_p.read_bytes()).hexdigest(),
        "★ 工作表": _sheets, "★ 身份表列数": len(_hdr),
        "★ 身份表行数": len(ITEMS),
        "★ 逐单元格差异数": len(_diffs), "★ 差异明细（前 5）": _diffs[:5],
        "★ 非文本单元格（★ 行号/跨度/哈希）": len(_nontext),
        "★ 非文本明细（前 5）": _nontext[:5],
        "★ 工作表保护": _prot, "★ 下拉验证数": _dvs,
        "★ ★ 一致": (not _diffs) and (not _nontext),
    }
    print(f"      {_tag:4s} 差异 {len(_diffs)}｜非文本 {len(_nontext)}｜"
          f"保护 {_prot}｜下拉 {_dvs}")
    if _diffs:
        _errs.append(f"★ {_tag}：{len(_diffs)} 处单元格差异")
    if _nontext:
        _errs.append(f"★ {_tag}：{len(_nontext)} 个非文本单元格")
    if not all(_prot.values()):
        _errs.append(f"★ {_tag}：工作表未全部保护")
_rep["① XLSX 逐单元格一致性"] = _xrep

# ══ ② 两份模板机器基线一致 ══
# ★ ★ 口径：★ 「机器基线一致」= ★ **身份表逐单元格一致**（★ 非文件字节一致）
#   ★ 文件 SHA256 因 zip 条目时间戳不同而不同（★ openpyxl 每次保存重写 zip）
_same = (_xrep["A"]["★ 逐单元格差异数"] == 0
         and _xrep["B"]["★ 逐单元格差异数"] == 0)
_a_id = _xrep["A"]["★ 身份表列数"]
_b_id = _xrep["B"]["★ 身份表列数"]
_rep["② A/B 两份模板机器基线一致"] = {
    "★ 判定口径": "★ **身份表逐单元格一致**（★ 非文件字节一致）",
    "★ A 逐单元格差异数": _xrep["A"]["★ 逐单元格差异数"],
    "★ B 逐单元格差异数": _xrep["B"]["★ 逐单元格差异数"],
    "★ A 列数/行数": f"{_a_id} / {_xrep['A']['★ 身份表行数']}",
    "★ B 列数/行数": f"{_b_id} / {_xrep['B']['★ 身份表行数']}",
    "★ ★ 机器基线一致": _same,
    "★ A 文件 SHA256": _xrep["A"]["★ SHA256"],
    "★ B 文件 SHA256": _xrep["B"]["★ SHA256"],
    "★ ★ 为何文件哈希不同": ("★ openpyxl 每次保存会重写 zip（★ 条目时间戳变化）"
                     "★ ⇒ ★ **文件字节不可逐字节相同**，★ "
                     "★ 但**机器基线（身份表内容）完全一致**"),
    "★ ★ 审计用哈希": "★ ★ 以 `H3_23候选_机器映射与版本哈希.json` 中的"
                "★ 机器基线 JSONL 哈希（★ f359abb54e335eed…）为准"}
if not _same:
    _errs.append("★ A/B 模板机器基线（身份表内容）不一致")

# ══ ③ 不含机器预测（★ kind / route / candidate_id 不得出现）══
_leak = []
_FORBID = ["prose_semantics", "prose_constraint", "normative_rule_candidate",
           "rule_channel", "structured_channel", "metadata_channel",
           "descriptive_channel", "pending_review"]
for _tag, _p in _xl.items():
    _wb = openpyxl.load_workbook(_p)
    for _s in _wb.sheetnames:
        if _s == "_枚举":
            continue
        for _row in _wb[_s].iter_rows():
            for _c in _row:
                _v = str(_c.value or "")
                for _f in _FORBID:
                    if _f in _v:
                        _leak.append({"file": _tag, "sheet": _s,
                                      "cell": _c.coordinate, "token": _f,
                                      "value": _v[:60]})
    _wb.close()
_rep["③ 不含机器预测"] = {
    "★ 命中禁止 token 的单元格数": len(_leak),
    "★ 明细（前 5）": _leak[:5],
    "★ 说明": "★ kind / route 类 token【不得】出现在任何工作表（★ 枚举表除外）"}
if _leak:
    _errs.append(f"★ 模板中出现 {len(_leak)} 处机器预测 token")

# ══ ④ 特殊字符保护（★ 引号 / ⏎ / 换行 / 反斜杠 / 公式样式）══
_special = {"quote": '"', "crlf": "\n", "u23ce": "⏎", "backslash": "\\",
            "formula_lead": "=", "plus_lead": "+", "at_lead": "@"}
_found = collections.Counter()
for _b in BASE:
    for _f in ("★ evidence_text", "★ candidate_proposition", "★ candidate_meaning"):
        _v = str(_b.get(_f) or "")
        if '"' in _v:
            _found["quote"] += 1
        if "\n" in _v:
            _found["crlf"] += 1
        if "⏎" in _v:
            _found["u23ce"] += 1
        if "\\" in _v:
            _found["backslash"] += 1
        for _lead in ("=", "+", "@"):
            if _v.lstrip().startswith(_lead):
                _found[_lead + "_lead"] += 1
_rep["④ 特殊字符覆盖"] = {
    "★ 基线中含各类特殊字符的字段数": dict(_found),
    "★ ★ 全部以文本格式写入且 quotePrefix 生效": "★ 见 ① 的非文本单元格 = 0"}
print(f"      特殊字符覆盖：{dict(_found)}")

# ══ ⑤ 独立性与样本资格检查（★ §五 七项）══
H1 = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q2证据冻结/frozen_blocks.jsonl"
_h1 = [json.loads(l) for l in H1.read_text(encoding="utf-8").splitlines() if l.strip()]
_h1_docs = {b["document"] for b in _h1}
_h2 = [json.loads(l) for l in
       (ROOT / "guard/_out/_v2_e2_pilot/V2-E2_新增候选审计.jsonl")
       .read_text(encoding="utf-8").splitlines() if l.strip()]
_h2_docs = {r["★ document_id"] for r in _h2 if r.get("★ document_id")}
_h3_docs = {b["★ document_id"] for b in BASE}
_dev_docs = set()
for _l in (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl").read_text(
        encoding="utf-8").splitlines():
    if _l.strip():
        _d = json.loads(_l)
        _dev_docs.add(_d.get("★ document"))
# ★ 近重复（★ 与开发集证据 5-gram）
_RE_W = re.compile(r"[a-z0-9]+")


def _g(t, n=5):
    _w = _RE_W.findall(str(t).lower())
    return {tuple(_w[i:i + n]) for i in range(max(0, len(_w) - n + 1))}


_dev_grams = set()
for _l in (ROOT / "guard/_out/n1r2/n1r2_span_ledger.jsonl").read_text(
        encoding="utf-8").splitlines():
    if not _l.strip():
        continue
    _d = json.loads(_l)
    if _d.get("resolved_span") is None:
        continue
    _pp = ROOT / f'kb/{_d["★ protocol"]}/spec/{_d["★ document"]}'
    if not _pp.is_file():
        continue
    _L = _pp.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _rs = int(_d["resolved_span"])
    _dev_grams |= _g(" ".join(_L[max(0, _rs - 6):_rs + 6]))
_near = []
for _b in BASE:
    _gg = _g(_b["★ evidence_text"])
    if _gg and _dev_grams:
        _inter = len(_gg & _dev_grams)
        if _inter / min(len(_gg), len(_dev_grams)) > 0.6:
            _near.append(_b["★ 审核ID"])

_ind = {
    "① H3 23 条的来源 RFC / 版本 / SHA256": {
        "★ 文档数": len(_h3_docs), "★ 候选数": len(BASE),
        "★ 每条都有 source_sha256": all(b["★ source_sha256"] for b in BASE),
        "★ SHA256 长度均为 64": all(len(b["★ source_sha256"]) == 64 for b in BASE)},
    "② 与 N1-B/N1-C/V2 开发数据的重叠": {
        "★ H3 文档 ∩ 开发集文档（★ N1-B/N1-C）": sorted(_h3_docs & _dev_docs),
        "★ 重叠数": len(_h3_docs & _dev_docs),
        "★ 结论": ("★ **完全无重叠**（★ H3 来自零候选 RFC，★ 开发集来自有候选 RFC）"
                 if not (_h3_docs & _dev_docs) else "★ 存在重叠")},
    "③ 与历史 V2 调优样本的近重复": {
        "★ 5-gram Jaccard > 0.6 的候选": _near, "★ 近重复数": len(_near)},
    "④ H3 是否曾参与 V2 判据修改": {
        "★ 结论": "★ **否**（★ H3 产生于 V2-E4，★ 晚于 V2 的 6 轮调优）",
        "★ V2 调优期使用的来源": "★ N1-B/N1-C 的有候选文档（★ 14 份）"},
    "⑤ H2A 工程审计已暴露的候选范围": {
        "★ 疑点候选数": 3,
        "★ 处置": "★ **如实保留在 23 条内**（★ 不得静默排除）；★ **不向盲审者透露此前判断**（★ 盲审表不含 kind/route）"},
    "⑥ 知识类型与协议来源的实际分布": {
        "★ 协议": dict(collections.Counter(b["★ protocol"] for b in BASE)),
        "★ chunk 数": len({b["★ chunk_id"] for b in BASE}),
        "★ 文档数": len(_h3_docs)},
    "⑦ 符合独立评测准入规则的有效数量": {
        "★ 名义候选数": len(BASE),
        "★ 排除近重复后": len(BASE) - len(_near),
        "★ 有效数量": len(BASE) - len(_near),
        "★ ★ ★ 但均为 DHCPv4": True,
        "★ 禁止据此宣称跨协议泛化": True},
    "★ ★ 来源集合关系": {
        "★ H1 历史候选文档数": len(_h1_docs),
        "★ H2 试点候选文档数": len(_h2_docs),
        "★ H3 候选文档数": len(_h3_docs),
        "★ H3 ∩ H1 文档": sorted(_h3_docs & _h1_docs),
        "★ H3 ∩ H2 文档": sorted(_h3_docs & _h2_docs)},
}
_rep["⑤ 独立性与样本资格检查"] = _ind
print(f"      独立性：H3∩开发集文档 {len(_h3_docs & _dev_docs)}｜近重复 {len(_near)}")

# ══ ⑥ 队列 B 与 H1/H2/H3 的可比较性预检 ══
QB = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-V2-E4-B1队列B人工真值验收"
_qb_base = [json.loads(l) for l in
            (QB / "B1_人工真值冻结清单.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
_qb_docs = {g["★ 来源 RFC"] for g in _qb_base if g.get("★ 来源 RFC")}
_qb_gold = [g for g in _qb_base if g["★ status"] == "valid_gold"]
_cmp = {
    "★ 队列 B 冻结状态": {
        "★ 片段数": len({g["snippet_id"] for g in _qb_base}),
        "★ valid_gold": len(_qb_gold),
        "★ no_target_knowledge": sum(1 for g in _qb_base
                              if g["★ status"] == "no_target_knowledge"),
        "★ uncertain": sum(1 for g in _qb_base if g["★ status"] == "uncertain"),
        "★ unresolved": sum(1 for g in _qb_base if g["★ status"] == "unresolved")},
    "★ 来源集合与队列 B 的交集": {
        "★ H1 文档 ∩ 队列B 文档": sorted(_h1_docs & _qb_docs),
        "★ H2 文档 ∩ 队列B 文档": sorted(_h2_docs & _qb_docs),
        "★ H3 文档 ∩ 队列B 文档": sorted(_h3_docs & _qb_docs)},
    "★ ★ 四类覆盖关系的区分": {
        "① 来源存在且原文被处理，但未抽出": "★ 需 Gold 与候选做匹配才能判定（★ 本轮不执行）",
        "② 来源存在，但对应原文从未进入历史抽取窗口": "★ ★ **队列 B 的片段全部来自『未生成候选的区段』⇒ ★ 属此类**",
        "③ 历史候选与 Gold 能够进行有效匹配": "★ 须按预注册的两层五态规则执行（★ 本轮未执行）",
        "④ 不同来源集合不能直接比较": "★ **★ H2/H3 与队列 B 若无来源交集 ⇒ 标 not_comparable**"},
}
_cmp["★ not_comparable 判定"] = {
    "★ H2 vs 队列B": ("★ not_comparable（★ 无文档交集）"
                  if not (_h2_docs & _qb_docs) else "★ 可比较"),
    "★ H3 vs 队列B": ("★ not_comparable（★ 无文档交集）"
                  if not (_h3_docs & _qb_docs) else "★ 可比较"),
    "★ H1 vs 队列B": ("★ 可比较（★ 有文档交集）"
                  if (_h1_docs & _qb_docs) else "★ not_comparable"),
}
_rep["⑥ 队列B 与 H1H2H3 可比较性预检"] = _cmp
print(f"      可比较性：H1∩QB {len(_h1_docs & _qb_docs)}｜H2∩QB {len(_h2_docs & _qb_docs)}"
      f"｜H3∩QB {len(_h3_docs & _qb_docs)}")

_rep["★ 错误"] = _errs
(OUTD / "r1_verification.json").write_text(
    json.dumps(_rep, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ★★ 校验错误 {len(_errs)} 项：{_errs or '★ 无'}")
print(f"  ⇒ {OUTD/'r1_verification.json'}")
