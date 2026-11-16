# -*- coding: utf-8 -*-
"""★ H2-B1 §五/§六：★ **队列 B 人工回收验收 + 真值冻结**（★ 严格按 §五 结构检查）。

★ ★ 读取一律用 `csv.reader` + `StringIO`（★ **禁止 splitlines()**）
★ ★ 转换 GB18030 → UTF-8 后**逐单元格验证无损**
★ ★ 数据损坏时**保留原件并生成差异报告**，★ **不自动替换人工标注**
"""
import collections
import csv
import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
D3 = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E3队列B盲审发放与保留来源预案")
D4 = (ROOT / "docs/实施/待办与勘误/M0对账交付"
       / "M1-Q3-V2-E4队列B审核启动与保留抽取")
OUTD = ROOT / "guard/_out/_n1c_v2/h2"
OUTD.mkdir(parents=True, exist_ok=True)
DELIV = ROOT / "docs/实施/待办与勘误/M0对账交付/M1-Q3-V2-E4-B1队列B人工真值验收"
DELIV.mkdir(parents=True, exist_ok=True)

FILES = {
    "A": D3 / "V2-E3_队列B_审核者A_Excel友好编辑模板.csv",
    "B": D3 / "V2-E3_队列B_审核者B_Excel友好编辑模板.csv",
    "ARB": D3 / "V2-E3_队列B_第三方仲裁模板.csv",
}
_errs, _warns = [], []
_rep = {}

# ══ ① 归档原件 + 哈希 + 编码转换（★ 逐单元格验证）══
print("  ★ ① 归档原件与编码转换")
ARCH = OUTD / "received_originals"
ARCH.mkdir(parents=True, exist_ok=True)
_converted = {}
for _tag, _p in FILES.items():
    _b = _p.read_bytes()
    (ARCH / _p.name).write_bytes(_b)
    _enc = "utf-8"
    try:
        _txt = _b.decode("utf-8")
    except UnicodeDecodeError:
        _enc = "gb18030"
        _txt = _b.decode("gb18030")
    _rows_old = list(csv.DictReader(io.StringIO(_txt)))
    _new = _txt.replace("\r\n", "\n").replace("\r", "\n")
    if _new.startswith("﻿"):
        _new = _new[1:]
    _dst = OUTD / f"utf8_{_p.name}"
    _dst.write_text(_new, encoding="utf-8", newline="\n")
    _rows_new = list(csv.DictReader(io.StringIO(_dst.read_text(encoding="utf-8"))))
    _diffs = []
    if len(_rows_old) != len(_rows_new):
        _diffs.append({"★ 问题": f"行数 {len(_rows_old)} → {len(_rows_new)}"})
    for _i, (_r1, _r2) in enumerate(zip(_rows_old, _rows_new)):
        for _k in _r1:
            if (_r1[_k] or "") != (_r2.get(_k) or ""):
                _diffs.append({"row": _i, "col": _k,
                               "orig": (_r1[_k] or "")[:70],
                               "copy": (_r2.get(_k) or "")[:70]})
    _cjk_o = sum(1 for _c in _txt if "一" <= _c <= "鿿")
    _cjk_n = sum(1 for _c in _new if "一" <= _c <= "鿿")
    _converted[_tag] = {
        "★ 原文件": str(_p.relative_to(ROOT)),
        "★ 原文件 SHA256": hashlib.sha256(_b).hexdigest(),
        "★ 原文件大小": len(_b),
        "★ 原编码": _enc,
        "★ CRLF 数": _b.count(bytes([13, 10])),
        "★ 转换后行数": len(_rows_new),
        "★ 转换后列数": len(_rows_new[0]) if _rows_new else 0,
        "★ 逐单元格差异数": len(_diffs),
        "★ 差异明细（前 5）": _diffs[:5],
        "★ 中文 原/新": f"{_cjk_o}/{_cjk_n}",
        "★ ★ 转换无损": (not _diffs) and _cjk_o == _cjk_n,
        "★ UTF-8 工作副本": str(_dst.relative_to(ROOT)),
    }
    print(f"      {_tag:4s} 编码={_enc}｜行={len(_rows_new)}｜列="
          f"{len(_rows_new[0]) if _rows_new else 0}｜差异={len(_diffs)}｜"
          f"无损={_converted[_tag]['★ ★ 转换无损']}")
    if _diffs:
        _errs.append(f"★ {_tag}：编码转换产生 {len(_diffs)} 处单元格差异 ⇒ ★ 数据损坏")
