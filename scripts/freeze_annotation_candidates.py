# -*- coding: utf-8 -*-
"""scripts/freeze_annotation_candidates.py —— 冻结 B 阶段人工标注集的**候选句**。

为什么需要它
------------
B 阶段要回答的问题只有一个：**「规则条目级」的表达层升级（C0 自由文本 → E1 两层模型）
到底带来了多少知识质量收益**。这个问题的答案依赖一份**独立的人工标注集**（评审 M6/R12：
评测集本身不可靠 ⇒ 结论不可信）。而标注集的**第一性输入**是候选句 —— 候选句没冻结，
标注就没有稳定坐标；标注完再换候选句，κ 与 F1 全部作废。

本脚本负责候选句的**冻结**（不是标注）：
  ① 从 ``core/fused/rfc_extractor.py::extract_constraint_candidates`` 取候选
     （B-3 成果：三协议共 430 条，span 覆盖 100%，TOC 污染 0）；
  ② 按 §4.6「每协议 40 条、共 120 条」做**分层抽样**，保证四类主体
     （method / field / status / message_type）都被覆盖；
  ③ 再把 120 条切成 **训练集 100 + holdout 20**（holdout 按协议分层）。

设计约束（与本仓既有风格一致）
------------------------------
· **确定性**：抽样**不使用任何随机数发生器**，而是「稳定哈希置换 + 等距取点」——
  同一份 kb/ 输入 ⇒ 同一份输出，跨 Python 版本、跨机器、跨运行完全一致。
  （刻意不用 ``random.Random(seed).sample()``：其实现细节随 CPython 版本漂移，
  「固定种子」只在同一解释器版本下可复现，不足以当实验基线。）
· **防信息泄漏**：分层用的主体分类只依据 **RFC 章节结构**
  （``fused_hub/targets/<p>/rfc_config.json`` 的章节号前缀 + 章节标题），
  **绝不读 ``profile.json`` 的 ``allowed_methods``**。理由见
  ``docs/rfc_source_bcd_roadmap.md`` §4.6 第 4 条：RTSP 的 ``allowed_methods``
  只有 8 个而实抽 11 个，差集 ``ANNOUNCE``/``RECORD``/``REDIRECT`` 是**真实 RTSP 方法** ——
  若拿它当「方法全集」参照，标注者会把真实方法误判为「不存在的方法」。
· **只写 derived/exp_semantic/**：不碰 kb/、fused_hub/、derived/per_source/。

产物
----
    derived/exp_semantic/candidates_frozen.jsonl   # 120 条全集（C0/E1/E2 共用同一批候选）
    derived/exp_semantic/candidates_train.jsonl     # 100 条训练集（模式表迭代只看这个）
    derived/exp_semantic/candidates_holdout.jsonl   # 20 条 holdout（单独落盘，最终评测用一次）

★ ``candidates_frozen.jsonl`` 是**全集**，C0/E1/E2 三组必须喂**同一批候选句**
  （roadmap §4.2 关键设计：否则差异可能来自候选集不同而非表达层不同）。
  但「模式表迭代不得看标注集」⇒ **迭代期只喂 ``candidates_train.jsonl``**，
  ``candidates_holdout.jsonl`` 一旦分离即单独落盘、只在最终评测用一次。

用法
----
    python scripts/freeze_annotation_candidates.py --out derived/exp_semantic/candidates_frozen.jsonl
    python scripts/freeze_annotation_candidates.py --out /tmp/cand2.jsonl   # 复现性自检

退出码
------
    ``0`` —— 成功；``2`` —— 用法/环境错误（kb spec 缺失等）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fused.rfc_extractor import extract_constraint_candidates  # noqa: E402

#: 参与实验的三个协议（roadmap §4.3 的三协议事实库）。
PROTOCOLS: tuple[str, ...] = ("rtsp", "sip", "smtp")

#: 四类主体（roadmap §4.6 第 1 条）。顺序固定 ⇒ 抽样结果确定。
SUBJECT_TYPES: tuple[str, ...] = ("method", "field", "status", "message_type")

#: 每协议抽多少条（roadmap §4.6 第 1 条：每协议 40 条，三协议共 120 条）。
PER_PROTOCOL = 40

#: holdout 总条数（roadmap §4.6 第 5 条：另留 20 条只在最终评测用一次）。
HOLDOUT_TOTAL = 20

#: holdout 按协议的分层配额（20 / 3 ⇒ 7/7/6，按协议名序确定性分配）。
HOLDOUT_PER_PROTOCOL: dict[str, int] = {"rtsp": 7, "sip": 7, "smtp": 6}

#: 稳定哈希盐。改它 ⇒ 抽样结果变；**不要**在已冻结后改。
DEFAULT_SALT = "protorag-b-annotation-freeze-v1"

#: 候选记录里原样保留的字段（+ 本脚本补的分类/切分字段）。
_FIELDS = ("text", "source", "protocol", "span_start", "span_end",
           "section_path", "section_no", "spec_version")


# ---------------------------------------------------------------------------
# 主体分类（分层依据）
# ---------------------------------------------------------------------------
def _leaf_title(cand: dict) -> str:
    """取章节树的叶子标题（最后一层），无路径时返回空串。"""
    path = cand.get("section_path") or []
    return str(path[-1]) if path else ""


def _under_section(section_no: str, prefixes: Any) -> bool:
    """section_no 是否落在 prefixes 里任一章节号前缀之下（含前缀本身）。"""
    for p in prefixes or ():
        if section_no == p or section_no.startswith(str(p) + "."):
            return True
    return False


def classify_subject(cand: dict, cfg: dict) -> str:
    """把候选句归到四类主体之一。

    ★ 判定依据**只有章节结构**（rfc_config 的章节号前缀 + 章节标题措辞），
      **不含任何「方法/字段名清单」** ⇒ 不会把 ``allowed_methods`` 的偏差
      带进标注集（roadmap §4.6 第 4 条的防泄漏要求）。

    优先级（顺序有意义，先到先得）：
      1. status  —— 落在状态码章节，或标题含 status/response code 措辞
      2. method  —— 落在方法章节，或标题是方法名/「X Command」/「Method Definitions」
      3. field   —— 落在字段章节，或标题含 header/field/option tag 措辞，
                    或标题是单个「头字段名式」词（如 ``Call-ID``、``Via``）
      4. message_type —— 兜底（消息级/语法级/描述性条款）
    """
    section_no = str(cand.get("section_no") or "")
    leaf = _leaf_title(cand)
    leaf_lower = leaf.lower()
    leaf_stripped = leaf.strip()

    # 1) status
    if _under_section(section_no, cfg.get("status_sections")):
        return "status"
    if ("status code" in leaf_lower or "status codes" in leaf_lower
            or "status line" in leaf_lower or "status-line" in leaf_lower
            or "response code" in leaf_lower or "reason phrase" in leaf_lower):
        return "status"

    # 2) method
    if _under_section(section_no, cfg.get("method_sections")):
        return "method"
    if leaf_stripped.isupper() and len(leaf_stripped) >= 3 and " " not in leaf_stripped:
        return "method"          # DESCRIBE / ANNOUNCE / SETUP / PLAY
    if ("method definition" in leaf_lower or leaf_lower.startswith("requests")
            or leaf_lower.endswith(" command") or leaf_lower.endswith(" method")):
        return "method"

    # 3) field
    if _under_section(section_no, cfg.get("field_sections")):
        return "field"
    if ("header" in leaf_lower or "field" in leaf_lower
            or "option tag" in leaf_lower or "parameter" in leaf_lower):
        return "field"
    if _looks_like_field_name(leaf_stripped):
        return "field"

    # 4) 兜底
    return "message_type"


#: 单个「头字段名式」词判定：``Call-ID`` / ``Max-Forwards`` / ``Via`` / ``Contact`` …
#: —— 含连字符，或首字母大写的驼峰/连字符短词（排除纯普通英文单词）。
_FIELD_NAME_STOPWORDS = frozenset({
    "Introduction", "Terminology", "Scope", "Overview", "Definitions",
    "References", "Acknowledgments", "Examples", "Background", "Body",
    "Lines", "Host", "Security", "Notes", "Structure", "Overview",
})


def _looks_like_field_name(leaf: str) -> bool:
    """章节标题是否是单个「字段名」而非普通词组。

    判据：不含空格；含连字符或下划线（``Call-ID``/``Max-Forwards``），
    或首字母大写且不是普通英文停用词（``Via``/``Contact``/``CSeq``）。
    """
    if not leaf or " " in leaf:
        return False
    if leaf in _FIELD_NAME_STOPWORDS:
        return False
    if "-" in leaf or "_" in leaf:
        return True
    return leaf[0].isupper() and leaf.lower() not in _FIELD_NAME_STOPWORDS


# ---------------------------------------------------------------------------
# 确定性抽样
# ---------------------------------------------------------------------------
def _stable_key(salt: str, protocol: str, cand: dict) -> str:
    """稳定哈希置换键：与 Python 版本、运行顺序、字典序都无关。"""
    raw = "|".join([
        salt, protocol, str(cand.get("source") or ""),
        str(cand.get("span_start")), str(cand.get("text") or ""),
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _even_spread(n: int, k: int, offset: float = 0.0) -> list[int]:
    """从 ``range(n)`` 里等距取 ``k`` 个下标（确定性、无随机）。

    ``offset=0.0`` 取端点均匀分布；``offset=0.5`` 取中点分布（用于 holdout，
    与训练集的取点模式错开）。
    """
    if k <= 0 or n <= 0:
        return []
    if k >= n:
        return list(range(n))
    return [min(n - 1, int((i + offset) * n / k)) for i in range(k)]


def _allocate(total: int, sizes: dict[str, int], min_one: bool) -> dict[str, int]:
    """把 ``total`` 个名额分给各层：先保底（可选），再按层大小**最大余数法**分配。

    ``min_one=True`` 时每个非空层至少拿 1 个（保证四类主体都进样本）；
    余数相同时按 ``SUBJECT_TYPES`` 的固定次序决胜 ⇒ 完全确定。
    """
    alloc = {k: 0 for k in sizes}
    active = [k for k in SUBJECT_TYPES if sizes.get(k, 0) > 0]
    if not active or total <= 0:
        return alloc

    if min_one and total >= len(active):
        for k in active:
            alloc[k] = 1
        left = total - len(active)
    else:
        left = total

    pool = {k: sizes[k] - alloc[k] for k in active}
    denom = sum(pool.values())
    if denom <= 0 or left <= 0:
        return alloc

    exact = {k: left * pool[k] / denom for k in active}
    base = {k: int(exact[k]) for k in active}
    for k in active:
        alloc[k] += base[k]
    rest = left - sum(base.values())
    order = sorted(active, key=lambda k: (-(exact[k] - base[k]),
                                           SUBJECT_TYPES.index(k)))
    for i in range(rest):
        k = order[i % len(order)]
        if alloc[k] < sizes[k]:
            alloc[k] += 1
    return alloc


def _pick(pool: list[dict], k: int, offset: float = 0.0) -> list[dict]:
    """从已按稳定哈希置换过的 ``pool`` 里等距取 ``k`` 条。"""
    if k <= 0:
        return []
    idx = _even_spread(len(pool), k, offset)
    return [pool[i] for i in idx]


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _load_rfc_cfg(protocol: str) -> dict:
    """读 ``fused_hub/targets/<p>/rfc_config.json``（章节结构，不含方法名清单）。"""
    path = REPO_ROOT / "fused_hub" / "targets" / protocol / "rfc_config.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_id(protocol: str, cand: dict) -> str:
    """内容寻址的稳定候选 id（同一候选永远同一个 id）。"""
    raw = "|".join([protocol, str(cand.get("source") or ""),
                    str(cand.get("span_start")), str(cand.get("text") or "")])
    return f"{protocol}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


# ★ 复用泄漏检查闸的判据（`annotate_candidates` 不引用本模块 ⇒ 无循环依赖）。
#   两处必须**同口径**，否则「剔除逻辑」与「泄漏闸」会各判各的。
#
# ⚠ 导入必须兼容两种调用形态：
#   ① 直接跑脚本：``python scripts/freeze_annotation_candidates.py`` ⇒ ``scripts/`` 在 sys.path 上
#   ② 作为包模块被测试导入：``from scripts.freeze_annotation_candidates import ...``
#      ⇒ 此时 ``scripts/`` **不在** sys.path 上，只写 `from annotate_candidates import ...`
#      会抛 ModuleNotFoundError，直接把整个测试模块变成 collection error。
try:  # pragma: no cover - 取决于调用形态
    from annotate_candidates import (  # noqa: E402
        _longest_common_substring as _lcs,
        _normalize_ws as _normalize_ws,
    )
except ImportError:  # pragma: no cover - 包导入形态
    from scripts.annotate_candidates import (  # noqa: E402
        _longest_common_substring as _lcs,
        _normalize_ws as _normalize_ws,
    )

#: L2 近似泄漏的阈值（与 `annotate_candidates.check_guide_leaks` 默认值一致）。
LEAK_MIN_COVERAGE = 0.5
LEAK_MIN_LENGTH = 45


def freeze(protocols: tuple[str, ...], per_protocol: int,
           holdout_per_protocol: dict[str, int],
           salt: str,
           guide_path: Optional[Path] = None) -> list[dict]:
    """执行抽样，返回 120 条（顺序确定：协议序 → 主体序 → 稳定哈希序）。

    ★ **排除「指南已逐字用过」的候选**（`guide_path` 给出时生效）：
      标注指南为了说明判定标准，会举真实句子作例子。若某条**候选**恰好与
      指南里的例句逐字相同，该条的答案就**暴露在指南里** ⇒ 它作为评测项
      已失去意义（roadmap §4.6 第 4 条的同类风险）。
      ⇒ 这类候选直接从候选池剔除，**而不是**放宽泄漏判据（放宽会掩盖真泄漏）。
      ⇒ 剔除后仍按原配额抽样，规模不变（120 条）。
    """
    guide_text = ""
    if guide_path is not None and guide_path.exists():
        guide_text = guide_path.read_text(encoding="utf-8")

    guide_norm = _normalize_ws(guide_text)

    def _leaked(text: str) -> bool:
        """该候选文本是否已在指南里泄漏（**逐字 L1 或近似 L2**）。

        ★ 与 `annotate_candidates.check_guide_leaks` **同判据**（复用其
          `_normalize_ws` 与 `_longest_common_substring`，阈值同值）⇒
          「剔除逻辑」与「泄漏闸」不会各判各的。
        - L1 逐字：归一化后整句出现在指南里
        - L2 近似：最长公共子串覆盖率 ≥ 0.5 且候选长度 ≥ 45
        （L2 加长度下限的原因：短候选天然与指南共享词汇，如状态码表行）
        """
        if not guide_norm or not text:
            return False
        norm = _normalize_ws(text)
        if norm in guide_norm:
            return True
        if len(norm) < LEAK_MIN_LENGTH:
            return False
        return _lcs(norm, guide_norm) / len(norm) >= LEAK_MIN_COVERAGE

    frozen: list[dict] = []
    for protocol in protocols:
        cfg = _load_rfc_cfg(protocol)
        raw = extract_constraint_candidates(protocol)
        buckets: dict[str, list[dict]] = {k: [] for k in SUBJECT_TYPES}
        for cand in raw:
            if _leaked(str(cand.get("text") or "")):
                continue          # 指南已暴露 ⇒ 剔除
            buckets[classify_subject(cand, cfg)].append(cand)

        sizes = {k: len(v) for k, v in buckets.items()}
        quota = _allocate(per_protocol, sizes, min_one=True)

        picked: list[dict] = []
        for st in SUBJECT_TYPES:
            pool = sorted(buckets[st],
                          key=lambda c: _stable_key(salt, protocol, c))
            picked.extend(_pick(pool, quota[st]))

        # 该协议内的 holdout：按主体层分层，再在层内取中点分布（与训练集错开）
        hq = _allocate(holdout_per_protocol.get(protocol, 0), quota, min_one=False)
        holdout_ids: set[str] = set()
        for st in SUBJECT_TYPES:
            layer = [c for c in picked if classify_subject(c, cfg) == st]
            for c in _pick(layer, hq[st], offset=0.5):
                holdout_ids.add(_candidate_id(protocol, c))

        for cand in sorted(picked,
                           key=lambda c: (SUBJECT_TYPES.index(classify_subject(c, cfg)),
                                          _stable_key(salt, protocol, c))):
            rec = {k: cand.get(k) for k in _FIELDS}
            rec["candidate_id"] = _candidate_id(protocol, cand)
            rec["subject_type"] = classify_subject(cand, cfg)
            rec["split"] = "holdout" if rec["candidate_id"] in holdout_ids else "train"
            frozen.append(rec)
    return frozen


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _summarize(rows: list[dict]) -> dict:
    return {
        "total": len(rows),
        "by_protocol": dict(sorted(Counter(r["protocol"] for r in rows).items())),
        "by_subject": dict(sorted(Counter(r["subject_type"] for r in rows).items())),
        "by_split": dict(sorted(Counter(r["split"] for r in rows).items())),
        "with_span": sum(1 for r in rows if r.get("span_start") is not None),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="冻结 B 阶段人工标注候选句（确定性分层抽样）")
    ap.add_argument("--out", required=True,
                    help="冻结全集输出路径（.jsonl）")
    ap.add_argument("--train-out", default=None,
                    help="训练集输出路径（默认与 --out 同目录的 candidates_train.jsonl）")
    ap.add_argument("--holdout-out", default=None,
                    help="holdout 输出路径（默认与 --out 同目录的 candidates_holdout.jsonl）")
    ap.add_argument("--protocols", default=",".join(PROTOCOLS),
                    help="参与协议，逗号分隔（默认 rtsp,sip,smtp）")
    ap.add_argument("--per-protocol", type=int, default=PER_PROTOCOL,
                    help=f"每协议条数（默认 {PER_PROTOCOL}）")
    ap.add_argument("--holdout-total", type=int, default=HOLDOUT_TOTAL,
                    help=f"holdout 总条数（默认 {HOLDOUT_TOTAL}）")
    ap.add_argument("--guide", default=str(REPO_ROOT / "docs" / "annotation_guide.md"),
                    help="标注指南路径；用于剔除『指南已逐字用过』的候选（默认启用）")
    ap.add_argument("--salt", default=DEFAULT_SALT,
                    help=f"稳定哈希盐（默认 {DEFAULT_SALT}）")
    ap.add_argument("--quiet", action="store_true", help="只写文件，不打印摘要")
    args = ap.parse_args(argv)

    protocols = tuple(p.strip() for p in args.protocols.split(",") if p.strip())
    if not protocols:
        print("[ERR] --protocols 为空", file=sys.stderr)
        return 2

    per_protocol = args.per_protocol
    total = per_protocol * len(protocols)
    holdout_total = min(args.holdout_total, total)

    # holdout 按协议分层：先按协议条数比例分，最大余数法 + 协议序决胜。
    base = {p: holdout_total * per_protocol // total for p in protocols}
    rest = holdout_total - sum(base.values())
    order = sorted(protocols, key=lambda p: (-(holdout_total * per_protocol % total), p))
    for i in range(rest):
        p = order[i % len(order)]
        base[p] += 1
    holdout_per_protocol = {p: base[p] for p in protocols}

    guide = Path(args.guide) if args.guide else None
    rows = freeze(protocols, per_protocol, holdout_per_protocol, args.salt,
                 guide_path=guide)

    out = Path(args.out)
    train_out = Path(args.train_out) if args.train_out else out.parent / "candidates_train.jsonl"
    holdout_out = (Path(args.holdout_out) if args.holdout_out
                   else out.parent / "candidates_holdout.jsonl")

    _write_jsonl(out, rows)
    _write_jsonl(train_out, [r for r in rows if r["split"] == "train"])
    _write_jsonl(holdout_out, [r for r in rows if r["split"] == "holdout"])

    if not args.quiet:
        summary = _summarize(rows)
        print(f"[OK] 冻结候选 {summary['total']} 条 → {out}")
        print(f"     按协议: {summary['by_protocol']}")
        print(f"     按主体: {summary['by_subject']}")
        print(f"     按切分: {summary['by_split']}")
        print(f"     带 span: {summary['with_span']}/{summary['total']}")
        print(f"     训练集 → {train_out}    holdout → {holdout_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
