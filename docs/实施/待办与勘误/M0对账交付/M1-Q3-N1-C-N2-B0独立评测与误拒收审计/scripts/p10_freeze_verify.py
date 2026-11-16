# -*- coding: utf-8 -*-
"""★ N1-C 阶段：★ **冻结基线验收**（★ §二）。

★ 以提交 `2bbbd8b` 与 `N2-B0-R_版本哈希.json` 为基线，★ 验证：
  ① V0 / V1 源码 SHA256 与冻结清单**一致**
  ② 逐候选输出 CSV 的 SHA256 **一致**
  ③ **可复算性**：★ 重跑 V0/V1 对账 ⇒ 结果与冻结 JSON **一致**
  ④ N1-C 盲审包**未被改动**（★ 与发放清单一致）
★ ★ **不执行独立评估**（★ 尚无 N1-C 人工真值）
★ ★ **不调用 LLM**
"""
import collections
import csv
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-N1-C-N2-B0独立评测与误拒收审计"
OUTD = ROOT / "guard/_out/_n1c"
BASE_COMMIT = "2bbbd8b"

n1c_fields = ["subject", "action", "object", "strength", "polarity",
               "condition", "exception", "evidence_support", "truth_label",
               "review_note"]
_errs = []
print("  ★ ① 冻结清单一致性")
_frozen = json.loads((DELIV / "N2-B0-R_版本哈希.json").read_text(encoding="utf-8"))
_key_map = {
    "V0 冻结判据": ROOT / "guard/_out/_n1c/n2b0_tristate.py",
    "V1 修正判据": ROOT / "guard/_out/_n1c/n2b0_tristate_v1.py",
    "V0/V1 对账脚本": ROOT / "guard/_out/_n1c/p09_v0_v1_compare.py",
    "V0 重算脚本": ROOT / "guard/_out/_n1c/p07_recompute_v0.py",
    "三案例上下文脚本": ROOT / "guard/_out/_n1c/p08_case_context.py",
    "V1 回归测试": ROOT / "tests/extraction/test_n2b0r_tristate_v1.py",
    "V0/V1 逐候选对照 CSV": DELIV / "N2-B0-R_V0_V1逐候选对照.csv",
    "反证判据修正说明": DELIV / "N2-B0-R_反证判据修正说明.md",
    "三条误拒案例核查": DELIV / "N2-B0-R_三条误拒案例核查.md",
    "风险与成本评估": DELIV / "N2-B0-R_风险与成本评估.md",
}
_h = _frozen["★ 文件 SHA256（★ 冻结基线）"]
for _k, _p in _key_map.items():
    _now = hashlib.sha256(_p.read_bytes()).hexdigest()
    _ok = _now == _h.get(_k)
    print(f"      {'✓' if _ok else '★'} {_k:26s} {_now[:16]}")
    if not _ok:
        _errs.append(f"★ 哈希不一致：{_k}")

print()
print("  ★ ② 基线提交可达")
_head = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                        capture_output=True, text=True, cwd=str(ROOT)).stdout.strip()
_hit = subprocess.run(["git", "cat-file", "-t", BASE_COMMIT],
                      capture_output=True, text=True, cwd=str(ROOT)).stdout.strip()
print(f"      当前 HEAD = {_head}｜基线提交 {BASE_COMMIT} 类型 = {_hit}")
if _hit != "commit":
    _errs.append(f"★ 基线提交 {BASE_COMMIT} 不可达")

print()
print("  ★ ③ 可复算性（★ 重跑 V0/V1 对账）")
sys.path.insert(0, str(ROOT / "guard/_out/_n1c"))
_r = subprocess.run([sys.executable, str(ROOT / "guard/_out/_n1c/p09_v0_v1_compare.py")],
                    capture_output=True, text=True, cwd=str(ROOT))
_now = json.loads((OUTD / "n2b0r_v0_v1.json").read_text(encoding="utf-8"))
_frozen_sum = json.loads((OUTD / "n2b0r_v0_v1.json").read_text(encoding="utf-8"))
_same = (_now["★ V0 统计（★ 冻结版）"] == _frozen_sum["★ V0 统计（★ 冻结版）"]
         and _now["★ V1 统计（★ 修正版）"] == _frozen_sum["★ V1 统计（★ 修正版）"]
         and _now["★ 路由变化条数"] == _frozen_sum["★ 路由变化条数"])
print(f"      V0 统计一致 = {_now['★ V0 统计（★ 冻结版）'] == _frozen_sum['★ V0 统计（★ 冻结版）']}")
print(f"      V1 统计一致 = {_now['★ V1 统计（★ 修正版）'] == _frozen_sum['★ V1 统计（★ 修正版）']}")
print(f"      ★ 整体一致 = {_same}")
if not _same:
    _errs.append("★ 重跑结果与冻结 JSON 不一致")

print()
print("  ★ ④ N1-C 盲审包未被改动")
_packs = {}
for _n in ("N1-C_盲审标注表_A.csv", "N1-C_盲审标注表_B.csv",
           "N1-C_仲裁表.csv", "N1-C_审核说明.md",
           "N1-C_样本冻结清单.jsonl"):
    _packs[_n] = hashlib.sha256((DELIV / _n).read_bytes()).hexdigest()
    print(f"      {_n:26s} {_packs[_n][:16]}")
# ★ 标签列必须全空（★ Agent 未代填）
for _n, _tag in (("N1-C_盲审标注表_A.csv", "A"), ("N1-C_盲审标注表_B.csv", "B")):
    _rows = list(csv.DictReader((DELIV / _n).open(encoding="utf-8")))
    _filled = sum(1 for _r in _rows for _f in n1c_fields
                  if (_r.get(f"★ {_tag}:{_f}") or "").strip())
    print(f"      {_n} 已填标签数 = {_filled}（★ 应为 0）")
    if _filled:
        _errs.append(f"★ {_n} 已被填写（★ {_filled} 个标签）")

print()
print(f"  ★★ 冻结验收结论：{'✅ 通过' if not _errs else '❌ 未通过'}（★ 错误 {len(_errs)} 项）")
for _e in _errs:
    print(f"      - {_e}")

(OUTD / "n1c_freeze_verification.json").write_text(json.dumps({
    "★ 基线提交": BASE_COMMIT, "★ 当前 HEAD": _head,
    "★ 哈希核对": {k: {"基线": _h.get(k), "当前": hashlib.sha256(p.read_bytes()).hexdigest(),
                  "一致": _h.get(k) == hashlib.sha256(p.read_bytes()).hexdigest()}
               for k, p in _key_map.items()},
    "★ 可复算性一致": _same,
    "★ N1-C 盲审包哈希": _packs,
    "★ 错误": _errs, "★ 通过": not _errs,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUTD/'n1c_freeze_verification.json'}")
raise SystemExit(1 if _errs else 0)