_rep["① 文件与编码验收"] = _converted

# ══ ② 结构检查 ══
print("  ★ ② 结构检查")
_parsed = {}
for _tag, _p in FILES.items():
    _rows = list(csv.DictReader(io.StringIO(
        (OUTD / f"utf8_{_p.name}").read_text(encoding="utf-8"))))
    _parsed[_tag] = _rows
_base = [json.loads(l) for l in
         (D3 / "V2-E3_原文与证据不可编辑字段基线.jsonl")
         .read_text(encoding="utf-8").splitlines() if l.strip()]
_base_ids = {b["snippet_id"] for b in _base}
_struct = {}
for _tag in ("A", "B"):
    _rows = _parsed[_tag]
    _ids = [r.get("snippet_id") for r in _rows]
    _sids = [i for i in _ids if i]
    _bad = sorted({i for i in _sids if i not in _base_ids})
    _gk = [r.get("gold_knowledge_id") for r in _rows
           if (r.get("gold_knowledge_id") or "").strip()]
    _gk_bad = [g for g in _gk if not (g or "").startswith("GK-")]
    _dup_gk = [g for g, c in collections.Counter(_gk).items() if c > 1]
    _cover = {i for i in _sids if i in _base_ids}
    _struct[_tag] = {
        "★ 行数": len(_rows),
        "★ 唯一 snippet_id 数": len(set(_sids)),
        "★ 覆盖基线 snippet_id 数": len(_cover),
        "★ 基线总数": len(_base_ids),
        "★ ★ 是否覆盖全部 54": len(_cover) == len(_base_ids),
        "★ 无效 snippet_id": _bad,
        "★ 原子知识行数（★ 允许 ≠ 54）": len(_gk),
        "★ 非法 gold_knowledge_id": _gk_bad,
        "★ 重复 gold_knowledge_id": _dup_gk,
        "★ 断裂引用（★ gold_knowledge_id 的 snippet 前缀不在基线内）": [
            g for g in _gk if g and g.startswith("GK-")
            and g[3:].rsplit("-", 1)[0] not in _base_ids],
    }
    print(f"      {_tag}: 行 {_struct[_tag]['★ 行数']}｜覆盖 "
          f"{_struct[_tag]['★ 覆盖基线 snippet_id 数']}/54｜原子知识 "
          f"{_struct[_tag]['★ 原子知识行数（★ 允许 ≠ 54）']}｜无效 sid "
          f"{len(_bad)}｜重复 gk {len(_dup_gk)}")
    if not _struct[_tag]["★ ★ 是否覆盖全部 54"]:
        _errs.append(f"★ {_tag} 未覆盖全部 54 个 snippet_id")
    if _bad:
        _errs.append(f"★ {_tag} 含无效 snippet_id {len(_bad)} 个")
    if _gk_bad or _dup_gk:
        _errs.append(f"★ {_tag} 原子知识 ID 异常")
_rep["② 结构检查"] = _struct

# ══ ③ 不可编辑字段与 E3 基线一致（★ 本包【本就不含原文】⇒ 校验标识列）══
_imm_check = {}
for _tag in ("A", "B"):
    _rows = _parsed[_tag]
    _map = {r.get("snippet_id"): r for r in _rows if r.get("snippet_id")}
    _miss = [b["snippet_id"] for b in _base
             if b["snippet_id"] not in _map]
    _imm_check[_tag] = {"★ 基线中缺失于回收文件的 snippet_id": _miss,
                   "★ 说明": ("★ 本模板【不含原文与哈希列】（★ 那是只读证据包的内容）"
                          "★ ⇒ ★ 不可编辑字段的逐单元格比对由 "
                          "★ `p72_freeze_pool.py --verify` 针对【片段级表】执行")}
    print(f"      {_tag}: 基线 snippet_id 缺失 {len(_miss)}")
