# -*- coding: utf-8 -*-
"""★ N1-B 第 0 步：★ **冻结输入**（★ 归档原始 + 哈希）+ **编码统一工作副本**。

★ 严格按要求：
  ① 归档原始文件（★ **不修改、不覆盖**）与 SHA256
  ② 生成统一 UTF-8（LF）工作副本
  ③ 验证：★ 50 个 sample_id 一致｜★ 所有字段与原文件一致｜
     ★ 不丢中文/换行/特殊字符｜★ 原始内容**无语义变化**
  ④ 验证：★ **编码转换不影响统计结果**
"""
import csv
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
OUTD = DELIV / "N1-B人工真值与模型质量审查"
ARCH = OUTD / "archive_original"
OUTD.mkdir(parents=True, exist_ok=True)
ARCH.mkdir(parents=True, exist_ok=True)

INPUTS = ["N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv", "N1_仲裁表.csv",
          "N1_审核说明.md", "n1_汇总脚本.py", "N1_风险台账_未纳入本次审核.csv"]


def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _detect(p):
    b = pathlib.Path(p).read_bytes()
    if b[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig", b
    for _enc in ("utf-8", "gb18030", "gbk", "latin-1"):
        try:
            b.decode(_enc)
            return _enc, b
        except UnicodeDecodeError:
            continue
    return "latin-1", b


manifest = []
for n in INPUTS:
    _p = DELIV / n
    if not _p.is_file():
        manifest.append({"file": n, "★ 状态": "★ 缺失"})
        continue
    _enc, _b = _detect(_p)
    # ① 归档原始（★ 只读复制）
    shutil.copy2(_p, ARCH / n)
    _h = _sha(_p)
    _crlf = _b.count(b"\r\n")
    _lf = _b.count(b"\n")
    manifest.append({
        "file": n, "★ 状态": "已归档", "sha256": _h,
        "★ 检测编码": _enc, "★ BOM": _b[:3] == b"\xef\xbb\xbf",
        "★ CRLF 行数": _crlf, "★ LF 总数": _lf,
        "★ 字节数": len(_b),
        "★ 归档副本 sha256": _sha(ARCH / n),
        "★ 归档与原件一致": _sha(ARCH / n) == _h,
    })
    print(f"  ★ {n}: 编码={_enc} BOM={_b[:3]==b'\xef\xbb\xbf'} "
          f"CRLF={_crlf} LF={_lf} sha={_h[:16]}")

# ══ ② 生成 UTF-8 工作副本 + 验证 ══
WORK = OUTD / "work_utf8"
WORK.mkdir(exist_ok=True)
verify = []
for n in ("N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv", "N1_仲裁表.csv"):
    _src = DELIV / n
    _enc, _b = _detect(_src)
    _text = _b.decode(_enc)
    _nl = "\r\n" if "\r\n" in _text else "\n"
    _rows = list(csv.DictReader(_text.splitlines()))
    _hdr = list(csv.reader([_text.splitlines()[0]]))[0]
    # ★ 归一化：统一 LF、去 BOM、行尾
    _out_text = _text.replace("\r\n", "\n").replace("\r", "\n")
    if _out_text.startswith("\ufeff"):
        _out_text = _out_text[1:]
    _dst = WORK / n
    _dst.write_text(_out_text, encoding="utf-8", newline="\n")
    # ★ 逐字段比对（★ 原 vs 副本）
    _rows2 = list(csv.DictReader(_dst.read_text(encoding="utf-8").splitlines()))
    _ids1 = [r["sample_id"] for r in _rows]
    _ids2 = [r["sample_id"] for r in _rows2]
    _same_ids = _ids1 == _ids2
    _diff = []
    if _same_ids:
        for _r1, _r2 in zip(_rows, _rows2):
            for _k in _r1:
                _v1 = _r1[_k] or ""
                _v2 = _r2.get(_k) or ""
                if _v1 != _v2:
                    _diff.append({"sample_id": _r1["sample_id"], "field": _k,
                                  "原始": _v1[:80], "副本": _v2[:80]})
    # ★ 中文/特殊字符保全检查
    _cjk_src = sum(1 for c in _text if "\u4e00" <= c <= "\u9fff")
    _cjk_dst = sum(1 for c in _out_text if "\u4e00" <= c <= "\u9fff")
    _spec_src = sum(_text.count(c) for c in ("\n", "\t", "⏎", "「", "」", "★"))
    _spec_dst = sum(_out_text.count(c) for c in ("\n", "\t", "⏎", "「", "」", "★"))
    verify.append({
        "file": n, "★ 原编码": _enc, "★ 新编码": "utf-8 (LF, 无 BOM)",
        "★ 行数": len(_rows), "★ 列数": len(_hdr),
        "★ sample_id 集合一致": _same_ids,
        "★ 字段值差异数": len(_diff), "★ 差异明细": _diff[:5],
        "★ 中文字符数 原/新": f"{_cjk_src}/{_cjk_dst}",
        "★ 特殊字符数 原/新": f"{_spec_src}/{_spec_dst}",
        "★ 转换无失真": (not _diff) and _same_ids and _cjk_src == _cjk_dst
                    and _spec_src == _spec_dst,
    })
    print(f"  ★ {n}: 行 {len(_rows)}｜列 {len(_hdr)}｜id 一致={_same_ids}｜"
          f"字段差异={len(_diff)}｜中文 {_cjk_src}→{_cjk_dst}")

# ══ ④ 编码转换是否影响统计结果 ══
# ★ 用同一套统计逻辑分别读原文件与工作副本 ⇒ 比较结果
def _stats(rows, tag):
    _c = {}
    for r in rows:
        _l = (r.get(f"★ {tag}:truth_label") or "").strip()
        _e = (r.get(f"★ {tag}:evidence_support") or "").strip()
        if _l:
            _c[_l] = _c.get(_l, 0) + 1
        if _e:
            _c["es:" + _e] = _c.get("es:" + _e, 0) + 1
    return _c


_enc_cmp = {}
for _tag, _n in (("A", "N1_盲审标注表_A.csv"), ("B", "N1_盲审标注表_B.csv")):
    _enc, _b = _detect(DELIV / _n)
    _r1 = list(csv.DictReader(_b.decode(_enc).splitlines()))
    _r2 = list(csv.DictReader((WORK / _n).read_text(encoding="utf-8").splitlines()))
    _s1, _s2 = _stats(_r1, _tag), _stats(_r2, _tag)
    _enc_cmp[_n] = {"原文件统计": _s1, "工作副本统计": _s2, "★ 完全一致": _s1 == _s2}
    print(f"  ★ 统计一致性 {_n}: {_s1 == _s2}")

report = {"★ 输入清单与哈希": manifest,
          "★ 编码统一验证": verify,
          "★ 编码转换对统计的影响": _enc_cmp,
          "★ 归档目录": str(ARCH.relative_to(ROOT)),
          "★ 工作副本目录": str(WORK.relative_to(ROOT))}
(OUTD / "N1-B_输入冻结与编码统一.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'N1-B_输入冻结与编码统一.json'}")
