# -*- coding: utf-8 -*-
"""★ N1-B：★ 把交付目录的 A/B/仲裁表转为 UTF-8（★ 原件另存仓库外，★ 逐字段验证一致）。

★ 原因：★ 审核者用 Excel 保存 ⇒ 三份表为 **GB18030** ⇒ **仓库不允许非 UTF-8 文件**
★ 处理：★ 原件（GB18030）移到 `guard/_out/n1b/archive_gb18030/`（★ 不入库）
       ★ 交付目录放 UTF-8 版（★ **逐字段与原件一致**，★ 已验证）
★ ★ **不修改任何人工标签内容**（★ 字段差异 0 已验证，★ 哈希留档）
"""
import csv
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
OUTD = DELIV / "N1-B人工真值与模型质量审查"
GB_ARCH = ROOT / "guard/_out/n1b/archive_gb18030"
GB_ARCH.mkdir(parents=True, exist_ok=True)

NAMES = ["N1_盲审标注表_A.csv", "N1_盲审标注表_B.csv", "N1_仲裁表.csv"]
report = []
for n in NAMES:
    _p = DELIV / n
    _b = _p.read_bytes()
    _enc = "utf-8"
    try:
        _b.decode("utf-8")
    except UnicodeDecodeError:
        _enc = "gb18030"
    _sha_before = hashlib.sha256(_b).hexdigest()
    # ① 原件另存仓库外
    shutil.copy2(_p, GB_ARCH / n)
    assert hashlib.sha256((GB_ARCH / n).read_bytes()).hexdigest() == _sha_before
    # ② 交付目录转 UTF-8（LF、无 BOM）
    _text = _b.decode(_enc).replace("\r\n", "\n").replace("\r", "\n")
    if _text.startswith("\ufeff"):
        _text = _text[1:]
    _p.write_text(_text, encoding="utf-8", newline="\n")
    # ③ 逐字段验证
    _rows_old = list(csv.DictReader(_b.decode(_enc).splitlines()))
    _rows_new = list(csv.DictReader(_p.read_text(encoding="utf-8").splitlines()))
    _diff = []
    for _r1, _r2 in zip(_rows_old, _rows_new):
        for _k in _r1:
            if (_r1[_k] or "") != (_r2.get(_k) or ""):
                _diff.append({"sample_id": _r1["sample_id"], "field": _k})
    _cjk_old = sum(1 for c in _b.decode(_enc) if "\u4e00" <= c <= "\u9fff")
    _cjk_new = sum(1 for c in _text if "\u4e00" <= c <= "\u9fff")
    report.append({
        "file": n, "★ 原编码": _enc,
        "★ 原 sha256": _sha_before,
        "★ 新 sha256": hashlib.sha256(_p.read_bytes()).hexdigest(),
        "★ 原件仓库外副本": str((GB_ARCH / n).relative_to(ROOT)),
        "★ 原件副本哈希一致": hashlib.sha256(
            (GB_ARCH / n).read_bytes()).hexdigest() == _sha_before,
        "★ 行数 原/新": f"{len(_rows_old)}/{len(_rows_new)}",
        "★ 字段差异数": len(_diff),
        "★ 中文字符 原/新": f"{_cjk_old}/{_cjk_new}",
        "★ ★ 无语义变化": (not _diff) and _cjk_old == _cjk_new
                    and len(_rows_old) == len(_rows_new),
    })
    print(f"  ★ {n}: { _enc } → utf-8｜字段差异 {len(_diff)}｜中文 {_cjk_old}→{_cjk_new}")

# ★ 仓库内的 archive_original（GB18030）⇒ 移出仓库
_old_arch = OUTD / "archive_original"
if _old_arch.is_dir():
    for _f in _old_arch.iterdir():
        shutil.move(str(_f), str(GB_ARCH / _f.name))
    shutil.rmtree(_old_arch)
    print("  ★ 仓库内 archive_original（GB18030）已移至 guard/_out/n1b/archive_gb18030/")

(OUTD / "N1-B_编码归一与原件保管.json").write_text(json.dumps({
    "★ 说明": ("★ 审核者用 Excel 保存 ⇒ A/B/仲裁表为 GB18030 ⇒ 仓库不允许非 UTF-8"
             "⇒ ★ 原件另存仓库外，★ 交付目录放 UTF-8 版（★ 逐字段一致）"),
    "★ 明细": report,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'N1-B_编码归一与原件保管.json'}")
