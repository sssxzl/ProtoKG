# -*- coding: utf-8 -*-
"""★ V2-E3 §三~§五：★ 生成**不可编辑字段基线** + **双层双盲标注包**。

★ ★ 防 Excel/CSV 损坏（★ §五）：
  ① 原文/证据跨度/不可编辑字段保留 **UTF-8 无 BOM 机器基线**
  ② 人工用**独立 Excel 友好模板**（★ 只含可编辑列），★ **不得覆盖机器基线**
  ③ ★ 优先只填可编辑标注字段
  ④ 导入时按 snippet_id / gold_knowledge_id 合并
  ⑤ 不可编辑字段**逐单元格比较**
  ⑥ ★ 正确处理引号/逗号/换行/⏎（★ 用 csv 模块 + QUOTE_ALL，★ 并做往返测试）
  ⑦ 导入后重新记录 SHA256
  ⑧ 任何证据字段非预期改变 ⇒ 停止
"""
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
E2 = ROOT / "guard/_out/_n1c_v2/e2"
OUTD = ROOT / "guard/_out/_n1c_v2/e3"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E3队列B盲审发放与保留来源预案")
DELIV.mkdir(parents=True, exist_ok=True)

_rows = [json.loads(l) for l in
         (E2 / "v2e2_queue_b_frozen.jsonl").read_text(encoding="utf-8").splitlines()
         if l.strip()]
_rows.sort(key=lambda r: r["sample_id"])

# ══ ① 不可编辑字段基线（含补算 SHA256）══
_base = []
for r in _rows:
    _p = ROOT / f"kb/{r['protocol']}/spec/{r['document']}"
    _sha = hashlib.sha256(_p.read_bytes()).hexdigest()
    _L = _p.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _lo, _hi = r["★ 证据跨度（行号）"]
    _seg = " ".join(_L[_lo - 1:_hi])
    _base.append({
        "snippet_id": r["sample_id"],
        "protocol": r["protocol"], "document": r["document"],
        "rfc_sha256": _sha,
        "★ 章节类型": r["★ 章节类型"],
        "★ 证据跨度（行号）": [_lo, _hi],
        "★ 证据原文": _seg,
        "★ 证据原文 sha256": hashlib.sha256(_seg.encode()).hexdigest(),
        "★ 所属抽取区间": r["★ 所属抽取区间"],
        "★ 不可编辑字段": ["snippet_id", "protocol", "document", "rfc_sha256",
                     "★ 章节类型", "★ 证据跨度（行号）", "★ 证据原文",
                     "★ 证据原文 sha256"],
    })
with (DELIV / "V2-E3_原文与证据不可编辑字段基线.jsonl").open("w", encoding="utf-8") as f:
    for b in _base:
        f.write(json.dumps(b, ensure_ascii=False) + "\n")
print(f"  ★ 不可编辑基线：{len(_base)} 条｜"
      f"sha256={hashlib.sha256((DELIV/'V2-E3_原文与证据不可编辑字段基线.jsonl').read_bytes()).hexdigest()[:16]}")

# ══ ② 片段级审核包（A / B）══
SNIP_HDR = ["snippet_id", "protocol", "document", "rfc_sha256", "★ 章节类型",
            "★ 证据跨度（行号）", "★ 原文（不可编辑）",
            "★ 是否存在目标知识", "★ 知识类别", "★ 是否需跨句/跨节证据",
            "★ 审核意见", "★ 不确定原因"]
SNIP_EDIT = ["★ 是否存在目标知识", "★ 知识类别", "★ 是否需跨句/跨节证据",
             "★ 审核意见", "★ 不确定原因"]


def _write_csv(path, header, rows):
    """★ 用 csv 模块 + QUOTE_ALL（★ 正确处理引号/逗号/换行）+ UTF-8 无 BOM。"""
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, quoting=csv.QUOTE_ALL, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
    return hashlib.sha256(path.read_bytes()).hexdigest()


_hashes = {}
for _tag in ("A", "B"):
    _rows_out = []
    for b in _base:
        _rows_out.append([
            b["snippet_id"], b["protocol"], b["document"], b["rfc_sha256"],
            b["★ 章节类型"], f'{b["★ 证据跨度（行号）"][0]}-{b["★ 证据跨度（行号）"][1]}',
            b["★ 证据原文"], "", "", "", "", ""])
    _p = DELIV / f"V2-E3_队列B_审核者{_tag}_片段级标注表.csv"
    _hashes[_p.name] = _write_csv(_p, SNIP_HDR, _rows_out)
    print(f"  ★ {_p.name}: {len(_rows_out)} 行 × {len(SNIP_HDR)} 列")

# ══ ③ 原子知识级标注包（A / B）══
KNOW_HDR = ["gold_knowledge_id", "snippet_id", "knowledge_kind", "evidence_span",
            "subject", "action", "object", "strength", "polarity", "condition",
            "exception", "evidence_support", "review_note", "★ 审核者"]
KNOW_EDIT = ["knowledge_kind", "evidence_span", "subject", "action", "object",
             "strength", "polarity", "condition", "exception", "evidence_support",
             "review_note"]
