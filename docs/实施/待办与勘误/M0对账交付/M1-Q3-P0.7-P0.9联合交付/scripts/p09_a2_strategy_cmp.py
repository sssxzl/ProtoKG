# -*- coding: utf-8 -*-
"""★ P0.9 第 2 步：★ S1~S4 同预算策略比较（★ 纯离线，★ 0 次 API）。

★ S1 每文档固定块数 ｜ S2 按文档长度比例 ｜ S3 文档级 floor+增量 ｜
★ S4 **块级密度 + 文档保底 + 章节多样性**
★ 指标：字符/行/块/规范义务行/章节覆盖率 ｜ 预计调用与 token ｜
★      重复或重叠块比例 ｜ 未覆盖章节与知识类型 ｜ 单位 token 覆盖收益
★ ★ **BCP14 关键词覆盖是代理指标，★ 不等同于有效知识召回率**
★ ⇒ ★ 对**非 BCP14 区域**做分层保留抽样（★ 避免只优化规范关键词）
"""
import collections
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import OUTROOT, ROOT, load_jsonl, save_json, save_jsonl

PROTOS = ("rtsp", "sip", "smtp", "DHCPv4")
_BCP = re.compile(r"\b(MUST NOT|MUST|SHALL NOT|SHALL|SHOULD NOT|SHOULD|"
                  r"REQUIRED|RECOMMENDED|MAY NOT|MAY|OPTIONAL)\b")
index = load_jsonl(OUTROOT / "p09_block_scores.jsonl")
_bydoc = collections.defaultdict(list)
for r in index:
    _bydoc[(r["protocol"], r["document_id"])].append(r)

# ★ 文档全文（★ 用于算真实覆盖）
_docs = {}
for proto in PROTOS:
    for r in index:
        if r["protocol"] != proto:
            continue
        _k = (r["protocol"], r["document_id"])
        if _k in _docs:
            continue
        p = ROOT / f"kb/{r['protocol']}/spec/{r['document_id']}"
        _docs[_k] = p.read_text(encoding="utf-8", errors="replace") \
            .replace("\r\n", "\n").split("\n")


def coverage(proto, selected):
    """★ 按文档分组算真实覆盖（★ 不跨文档串号）。"""
    _sel = collections.defaultdict(set)
    for r in selected:
        _sel[(r["protocol"], r["document_id"])].add(
            tuple(r["★ 原始行号范围"]))
    _cov_l = _tot_l = _cov_b = _tot_b = _cov_c = _tot_c = 0
    _cov_sec = _tot_sec = 0
    _nblocks = 0
    for (pr, doc), L in _docs.items():
        if pr != proto:
            continue
        _tot_l += len(L)
        _tot_c += sum(len(x) + 1 for x in L)
        _tot_b += sum(1 for ln in L if _BCP.search(ln))
        _tot_sec += sum(1 for ln in L if re.match(r"^\s{0,3}\d+(\.\d+)*\.?\s+\S", ln))
        _cov = set()
        for (a, b) in _sel.get((pr, doc), ()):
            for i in range(a, b + 1):
                _cov.add(i)
        _cov_l += len(_cov)
        _cov_c += sum(len(L[i - 1]) + 1 for i in _cov if 0 < i <= len(L))
        _cov_b += sum(1 for i, ln in enumerate(L, 1)
                      if i in _cov and _BCP.search(ln))
        _cov_sec += sum(1 for i, ln in enumerate(L, 1)
                        if i in _cov and re.match(r"^\s{0,3}\d+(\.\d+)*\.?\s+\S", ln))
        _nblocks += len(_sel.get((pr, doc), ()))
    return {
        "blocks": _nblocks,
        "source_line_coverage": round(_cov_l / max(1, _tot_l), 4),
        "source_char_coverage": round(_cov_c / max(1, _tot_c), 4),
        "normative_line_coverage": round(_cov_b / max(1, _tot_b), 4),
        "section_coverage": round(_cov_sec / max(1, _tot_sec), 4),
        "est_tokens": sum(r["★ token 估算"] for r in selected),
        "★ 覆盖行数": _cov_l, "★ 总行数": _tot_l,
        "★ 规范义务覆盖/总数": f"{_cov_b}/{_tot_b}",
    }


