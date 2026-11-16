# -*- coding: utf-8 -*-
"""★ V2-E3 §二：★ **队列 B 冻结输入验收**（★ 复算 7 项，★ 任一不满足 ⇒ 停止发放）。

★ 唯一抽样输入 = V2-E2 已冻结清单（★ 不得自动替换或重新抽取样本）
"""
import collections
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "guard/_out/_n1c_v2/e1"))
import section_kinds as SK

E2 = ROOT / "guard/_out/_n1c_v2/e2"
PILOT = ROOT / "guard/_out/_v2_e2_pilot"
OUTD = ROOT / "guard/_out/_n1c_v2/e3"
OUTD.mkdir(parents=True, exist_ok=True)
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E3队列B盲审发放与保留来源预案")
DELIV.mkdir(parents=True, exist_ok=True)

_rows = [json.loads(l) for l in
         (E2 / "v2e2_queue_b_frozen.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]
_errs = []
_checks = {}

# ① 总样本数
_checks["① 总样本数 = 54"] = (len(_rows), len(_rows) == 54)
# ② 五类章节分布
_kd = collections.Counter(r["★ 章节类型"] for r in _rows)
_exp_kd = {"① 协议操作与行为规范": 13, "② 消息格式与 ABNF": 12,
           "③ 状态、响应与错误处理": 8, "④ 定义、注册与参数说明": 13,
           "⑤ 附录、元数据及其他": 8}
_checks["② 五类章节分布"] = (dict(_kd), dict(_kd) == _exp_kd)
# ③ 协议分布
_pd = collections.Counter(r["protocol"] for r in _rows)
_exp_pd = {"DHCPv4": 27, "smtp": 15, "rtsp": 6, "sip": 6}
_checks["③ 协议分布"] = (dict(_pd), dict(_pd) == _exp_pd)
# ④ 每 RFC ≤ 6
_dd = collections.Counter(f"{r['protocol']}/{r['document']}" for r in _rows)
_checks["④ 每份 RFC ≤ 6"] = (max(_dd.values()), max(_dd.values()) <= 6)
# ⑤ snippet_id 唯一
_ids = [r["sample_id"] for r in _rows]
_checks["⑤ snippet_id 唯一"] = (len(set(_ids)), len(set(_ids)) == len(_ids))
# ⑥ RFC 文件与原文 SHA256 可校验
_sha_ok = 0
_sha_missing = 0
_sha_bad = []
_baseline = {}
_bp = DELIV / "V2-E3_原文与证据不可编辑字段基线.jsonl"
if _bp.is_file():
    _baseline = {json.loads(l)["snippet_id"]: json.loads(l)
                 for l in _bp.read_text(encoding="utf-8").splitlines() if l.strip()}
for r in _rows:
    _p = ROOT / f"kb/{r['protocol']}/spec/{r['document']}"
    if not _p.is_file():
        _sha_bad.append((r["sample_id"], "★ 源文件不存在"))
        continue
    _now = hashlib.sha256(_p.read_bytes()).hexdigest()
    _b = _baseline.get(r["sample_id"])
    if not _b:
        _sha_missing += 1
        continue
    if _b.get("rfc_sha256") == _now:
        _sha_ok += 1
    else:
        _sha_bad.append((r["sample_id"], "★ 基线哈希 ≠ 实际"))
_checks["⑥ RFC SHA256 可校验（★ E3 不可编辑基线）"] = (
    {"基线中一致": _sha_ok, "★ 基线缺失": _sha_missing,
     "★ 不一致": _sha_bad[:5]}, _sha_ok == len(_rows))
# ⑦ 原文跨度可定位
_span_ok = 0
_span_bad = []
for r in _rows:
    _p = ROOT / f"kb/{r['protocol']}/spec/{r['document']}"
    if not _p.is_file():
        continue
    _L = _p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _lo, _hi = r["★ 证据跨度（行号）"]
    if 1 <= _lo <= _hi <= len(_L):
        # ★ 冻结时证据文本 = " ".join(lines[lo-1:hi])（★ 单空格连接）⇒ ★ 复核须同
        _seg = " ".join(_L[_lo - 1:_hi])
        _exp = (r.get("★ 证据文本") or "").strip()
        if _seg.strip()[:200] == _exp[:200] or _exp[:200] in _seg.strip():
            _span_ok += 1
        else:
            _span_bad.append((r["sample_id"], "★ 证据文本与原文不符"))
    else:
        _span_bad.append((r["sample_id"], f"★ 行号越界 {_lo}~{_hi} / {len(_L)}"))
_checks["⑦ 原文跨度可定位"] = (
    {"可定位": _span_ok, "★ 异常": _span_bad[:5]}, _span_ok == len(_rows))
# ⑧ 排除机制
_pilot_recs = [json.loads(l) for l in
               (PILOT / "V2-E2_新增候选审计.jsonl").read_text(encoding="utf-8").splitlines()
               if l.strip()]
_pilot_chunks = {r.get("★ chunk_id") for r in _pilot_recs if r.get("★ chunk_id")}
_qb_chunks = {f"{r['protocol']}/{r['document']}" for r in _rows}
_overlap_same_doc = 0
_overlap_same_seg = 0
for r in _rows:
    if f"{r['protocol']}/{r['document']}" in _qb_chunks:
        for _pc in _pilot_chunks:
            if _pc.startswith(f"{r['document']}@"):
                _overlap_same_doc += 1
                _lo = r["★ 证据跨度（行号）"][0]
                _pstart = int(_pc.split("@")[-1])
                if _pstart <= r["★ 证据跨度（行号）"][1] and \
                        r["★ 证据跨度（行号）"][0] <= _pstart + 100:
                    _overlap_same_seg += 1
_checks["⑧ 排除机制（★ 试点块与队列B 片段）"] = (
    {"同文档": _overlap_same_doc, "★ 同区段（★ 应为 0）": _overlap_same_seg},
    _overlap_same_seg == 0)

print("  ★ 队列 B 冻结清单验收：")
for _k, (_v, _ok) in _checks.items():
    print(f"      {'✔' if _ok else '✘'} {_k}: {json.dumps(_v, ensure_ascii=False)[:150]}")
    if not _ok:
        _errs.append(f"★ {_k} 不满足：{_v}")
print()
print(f"  ★★ 验收结论：{'✅ 通过 ⇒ 可发放' if not _errs else '❌ 未通过 ⇒ 停止发放'}"
      f"（★ 错误 {len(_errs)} 项）")
(OUTD / "v2e3_queue_b_acceptance.json").write_text(json.dumps({
    "★ 各项检查": {k: {"值": v[0], "通过": v[1]} for k, v in _checks.items()},
    "★ 错误": _errs, "★ 通过": not _errs,
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"  ⇒ {OUTD/'v2e3_queue_b_acceptance.json'}")
raise SystemExit(1 if _errs else 0)
