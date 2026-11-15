# -*- coding: utf-8 -*-
"""★ N1-R2 发放前检查①：三份文件（A/B/仲裁表）逐 ID 对照 + 与跨度台账一致性。

★ 校验项：
  1) A / B / 仲裁表 **ID 集合完全相同**，共 50 条，★ R=30、K=20
  2) 每条的 `resolved_span` / `chunk_id` / `★ 锚点行原文` 与 `n1r2_span_ledger.jsonl` **一致**
  3) ★ **不得使用旧版 final_label 表** ⇒ ★ 检查交付目录无旧表、★ 且新表**不含** final_label 列
  4) 列数与表头一致（★ 无 None 键）
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N0-N3准入审查"
OUT = ROOT / "guard/_out/n1r2"
LEDGER = OUT / "n1r2_span_ledger.jsonl"

errs, notes = [], []

# ★ 旧版表必须**不存在**
for _old in ("N1_人工标注表.csv", "N1_人工标注表.md"):
    if (DELIV / _old).exists():
        errs.append(f"★ 仍存在旧版表：{_old}（★ 不得使用）")

led = {json.loads(l)["sample_id"]: json.loads(l) for l in
       LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()}


def _read(name):
    with (DELIV / name).open(encoding="utf-8") as f:
        _r = csv.DictReader(f)
        _rows = list(_r)
        _hdr = _r.fieldnames
    # ★ 列数一致性（★ None 键 ⇒ 多余列）
    for _i, _row in enumerate(_rows):
        if None in _row:
            errs.append(f"★ {name} 第 {_i+1} 行有多余列（★ 表头 {len(_hdr)} 列）")
    return _rows, _hdr


_a, _ha = _read("N1_盲审标注表_A.csv")
_b, _hb = _read("N1_盲审标注表_B.csv")
_arb, _harp = _read("N1_仲裁表.csv")

_ids_a = [r["sample_id"] for r in _a]
_ids_b = [r["sample_id"] for r in _b]
_ids_arb = [r["sample_id"] for r in _arb]

# ① ID 集合
if set(_ids_a) != set(_ids_b):
    errs.append(f"★ A/B ID 不一致：{set(_ids_a) ^ set(_ids_b)}")
if set(_ids_a) != set(_ids_arb):
    errs.append(f"★ A/仲裁 ID 不一致：{set(_ids_a) ^ set(_ids_arb)}")
if len(_ids_a) != 50:
    errs.append(f"★ 样本数 {len(_ids_a)} ≠ 50")
if len(set(_ids_a)) != len(_ids_a):
    errs.append("★ A 表存在重复 sample_id")
for _n, _ids in (("A", _ids_a), ("B", _ids_b), ("仲裁", _ids_arb)):
    _dup = [k for k, v in __import__("collections").Counter(_ids).items() if v > 1]
    if _dup:
        errs.append(f"★ {_n} 表重复 sample_id：{_dup}")

# ② R/K 分布
_grp = {}
for r in _a:
    _grp[r.get("分组", "")] = _grp.get(r.get("分组", ""), 0) + 1
notes.append(f"★ 分组分布：{_grp}")
if _grp.get("R") != 30 or _grp.get("K") != 20:
    errs.append(f"★ R/K 分布 {_grp} ⇒ 期望 R=30、K=20")
for _n, _rows in (("B", _b), ("仲裁", _arb)):
    _g2 = {}
    for r in _rows:
        _g2[r.get("分组", "")] = _g2.get(r.get("分组", ""), 0) + 1
    if _g2 != _grp:
        errs.append(f"★ {_n} 的 R/K 分布与 A 不一致：{_g2}")

# ③ 与跨度台账逐条比对
for _r in _a:
    _sid = _r["sample_id"]
    _L = led.get(_sid)
    if not _L:
        errs.append(f"★ {_sid}：跨度台账中不存在")
        continue
    if str(_L["resolved_span"]) != str(_r.get("★ resolved_span", "")).strip():
        errs.append(f"★ {_sid}：resolved_span 不一致"
                    f"（台账 {_L['resolved_span']} vs 表 {_r.get('★ resolved_span')}）")
    if str(_L["chunk_start"]) != str(_r.get("chunk_start", "")).strip():
        errs.append(f"★ {_sid}：chunk_start 不一致")
    _expect_chunk = f"{_L['★ document']}@{_L['chunk_start']}"
    if _r.get("chunk_id", "").strip() != _expect_chunk:
        errs.append(f"★ {_sid}：chunk_id 不一致"
                    f"（台账推导 {_expect_chunk} vs 表 {_r.get('chunk_id')}）")
    if _r.get("★ span_mode", "").strip() != _L["span_mode"]:
        errs.append(f"★ {_sid}：span_mode 不一致")
    # ★ 锚点行原文必须与 RFC 原文一致（★ 独立核查）
    _doc = ROOT / f"kb/{_L['★ protocol']}/spec/{_L['★ document']}"
    _lines = _doc.read_text(encoding="utf-8", errors="replace") \
        .replace("\r\n", "\n").split("\n")
    _rs = int(_L["resolved_span"])
    _anchor = _lines[_rs - 1]
    _in_tbl = (_r.get("★ 锚点行原文（★ 合法可为空）") or "").strip()
    if _in_tbl.replace(" ⏎ ", "\n").strip() != _anchor.strip():
        errs.append(f"★ {_sid}：锚点行原文与 RFC 原文不一致")
    # ★ 上下文必须含该行
    if f"{_rs}:" not in (_r.get("★ RFC 原文上下文（锚点 ±6 行）") or ""):
        errs.append(f"★ {_sid}：上下文未含锚点行 {_rs}")

# ④ 新表不得含 final_label 列（★ 旧契约残留）
for _n, _hdr in (("A", _ha), ("B", _hb)):
    _bad = [h for h in _hdr if "final_label" in h]
    if _bad:
        errs.append(f"★ {_n} 表仍含旧契约列：{_bad}")
    _m = [h for h in _hdr if any(w in h for w in ("L2", "verdict", "final_state"))]
    if _m:
        errs.append(f"★ {_n} 表含模型状态列：{_m}")

print("  ★ 三文件一致性检查")
print(f"      A {len(_a)} 行 × {len(_ha)} 列 ｜ B {len(_b)} 行 × {len(_hb)} 列 "
      f"｜ 仲裁 {len(_arb)} 行 × {len(_harp)} 列")
for _n in notes:
    print(f"      {_n}")
print(f"      ★ 错误 {len(errs)} 项")
for _e in errs[:20]:
    print(f"        - {_e}")

(OUT / "n1r2_consistency_check.json").write_text(json.dumps({
    "★ 错误": errs, "★ 提示": notes,
    "★ 通过": not errs,
    "★ A/B/仲裁 ID 集合一致": set(_ids_a) == set(_ids_b) == set(_ids_arb),
    "★ 样本数": len(_ids_a), "★ 分组": _grp,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUT/'n1r2_consistency_check.json'}")
raise SystemExit(1 if errs else 0)