for _tag in ("A", "B"):
    _rows_out = []
    for b in _base:
        _rows_out.append([f'GK-{b["snippet_id"]}-1', b["snippet_id"], "", "", "", "",
                          "", "", "", "", "", "", "", ""])
    _p = DELIV / f"V2-E3_队列B_审核者{_tag}_原子知识级标注表.csv"
    _hashes[_p.name] = _write_csv(_p, KNOW_HDR, _rows_out)
    print(f"  ★ {_p.name}: {len(_rows_out)} 行 × {len(KNOW_HDR)} 列")

# ══ ④ 第三方仲裁模板 ══
ARB_HDR = ["gold_knowledge_id", "snippet_id", "★ A:knowledge_kind",
           "★ B:knowledge_kind", "★ 仲裁后 knowledge_kind",
           "★ A:strength", "★ B:strength", "★ 仲裁后 strength",
           "★ A:polarity", "★ B:polarity", "★ 仲裁后 polarity",
           "★ A:subject", "★ B:subject", "★ 仲裁后 subject",
           "★ A:evidence_support", "★ B:evidence_support",
           "★ 仲裁后 evidence_support",
           "★ 仲裁后 evidence_span", "★ 匹配争议类型",
           "★ 仲裁者 ID（★ 匿名编号）", "★ 审核日期", "★ 仲裁理由",
           "★ 是否 unresolved"]
ARB_ROWS = []
for b in _base:
    ARB_ROWS.append([f'GK-{b["snippet_id"]}-1', b["snippet_id"]] + [""] * 20
                    + ["★ 否"])
_p = DELIV / "V2-E3_队列B_第三方仲裁模板.csv"
_hashes[_p.name] = _write_csv(_p, ARB_HDR, ARB_ROWS)
print(f"  ★ {_p.name}: {len(ARB_ROWS)} 行 × {len(ARB_HDR)} 列")

# ══ ⑤ Excel 友好编辑模板（★ 只含可编辑列，★ 不含原文）══
EDIT_HDR = ["snippet_id", "★ 是否存在目标知识", "★ 知识类别", "★ 是否需跨句/跨节证据",
            "★ 审核意见", "★ 不确定原因", "gold_knowledge_id", "knowledge_kind",
            "evidence_span", "subject", "action", "object", "strength",
            "polarity", "condition", "exception", "evidence_support", "review_note",
            "★ 审核者 ID", "★ 审核日期"]
for _tag in ("A", "B"):
    _rows_out = []
    for b in _base:
        _rows_out.append([b["snippet_id"], "", "", "", "", "",
                          f'GK-{b["snippet_id"]}-1', "", "", "", "", "", "", "", "",
                          "", "", "", ""])
    _p = DELIV / f"V2-E3_队列B_审核者{_tag}_Excel友好编辑模板.csv"
    _hashes[_p.name] = _write_csv(_p, EDIT_HDR, _rows_out)
    print(f"  ★ {_p.name}: {len(_rows_out)} 行 × {len(EDIT_HDR)} 列（★ **不含原文**）")

# ══ ⑥ 往返完整性测试（★ 特殊字符）══
_probe = 'a"b,c\nd⏎e\\f'
_tmp = OUTD / "_roundtrip.csv"
_write_csv(_tmp, ["x"], [[_probe]])
# ★★ **必须用 csv.reader + StringIO 读取**（★ 不可用 splitlines()）
#   ★★ splitlines() 会把**字段内的换行**也切开 ⇒ ★★ 这正是 N1-C 出现
#   ★★ 「行被拆成 26 列 + 12 列」的根因之一
import io as _io
_back = list(csv.reader(_io.StringIO(_tmp.read_text(encoding="utf-8"))))
_rt = (_back[1][0] == _probe) if len(_back) > 1 else False
# ★★ 反证：★ 若用 splitlines() 会失败（★ 记录该风险）
_bad_split = len(list(csv.DictReader(_tmp.read_text(encoding="utf-8").splitlines())))
_split_ok = (_bad_split == 1 and list(csv.DictReader(
    _tmp.read_text(encoding="utf-8").splitlines()))[0]["x"] == _probe)
_tmp.unlink()
print(f"  ★ CSV 往返完整性（★ 引号/逗号/换行/⏎/反斜杠）：{'✔ 通过' if _rt else '✘ 失败'}")
print(f"  ★★ 反证：★ 用 splitlines() 读的结果 = {_bad_split} 行｜"
      f"★ splitlines() 读法是否仍正确 = {_split_ok}"
      f"（★ ★ 若为 False ⇒ **证实 splitlines() 会破坏多行字段**）")
_bom = all(not (DELIV / n).read_bytes().startswith(b"\xef\xbb\xbf")
           for n in _hashes)
_crlf = all(b"\r\n" not in (DELIV / n).read_bytes() for n in _hashes)
print(f"  ★ 全部文件 UTF-8 无 BOM = {_bom}｜统一 LF = {_crlf}")

(DELIV / "V2-E3_发放包文件哈希.json").write_text(json.dumps({
    "★ 文件哈希": _hashes,
    "★ 不可编辑基线哈希": hashlib.sha256(
        (DELIV / "V2-E3_原文与证据不可编辑字段基线.jsonl").read_bytes()).hexdigest(),
    "★ CSV 往返完整性": _rt, "★ 全部无 BOM": _bom, "★ 全部 LF": _crlf,
    "★ splitlines() 反证": {"★ 行数": _bad_split, "★ 是否仍正确": _split_ok},
}, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {DELIV/'V2-E3_发放包文件哈希.json'}")