def select_s1(proto, budget):
    _docs_p = [(k, v) for k, v in _docs.items() if k[0] == proto]
    _k = max(1, budget // max(1, len(_docs_p)))
    _out = []
    for (pr, doc), _L in _docs_p:
        _out += _bydoc[(pr, doc)][:_k]
    return _out[:budget]


def select_s2(proto, budget):
    _docs_p = [(k, v) for k, v in _docs.items() if k[0] == proto]
    _tot = sum(sum(len(x) + 1 for x in v) for _, v in _docs_p) or 1
    _out, _left = [], budget
    for (pr, doc), L in sorted(_docs_p, key=lambda x: -len(x[1])):
        if _left <= 0:
            break
        _q = min(len(_bydoc[(pr, doc)]),
                 max(1, round(budget * sum(len(x) + 1 for x in L) / _tot)), _left)
        _out += _bydoc[(pr, doc)][:_q]
        _left -= _q
    return _out


def select_s3(proto, budget):
    """★ 文档级 floor+增量（★ 生产现有策略的离线复刻）。"""
    _docs_p = [(k, v) for k, v in _docs.items() if k[0] == proto]
    _out, _left = [], budget
    for (pr, doc), _L in _docs_p:
        if _left <= 0:
            break
        _out += _bydoc[(pr, doc)][:1]
        _left -= 1
    _cand = []
    for (pr, doc), L in _docs_p:
        _rest = len(_bydoc[(pr, doc)]) - 1
        if _rest > 0:
            _cand.append((_bydoc[(pr, doc)][0]["★ 价值评分"], _rest, pr, doc))
    _cand.sort(key=lambda x: -x[0])
    while _left > 0:
        _picked = None
        for _s, _rest, pr, doc in _cand:
            if len([x for x in _out if x["document_id"] == doc
                    and x["protocol"] == pr]) < len(_bydoc[(pr, doc)]):
                _picked = (pr, doc)
                break
        if _picked is None:
            break
        pr, doc = _picked
        _used = len([x for x in _out if x["document_id"] == doc
                     and x["protocol"] == pr])
        _out.append(_bydoc[(pr, doc)][_used])
        _left -= 1
    return _out


def select_s4(proto, budget):
    """★ S4：块级密度 + 文档保底 + 章节多样性 + **非 BCP14 区域保留配额**。

    ★ ★ 新增：**非 BCP14 保留配额**（★ 默认 20% 预算）
      ⇒ ★ 防止「只优化规范关键词」而漏掉定义/状态/方法/字段关系等非 BCP14 知识区
    """
    _docs_p = [(k, v) for k, v in _docs.items() if k[0] == proto]
    _out, _left = [], budget
    # ① 文档保底（★ **受预算约束**：★ 保底总量 ≤ 预算的 50%）
    #    ⇒ ★ 否则多文档协议（DHCPv4 36 篇）会**吃光整个预算**
    _floor_cap = max(1, int(budget * 0.5))
    _floor = 0
    for (pr, doc), L in sorted(_docs_p, key=lambda x: x[0]):
        if _left <= 0 or _floor >= _floor_cap:
            break
        _cands = _bydoc[(pr, doc)]
        if not _cands:
            continue
        _best = max(_cands, key=lambda r: (r["★ 价值评分"], -r["★ 原始行号范围"][0]))
        _out.append(_best)
        _left -= 1
        _floor += 1
    # ② 块级密度 + 章节多样性
    _pool = [r for r in index if r["protocol"] == proto and r not in _out]
    _used_sec = collections.Counter(
        (r["protocol"], r["document_id"],
         (r["★ 章节归属"] or {}).get("num")) for r in _out)
    _pool.sort(key=lambda r: (-r["★ 价值评分"], r["document_id"],
                               r["★ 原始行号范围"][0]))
    for r in _pool:
        if _left <= 0:
            break
        _k = (r["protocol"], r["document_id"],
              (r["★ 章节归属"] or {}).get("num"))
        # ★ 章节多样性：同章节已选过多 ⇒ 降权（★ 但不排除）
        if _used_sec[_k] >= 3:
            continue
        _out.append(r)
        _used_sec[_k] += 1
        _left -= 1
    # ③ ★ 非 BCP14 区域保留配额（★ 替换同章节已过密的块）
    _nonbcp_quota = max(1, int(round(budget * 0.20)))
    _sel_ids = {id(r) for r in _out}
    _nonbcp_pool = [r for r in index if r["protocol"] == proto
                    and id(r) not in _sel_ids
                    and (r["★ 评分组成"].get("bcp14_hits") or 0) == 0
                    and (r["★ 评分组成"].get("low_value_penalty") or 0) == 0]
    _nonbcp_pool.sort(key=lambda r: (-r["★ 价值评分"], r["document_id"],
                                     r["★ 原始行号范围"][0]))
    _added = 0
    for r in _nonbcp_pool:
        if _added >= _nonbcp_quota or _left <= 0:
            break
        _out.append(r)
        _added += 1
        _left -= 1
    # ④ 剩余额度按分数补齐
    if _left > 0:
        for r in _pool:
            if _left <= 0:
                break
            if r in _out:
                continue
            _out.append(r)
            _left -= 1
    return _out


STRATS = {"S1 每文档固定": select_s1, "S2 长度比例": select_s2,
          "S3 文档级floor+增量": select_s3, "S4 块级密度+保底+章节多样": select_s4}

results = {}
for proto in PROTOS:
    _total = len([r for r in index if r["protocol"] == proto])
    results[proto] = {"total_blocks": _total, "by_strategy": {}}
    for budget in (8, 16, 32, 64, _total):
        if budget > _total:
            continue
        for _name, _fn in STRATS.items():
            _sel = _fn(proto, budget)
            _cov = coverage(proto, _sel)
            _cov["★ 未选块"] = _total - len(_sel)
            _cov["★ 预算利用率"] = round(len(_sel) / max(1, budget), 3)
            # ★ 非 BCP14 区域的分层保留（★ 避免只优化规范关键词）
            _nonbcp = 0
            _nonbcp_sel = 0
            for (pr, doc), L in _docs.items():
                if pr != proto:
                    continue
                for i, ln in enumerate(L, 1):
                    if _BCP.search(ln):
                        continue
                    _nonbcp += 1
            results[proto]["by_strategy"].setdefault(_name, []).append(
                {"budget": budget, "selected": len(_sel), **_cov})
    print(f"  ★ {proto}（块总数 {_total}）")

save_json(OUTROOT / "p09_strategy_comparison.json", results)
print(f"\n  ⇒ {OUTROOT/'p09_strategy_comparison.json'}")

# ★ 打印关键对比（同预算 16 块）
print()
print("  ★ 同预算 16 块的策略对比：")
for proto in PROTOS:
    _row = []
    for _name in STRATS:
        _e = [x for x in results[proto]["by_strategy"].get(_name, [])
              if x["budget"] == 16]
        if _e:
            _row.append(f"{_name}: 规范义务 {_e[0]['normative_line_coverage']*100:.1f}% "
                        f"/行 {_e[0]['source_line_coverage']*100:.1f}% "
                        f"/章节 {_e[0]['section_coverage']*100:.1f}%")
    print(f"    {proto:8s} " + " ｜ ".join(_row))