_rep["③ 不可编辑字段核对"] = _imm_check

# ══ ④ 证据包一致性 ══
_pk = json.loads((D4 / "V2-E4_队列B只读证据包哈希.json").read_text(encoding="utf-8"))
_ev_rows = [json.loads(l) for l in
            (D4 / "V2-E4_队列B只读证据包.jsonl").read_text(encoding="utf-8").splitlines()
            if l.strip()]
_ev_ok = (hashlib.sha256((D4 / "V2-E4_队列B只读证据包.html").read_bytes()).hexdigest()
          == _pk["★ 只读证据包 html"])
_rep["④ 证据包一致性"] = {
    "★ 证据包条数": len(_ev_rows),
    "★ html 哈希与清单一致": _ev_ok,
    "★ jsonl 哈希与清单一致": (
        hashlib.sha256((D4 / "V2-E4_队列B只读证据包.jsonl").read_bytes()).hexdigest()
        == _pk["★ 只读证据包 jsonl"]),
    "★ snippet_id 集合与基线一致": (
        {r["snippet_id"] for r in _ev_rows} == _base_ids),
}
print(f"      证据包 {len(_ev_rows)} 条｜html 哈希一致={_ev_ok}")

# ══ ⑤ 片段级一致性 + 原子知识级一致性 ══
SNIP_FIELDS = ["★ 是否存在目标知识", "★ 知识类别", "★ 是否需跨句/跨节证据",
               "★ 审核意见", "★ 不确定原因"]
KNOW_FIELDS = ["knowledge_kind", "evidence_span", "subject", "action", "object",
               "strength", "polarity", "condition", "exception",
               "evidence_support", "review_note"]


def _snip_map(rows):
    """★ 片段级：★ 按 snippet_id 去重（★ 一片段多条知识时会有重复行）。"""
    _m = {}
    for _r in rows:
        _sid = (_r.get("snippet_id") or "").strip()
        if not _sid:
            continue
        _m.setdefault(_sid, _r)
    return _m


_A_s, _B_s = _snip_map(_parsed["A"]), _snip_map(_parsed["B"])
_snip_stats = {
    "★ A 覆盖": len(_A_s), "★ B 覆盖": len(_B_s),
    "★ 是否存在目标知识 分布 A": dict(collections.Counter(
        (_A_s[s].get("★ 是否存在目标知识") or "").strip() for s in _A_s)),
    "★ 是否存在目标知识 分布 B": dict(collections.Counter(
        (_B_s[s].get("★ 是否存在目标知识") or "").strip() for s in _B_s)),
    "★ 知识类别分布 A": dict(collections.Counter(
        (_A_s[s].get("★ 知识类别") or "").strip() for s in _A_s)),
    "★ 知识类别分布 B": dict(collections.Counter(
        (_B_s[s].get("★ 知识类别") or "").strip() for s in _B_s)),
    "★ uncertain 数 A": sum(1 for s in _A_s
                     if "不确定" in (_A_s[s].get("★ 是否存在目标知识") or "")),
    "★ uncertain 数 B": sum(1 for s in _B_s
                     if "不确定" in (_B_s[s].get("★ 是否存在目标知识") or "")),
    "★ 无目标知识片段数 A": sum(1 for s in _A_s
                      if (_A_s[s].get("★ 是否存在目标知识") or "").strip() in ("否", "无")),
    "★ 无目标知识片段数 B": sum(1 for s in _B_s
                      if (_B_s[s].get("★ 是否存在目标知识") or "").strip() in ("否", "无")),
}
_snip_same = sum(1 for s in _A_s if s in _B_s and
                 (_A_s[s].get("★ 是否存在目标知识") or "").strip()
                 == (_B_s[s].get("★ 是否存在目标知识") or "").strip())
_snip_stats["★ 片段级『是否存在目标知识』一致数"] = _snip_same
_snip_stats["★ 片段级一致率"] = round(_snip_same / max(1, len(_A_s)), 4)


def _know_map(rows):
    _m = {}
    for _r in rows:
        _gk = (_r.get("gold_knowledge_id") or "").strip()
        if not _gk:
            continue
        _m[_gk] = _r
    return _m


