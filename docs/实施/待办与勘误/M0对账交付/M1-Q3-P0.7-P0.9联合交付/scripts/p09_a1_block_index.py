# -*- coding: utf-8 -*-
"""★ P0.9 第 1 步：★ 精确块索引 + 块级价值评分（★ 纯离线，★ 0 次 API）。

★ 严格使用**真实行号覆盖**（★ 不得再用已被证伪的「每块固定 58 行」近似）
★ 块级清单记录：protocol / document_id / RFC SHA256 / chunk_id / 原始行号范围 /
★ 字符偏移 / chunk hash / 章节归属 / 真实字符数与 token 估算 / 已处理-未处理状态 / 未选中原因
"""
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3]))
from _lib import OUTROOT, save_json, save_jsonl
from core import paths
from core.fused.extraction import prose_semantics as ps

PROTOS = ("rtsp", "sip", "smtp", "DHCPv4")
CHARS = ps._MAX_BLOCK_CHARS
_BCP = re.compile(r"\b(MUST NOT|MUST|SHALL NOT|SHALL|SHOULD NOT|SHOULD|"
                  r"REQUIRED|RECOMMENDED|MAY NOT|MAY|OPTIONAL)\b")
_RE_SEC = re.compile(r"^\s{0,3}(\d+(?:\.\d+)*)\.?\s+([A-Z][A-Za-z0-9 /\-()]{3,70})\s*$")
_RE_CAP = re.compile(r"^(Figure|Table|Note|Listing)\s+\d+", re.I)
_RE_ABNF = re.compile(r"^[=;]")
_RE_PAGE = re.compile(r"^\[Page \d+\]")
_RE_LOW = re.compile(r"^(Abstract|Index|Table of Contents|References|"
                     r"Acknowledg|Authors' Addresses|Contributors|"
                     r"Copyright Notice|Status of this Memo)", re.I)

# ★ 低价值信号（★ 版权页/目录/重复样板/纯参考文献）
_RE_COPY = re.compile(r"Copyright \(C\)|All Rights Reserved|"
                       r"Distribution of this memo is unlimited|"
                       r"Internet Society|Standards Track|This document is", re.I)

# ★ 规范线索（★ 只是**发现线索**，★ 不是规范义务成立的证明）
_NORM_HINT = {
    "bcp14": 3.0,
    "method": 1.2,          # SETUP / TEARDOWN / OPTIONS ...
    "header": 1.0,          # CSeq / Via / Require ...
    "status_code": 1.2,     # 4xx / 5xx
    "state_transition": 1.5,  # MUST ... state
    "field_format": 1.0,    # = / ::=
    "xref": 0.6,            # Section 引用
    "condition": 0.8,       # if / unless / except
}


def _sections(lines):
    _out = []
    for i, ln in enumerate(lines, 1):
        m = _RE_SEC.match(ln)
        if m:
            _out.append((i, m.group(1), m.group(2).strip()))
    return _out


def _block_split(lines):
    """★ 真实切块（★ 与生产 `_split_blocks` 同逻辑，★ 但取全文）。"""
    out, cur, start = [], [], 1
    for i, ln in enumerate(lines, 1):
        if not cur:
            start = i
        cur.append(ln)
        if sum(len(x) + 1 for x in cur) >= CHARS:
            out.append((start, "\n".join(cur)))
            cur = []
    if cur:
        out.append((start, "\n".join(cur)))
    return out


