# -*- coding: utf-8 -*-
"""★ N1-C 阶段：★ **差异报告 + 工作副本合成修复**。

★ 依据用户指令：★「任何身份、证据或候选字段发生非预期改变，★ 立即停止评估并提交差异报告」
★ ⇒ ★ **本脚本只做「输入修复」，★ 不修改 V0/V1 判据、★ 不修改 M1~M8 定义**

★ 修复方式（★ 完全可复算）：
  · 26 个**不可编辑列**（★ 候选与证据）⇒ ★ **从 git 发放时冻结版取回**（★ 无损）
  · 10+1 个**可编辑标签列**（★ 审核者填写）⇒ ★ **从回收文件取回**（★ 完整保留）
  · ★ 被 Excel 破坏引号导致的**断行**⇒ ★ **按冻结版的行骨架重组**
★ ★ **原件（GB18030）保留在 `archive_n1c_received/`**（★ 不修改）
"""
import collections
import csv
import io
import json
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
OUTD = ROOT / "guard/_out/_n1c"
ARCH = OUTD / "archive_n1c_received"
WORK = OUTD / "work_n1c_utf8"
FIXED = OUTD / "work_n1c_fixed"
FIXED.mkdir(parents=True, exist_ok=True)
ISSUED = "61572e7"
GBASE = "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
FIELDS = ["subject", "action", "object", "strength", "polarity", "condition",
          "exception", "evidence_support", "truth_label", "review_note"]
NAMES = {"A": "N1-C_盲审标注表_A.csv", "B": "N1-C_盲审标注表_B.csv",
         "ARB": "N1-C_仲裁表.csv"}


def _dec(p):
    b = pathlib.Path(p).read_bytes()
    try:
        return b.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return b.decode("gb18030"), "gb18030"


def _rows(text):
    return list(csv.DictReader(io.StringIO(text).read().splitlines()))


def _gold(name):
    _g = subprocess.run(["git", "show", f"{ISSUED}:{GBASE}/{name}"],
                        capture_output=True, cwd=str(ROOT))
    if _g.returncode != 0:
        raise SystemExit(f"★ 无法取发放时版本：{name}")
    return _g.stdout.decode("utf-8")


report = {"★ 差异分类": {}, "★ 修复": {}}
_diff_detail = []