_A_k, _B_k = _know_map(_parsed["A"]), _know_map(_parsed["B"])
# ★ 语义对齐：★ 按 (snippet_id, 序号) 对齐（★ 同一片段的第 N 条知识）
def _sem_key(r):
    _sid = (r.get("snippet_id") or "").strip()
    _gk = (r.get("gold_knowledge_id") or "").strip()
    _seq = _gk.rsplit("-", 1)[-1] if "-" in _gk else "1"
    return (_sid, _seq)


_A_s2 = {_sem_key(r): r for r in _parsed["A"]
         if (r.get("gold_knowledge_id") or "").strip()}
_B_s2 = {_sem_key(r): r for r in _parsed["B"]
         if (r.get("gold_knowledge_id") or "").strip()}
_common = set(_A_s2) & set(_B_s2)
_only_a = set(_A_s2) - set(_B_s2)
_only_b = set(_B_s2) - set(_A_s2)
_field_diff = collections.Counter()
_evidence_diff = collections.Counter()
_pair_same = 0
for _k in _common:
    _a, _b = _A_s2[_k], _B_s2[_k]
    _same = True
    for _f in KNOW_FIELDS:
        if (_a.get(_f) or "").strip() != (_b.get(_f) or "").strip():
            _field_diff[_f] += 1
            _same = False
    if (_a.get("evidence_support") or "").strip() != \
            (_b.get("evidence_support") or "").strip():
        _evidence_diff["evidence_support"] += 1
    if _same:
        _pair_same += 1
_know_stats = {
    "★ A 原子知识数": len(_A_s2), "★ B 原子知识数": len(_B_s2),
    "★ 语义对齐后的共同知识数": len(_common),
    "★ 只由 A 识别": len(_only_a), "★ 只由 B 识别": len(_only_b),
    "★ 逐字段全同的知识对": _pair_same,
    "★ 关键字段分歧计数": dict(_field_diff),
    "★ 证据支持分歧": dict(_evidence_diff),
    "★ ★ 未做字段级 Kappa（★ 原子知识匹配未完成）": True,
}
print(f"      片段级一致 {_snip_same}/{len(_A_s)}；原子知识 A {len(_A_s2)} B {len(_B_s2)}"
      f"｜共同 {len(_common)}｜仅A {len(_only_a)}｜仅B {len(_only_b)}")
_rep["⑤ 双层一致性统计"] = {"★ 片段级": _snip_stats, "★ 原子知识级": _know_stats}

# ══ ⑥ 第三方仲裁有效性 ══
_arb = _parsed["ARB"]
_arb_checks = {"★ 行数": len(_arb), "★ 填了结论的行数": sum(
    1 for _r in _arb if (_r.get("★ 仲裁后 knowledge_kind") or "").strip()
    or (_r.get("★ 仲裁后 truth_label") or "").strip()),
    "★ 有审核者 ID 的行数": sum(
        1 for _r in _arb if (_r.get("★ 仲裁者 ID（★ 匿名编号）") or "").strip()),
    "★ 有日期的行数": sum(
        1 for _r in _arb if (_r.get("★ 审核日期") or "").strip()),
    "★ 有理由的行数": sum(
        1 for _r in _arb if (_r.get("★ 仲裁理由") or "").strip()),
    "★ unresolved 标记分布": dict(collections.Counter(
        (_r.get("★ 是否 unresolved") or "").strip() for _r in _arb)),
}
# ★ 仲裁 ID 是否与 A/B 审核者 ID 不同
_ids_a = {(_r.get("★ 审核者 ID") or "").strip() for _r in _parsed["A"]} - {""}
_ids_b = {(_r.get("★ 审核者 ID") or "").strip() for _r in _parsed["B"]} - {""}
_ids_arb = {(_r.get("★ 仲裁者 ID（★ 匿名编号）") or "").strip() for _r in _arb} - {""}
_arb_checks["★ A 审核者 ID"] = sorted(_ids_a)
_arb_checks["★ B 审核者 ID"] = sorted(_ids_b)
_arb_checks["★ 仲裁者 ID"] = sorted(_ids_arb)
_arb_checks["★ ★ 仲裁者与 A/B 区分开"] = bool(
    _ids_arb and _ids_arb.isdisjoint(_ids_a) and _ids_arb.isdisjoint(_ids_b))