def score_block(text, lines_range, all_lines):
    """★ 块级价值评分（★ 可解释的组成部分 + 固定版本 + 确定性）。"""
    _parts = {}
    _low = []
    _up = text.upper()
    _n_bcp = len(_BCP.findall(text))
    _parts["bcp14_hits"] = _n_bcp
    _parts["bcp14_score"] = round(min(_n_bcp, 8) * _NORM_HINT["bcp14"], 3)
    _n_sec = len(re.findall(r"\bSection\s+\d", text))
    _parts["xref_score"] = round(min(_n_sec, 5) * _NORM_HINT["xref"], 3)
    _n_hdr = len(re.findall(r"\b[A-Z][A-Za-z-]{2,}\s+(header|field)\b", text))
    _parts["header_score"] = round(min(_n_hdr, 6) * _NORM_HINT["header"], 3)
    _n_meth = len(re.findall(
        r"\b(SETUP|PLAY|PAUSE|TEARDOWN|OPTIONS|DESCRIBE|ANNOUNCE|RECORD|"
        r"INVITE|ACK|BYE|CANCEL|REGISTER|SUBSCRIBE|PUBLISH|MESSAGE)\b", text))
    _parts["method_score"] = round(min(_n_meth, 8) * _NORM_HINT["method"], 3)
    _n_st = len(re.findall(r"\b(state|mode|transaction|dialog)\b", text, re.I))
    _parts["state_score"] = round(min(_n_st, 6) * _NORM_HINT["state_transition"], 3)
    _n_cond = len(re.findall(r"\b(if|unless|except|only when|in response to)\b",
                             text, re.I))
    _parts["condition_score"] = round(min(_n_cond, 5) * _NORM_HINT["condition"], 3)
    _n_abnf = sum(1 for ln in lines_range if _RE_ABNF.match(ln.strip()))
    _parts["abnf_score"] = round(min(_n_abnf, 4) * _NORM_HINT["field_format"], 3)
    # ★ 低价值标记
    if _RE_COPY.search(text):
        _low.append("copyright_boilerplate")
    if _RE_CAP.match(text.strip()):
        _low.append("caption")
    if _RE_LOW.match(text.strip()):
        _low.append("front_matter")
    if _RE_PAGE.match(text.strip()):
        _low.append("page_footer")
    _low_score = len(_low) * 1.6
    _parts["low_value_signals"] = _low
    _parts["low_value_penalty"] = round(_low_score, 3)
    _total = round(sum(v for k, v in _parts.items()
                       if k.endswith("_score")) - _low_score, 3)
    return _total, _parts


index = []
for proto in PROTOS:
    for f in sorted(paths.kb_source_dir(proto, "rfc").glob("*.txt")):
        raw = f.read_bytes()
        _sha = hashlib.sha256(raw).hexdigest()
        text = raw.decode("utf-8", errors="replace").replace("\r\n", "\n")
        lines = text.split("\n")
        secs = _sections(lines)
        for bi, (start, btext) in enumerate(_block_split(lines)):
            end = start + btext.count("\n")
            _blk_lines = lines[start - 1:end]
            # ★ 章节归属（★ 最近的、编号更小的标题）
            _sec = None
            for s in secs:
                if s[0] <= start:
                    _sec = {"line": s[0], "num": s[1], "title": s[2]}
            _score, _parts = score_block(btext, _blk_lines, lines)
            index.append({
                "protocol": proto,
                "document_id": f.name,
                "rfc_sha256": _sha,
                "chunk_id": f"{f.name}@{start}",
                "★ 原始行号范围": [start, end],
                "★ 字符偏移": [sum(len(x) + 1 for x in lines[:start - 1]),
                              sum(len(x) + 1 for x in lines[:end])],
                "chunk_hash": hashlib.sha256(
                    f"{f.name}|{start}|{btext}".encode("utf-8")).hexdigest(),
                "★ 章节归属": _sec,
                "★ 真实字符数": len(btext),
                "★ 真实行数": end - start + 1,
                "★ token 估算": round(len(btext) / 3.2),      # ★ 中文/英文混合经验值
                "processed": False,
                "★ 未选中原因": None,
                "★ 价值评分": _score,
                "★ 评分组成": _parts,
            })

print(f"  ★ 块索引总数 = {len(index)}")
_by = {}
for r in index:
    _by[r["protocol"]] = _by.get(r["protocol"], 0) + 1
print(f"  ★ 按协议: {_by}")
# ★ 全文选齐时的真实覆盖（★ ★ **按文档分组**计算 ⇒ 避免跨文档行号串号）
for proto in PROTOS:
    _rs = [r for r in index if r["protocol"] == proto]
    _cov_l_total = _cov_b_total = _tot_l = _tot_b = 0
    for f in sorted(paths.kb_source_dir(proto, "rfc").glob("*.txt")):
        L = f.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
        _tot_l += len(L)
        _tot_b += sum(1 for ln in L if _BCP.search(ln))
        _cov = set()
        for r in _rs:
            if r["document_id"] != f.name:
                continue
            for i in range(r["★ 原始行号范围"][0], r["★ 原始行号范围"][1] + 1):
                _cov.add(i)
        _cov_l_total += len(_cov)
        _cov_b_total += sum(1 for i, ln in enumerate(L, 1)
                            if i in _cov and _BCP.search(ln))
    print(f"    {proto:8s}: 块 {len(_rs):4d}｜行覆盖 {_cov_l_total}/{_tot_l} = "
          f"{_cov_l_total/max(1,_tot_l)*100:.2f}%｜规范义务行 {_cov_b_total}/{_tot_b} = "
          f"{_cov_b_total/max(1,_tot_b)*100:.2f}%")
save_jsonl(OUTROOT / "p09_block_scores.jsonl", index)
print(f"\n  ⇒ {OUTROOT/'p09_block_scores.jsonl'}")