for _tag in ("A", "B"):
    _name = NAMES[_tag]
    _gold_txt = _gold(_name)
    _gold_rows = _rows(_gold_txt)
    _gold_hdr = list(csv.reader(io.StringIO(_gold_txt).read().splitlines()))[0]
    # ★ 回收文件（GB18030）
    _rec_txt, _enc = _dec(DELIV / _name)
    _rec_rows = _rows(_rec_txt)
    _lbl_cols = [f"★ {_tag}:{f}" for f in FIELDS] + [f"★ {_tag}:审核者"]
    # ★ 回收文件里被拆行的样本：★ 其标签值可能落在相邻行
    _rec_by_id = {}
    _spill = []
    for _r in _rec_rows:
        _sid = (_r.get("sample_id") or "").strip()
        if _sid in {g["sample_id"] for g in _gold_rows}:
            _rec_by_id[_sid] = _r
        else:
            _spill.append(_r)
    # ★ 逐单元格差异（只报证据/候选列 ⇒ 标签列不算）
    _imm = [c for c in _gold_hdr if c not in _lbl_cols]
    _diffs = []
    for _g in _gold_rows:
        _sid = _g["sample_id"]
        _r = _rec_by_id.get(_sid)
        if not _r:
            continue
        for _c in _imm:
            _a = (_g.get(_c) or "")
            _b = (_r.get(_c) or "")
            if _a != _b:
                _kind = ("★ 换行标记 ⏎→?（★ Excel GB18030 字符集替换）"
                         if ("⏎" in _a and "?" in _b) else
                         ("★ 布尔规范化 False→FALSE" if _a in ("False", "True")
                          and _b in ("FALSE", "TRUE") else "★ 其他"))
                _diffs.append({"sample_id": _sid, "col": _c, "★ 类型": _kind,
                               "发放时": _a[:80], "现在": _b[:80]})
    _types = collections.Counter(d["★ 类型"] for d in _diffs)
    print(f"  ★ {_name}：不可编辑列差异 {len(_diffs)} 处｜类型 {dict(_types)}")
    report["★ 差异分类"].setdefault(_name, dict(_types))
    _diff_detail.append({"file": _name, "★ 差异明细（前 5）": _diffs[:5],
                          "★ 断行产生的多余行数": len(_spill),
                          "★ 多余行首列样例": [s.get("sample_id", "")[:50]
                                          for s in _spill[:2]]})
    # ★ ★ 合成修复工作副本：★ 证据列取冻结版（★ 无损）、★ 标签列取回收版
    _out_hdr = _gold_hdr
    # ★ ★ 断行样本的标签恢复：★ Excel 未转义换行 ⇒ 该行被拆成两段，
    #   ★ 第二段的 [2..12] ⇒ 对应表头 [27..37]（★ 偏移 -25）
    _spill_by_hdr = {}
    _rec_raw = list(csv.reader(_rec_txt.splitlines()))
    for _rr in _rec_raw:
        if len(_rr) == 12 and (_rr[9] or "").strip() in (
                "valid_confirmed", "valid_rejection",
                "pending_insufficient_evidence", "uncertain_requires_human"):
            _spill_by_hdr = {i: (_rr[i - 25] if 0 <= i - 25 < len(_rr) else "")
                            for i in range(26, 37)}
    _out_rows = []
    for _g in _gold_rows:
        _sid = _g["sample_id"]
        _r = _rec_by_id.get(_sid, {})
        _row = dict(_g)
        for _c in _lbl_cols:
            _row[_c] = (_r.get(_c) or "")
        # ★ 断行样本：★ 标签列从错位行恢复（★ 若主记录为空）
        if not any((_row.get(c) or "").strip() for c in _lbl_cols)                 and _spill_by_hdr:
            for _i in range(26, 37):
                _row[_gold_hdr[_i]] = _spill_by_hdr.get(_i, "")
        _out_rows.append(_row)
    _buf = io.StringIO()
    _w = csv.DictWriter(_buf, fieldnames=_out_hdr, lineterminator="\n")
    _w.writeheader()
    _w.writerows(_out_rows)
    (FIXED / _name).write_text(_buf.getvalue(), encoding="utf-8", newline="\n")
    report["★ 修复"][_name] = {
        "★ 行数": len(_out_rows), "★ 列数": len(_out_hdr),
        "★ 证据/候选列来源": "★ git 发放时冻结版（★ 无损）",
        "★ 标签列来源": "★ 回收文件（★ 审核者填写）",
        "★ 已填标签数": sum(1 for r in _out_rows for c in _lbl_cols
                        if (r.get(c) or "").strip()),
        "★ 与冻结版证据列差异": 0,
    }
    print(f"      ⇒ 修复副本 {FIXED.name}/{_name}：{len(_out_rows)} 行 × {len(_out_hdr)} 列"
          f"｜已填标签 {report['★ 修复'][_name]['★ 已填标签数']}")

# ★ 仲裁表：★ 全部列都是可填列 ⇒ ★ 只做编码转换（★ 不合成）
_gold_txt = _gold(NAMES["ARB"])
_gold_rows = _rows(_gold_txt)
_gold_hdr = list(csv.reader(io.StringIO(_gold_txt).read().splitlines()))[0]
_rec_txt, _enc = _dec(DELIV / NAMES["ARB"])
_rec_rows = _rows(_rec_txt)
_rec_by_id = {r["sample_id"]: r for r in _rec_rows}
_out_rows = []
for _g in _gold_rows:
    _r = _rec_by_id.get(_g["sample_id"], {})
    _row = dict(_g)
    for _c in _gold_hdr:
        _row[_c] = (_r.get(_c) or "")
    _out_rows.append(_row)
_buf = io.StringIO()
_w = csv.DictWriter(_buf, fieldnames=_gold_hdr, lineterminator="\n")
_w.writeheader()
_w.writerows(_out_rows)
(FIXED / NAMES["ARB"]).write_text(_buf.getvalue(), encoding="utf-8", newline="\n")
print(f"  ★ 仲裁表修复副本：{len(_out_rows)} 行 × {len(_gold_hdr)} 列"
      f"｜已填 {sum(1 for r in _out_rows for c in _gold_hdr if (r.get(c) or '').strip())} 个单元格")
report["★ 修复"][NAMES["ARB"]] = {"★ 行数": len(_out_rows), "★ 列数": len(_gold_hdr),
                            "★ 说明": "★ 仲裁表全部列为可填列 ⇒ ★ 仅做编码转换与行骨架对齐"}

report["★ 差异明细"] = _diff_detail
(OUTD / "n1c_input_diff_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'n1c_input_diff_report.json'}")
print(f"  ⇒ 修复副本目录：{FIXED}")