# ★ 复制 A 或 B 答案是否算「完成仲裁」
_copy_only = 0
_resolved = 0
for _r in _arb:
    _ak = (_r.get("★ 仲裁后 knowledge_kind") or "").strip()
    if not _ak:
        continue
    _av = (_r.get("★ A:knowledge_kind") or "").strip()
    _bv = (_r.get("★ B:knowledge_kind") or "").strip()
    _arv = (_r.get("★ 仲裁后 knowledge_kind") or "").strip()
    _arv = "" if _arv.lower() in ("null", "none", "nan") else _arv
    if _arv in (_av, _bv) and not (_r.get("★ 仲裁理由") or "").strip():
        _copy_only += 1
    else:
        _resolved += 1
_arb_checks["★ 仅复制 A/B 且无理由（★ 不算完成仲裁）"] = _copy_only
_arb_checks["★ 实质裁定的条目数"] = _resolved
print(f"      仲裁：填结论 {_arb_checks['★ 填了结论的行数']}｜有ID "
      f"{_arb_checks['★ 有审核者 ID 的行数']}｜有日期 {_arb_checks['★ 有日期的行数']}"
      f"｜有理由 {_arb_checks['★ 有理由的行数']}｜仅复制无理由 {_copy_only}")
_rep["⑥ 第三方仲裁有效性"] = _arb_checks

# ══ ⑦ 生成 Gold（★ 严格区分四态）══
_gold = []
for _sid in sorted(_base_ids):
    _a = _A_s.get(_sid, {})
    _b = _B_s.get(_sid, {})
    _av = (_a.get("★ 是否存在目标知识") or "").strip()
    _bv = (_b.get("★ 是否存在目标知识") or "").strip()
    _ak = [_r for _r in _parsed["A"]
           if (_r.get("snippet_id") or "").strip() == _sid
           and (_r.get("gold_knowledge_id") or "").strip()]
    _bk = [_r for _r in _parsed["B"]
           if (_r.get("snippet_id") or "").strip() == _sid
           and (_r.get("gold_knowledge_id") or "").strip()]
    _arb_rows = [_r for _r in _arb
                 if (_r.get("snippet_id") or "").strip() == _sid]
    _ar = _arb_rows[0] if _arb_rows else {}
    _areason = (_ar.get("★ 仲裁理由") or "").strip()
    _adispute = (_ar.get("★ 匹配争议类型") or "").strip()
    # ★ ★ 仲裁优先（★ 第三方裁定【优先于】A/B 原始判定）
    _adj_exists = None
    if "exists=否" in _areason:
        _adj_exists = False
    elif "exists=是" in _areason:
        _adj_exists = True
    _n_gold = max(len(_ak), len(_bk))
    _status = "unresolved"
    if _adj_exists is False:
        # ★ ★ 仲裁裁定「无目标知识」⇒ ★ **items 为空**（★ 不生成原子知识 Gold）
        _status = "no_target_knowledge"
        _n_gold = 0
    elif _adj_exists is True:
        _status = "valid_gold"
    elif _n_gold == 0:
        if _av and _bv and _av == _bv:
            _status = ("no_target_knowledge" if _av in ("否", "无")
                       else "uncertain")
        elif "不确定" in (_av + _bv):
            _status = "uncertain"
        else:
            _status = "unresolved"
    else:
        _status = "valid_gold"
    for _i in range(_n_gold):
        _ga = _ak[_i] if _i < len(_ak) else {}
        _gb = _bk[_i] if _i < len(_bk) else {}
        _gkind = (_ga.get("knowledge_kind") or _gb.get("knowledge_kind") or "").strip()
        _gspan = (_ga.get("evidence_span") or _gb.get("evidence_span") or "").strip()
        _gkind_b = (_gb.get("knowledge_kind") or "").strip()
        _d = {f: ((_ga.get(f) or "").strip() != (_gb.get(f) or "").strip())
              for f in KNOW_FIELDS}
        _und = [f for f, v in _d.items() if v]
        def _av_of(row, col):
            _v = (row.get(col) or "").strip()
            return "" if _v.lower() in ("null", "none", "nan") else _v
        _ares = _av_of(_ar, "★ 仲裁后 knowledge_kind")
        if not _ares:
            _ares = _gkind
        _gold.append({
            "gold_knowledge_id": (_ga.get("gold_knowledge_id")
                                  or _gb.get("gold_knowledge_id") or f"GK-{_sid}-{_i+1}"),
            "snippet_id": _sid,
            "knowledge_kind": _ares or _gkind,
            "evidence_span": _gspan,
            "★ 原文支持说明": (_ga.get("review_note") or _gb.get("review_note") or "").strip(),
            "★ 适用的结构化字段": {
                f: (_av_of(_ar, f"★ 仲裁后 {f}")
                    or (_ga.get(f) or "").strip()
                    or (_gb.get(f) or "").strip())
                for f in KNOW_FIELDS if f != "review_note"},
            "★ 仲裁状态": ("★ 已仲裁" if _ares else
                        ("★ 无实质分歧" if not _und else "★ 字段级分歧未仲裁")),
            "★ 分歧字段": _und,
            "★ status": _status,
            "★ 来源 RFC": next((x["document"] for x in _base
                          if x["snippet_id"] == _sid), ""),
            "★ 来源版本哈希": next((x["rfc_sha256"] for x in _base
                           if x["snippet_id"] == _sid), ""),
            "★ A 原始": {f: (_ga.get(f) or "").strip() for f in KNOW_FIELDS},
            "★ B 原始": {f: (_gb.get(f) or "").strip() for f in KNOW_FIELDS},
        })
    if _n_gold == 0:
        _gold.append({
            "gold_knowledge_id": f"GK-{_sid}-0",
            "snippet_id": _sid, "knowledge_kind": "", "evidence_span": "",
            "★ 原文支持说明": (_a.get("★ 审核意见") or "").strip(),
            "★ 适用的结构化字段": {},
            "★ 仲裁状态": "★ 无原子知识",
            "★ 分歧字段": ([] if _av == _bv else ["★ 是否存在目标知识"]),
            "★ status": _status,
            "★ 来源 RFC": next((x["document"] for x in _base
                          if x["snippet_id"] == _sid), ""),
            "★ 来源版本哈希": next((x["rfc_sha256"] for x in _base
                           if x["snippet_id"] == _sid), ""),
            "★ A 原始": {}, "★ B 原始": {},
        })

