# -*- coding: utf-8 -*-
"""★ N1-C 阶段：★ **输入完整性检查**（★ 揭盲后、评估前，★ 必须最先执行）。

★ 步骤：
  ① 归档三份原件（★ GB18030）+ SHA256（★ **不修改原件**）
  ② 生成 UTF-8 工作副本 ＋ **逐单元格**验证转换前后内容完全一致
  ③ 从 git（★ 发放时提交 `61572e7`）取原始 UTF-8 版本，
     ★ 逐单元格比对 **26 个不可编辑的候选与证据列**（★ 任何非预期改变 ⇒ 立即停止）
  ④ **重新复算**全部数字（★ 不写死）
★ ★ **不执行评估**；★ **不修改 V0/V1 判据或 M1~M8 定义**；★ **0 次 LLM**
"""
import collections
import csv
import hashlib
import io
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
OUTD = ROOT / "guard/_out/_n1c"
ARCH = OUTD / "archive_n1c_received"
ARCH.mkdir(parents=True, exist_ok=True)
WORK = OUTD / "work_n1c_utf8"
WORK.mkdir(parents=True, exist_ok=True)
ISSUED_COMMIT = "61572e7"
NAMES = ["N1-C_盲审标注表_A.csv", "N1-C_盲审标注表_B.csv", "N1-C_仲裁表.csv"]
# ★ 26 个不可编辑列（★ 37 列 − A/B 标签 10 列 − 审核者 1 列）
LABEL_COLS_A = [f"★ A:{f}" for f in
                ("subject", "action", "object", "strength", "polarity",
                 "condition", "exception", "evidence_support", "truth_label",
                 "review_note")] + ["★ A:审核者"]
LABEL_COLS_B = [f"★ B:{f}" for f in
                ("subject", "action", "object", "strength", "polarity",
                 "condition", "exception", "evidence_support", "truth_label",
                 "review_note")] + ["★ B:审核者"]

_errs = []
_warn = []
_report = {}

# ══ ① 归档原件 + 哈希 ══
print("  ★ ① 归档原件")
for _n in NAMES:
    _p = DELIV / _n
    _b = _p.read_bytes()
    _sha = hashlib.sha256(_b).hexdigest()
    (ARCH / _n).write_bytes(_b)
    _enc = "utf-8"
    try:
        _b.decode("utf-8")
    except UnicodeDecodeError:
        _enc = "gb18030"
    print(f"      {_n:26s} 编码={_enc} CRLF={_b.count(b(chr(13)+chr(10),'ascii')) if False else _b.count(bytes([13,10]))}"
          f" LF={_b.count(bytes([10]))} sha={_sha[:16]}")
    _report.setdefault("★ 原件归档", {})[_n] = {
        "sha256": _sha, "★ 编码": _enc,
        "★ CRLF": _b.count(bytes([13, 10])), "★ LF": _b.count(bytes([10])),
        "★ 归档与原件一致": hashlib.sha256((ARCH / _n).read_bytes()).hexdigest() == _sha}

# ══ ② UTF-8 工作副本 + 逐单元格验证 ══
print()
print("  ★ ② UTF-8 工作副本 ＋ 逐单元格验证")
def _decode(p):
    _b = p.read_bytes()
    try:
        return _b.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return _b.decode("gb18030"), "gb18030"


def _to_rows(text):
    return list(csv.DictReader(io.StringIO(text).read().splitlines()))


_conv = {}
for _n in NAMES:
    _txt, _enc = _decode(DELIV / _n)
    _rows_old = _to_rows(_txt)
    _hdr = list(csv.reader(io.StringIO(_txt).read().splitlines()))[0]
    _new_txt = _txt.replace("\r\n", "\n").replace("\r", "\n")
    if _new_txt.startswith("\ufeff"):
        _new_txt = _new_txt[1:]
    _dst = WORK / _n
    _dst.write_text(_new_txt, encoding="utf-8", newline="\n")
    _rows_new = _to_rows(_dst.read_text(encoding="utf-8"))
    _diff = []
    if len(_rows_old) != len(_rows_new):
        _errs.append(f"★ {_n}：行数变化 {len(_rows_old)}→{len(_rows_new)}")
    for _r1, _r2 in zip(_rows_old, _rows_new):
        for _k in _r1:
            if (_r1[_k] or "") != (_r2.get(_k) or ""):
                _diff.append({"row": _r1.get("sample_id"), "col": _k,
                              "orig": (_r1[_k] or "")[:60],
                              "copy": (_r2.get(_k) or "")[:60]})
    _cjk_o = sum(1 for c in _txt if "\u4e00" <= c <= "\u9fff")
    _cjk_n = sum(1 for c in _new_txt if "\u4e00" <= c <= "\u9fff")
    _conv[_n] = {"★ 原编码": _enc, "★ 行数": len(_rows_old), "★ 列数": len(_hdr),
                "★ 单元格差异数": len(_diff), "★ 差异明细": _diff[:5],
                "★ 中文 原/新": f"{_cjk_o}/{_cjk_n}",
                "★ ★ 转换无损": not _diff and _cjk_o == _cjk_n
                          and len(_rows_old) == len(_rows_new)}
    print(f"      {_n:26s} 转换无损={_conv[_n]['★ ★ 转换无损']}"
          f"｜单元格差异={len(_diff)}｜中文 {_cjk_o}→{_cjk_n}")
    if _diff:
        _errs.append(f"★ {_n}：编码转换产生 {len(_diff)} 处单元格差异")
_report["★ 编码转换验证"] = _conv

# ══ ③ 从 git 取发放时版本，逐单元格比对不可编辑列 ══
print()
print("  ★ ③ 与发放时冻结版本（git %s）逐单元格比对" % ISSUED_COMMIT)
_git_base = "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
_git_cmp = {}
for _n, _lbl in ((NAMES[0], LABEL_COLS_A), (NAMES[1], LABEL_COLS_B),
                  (NAMES[2], [])):
    _g = subprocess.run(["git", "show", f"{ISSUED_COMMIT}:{_git_base}/{_n}"],
                         capture_output=True, cwd=str(ROOT))
    if _g.returncode != 0:
        _errs.append(f"★ 无法从 git 取出发放时版本：{_n}")
        continue
    _gold = _g.stdout.decode("utf-8")
    _grows = {r["sample_id"]: r for r in _to_rows(_gold)}
    _nrows = {r["sample_id"]: r for r in _to_rows((WORK / _n).read_text(encoding="utf-8"))}
    _immutable = [c for c in _gold.split("\n")[0].split(",")
                  if c and c not in _lbl]
    _diffs = []
    for _sid in sorted(set(_grows) | set(_nrows)):
        if _sid not in _grows or _sid not in _nrows:
            _diffs.append({"sample_id": _sid, "★ 问题": "★ ID 集合不一致"})
            continue
        for _c in _immutable:
            _a = (_grows[_sid].get(_c) or "")
            _b = (_nrows[_sid].get(_c) or "")
            if _a != _b:
                _diffs.append({"sample_id": _sid, "col": _c,
                               "发放时": _a[:90], "现在": _b[:90]})
    _git_cmp[_n] = {"★ 不可编辑列数": len(_immutable),
                 "★ 比对单元格数": len(_immutable) * len(_grows),
                 "★ 差异数": len(_diffs), "★ 差异明细": _diffs[:8],
                 "★ ★ 完全一致": not _diffs}
    print(f"      {_n:26s} 不可编辑列={len(_immutable)}｜比对单元格="
          f"{len(_immutable)*len(_grows)}｜差异={len(_diffs)}")
    if _diffs:
        _errs.append(f"★ ★ {_n}：{len(_diffs)} 处**不可编辑列**被改动")
        for _d in _diffs[:5]:
            print(f"          - {_d}")
_report["★ 与发放时版本比对（★ 不可编辑列）"] = _git_cmp