with (DELIV / "B1_人工真值冻结清单.jsonl").open("w", encoding="utf-8") as f:
    for _g in _gold:
        f.write(json.dumps(_g, ensure_ascii=False) + "\n")
with (DELIV / "B1_原子知识对齐台账.jsonl").open("w", encoding="utf-8") as f:
    for _g in _gold:
        f.write(json.dumps(_g, ensure_ascii=False) + "\n")
_status_c = collections.Counter(g["★ status"] for g in _gold)
_frozen_hash = hashlib.sha256(
    (DELIV / "B1_人工真值冻结清单.jsonl").read_bytes()).hexdigest()
_rep["⑦ Gold 冻结"] = {
    "★ status 分布": dict(_status_c),
    "★ Gold 总条数": len(_gold),
    "★ 有效知识数（★ valid_gold）": _status_c.get("valid_gold", 0),
    "★ no_target_knowledge": _status_c.get("no_target_knowledge", 0),
    "★ uncertain": _status_c.get("uncertain", 0),
    "★ unresolved": _status_c.get("unresolved", 0),
    "★ 冻结清单 SHA256": _frozen_hash,
    "★ 片段级字段分歧未仲裁的片段数": sum(
        1 for g in _gold if g.get("★ 分歧字段")),
}
print(f"      Gold {len(_gold)} 条｜{dict(_status_c)}")
_rep["★ 错误"] = _errs
_rep["★ 警告"] = _warns
(OUTD / "h2_b1_acceptance.json").write_text(
    json.dumps(_rep, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ★★ 验收错误 {len(_errs)} 项：{_errs or '★ 无'}")
print(f"  ⇒ {OUTD/'h2_b1_acceptance.json'}")
print(f"  ⇒ {DELIV/'B1_人工真值冻结清单.jsonl'}")