# ══ ④ 复算全部数字 ══
print()
print("  ★ ④ 复算数字")
_A = _to_rows((WORK / NAMES[0]).read_text(encoding="utf-8"))
_B = _to_rows((WORK / NAMES[1]).read_text(encoding="utf-8"))
_AR = _to_rows((WORK / NAMES[2]).read_text(encoding="utf-8"))
_ids = [r["sample_id"] for r in _A]
_ids_set = set(_ids)
_calc = {
    "★ A 行数/列数": f"{len(_A)} / {len(_A[0])}",
    "★ B 行数/列数": f"{len(_B)} / {len(_B[0])}",
    "★ 仲裁表 行数/列数": f"{len(_AR)} / {len(_AR[0])}",
    "★ A/B/仲裁 sample_id 集合一致": (
        _ids_set == {r["sample_id"] for r in _B} == {r["sample_id"] for r in _AR}),
    "★ A/B truth_label 一致数": sum(
        1 for r in _A if (r.get("★ A:truth_label") or "").strip()
        == (_bm[_sid].get("★ B:truth_label") or "").strip())
        if False else sum(1 for r in _A
                          if (r.get("★ A:truth_label") or "").strip()
                          == ({x["sample_id"]: x for x in _B}[r["sample_id"]]
                              .get("★ B:truth_label") or "").strip()),
    "★ evidence_support 一致数": sum(
        1 for r in _A if (r.get("★ A:evidence_support") or "").strip()
        == ({x["sample_id"]: x for x in _B}[r["sample_id"]]
            .get("★ B:evidence_support") or "").strip()),
}
_bm = {x["sample_id"]: x for x in _B}
_calc["★ A/B truth_label 一致数"] = sum(
    1 for r in _A if (r.get("★ A:truth_label") or "").strip()
    == (_bm[r["sample_id"]].get("★ B:truth_label") or "").strip())
_calc["★ evidence_support 一致数"] = sum(
    1 for r in _A if (r.get("★ A:evidence_support") or "").strip()
    == (_bm[r["sample_id"]].get("★ B:evidence_support") or "").strip())
_calc["★ truth_label 分布"] = dict(collections.Counter(
    (r.get("★ A:truth_label") or "").strip() for r in _A))
_calc["★ 仲裁表 已填结论数"] = sum(
    1 for r in _AR if (r.get("★ 仲裁后 truth_label") or "").strip())
_calc["★ 仲裁表 审核编号非空数"] = sum(
    1 for r in _AR if (r.get("★ 仲裁者 ID（★ 匿名编号）") or "").strip())
_calc["★ 仲裁表 日期非空数"] = sum(
    1 for r in _AR if (r.get("★ 审核日期") or "").strip())
_calc["★ 仲裁表 理由非空数"] = sum(
    1 for r in _AR if (r.get("★ 仲裁理由") or "").strip())
_calc["★ 协议分布"] = dict(collections.Counter(r.get("protocol", "") for r in _A))
_calc["★ chunk 数"] = len({r.get("chunk_id", "") for r in _A})
for _k, _v in _calc.items():
    print(f"      {_k:32s} {_v}")
_report["★ 复算数字"] = _calc

# ══ evidence_support / 字段级分歧 ══
_es_diff = [{"sample_id": r["sample_id"],
             "A": (r.get("★ A:evidence_support") or "").strip(),
             "B": (_bm[r["sample_id"]].get("★ B:evidence_support") or "").strip()}
            for r in _A
            if (r.get("★ A:evidence_support") or "").strip()
            != (_bm[r["sample_id"]].get("★ B:evidence_support") or "").strip()]
_f_diff = []
for r in _A:
    _b = _bm[r["sample_id"]]
    for _f in ("subject", "action", "object", "strength", "polarity",
               "condition", "exception"):
        _a = (r.get(f"★ A:{_f}") or "").strip()
        _bv = (_b.get(f"★ B:{_f}") or "").strip()
        if _a != _bv:
            _f_diff.append({"sample_id": r["sample_id"], "field": _f,
                            "A": _a[:70], "B": _bv[:70]})
_report["★ evidence_support 分歧"] = _es_diff
_report["★ 字段级分歧（★ 全部）"] = _f_diff
print()
print(f"  ★ evidence_support 分歧 = {len(_es_diff)} 条："
      f"{[d['sample_id'] for d in _es_diff]}")
print(f"  ★ 字段级分歧单元格 = {len(_f_diff)} 处")

(OUTD / "n1c_input_acceptance.json").write_text(json.dumps(
    {"★ 报告": _report, "★ 错误": _errs, "★ 通过": not _errs},
    ensure_ascii=False, indent=2), encoding="utf-8")
print()
print(f"  ★★ 输入完整性检查：{'✅ 通过' if not _errs else '❌ 未通过（★ 须停止评估）'}"
      f"（★ 错误 {len(_errs)} 项）")
for _e in _errs:
    print(f"      - {_e}")
print(f"\n  ⇒ {OUTD/'n1c_input_acceptance.json'}")
raise SystemExit(1 if _errs else 0)
