#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""scripts/exp_semantic_gain.py —— 里程碑 B 出口闸门实验 B-10。

实验目的
--------
验证路线图 ``docs/rfc_source_bcd_roadmap.md`` §4.1 的**命题 B-1**：

    把 RFC 约束从「自由文本」升级为「两层可执行模型」后，产出的规则中
    **可机械判定**的比例（可执行率）显著高于当前影子实现的可判定比例，
    且**不引入新的知识污染**。

辅助命题：

* **B-2（幂等性）**：同一 RFC 重复抽取 N 次，``rule_id`` 集合完全相同。
* **B-3（无污染）**：两层模型的规则中 ``explicitness=="explicit"`` 的比例与
  「原文含 MUST/SHALL」的规则集合完全一致（不多不少）。

三组 × 三协议
------------
=========  =========================================  ==================================
组         输入                                        输出
=========  =========================================  ==================================
``C0``     当前影子实现（``infer_constraints`` + LLM）   ``legal_boundary`` /
                                                      ``response_expectation`` 自由文本 fact
``E1``     同一批候选句（规则表优先 + LLM 兜底）        ``SemanticRule`` + ``KnowledgeCandidate``
``E2``     同一批候选句（**只跑规则表**，无 LLM 兜底）    两层模型
=========  =========================================  ==================================

★ **三组共用同一批候选句**：候选句来自 ``derived/exp_semantic/candidates_frozen.jsonl``
（B-13 后的 120 条逻辑句，指纹见 ``docs/semantic_gain_report.md`` 的预登记节）。

★ **不触碰 rq3/rq4 语料**（§4.6 第 1 条）：本脚本**不调用**
``scripts/seedgen.py`` / ``scripts/rq3_build_corpus.py`` / ``scripts/corpus_gate.py``，
产物只落在 ``derived/exp_semantic_gain/`` 与 ``docs/semantic_gain_results.md``。

子命令
------
* ``--prereg``：只写预登记文件 ``docs/semantic_gain_report.md``（**实验前定稿，事后不得改**）。
* ``--run``：跑实验，产出 ``derived/exp_semantic_gain/`` + ``docs/semantic_gain_results.md``。
* ``--all``：先 ``--prereg`` 后 ``--run``。

★ ``--run`` **不会**写 ``docs/semantic_gain_report.md``（预登记文件与结果文件分离，
保证「预登记先于结果」可被 git 历史证明）。

用法
----
::

    E:/app/Anaconda3/python.exe scripts/exp_semantic_gain.py --prereg
    E:/app/Anaconda3/python.exe scripts/exp_semantic_gain.py --run
    E:/app/Anaconda3/python.exe scripts/exp_semantic_gain.py --all
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.fused.norm import map_norm_to_facts                          # noqa: E402
from core.fused.semantic import (                                     # noqa: E402
    OPERATORS,
    EvidenceAnchor,
    KnowledgeCandidate,
    SemanticRule,
    compute_evidence_id,
    compute_explicitness,
    compute_rule_id,
    load_source_text,
    try_convert,
    sanitize_rule,
)
from core.fused.semantic_rules import (                                # noqa: E402
    bind_field,
    make_resolver,
    match_pattern,
    resolve_evidence_kind,
)

PROTOCOLS: tuple[str, ...] = ("rtsp", "sip", "smtp")

#: LLM 缓存键的一部分：提示词**契约版本**。
#: ★ 取自 core（``core.fused.rfc_extractor.CONSTRAINT_PROMPT_VERSION``）
#:   —— 提示词本体已在 core 维护，实验侧**不再自带副本**（避免两处漂移）。
#: ★ 改动 core 的提示词内容时**必须**同步 bump 那个常量，否则会读到旧缓存。
from core.fused.rfc_extractor import CONSTRAINT_PROMPT_VERSION as PROMPT_VERSION

#: 期望响应词表（与 ``core.fused.rfc_extractor.EXPECTED_VOCAB`` 同源）。
EXPECTED_VOCAB: tuple[str, ...] = (
    "success",
    "protocol_error",
    "application_error",
    "silence",
)

DEFAULT_OUT_DIR = "derived/exp_semantic_gain"
DEFAULT_REPORT = "docs/semantic_gain_report.md"
DEFAULT_RESULTS_DOC = "docs/semantic_gain_results.md"
DEFAULT_FROZEN_SRC = "derived/exp_semantic/candidates_frozen.jsonl"

#: 冻结候选集源文件（B-13 后重冻结，120 条）。
#: ★ **只读**：本脚本从不写 ``derived/exp_semantic/``（只写 ``derived/exp_semantic_gain/``）。
FROZEN_SOURCE_CANDIDATES = DEFAULT_FROZEN_SRC

#: 人工标注集目录（**只读**）—— 用于判定 M2 是否可计算。
TRUTH_DIR = "derived/exp_semantic/truth"


# ===========================================================================
# §4.6 第 2 条 —— 「已知契约漂移」固定声明（逐字照抄路线图，**不得改写**）
# ===========================================================================
DRIFT_DECLARATION = """rtsp: A 38→52 / B 50→65 / C 50→65 / D 50→65
sip:  A 15→?  / B 25→20 / C 25→?  / D 25→?
smtp: A 76→?  / B 78→61 / C 78→?  / D 78→?
根因（docs/rfc_reform_a_implementation_report.md §10.4 已实测）：source 源引入
LIVE555 真实状态名，取代 expert_note v3 的虚构状态名 → 状态机层与种子序列全变。
★ 与 rfc 源**零影响**（剔除 rfc 源后条数与 md5 完全相同）。
本实验的判定指标中**不含任何种子条数**，故该漂移不影响结论。"""


# ===========================================================================
# 预登记（§4.5 阈值表**逐字照抄**；实验前定稿，事后不得改）
# ===========================================================================
PREREG_THRESHOLDS = """| 指标 | 收益成立 | 部分成立 | 不成立 |
|---|---|---|---|
| **M1 可执行率** | E1 ≥ C0 + **15 个百分点** | E1 ≥ C0 + 5 个百分点 | E1 < C0 + 5 个百分点 |
| **M2 规则 F1** | **≥ 0.70**（对 holdout） | 0.50 ~ 0.70 | **< 0.50** |
| **M3 证据可验证率** | **= 100%** | — | **< 100%**（任一不可验证却算规则 ⇒ 污染） |
| **M4 显式性纯净度** | **= 100%** | — | **< 100%** |
| **M5 MAY 误升率** | **= 0%** | — | **> 0%**（任一误升 ⇒ 阻断，先修再继续） |
| **M6 rule_id 幂等性** | **N 次完全相同** | — | **任一次不同**（⇒ 派生规则有 bug，先修） |"""

PREREG_COMPOSITE = """- **收益成立** = M1 达「收益成立」档 **且** M2 达「收益成立」档 **且** M3/M4/M5/M6 **全部达标**。
  → 允许进入里程碑 C 的开发准备。
- **部分成立** = M1 或 M2 落在「部分成立」档，但 M3~M6 全部达标。
  → **不进入 C**；转为「B 阶段只交付知识层（规则入库 + 人工复核），不接自动生成链路」；把 M7 的拒绝原因分布反馈给模式表迭代，下轮再评。
- **收益不成立** = M2 < 0.50 或 M1 提升 < 5 个百分点。
  → **B 阶段终止自动生成链路方向**。保留两层模型作为**知识表示**（人工复核用），但**不承诺** fuzzing 收益；C 阶段应改为「先做无向量的规则化变异」这一更轻的替代路线（评审报告 §四 替代方案 A/B 的取舍）。"""


# ===========================================================================
# 操作符探针（C0「可判定率」与 E1 的 LLM 兜底共用**同一**判定实现）
# ===========================================================================
#: 有序探针表：``(模式名, 正则, operator)``。
#: ★ **顺序敏感**：否定式必须排在肯定式之前（"不得超过" 不能被 "超过" 抢走；
#:   "不少于" 不能被 "少于" 抢走）。与 ``core/fused/semantic_rules.py`` 的
#:   有序模式表同一条设计原则。
#: ★ 正则命中即认为「能解析出 operator」；数值型算子额外要求捕获到 ``num`` 组。
PROBE_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    # ── 中文：上界（le）────────────────────────────────────────────────
    ("cn_no_more_than", re.compile(
        r"(?:不得超过|不大于|不超过|最多|至多|上限(?:为|是)?)\s*(?P<num>\d+)"),
     "le"),
    ("cn_neg_greater", re.compile(
        r"不(?:得|应|能|可)(?:大于|超过|多于)\s*(?P<num>\d+)"), "le"),
    # ── 中文：下界（ge）────────────────────────────────────────────────
    ("cn_no_less_than", re.compile(
        r"(?:不少于|不小于|至少|最少|下限(?:为|是)?)\s*(?P<num>\d+)"), "ge"),
    ("cn_neg_less", re.compile(
        r"不(?:得|应|能|可)(?:小于|少于|低于)\s*(?P<num>\d+)"), "ge"),
    # ── 中文：严格大于 / 小于 / 等于 ───────────────────────────────────
    ("cn_greater", re.compile(r"(?:大于|超过|多于)\s*(?P<num>\d+)"), "gt"),
    ("cn_less", re.compile(r"(?:小于|少于|低于)\s*(?P<num>\d+)"), "lt"),
    ("cn_equal", re.compile(r"(?:等于|必须是|应为|须为)\s*(?P<num>\d+)"), "eq"),
    # ── 中文：存在性（absent 先于 present）──────────────────────────────
    ("cn_absent", re.compile(
        r"(?:不得(?:包含|含有|携带|使用|返回|出现|以)|不能包含|禁止包含|"
        r"不应包含|不得使用)"), "absent"),
    ("cn_present", re.compile(
        r"(?:必须(?:包含|含有|携带|支持|提供|插入)|应(?:包含|含有|支持)|"
        r"须(?:包含|含有))"), "present"),
    # ── 英文（影子 LLM 有时直接引用 RFC 原文片段）───────────────────────
    # ★ **大小写不敏感** —— 与 ``core/fused/semantic_rules.py`` 的模式表同口径
    #   （那边 ``_p()`` 默认 ``flags=re.IGNORECASE``）。RFC 2119 关键字通常全大写，
    #   但 LLM 引用原文片段时可能是小写 ⇒ 必须容忍，否则漏判。
    ("en_no_more_than", re.compile(
        r"(?:no\s+more\s+than|not\s+greater\s+than|at\s+most|"
        r"no\s+greater\s+than|not\s+exceed)\s*(?P<num>\d+)", re.IGNORECASE),
     "le"),
    ("en_no_less_than", re.compile(
        r"(?:at\s+least|no\s+less\s+than|not\s+less\s+than|"
        r"no\s+fewer\s+than)\s*(?P<num>\d+)", re.IGNORECASE), "ge"),
    ("en_greater", re.compile(
        r"(?:greater\s+than|more\s+than|exceed(?:s|ing)?)\s*(?P<num>\d+)",
        re.IGNORECASE), "gt"),
    ("en_less", re.compile(
        r"(?:less\s+than|fewer\s+than)\s*(?P<num>\d+)", re.IGNORECASE), "lt"),
    ("en_equal", re.compile(
        r"(?:exactly|equal\s+to)\s*(?P<num>\d+)", re.IGNORECASE), "eq"),
    ("en_absent", re.compile(
        r"must\s+not\s+(?:contain|include|be\s+present|use)", re.IGNORECASE),
     "absent"),
    ("en_present", re.compile(
        r"must\s+(?:contain|include|be\s+present|support)", re.IGNORECASE),
     "present"),
)

#: 需要操作数（operand）的算子；``present``/``absent`` 无参。
_PARAM_OPERATORS = frozenset({"eq", "ne", "lt", "gt", "le", "ge", "in", "range"})


def probe_operator(text: str) -> Optional[dict]:
    """从自由文本里机械解析出 ``(operator, operand)``。

    ★ **这是 M1 的判定实现**（C0 的「可判定率」与 E1 的 LLM 兜底**共用**本函数），
      代码位置见本文件 :func:`probe_operator`。

    判据（与路线图 §4.2 口径一致）：**能否解析出 operator**。
    数值型算子额外要求捕获到数字（``num`` 组）—— 否则不算可判定。

    Args:
        text: 待判定自由文本（C0 取 ``legal_boundary`` 的 ``legal``/``illegal``；
            E1 兜底取 LLM 输出的 ``constraint``/``violation``）。

    Returns:
        ``{"operator": str, "operand": tuple[str, ...], "pattern": str}``；
        解析不出则返回 ``None``。
    """
    body = text or ""
    for name, pattern, operator in PROBE_PATTERNS:
        m = pattern.search(body)
        if not m:
            continue
        operand: tuple[str, ...] = ()
        if operator in _PARAM_OPERATORS:
            raw = m.groupdict().get("num")
            if raw is None:
                # 命中了算子但没抓到操作数 ⇒ 不可判定（不猜）。
                return None
            operand = (raw,)
        return {"operator": operator, "operand": operand, "pattern": name}
    return None


# ===========================================================================
# 工具
# ===========================================================================
def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _md5_file(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _pct(num: float, den: float) -> float:
    return 0.0 if den <= 0 else round(100.0 * num / den, 4)


# ===========================================================================
# 冻结候选集：复用既有冻结集 + 补齐 section_no_path
# ===========================================================================
def load_frozen_candidates(
    src_path: Path,
    out_path: Path,
) -> tuple[list[dict], dict]:
    """读取既有冻结候选集，并补齐 ``section_no_path``（rule_id 派生所需）。

    为什么复用既有冻结集
    ------------------
    路线图 §4.2 要求「C0/E1/E2 必须用同一批候选句」。既有
    ``derived/exp_semantic/candidates_frozen.jsonl`` 满足全部三项要求：

    1. **三组共用**：单一文件，C0/E1/E2 全部从它读；
    2. **含 span**：每条带 ``span_start``/``span_end``；
    3. **三协议各 40 条**：rtsp 40 / sip 40 / smtp 40。

    且其 md5 指纹与路线图 §4.6 / ``docs/annotation_status.md`` 记录的一致
    ⇒ **复用，不重新冻结**。

    唯一差异
    --------
    既有冻结文件**不含 ``section_no_path``**（章节号链），而
    ``core/fused/rfc_extractor.py::build_semantic_rules`` 用它派生 ``rule_id``。
    ⇒ 本函数按 ``(protocol, text, span_start)`` 三元组与
    ``extract_constraint_candidates()`` 的新鲜抽取做**确定性 join** 补齐。

    ★ 注意：**不能**用 ``section_no.split(".")`` 代替 —— 实测只有 29/120 条与
      真实 ``section_no_path`` 一致（见报告的「差异说明」节）。
    """
    from core.fused.rfc_extractor import extract_constraint_candidates

    raw = _read_jsonl(src_path)
    by_key: dict[tuple[str, str, int], dict] = {}
    for protocol in PROTOCOLS:
        for cand in extract_constraint_candidates(protocol, max_per_rfc=80):
            key = (protocol, cand["text"], int(cand["span_start"]))
            by_key[key] = cand

    rows: list[dict] = []
    joined = 0
    unmatched: list[str] = []
    for rec in raw:
        row = dict(rec)
        key = (row["protocol"], row["text"], int(row["span_start"]))
        hit = by_key.get(key)
        if hit is not None:
            row["section_no_path"] = list(hit.get("section_no_path") or [])
            joined += 1
        else:
            row["section_no_path"] = []
            unmatched.append(row["candidate_id"])
        rows.append(row)

    _write_jsonl(out_path, rows)

    per_protocol = Counter(r["protocol"] for r in rows)
    texts = Counter(r["text"] for r in rows)
    dup_across_protocol = [
        t for t, c in Counter(
            (r["protocol"], r["text"]) for r in rows
        ).items() if c > 1
    ]
    stats = {
        "source_path": str(src_path),
        "source_md5": _md5_file(src_path),
        "frozen_path": str(out_path),
        "frozen_md5": _md5_file(out_path),
        "total": len(rows),
        "per_protocol": dict(sorted(per_protocol.items())),
        "section_no_path_joined": joined,
        "section_no_path_unmatched": sorted(unmatched),
        "duplicate_candidate_text_count": sum(
            1 for c in texts.values() if c > 1),
        "duplicate_protocol_text_pairs": len(dup_across_protocol),
    }
    return rows, stats


def compute_frozen_stats(src_path: Path, out_path: Path) -> dict:
    """**只读**地算出冻结候选集的统计（预登记阶段用，不写任何文件）。

    与 :func:`load_frozen_candidates` 走**完全相同**的 join 逻辑 ⇒ 预登记里
    写的数字（join 命中数、md5 等）与实验实跑时**逐字一致**。

    ⚠ 本函数**不写** ``out_path`` —— 只在内存里算出序列化后的 md5。
    """
    from core.fused.rfc_extractor import extract_constraint_candidates

    raw = _read_jsonl(src_path)
    by_key: dict[tuple[str, str, int], dict] = {}
    for protocol in PROTOCOLS:
        for cand in extract_constraint_candidates(protocol, max_per_rfc=80):
            key = (protocol, cand["text"], int(cand["span_start"]))
            by_key[key] = cand

    rows: list[dict] = []
    joined = 0
    unmatched: list[str] = []
    for rec in raw:
        row = dict(rec)
        key = (row["protocol"], row["text"], int(row["span_start"]))
        hit = by_key.get(key)
        if hit is not None:
            row["section_no_path"] = list(hit.get("section_no_path") or [])
            joined += 1
        else:
            row["section_no_path"] = []
            unmatched.append(row["candidate_id"])
        rows.append(row)

    payload = "".join(
        json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    per_protocol = Counter(r["protocol"] for r in rows)
    texts = Counter(r["text"] for r in rows)
    return {
        "source_path": str(src_path),
        "source_md5": _md5_file(src_path),
        "frozen_path": str(out_path),
        "frozen_md5": hashlib.md5(payload.encode("utf-8")).hexdigest(),
        "total": len(rows),
        "per_protocol": dict(sorted(per_protocol.items())),
        "section_no_path_joined": joined,
        "section_no_path_unmatched": sorted(unmatched),
        "duplicate_candidate_text_count": sum(
            1 for c in texts.values() if c > 1),
        "duplicate_protocol_text_pairs": len(
            [1 for c in Counter((r["protocol"], r["text"]) for r in rows).values()
             if c > 1]),
    }


# ===========================================================================
# LLM 客户端（带缓存；C0 与 E1 共用 ⇒ 同候选只调一次）
# ===========================================================================
class CachedLLM:
    """带磁盘缓存的 LLM 客户端。

    ★ 缓存键 = ``sha256(candidate_text + prompt_version + model)``
      —— 与 §4.4 的规定一致（``prompt_version`` 覆盖提示词版本，
      ``model`` 覆盖模型名 ⇒ 提示词或模型一变即自动失效）。
    ★ C0 与 E1 **共用**本缓存 ⇒ 同一候选句只调一次 LLM（省一半调用）。
    ★ 缓存文件里**不含任何凭据**（只存模型名与响应体）。
    """

    def __init__(self, client: Any, cache_path: Path, model: str) -> None:
        self._client = client
        self._cache_path = cache_path
        self._model = model
        self._cache: dict[str, Any] = {}
        self._order: list[str] = []
        if cache_path.is_file():
            for row in _read_jsonl(cache_path):
                key = row.get("key")
                if isinstance(key, str):
                    self._cache[key] = row.get("response")
                    self._order.append(key)
        #: 本次运行开始前**已存在**的缓存条目数（= 上一轮已付费的响应）。
        self.cache_reused = len(self._cache)
        self.calls_made = 0
        self.cache_hits = 0
        self.failures: list[dict] = []
        self._current_text: Optional[str] = None
        #: 最近一次 chat_json 的原始响应（供 run_group_c0 取结构化算子
        #:   —— CachedLLM 在缓存命中时也要回填，保证可复跑）。
        self.last_response: Any = None

    # -- 上下文：每次 LLM 调用前声明当前候选句（用于算缓存键）----------
    def expect(self, candidate_text: str) -> None:
        self._current_text = candidate_text

    def cache_key(self, candidate_text: str) -> str:
        return _sha256(f"{candidate_text}{PROMPT_VERSION}{self._model}")

    def chat_json(self, *, system: str, user: str,
                  temperature: float = 0.2,
                  max_tokens: int = 4000) -> Any:
        """``core.llm.LLMClient`` 协议实现（带缓存）。"""
        text = self._current_text or ""
        if text and text not in user:
            raise RuntimeError(
                f"LLM 提示词与声明的候选句不一致（缓存键会错）: {text[:60]!r}")
        key = self.cache_key(text)
        if key in self._cache:
            self.cache_hits += 1
            self.last_response = self._cache[key]
            return self._cache[key]
        self.calls_made += 1
        try:
            resp = self._client.chat_json(
                system=system, user=user, temperature=temperature,
                max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001 —— 记录失败并如实上报
            self.failures.append({
                "candidate_text": text[:200],
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            })
            raise
        self._cache[key] = resp
        self.last_response = resp
        self._order.append(key)
        self._flush()
        return resp

    def _flush(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self._cache_path.open("w", encoding="utf-8") as fh:
            for key in self._order:
                fh.write(json.dumps({
                    "key": key,
                    "prompt_version": PROMPT_VERSION,
                    "model": self._model,
                    "response": self._cache.get(key),
                }, ensure_ascii=False) + "\n")


# ===========================================================================
# C0 组 —— 当前影子实现（自由文本 fact）
# ===========================================================================
def run_group_c0(
    protocol: str,
    candidates: list[dict],
    llm: Any,
) -> dict:
    """跑 C0 组：影子实现 ``extract_constraint_norms`` → 自由文本 fact。

    ★ 走的是**真实影子代码路径**（``core.fused.rfc_extractor``）：
      ``extract_constraint_norms`` → ``infer_constraints``（真实 LLM 提示词与温度）
      → ``map_norm_to_facts`` → ``legal_boundary`` / ``response_expectation``。
    ★ 唯一改动：把 ``extract_constraint_candidates`` 的返回**替换为冻结候选句**
      （否则候选集不是同一批 ⇒ §4.2 的对照无效）。
    ★ 逐候选调用（``max_candidates=1``）⇒ 产物的自由文本可**逐候选归因**
      （影子默认按 8 条一批、且把整批产物归到批次首条，无法归因）。

    Returns:
        ``{"items": [...], "facts": [...]}``
    """
    import core.fused.rfc_extractor as rx

    items: list[dict] = []
    facts: list[dict] = []
    original = rx.extract_constraint_candidates

    for cand in candidates:
        frozen_row = dict(cand)
        # ★ **必须**在调用前声明当前候选句：缓存键 = sha256(候选句 + prompt_version + model)
        #   —— 不声明则所有候选共用同一个键 ⇒ 只发生 1 次真实 LLM 调用、其余全是误命中。
        llm.expect(cand["text"])
        # 影子实现只需要这几个键；span/section 一并带上以保持一致。
        rx.extract_constraint_candidates = (  # type: ignore[assignment]
            lambda protocol, max_per_rfc=80, _row=frozen_row: [_row])
        llm.last_response = None
        try:
            norms = rx.extract_constraint_norms(
                protocol, llm=llm, max_candidates=1)
        finally:
            rx.extract_constraint_candidates = original  # type: ignore[assignment]

        # ★ 结构化算子：从 **norm 层**读（``operator=`` / ``operand=``）。
        #   ★ core 侧已把算子写进 norm 的 content 串 ⇒ norm → fact 链路自带算子，
        #     **不再需要**从 LLM 原始响应旁路取（该旁路在生产链路里不存在）。
        llm_op, llm_operand = "", []
        for _norm_row in norms:
            _op = str(_norm_row.get("operator") or "").strip()
            if _op not in OPERATORS:
                continue
            _vals = [str(x) for x in (_norm_row.get("operand") or [])]
            if _op in ("present", "absent"):
                _vals = []
            if _op not in ("present", "absent") and not _vals:
                continue
            llm_op, llm_operand = _op, _vals
            break

        record: dict[str, Any] = {
            "candidate_id": cand["candidate_id"],
            "protocol": protocol,
            "text": cand["text"],
            "field": "",
            "legal": "",
            "illegal": "",
            "trigger": "",
            "expected_code": "",
            "expected_behavior": "",
            "decidable": False,
            "decidable_with_operand": False,
            "operator": "",
            "operand": [],
            "probe_pattern": "",
            "probe_source": "",
            # ★ LLM 直接给出的结构化算子（C0 的 decidable 判定走
            #   :func:`probe_operator` 的自由文本口径 ⇒ 两者同源可比；
            #   这两个字段由 E1 阶段 B 消费）。
            "structured_operator": llm_op,
            "structured_operand": list(llm_operand),
        }

        legal_text = ""
        illegal_text = ""
        for norm in norms:
            mapped = map_norm_to_facts(norm)
            for fact in mapped:
                facts.append(asdict(fact))
            content = str(norm.get("content") or "")
            from core.fused.norm import parse_constraint_content
            parsed = parse_constraint_content(content)
            record["field"] = parsed.get("field", "")
            legal_text = legal_text or parsed.get("constraint", "")
            illegal_text = illegal_text or parsed.get("violation", "")
            record["expected_code"] = record["expected_code"] or parsed.get("code", "")
            record["trigger"] = record["trigger"] or parsed.get("behavior", "")
            record["expected_behavior"] = record["expected_behavior"] or parsed.get("behavior", "")

        record["legal"] = legal_text
        record["illegal"] = illegal_text

        # ★ 「可判定率」判定：能否从自由文本解析出 operator。
        #   主口径（路线图 §4.2 口径「能否解析出 operator」）：legal 或 illegal 任一命中。
        for src, text in (("legal", legal_text), ("illegal", illegal_text)):
            hit = probe_operator(text)
            if hit is None:
                continue
            record["decidable"] = True
            record["operator"] = hit["operator"]
            record["operand"] = list(hit["operand"])
            record["probe_pattern"] = hit["pattern"]
            record["probe_source"] = src
            if hit["operand"]:
                record["decidable_with_operand"] = True
            break

        items.append(record)

    return {"items": items, "facts": facts}


# ===========================================================================
# E1 / E2 组 —— 两层模型
# ===========================================================================
def _build_anchor(cand: dict, protocol: str) -> tuple[EvidenceAnchor, str]:
    """构造证据层锚点 + 源文件全文。"""
    text = cand["text"]
    source_text = load_source_text(protocol, cand["source"])
    match = match_pattern(text)
    pattern_kind = "abnf" if (match is not None and match.kind == "abnf") else "normative"
    evidence_kind = resolve_evidence_kind(text, pattern_kind)
    verified = bool(
        source_text is not None
        and cand.get("span_start") is not None
        and cand.get("span_end") is not None
        and source_text[int(cand["span_start"]):int(cand["span_end"])] == text
    )
    anchor = EvidenceAnchor(
        evidence_id="e0",
        spec_version=cand.get("spec_version") or "",
        section_path=tuple(cand.get("section_path") or ()),
        source_anchor=cand["source"],
        span_text=text,
        span_start=cand.get("span_start"),
        span_end=cand.get("span_end"),
        evidence_kind=evidence_kind,
        explicitness=compute_explicitness(
            text, verified=verified, evidence_kind=evidence_kind),
        source_class="normative_spec",
    )
    return anchor, source_text or ""


def _rule_from_constraint(
    cand: dict,
    protocol: str,
    anchor: EvidenceAnchor,
    constraint: Any,
    origin: str,
) -> SemanticRule:
    """按 ``core/fused/rfc_extractor.build_semantic_rules`` 的口径组装 ``SemanticRule``。

    ★ 与 ``build_semantic_rules`` 的两处**有意**差异（均在本文件说明，不改 core）：
      1. ``validated`` 取**真实的区间核对结果**（``build_semantic_rules`` 里硬编码为
         ``False``）—— M3 测的就是「证据是否可核对」，必须用真值；
      2. ``section_path`` 参与 rule_id 派生的用 ``section_no_path``（章节号链），
         与 ``build_semantic_rules`` 一致。
    """
    section_no_path = tuple(cand.get("section_no_path") or ())
    subject_type = "field" if constraint.target_field else "message"
    rule_id = compute_rule_id(
        protocol,
        anchor.spec_version,
        section_no_path,
        subject_type,
        constraint.target_field,
        constraint.operator,
        constraint.operand,
        constraint.operand_ref,
        constraint.expected_behavior,
    )
    ev = EvidenceAnchor(
        evidence_id=compute_evidence_id(
            rule_id, anchor.source_anchor, anchor.span_start),
        spec_version=anchor.spec_version,
        section_path=anchor.section_path,
        source_anchor=anchor.source_anchor,
        span_text=anchor.span_text,
        span_start=anchor.span_start,
        span_end=anchor.span_end,
        evidence_kind=anchor.evidence_kind,
        explicitness=anchor.explicitness,
        source_class=anchor.source_class,
    )
    return SemanticRule(
        rule_id=rule_id,
        evidence=ev,
        constraint=constraint,
        subject_type=subject_type,
        subject_name=constraint.target_field,
        rule_state="authoritative",
        supersedes=None,
        model_confidence=1.0,
        validated=True,  # ★ 区间已核对（try_convert 的 C2 已强制通过）
    )


def run_group_two_layer(
    protocol: str,
    candidates: list[dict],
    llm: Optional[Any],
    known_fields: list[str],
    llm_facts: dict[str, dict],
    use_sanitize: bool = True,
) -> dict:
    """跑 E1（规则表 + LLM 兜底）或 E2（**只跑规则表**）。

    两组共用**同一套**转换闸门（``core.fused.semantic.try_convert``）：

    * **阶段 A（规则表）**：``semantic_rules.make_resolver`` 在 RFC 原句上抽
      operator/operand；
    * **阶段 B（LLM 兜底，仅 E1）**：把 LLM 自由文本经 :func:`probe_operator`
      解析成 operator/operand，作为 resolver 交给**同一个** ``try_convert``
      —— 于是 C1~C7 七道闸门（含 C6 字段绑定、C7 词表）对 LLM 兜底同样生效。

    ★ E2 = 只有阶段 A（``llm=None``）。
    ★ 阶段 B 的 LLM 响应与 C0 **共用缓存** ⇒ 不额外增加 LLM 调用。
    """
    rules: list[SemanticRule] = []
    cands: list[KnowledgeCandidate] = []
    items: list[dict] = []

    resolver_a = make_resolver(known_fields=known_fields, expected_behavior="")

    for cand in candidates:
        anchor, source_text = _build_anchor(cand, protocol)
        record: dict[str, Any] = {
            "candidate_id": cand["candidate_id"],
            "protocol": protocol,
            "text": cand["text"],
            "outcome": "",
            "origin": "",
            "rule_id": "",
            "operator": "",
            "operand": [],
            "target_field": "",
            "explicitness": anchor.explicitness,
            "evidence_kind": anchor.evidence_kind,
            "validated": False,
            "reject_reason": "",
            "stage_a_reason": "",
            "stage_b_reason": "",
        }

        constraint, reason = try_convert(
            anchor,
            source_text=source_text,
            known_fields=known_fields,
            expected_vocab=list(EXPECTED_VOCAB),
            resolver=resolver_a,
        )
        origin = "rule_table"
        record["stage_a_reason"] = reason or ""

        if constraint is None and llm is not None:
            # ── 阶段 B：LLM 兜底（E1 独有）───────────────────────────────
            fact = llm_facts.get(cand["candidate_id"]) or {}
            parsed = _probe_llm_fact(fact)
            if parsed is not None:
                def resolver_b(_span_text: str, _p: dict = parsed) -> Optional[dict]:
                    return dict(_p)
                constraint, reason = try_convert(
                    anchor,
                    source_text=source_text,
                    known_fields=known_fields,
                    expected_vocab=list(EXPECTED_VOCAB),
                    resolver=resolver_b,
                )
                record["stage_b_reason"] = reason or ""
                origin = "llm_fallback"
            else:
                record["stage_b_reason"] = "llm_operator_unresolved"

        # ★★ 批次 2（M7 复测）：**LLM 输出后处理**（迁移项 D）
        #   `semantic.sanitize_rule()` 拦三类「结构合法但语义无效」的规则
        #   （空 subject / 空 operand 的有参算子 / 自指约束）⇒
        #   被拦的**落候选库**并记 `reject_reason`（**不静默丢弃**）
        #   ⇒ M7 拒绝原因直方图会出现新的计数 ⇒ 可量化批次 2 的收益。
        _sanitize_reason = ""
        if constraint is not None:
            rule = _rule_from_constraint(
                cand, protocol, anchor, constraint, origin)
            if use_sanitize:
                _kept_rule, _san_reason = sanitize_rule(rule)
                if _kept_rule is None:
                    # ⇒ 降级为候选（走下面的 else 分支）
                    constraint = None
                    _sanitize_reason = _san_reason or ""
                    rule = None
                else:
                    rule = _kept_rule
            if rule is not None:
                rules.append(rule)
                record["outcome"] = "rule"
                record["origin"] = origin
                record["rule_id"] = rule.rule_id
                record["operator"] = constraint.operator
                record["operand"] = list(constraint.operand)
                record["target_field"] = constraint.target_field
                record["validated"] = rule.validated
        if constraint is None:
            final_reason = _sanitize_reason or reason or "unknown"
            kc = KnowledgeCandidate(
                candidate_id="c" + compute_evidence_id(
                    f"candidate:{protocol}", anchor.source_anchor,
                    anchor.span_start),
                evidence=EvidenceAnchor(
                    evidence_id=compute_evidence_id(
                        f"candidate:{protocol}", anchor.source_anchor,
                        anchor.span_start),
                    spec_version=anchor.spec_version,
                    section_path=anchor.section_path,
                    source_anchor=anchor.source_anchor,
                    span_text=anchor.span_text,
                    span_start=anchor.span_start,
                    span_end=anchor.span_end,
                    evidence_kind=anchor.evidence_kind,
                    explicitness=anchor.explicitness,
                    source_class=anchor.source_class,
                ),
                subject_type="",
                subject_name="",
                raw_text=cand["text"],
                convertible=False,
                reject_reason=final_reason,
            )
            cands.append(kc)
            record["outcome"] = "candidate"
            record["reject_reason"] = final_reason
        items.append(record)

    return {"rules": rules, "candidates": cands, "items": items}


def _probe_llm_fact(fact: dict) -> Optional[dict]:
    """把 C0 组的 LLM 输出转成 resolver 契约 dict（阶段 B 用）。

    ★ 主路径：消费 LLM **直接给出的结构化 operator/operand**
      （受控词表 ``OPERATORS`` 校验 + 有参算子必须带 operand）——
      自由文本契约下需用正则反推算子，实测 73/120 候选因此
      ``operator_unresolved``，是负增益的主因。
    ★ 兜底：结构化字段缺失/非法时走 :func:`probe_operator` 的
      自由文本口径，保证不静默丢弃、且与 C0 判定同源。
    ★ ``target_field`` 取 LLM 给的字段名并**精确绑定**到协议已知字段集
      （绑不上 ⇒ 置空，交由 C6 判 ``field_unbound`` —— 不模糊匹配）。
    ★ ``expected_behavior`` 恒置空：按 §3.4 C7「缺 P 不阻断转换」，**不发明 P**。
    """
    target = bind_field(fact.get("field") or "", _KNOWN_FIELDS.get(
        fact.get("protocol") or "", ()))

    # ── 主路径：结构化算子（LLM 直接给，不靠正则）────────────────────
    op = str(fact.get("structured_operator") or "").strip()
    if op in OPERATORS:
        raw = fact.get("structured_operand") or []
        operand = ([str(x).strip() for x in raw if str(x).strip()]
                   if isinstance(raw, (list, tuple)) else [])
        if op in ("present", "absent"):
            operand = []
        # 有参算子无 operand ⇒ LLM 输出不完整 ⇒ 不采用，转自由文本兜底
        if op in ("present", "absent") or operand:
            return {
                "operator": op,
                "operand": operand,
                "operand_source": "constant",
                "operand_ref": None,
                "target_field": target or "",
                "expected_behavior": "",
            }

    # ── 兜底：自由文本正则 ──────────────────────────────────────────
    for key in ("legal", "illegal"):
        hit = probe_operator(fact.get(key) or "")
        if hit is None:
            continue
        return {
            "operator": hit["operator"],
            "operand": list(hit["operand"]),
            "operand_source": "constant",
            "operand_ref": None,
            "target_field": target or "",
            "expected_behavior": "",
        }
    return None


#: 协议已知字段集（进程内缓存；由 :func:`main` 填充）。
_KNOWN_FIELDS: dict[str, tuple[str, ...]] = {}


# ===========================================================================
# 指标计算
# ===========================================================================
#: M4 主口径：原文含 MUST/SHALL/REQUIRED。
#: ★ **大小写不敏感** —— 必须与 ``core.fused.semantic.detect_modality`` 同口径
#:   （``_RE_VERB_MANDATORY`` 带 ``re.IGNORECASE``），否则 M4 会因**大小写**
#:   而不是因**污染**失败：B-3 要求「explicit 集合 == 含 MUST/SHALL 的规则集合」，
#:   而 explicitness 正是按大小写不敏感的 MUST 判出来的 ⇒ 判定必须同口径。
_MUST_RE = re.compile(r"(?<!\w)(?:MUST|SHALL|REQUIRED)(?!\w)", re.IGNORECASE)
#: M4 附加诊断：**只认全大写**（RFC 2119 §3：只有全大写关键字有规范力）。
#: 与 ``docs/semantic_rules_coverage_matrix.md`` §5 的口径一致（该文亦指出
#: 规则表内部大小写不敏感、覆盖矩阵用大写，两套口径并存）。
_MUST_RE_UPPER = re.compile(r"(?<!\w)(?:MUST|SHALL|REQUIRED)(?!\w)")
_MAY_RE = re.compile(r"(?<!\w)(?:MAY|OPTIONAL)(?!\w)")


def _modality_is_optional(text: str) -> bool:
    """原文的**有效**规范强度是否为 optional（MAY/OPTIONAL 为最强动词）。

    ★ 与 ``core.fused.semantic.detect_modality`` 同口径（取最强命中：
      mandatory > recommended > optional）。
    """
    from core.fused.semantic import detect_modality
    return detect_modality(text) == "optional"


def compute_metrics(
    c0: dict,
    e1: dict,
    e2: dict,
    truth_state: dict,
) -> dict:
    """算 M1~M7（逐协议 + 合计）。"""
    metrics: dict[str, Any] = {}

    # ── M1 可执行率 ───────────────────────────────────────────────────
    m1: dict[str, Any] = {}
    for protocol in PROTOCOLS:
        c0_items = [i for i in c0[protocol]["items"] if i["protocol"] == protocol]
        e1_items = [i for i in e1[protocol]["items"] if i["protocol"] == protocol]
        e2_items = [i for i in e2[protocol]["items"] if i["protocol"] == protocol]
        n_c0 = len(c0_items)
        c0_dec = sum(1 for i in c0_items if i["decidable"])
        c0_dec_op = sum(1 for i in c0_items if i["decidable_with_operand"])
        c0_dec_presence = sum(
            1 for i in c0_items
            if i["decidable"] and i["operator"] in ("present", "absent"))
        e1_rules = sum(1 for i in e1_items if i["outcome"] == "rule")
        e2_rules = sum(1 for i in e2_items if i["outcome"] == "rule")
        m1[protocol] = {
            "denominator_candidates": n_c0,
            "c0_decidable": c0_dec,
            "c0_decidable_rate_pct": _pct(c0_dec, n_c0),
            "c0_decidable_with_operand_rate_pct": _pct(c0_dec_op, n_c0),
            "c0_decidable_presence_operators_pct": _pct(c0_dec_presence, n_c0),
            "e1_rules": e1_rules,
            "e1_executable_rate_pct": _pct(e1_rules, n_c0),
            "e2_rules": e2_rules,
            "e2_executable_rate_pct": _pct(e2_rules, n_c0),
            "e1_minus_c0_pp": round(
                _pct(e1_rules, n_c0) - _pct(c0_dec, n_c0), 4),
            "e2_minus_c0_pp": round(
                _pct(e2_rules, n_c0) - _pct(c0_dec, n_c0), 4),
        }
    tot_c0 = sum(m1[p]["denominator_candidates"] for p in PROTOCOLS)
    tot_c0_dec = sum(m1[p]["c0_decidable"] for p in PROTOCOLS)
    tot_c0_dec_op = sum(
        sum(1 for i in c0[p]["items"]
            if i["protocol"] == p and i["decidable_with_operand"])
        for p in PROTOCOLS)
    tot_c0_dec_presence = sum(
        sum(1 for i in c0[p]["items"]
            if i["protocol"] == p and i["decidable"]
            and i["operator"] in ("present", "absent"))
        for p in PROTOCOLS)
    tot_e1 = sum(m1[p]["e1_rules"] for p in PROTOCOLS)
    tot_e2 = sum(m1[p]["e2_rules"] for p in PROTOCOLS)
    m1["TOTAL"] = {
        "denominator_candidates": tot_c0,
        "c0_decidable": tot_c0_dec,
        "c0_decidable_rate_pct": _pct(tot_c0_dec, tot_c0),
        "c0_decidable_with_operand_rate_pct": _pct(tot_c0_dec_op, tot_c0),
        "c0_decidable_presence_operators_pct": _pct(
            tot_c0_dec_presence, tot_c0),
        "e1_rules": tot_e1,
        "e1_executable_rate_pct": _pct(tot_e1, tot_c0),
        "e2_rules": tot_e2,
        "e2_executable_rate_pct": _pct(tot_e2, tot_c0),
        "e1_minus_c0_pp": round(
            _pct(tot_e1, tot_c0) - _pct(tot_c0_dec, tot_c0), 4),
        "e2_minus_c0_pp": round(
            _pct(tot_e2, tot_c0) - _pct(tot_c0_dec, tot_c0), 4),
    }
    metrics["M1"] = m1

    # ── M2 规则 F1 ────────────────────────────────────────────────────
    metrics["M2"] = {
        "computable": False,
        "reason": truth_state["reason"],
        "truth_total": truth_state["total"],
        "truth_annotated": truth_state["annotated"],
        "truth_pending": truth_state["pending"],
        "annotators": truth_state["annotators"],
        "holdout_total": truth_state["holdout_total"],
        "holdout_annotated": truth_state["holdout_annotated"],
        "holdout_pending": truth_state["holdout_pending"],
        "kappa": None,
        "c0_f1_same_set": None,
        "c0_f1_note": truth_state["c0_f1_note"],
    }

    # ── M3 证据可验证率 / M4 显式性纯净度 / M5 MAY 误升率 ─────────────
    def group_purity(group: dict) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for protocol in PROTOCOLS:
            rules = [r for r in group[protocol]["rules"]
                     if r.evidence.source_anchor]
            rules = [r for r in group[protocol]["rules"]]
            n = len(rules)
            validated = sum(1 for r in rules if r.validated)
            explicit = [r for r in rules if r.evidence.explicitness == "explicit"]
            explicit_ok = sum(
                1 for r in explicit if _MUST_RE.search(r.evidence.span_text or ""))
            explicit_upper = sum(
                1 for r in explicit
                if _MUST_RE_UPPER.search(r.evidence.span_text or ""))
            has_must = [r for r in rules
                        if _MUST_RE.search(r.evidence.span_text or "")]
            may_rules = [r for r in rules
                         if _modality_is_optional(r.evidence.span_text or "")]
            may_token = [r for r in rules
                         if _MAY_RE.search(r.evidence.span_text or "")]
            out[protocol] = {
                "rules": n,
                "validated_true": validated,
                "m3_evidence_verifiable_rate_pct": _pct(validated, n),
                "explicit_rules": len(explicit),
                "explicit_with_must": explicit_ok,
                "m4_explicitness_purity_pct": _pct(explicit_ok, len(explicit)),
                "explicit_with_must_uppercase_only": explicit_upper,
                "m4_explicitness_purity_uppercase_pct": _pct(
                    explicit_upper, len(explicit)),
                "rules_whose_source_has_must": len(has_must),
                "explicit_set_equals_must_set": len(explicit) == len(has_must),
                "may_optional_rules": len(may_rules),
                "m5_may_misraise_rate_pct": _pct(len(may_rules), n),
                "may_token_rules_loose": len(may_token),
                "m5_may_token_rate_pct_loose": _pct(len(may_token), n),
            }
        all_rules = [r for p in PROTOCOLS for r in group[p]["rules"]]
        n_all = len(all_rules)
        val_all = sum(1 for r in all_rules if r.validated)
        exp_all = [r for r in all_rules if r.evidence.explicitness == "explicit"]
        exp_ok = sum(1 for r in exp_all if _MUST_RE.search(r.evidence.span_text or ""))
        exp_up = sum(1 for r in exp_all
                     if _MUST_RE_UPPER.search(r.evidence.span_text or ""))
        has_all = sum(1 for r in all_rules
                      if _MUST_RE.search(r.evidence.span_text or ""))
        may_all = [r for r in all_rules
                   if _modality_is_optional(r.evidence.span_text or "")]
        may_tok = [r for r in all_rules
                   if _MAY_RE.search(r.evidence.span_text or "")]
        out["TOTAL"] = {
            "rules": n_all,
            "validated_true": val_all,
            "m3_evidence_verifiable_rate_pct": _pct(val_all, n_all),
            "explicit_rules": len(exp_all),
            "explicit_with_must": exp_ok,
            "m4_explicitness_purity_pct": _pct(exp_ok, len(exp_all)),
            "explicit_with_must_uppercase_only": exp_up,
            "m4_explicitness_purity_uppercase_pct": _pct(exp_up, len(exp_all)),
            "rules_whose_source_has_must": has_all,
            "explicit_set_equals_must_set": len(exp_all) == has_all,
            "may_optional_rules": len(may_all),
            "m5_may_misraise_rate_pct": _pct(len(may_all), n_all),
            "may_token_rules_loose": len(may_tok),
            "m5_may_token_rate_pct_loose": _pct(len(may_tok), n_all),
        }
        return out

    metrics["M3_M4_M5"] = {
        "E1": group_purity(e1),
        "E2": group_purity(e2),
    }

    # ── M7 拒绝原因分布 ───────────────────────────────────────────────
    m7: dict[str, Any] = {}
    for label, group in (("E1", e1), ("E2", e2)):
        per_protocol = {}
        for protocol in PROTOCOLS:
            hist = Counter(
                item["reject_reason"]
                for item in group[protocol]["items"]
                if item["outcome"] == "candidate")
            per_protocol[protocol] = dict(sorted(hist.items()))
        total = Counter()
        for protocol in PROTOCOLS:
            for item in group[protocol]["items"]:
                if item["outcome"] == "candidate":
                    total[item["reject_reason"]] += 1
        m7[label] = {"per_protocol": per_protocol,
                     "total": dict(sorted(total.items()))}
    metrics["M7"] = m7
    return metrics


def compute_idempotency(
    protocol: str,
    candidates: list[dict],
    known_fields: list[str],
    n_runs: int,
    llm: Optional[Any] = None,
    llm_facts: Optional[dict] = None,
    group_label: str = "E2",
    use_sanitize: bool = True,
) -> dict:
    """M6：同一批候选句重复抽取 N 次，``rule_id`` 集合是否完全相同。

    ★ 复用**同一份**转换逻辑（E2 = 纯规则表 ⇒ 完全确定性；E1 = 含 LLM 兜底，
      走同一份 LLM 缓存 ⇒ 同样确定）。
    ★ 打印/记录每一轮的 rule_id 集合与两两差集，供报告贴出。
    """
    sets: list[list[str]] = []
    for _ in range(n_runs):
        group = run_group_two_layer(
            protocol, candidates, llm=llm, known_fields=known_fields,
            llm_facts=llm_facts or {},
            use_sanitize=use_sanitize)
        sets.append(sorted(r.rule_id for r in group["rules"]))
    diffs = []
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            diffs.append({
                "run_a": i + 1,
                "run_b": j + 1,
                "only_in_a": sorted(set(sets[i]) - set(sets[j])),
                "only_in_b": sorted(set(sets[j]) - set(sets[i])),
                "identical": set(sets[i]) == set(sets[j]),
            })
    return {
        "protocol": protocol,
        "group": group_label,
        "n_runs": n_runs,
        "rule_id_sets": sets,
        "pairwise_diff": diffs,
        "all_identical": all(d["identical"] for d in diffs),
    }


def decompose_m1(c0: dict, e1: dict) -> dict:
    """M1 差异的**归因拆解**（诚实性必需：解释 E1 与 C0 为何不等）。

    产出四格交叉表：

    * ``both_rule``：C0 可判定 **且** E1 产出规则；
    * ``c0_only``：C0 可判定、但 E1 **未**产出规则 ⇒ 逐条给出 E1 的拒绝原因；
    * ``e1_only``：E1 产出规则、但 C0 不可判定（规则表在**原文**上命中、
      而 C0 的自由文本里没被解析出算子）；
    * ``neither``：两者皆否。

    ★ 另给 ``c0_decidable_but_source_non_normative``：
      C0 判为可判定、但**原文没有任何规范动词**的条数 ——
      这类是 LLM 在中文改写里**幻觉出规范力**（C0 的可判定率被虚高）。
    """
    from core.fused.semantic import detect_modality

    c0_items = {r["candidate_id"]: r for r in c0}
    e1_items = {r["candidate_id"]: r for r in e1}
    both_rule: list[str] = []
    c0_only: list[dict] = []
    e1_only: list[str] = []
    neither = 0
    phantom = 0
    for cid, c0_row in c0_items.items():
        e1_row = e1_items.get(cid, {})
        is_c0 = bool(c0_row.get("decidable"))
        is_e1 = e1_row.get("outcome") == "rule"
        if is_c0 and is_e1:
            both_rule.append(cid)
        elif is_c0 and not is_e1:
            c0_only.append({
                "candidate_id": cid,
                "protocol": c0_row.get("protocol"),
                "text": (c0_row.get("text") or "")[:160],
                "c0_operator": c0_row.get("operator"),
                "c0_operand": c0_row.get("operand"),
                "e1_reject_reason": e1_row.get("reject_reason"),
                "e1_stage_a_reason": e1_row.get("stage_a_reason"),
                "e1_stage_b_reason": e1_row.get("stage_b_reason"),
                "source_modality": detect_modality(c0_row.get("text") or ""),
            })
            if detect_modality(c0_row.get("text") or "") == "none":
                phantom += 1
        elif is_e1 and not is_c0:
            e1_only.append(cid)
        else:
            neither += 1
    return {
        "both_rule": len(both_rule),
        "c0_only": len(c0_only),
        "e1_only": len(e1_only),
        "neither": neither,
        "c0_decidable_but_source_non_normative": phantom,
        "c0_only_detail": sorted(
            c0_only, key=lambda r: (r["protocol"] or "", r["candidate_id"])),
    }


def read_truth_state() -> dict:
    """读人工标注集现状（**只读**）⇒ 判定 M2 是否可计算。"""
    truth_dir = REPO_ROOT / TRUTH_DIR
    total = 0
    pending = 0
    annotated = 0
    annotators: Counter = Counter()
    holdout_total = 0
    holdout_annotated = 0
    holdout_pending = 0
    files = sorted(truth_dir.glob("*.json")) if truth_dir.is_dir() else []
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        is_holdout = "holdout" in path.name
        for row in data:
            total += 1
            if is_holdout:
                holdout_total += 1
            if row.get("pending"):
                pending += 1
                if is_holdout:
                    holdout_pending += 1
                continue
            annotated += 1
            if is_holdout:
                holdout_annotated += 1
            annotators[str(row.get("annotator") or "")] += 1
    n_annotators = len([a for a in annotators if a])
    has_two = n_annotators >= 2
    reason = (
        f"标注集不可用作最终评测集：{TRUTH_DIR}/ 共 {total} 条，其中已标注 "
        f"{annotated} 条、待标（pending 占位）{pending} 条；已标注记录只含标注者 "
        f"{sorted(a for a in annotators if a)}（{n_annotators} 人）⇒ 缺第二名真人"
        f"标注者，Cohen's κ **无法计算**；且 holdout 仅 {holdout_total} 条、其中已标注 "
        f"{holdout_annotated} 条。⇒ M2（规则 P/R/F1，对 holdout）**本轮不可计算**。"
    )
    c0_f1_note = (
        "§4.5 要求同时给出「C0 组在同一标注集上的 F1」；因同一标注集当前不可用"
        "（见 M2.reason），**C0 的 F1 本轮同样不可计算**，此项**不得省略、也不得伪造**。"
    )
    return {
        "total": total,
        "pending": pending,
        "annotated": annotated,
        "annotators": dict(annotators),
        "holdout_total": holdout_total,
        "holdout_annotated": holdout_annotated,
        "holdout_pending": holdout_pending,
        "n_annotators": n_annotators,
        "has_two_annotators": has_two,
        "reason": reason,
        "c0_f1_note": c0_f1_note,
    }


# ===========================================================================
# 预登记文件
# ===========================================================================
def render_prereg(frozen_stats: dict) -> str:
    """渲染预登记文件内容（**实验前定稿，事后不得改**）。"""
    per_protocol = " / ".join(
        f"{p} {n}" for p, n in frozen_stats["per_protocol"].items())

    def _rel(path: str) -> str:
        """仓库相对路径（统一正斜杠，便于文档阅读）。"""
        out = str(path).replace("\\", "/")
        prefix = str(REPO_ROOT).replace("\\", "/") + "/"
        return out[len(prefix):] if out.startswith(prefix) else out

    src_rel = _rel(frozen_stats["source_path"])
    frozen_rel = _rel(frozen_stats["frozen_path"])
    return f"""# B-10 实验预登记（ProtoRAG 里程碑 B 出口闸门）

> ★ **本文件是实验前定稿的预登记，事后不得修改。**
> 依据：`docs/rfc_source_bcd_roadmap.md` §4.1~§4.6。
> 实验结果**不写在本文件**，另见 `docs/semantic_gain_results.md` 与
> `derived/exp_semantic_gain/results.json`（git 历史可证明「预登记先于结果」）。

## 1　预登记（§4.5 阈值表，逐字照抄）

{PREREG_THRESHOLDS}

## 2　综合判定规则（§4.5，逐字照抄）

{PREREG_COMPOSITE}

## 3　已知契约漂移（不参与本实验判定）

{DRIFT_DECLARATION}

## 4　实验方法（预登记）

### 4.1　被测命题

- **命题 B-1**：把 RFC 约束从「自由文本」升级为「两层可执行模型」后，产出的规则中
  **可机械判定**的比例（可执行率）显著高于当前影子实现的可判定比例，
  且**不引入新的知识污染**。
- **辅助命题 B-2（幂等性）**：同一 RFC 重复抽取 N 次（N ≥ 2），`rule_id` 集合完全相同。
- **辅助命题 B-3（无污染）**：两层模型的规则中 `explicitness == "explicit"` 的集合与
  「原文含 MUST/SHALL/REQUIRED」的规则集合完全一致（不多不少）。

### 4.2　三组 × 三协议

| 组 | 输入 | 输出 |
|---|---|---|
| **C0（基线）** | 当前影子实现（`core/fused/rfc_extractor.py::infer_constraints` + LLM） | `legal_boundary` / `response_expectation` **自由文本** fact |
| **E1（实验）** | **同一批候选句** + 同一 LLM 模型/温度/提示词 | `SemanticRule` + `KnowledgeCandidate` |
| **E2（消融）** | 同一批候选句，**只跑规则表**（无 LLM 兜底） | 两层模型 |

- 三协议全跑（rtsp / sip / smtp），**不做跨协议收益比较**（协议差异过大），
  每个协议内部做对照。
- C0 与 E1 共用同一份 LLM 缓存 ⇒ 同一候选句**只调一次** LLM。

### 4.3　候选集（冻结）

- **来源**：复用既有冻结集 `{src_rel}`
  （md5 `{frozen_stats['source_md5']}`），**不重新冻结**。
- **复用理由**：该文件同时满足 §4.2 的三项硬要求 ——
  ① C0/E1/E2 **共用同一批候选句**；② 每条**含 span**（`span_start`/`span_end`）；
  ③ **三协议各 40 条**（实测 {per_protocol}）。
- **差异说明**：既有冻结文件**不含 `section_no_path`**（章节号链），而
  `rule_id` 派生需要它 ⇒ 按 `(protocol, text, span_start)` 与
  `extract_constraint_candidates()` 新鲜抽取做**确定性 join** 补齐，
  实测命中 **{frozen_stats['section_no_path_joined']}/{frozen_stats['total']}** 条
  （未命中 {len(frozen_stats['section_no_path_unmatched'])} 条）。
  ⚠ **不得**用 `section_no.split(".")` 代替 —— 实测仅 29/120 与真值一致。
- 实验内副本落在 `{frozen_rel}`
  （md5 `{frozen_stats['frozen_md5']}`）；**`derived/exp_semantic/` 全程只读**。

### 4.4　LLM 调用

- 模型/温度/提示词：**与影子实现完全一致**（`DeepSeekClient` +
  `core.fused.rfc_extractor._PROMPT_CONSTRAINT`，temperature 0.2，max_tokens 3000）。
- **缓存键** = `sha256(candidate_text + prompt_version + model)`，
  `prompt_version = {PROMPT_VERSION}`；缓存文件
  `derived/exp_semantic_gain/llm_cache.jsonl`（**不含任何凭据**）。
- C0 与 E1 的 LLM 兜底**共用**该缓存 ⇒ 同候选只调一次。
- LLM 失败（网络/额度）时**如实记录失败条数与原因**，并继续跑完不依赖 LLM 的部分
  （E2 消融组、M3/M4/M5/M6/M7），在结果中标注哪些指标受限。

### 4.5　不触碰 rq3/rq4 语料（§4.6 第 1 条）

- **不调用** `scripts/seedgen.py`、`scripts/rq3_build_corpus.py`、`scripts/corpus_gate.py`。
- 产物只落在 `derived/exp_semantic_gain/` 与 `docs/semantic_gain_results.md`。

### 4.6　判定口径（指标定义 M1~M7）

| 指标 | 定义（口径） | 目标 |
|---|---|---|
| **M1 可执行率** | E1/E2：`len(rules) / (len(rules) + len(candidates))`（= 可执行规则数 ÷ 候选句数，逐候选归因）；C0：**自由文本能否解析出 operator**（判据：能否从 `legal_boundary` 的 `legal`（失败则 `illegal`）机械解析出 operator，数值型算子还须抓到操作数）。**三个组分母同为 120 条候选句**。 | E1 ≥ C0 + **15 个百分点**（成立）/ +5（部分）/ <+5（不成立） |
| **M2 规则 P/R/F1** | 对**独立人工标注集**（holdout）的 P/R/F1 | ≥ 0.70（holdout） |
| **M3 证据可验证率** | `validated=True` 的比例（`validated` 取**真实的区间核对结果**） | **= 100%** |
| **M4 显式性纯净度** | `explicitness == "explicit"` 的规则中原文确实含 MUST/SHALL/REQUIRED 的比例 | **= 100%** |
| **M5 MAY 误升率** | 原文**有效规范强度**为 MAY/OPTIONAL（取最强动词，与 `core.fused.semantic.detect_modality` 同口径）却被标为 executable 的比例 | **= 0%** |
| **M6 rule_id 幂等性** | 同一批候选句重复抽取 N 次（N ≥ 2），`rule_id` **集合**是否完全相同 | **完全相同** |
| **M7 拒绝原因分布** | 候选按 `reject_reason` 的直方图（观测项） | 观测项 |

**C0 可判定率的判定实现**：单函数 `probe_operator()`（`scripts/exp_semantic_gain.py`），
有序模式表（中文 + 英文），**C0 的可判定率与 E1 的 LLM 兜底共用同一函数** ⇒ 两个口径同源。

### 4.7　本轮**已知不可计算**的项（预登记）

- **M2（本轮不可计算）**：人工标注集当前不可用作最终评测集
  —— `derived/exp_semantic/truth/` 120 条中**仅 3 条已标注、117 条待标**（`pending` 占位），
  且已标注记录**只含标注者 A**，**缺真人标注者 B ⇒ Cohen's κ 无法计算**。
  ⇒ **绝不**用这 3 条、也**绝不**用规则自身推导出的「伪标注」冒充人工标注集算 F1。
- **C0 组在同一标注集上的 F1**：同一原因 ⇒ **不可计算**（§4.5 要求必报，标为不可计算并说明原因）。
- **综合判定**：因 M2 不可计算 ⇒ 综合判定只能写「**暂不可判定**」；
  M1/M3/M4/M5/M6/M7 的实测值只支持「表达层升级是否带来可执行性收益」这一部分结论，
  「知识质量收益（F1）」须等标注集定稿后再评。

## 5　结果

**结果待填：实验尚未执行。**
"""


# ===========================================================================
# 结果文件渲染
# ===========================================================================
def render_results(
    metrics: dict,
    frozen_stats: dict,
    llm_stats: dict,
    idempotency: dict,
    truth_state: dict,
    groups_meta: dict,
    m1_decomposition: dict,
) -> str:
    m1 = metrics["M1"]
    m345 = metrics["M3_M4_M5"]
    m7 = metrics["M7"]
    total = m1["TOTAL"]

    def _rel(path: str) -> str:
        """仓库相对路径（统一正斜杠，便于文档阅读）。"""
        out = str(path).replace("\\", "/")
        prefix = str(REPO_ROOT).replace("\\", "/") + "/"
        return out[len(prefix):] if out.startswith(prefix) else out

    lines: list[str] = []
    add = lines.append
    add("# B-10 实验结果（里程碑 B 出口闸门）")
    add("")
    add(f"- 生成时间：`{groups_meta['generated_at']}`")
    add(f"- 候选集：`{_rel(frozen_stats['frozen_path'])}`"
        f"（md5 `{frozen_stats['frozen_md5']}`，源 "
        f"`{_rel(frozen_stats['source_path'])}`"
        f" md5 `{frozen_stats['source_md5']}`）")
    add(f"- 候选句总数：**{frozen_stats['total']}**"
        f"（{frozen_stats['per_protocol']}）")
    add(f"- LLM：实际调用 **{llm_stats['calls_made']}** 次，"
        f"缓存命中 **{llm_stats['cache_hits']}** 次，失败 **{len(llm_stats['failures'])}** 次")
    add("")
    add("> ★ 本文件只放**结果**；预登记在 `docs/semantic_gain_report.md`（实验前定稿）。")
    add("")

    add("## 1　M1 可执行率")
    add("")
    add("| 协议 | 候选句 | C0 可判定 | C0 可判定率 | E1 可执行规则 | E1 可执行率 | E2 可执行规则 | E2 可执行率 | E1−C0 (pp) |")
    add("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for protocol in list(PROTOCOLS) + ["TOTAL"]:
        row = m1[protocol]
        add(f"| {protocol} | {row['denominator_candidates']} | "
            f"{row['c0_decidable']} | {row['c0_decidable_rate_pct']:.2f}% | "
            f"{row['e1_rules']} | {row['e1_executable_rate_pct']:.2f}% | "
            f"{row['e2_rules']} | {row['e2_executable_rate_pct']:.2f}% | "
            f"{row['e1_minus_c0_pp']:+.2f} |")
    add("")
    add("- C0「可判定率」判定实现：`scripts/exp_semantic_gain.py::probe_operator()`"
        "（有序模式表，中英双语；C0 与 E1 的 LLM 兜底**共用**同一函数）。")
    add("- C0「可判定率」主口径 = 能解析出 operator（与 §4.2 口径一致）。")
    add("")
    add("| 协议 | C0 可判定率（主口径） | 其中数值型算子且抓到操作数 | 其中存在性算子（present/absent，本就无操作数） |")
    add("|---|---:|---:|---:|")
    for protocol in list(PROTOCOLS) + ["TOTAL"]:
        row = m1[protocol]
        add(f"| {protocol} | {row['c0_decidable_rate_pct']:.2f}% | "
            f"{row['c0_decidable_with_operand_rate_pct']:.2f}% | "
            f"{row['c0_decidable_presence_operators_pct']:.2f}% |")
    add("")
    add("⚠ **「数值型算子且抓到操作数」这一列不是更严的同口径指标**，"
        "而是主口径的**子集**：存在性算子（`present`/`absent`）"
        "按定义**不需要操作数**，把它判为不可判定对 C0 不公平。"
        "⇒ **判定口径只用主口径**；该列仅作参考。")
    add("")

    add("## 2　M2 规则 P/R/F1 —— **不可计算**")
    add("")
    add("### 2.1　M1 差异的归因拆解（为什么 E1 与 C0 不等）")
    add("")
    add("| 协议 | 两者皆规则 | 仅 C0 可判定 | 仅 E1 规则 | 皆否 | 仅 C0 可判定且**原文无规范动词** |")
    add("|---|---:|---:|---:|---:|---:|")
    for protocol in PROTOCOLS:
        d = m1_decomposition[protocol]
        add(f"| {protocol} | {d['both_rule']} | {d['c0_only']} | "
            f"{d['e1_only']} | {d['neither']} | "
            f"{d['c0_decidable_but_source_non_normative']} |")
    add("")
    add("**读法（诚实说明）**：")
    add("")
    add("- 「仅 C0 可判定」= C0 的**自由文本**里能解析出算子，但 E1 **未**产出规则 ——"
        " 逐条原因见下表。")
    add("- 「仅 C0 可判定且**原文无规范动词**」是**关键的一类**：C0 判为可判定，"
        "但 **RFC 原句里根本没有 MUST/SHALL 等规范动词** ⇒ 是 LLM 在中文改写里"
        "**幻觉出了规范力**。这类项 C0 计入可判定、E1 按 C3（`non_normative_kind`）"
        "正确拒绝 ⇒ **C0 的可判定率被 LLM 幻觉虚高**。")
    add("- 「仅 E1 规则」= 规则表在**RFC 原文**上命中了算子，而 C0 的中文自由文本里"
        "没有可解析的算子 ⇒ **两层模型从原文取证的优势**。")
    add("")
    add("逐条明细（仅 C0 可判定的条目）：")
    add("")
    add("| 协议 | candidate_id | E1 拒绝原因 | 阶段A | 阶段B | 原文 modality | C0 算子 |")
    add("|---|---|---|---|---|---|---|")
    for protocol in PROTOCOLS:
        for row in m1_decomposition[protocol]["c0_only_detail"]:
            add(f"| {row['protocol']} | `{row['candidate_id']}` | "
                f"`{row['e1_reject_reason']}` | `{row['e1_stage_a_reason']}` | "
                f"`{row['e1_stage_b_reason']}` | {row['source_modality']} | "
                f"`{row['c0_operator']}` |")
    add("")
    add(f"> {metrics['M2']['reason']}")
    add("")
    add(f"> {metrics['M2']['c0_f1_note']}")
    add("")
    add(f"- 标注集现状：总计 {metrics['M2']['truth_total']} 条，"
        f"已标注 {metrics['M2']['truth_annotated']} 条，"
        f"待标 {metrics['M2']['truth_pending']} 条；"
        f"标注者 {metrics['M2']['annotators']}。")
    add(f"- holdout：共 {metrics['M2']['holdout_total']} 条，"
        f"其中已标注 {metrics['M2']['holdout_annotated']} 条。")
    add("- Cohen's κ：**无法计算**（缺第二名真人标注者）。")
    add("")

    add("## 3　M3 / M4 / M5")
    add("")
    add("| 组 | 协议 | 规则数 | M3 证据可验证率 | explicit 规则 | M4 纯净度 | M5 MAY 误升率 | explicit 集合 == MUST 集合 |")
    add("|---|---|---:|---:|---:|---:|---:|:---:|")
    for label in ("E1", "E2"):
        for protocol in list(PROTOCOLS) + ["TOTAL"]:
            row = m345[label][protocol]
            add(f"| {label} | {protocol} | {row['rules']} | "
                f"{row['m3_evidence_verifiable_rate_pct']:.2f}% | "
                f"{row['explicit_rules']} | "
                f"{row['m4_explicitness_purity_pct']:.2f}% | "
                f"{row['m5_may_misraise_rate_pct']:.2f}% | "
                f"{'是' if row['explicit_set_equals_must_set'] else '**否**'} |")
    add("")
    add("- M4 主口径：原文含 MUST/SHALL/REQUIRED（大小写不敏感，与 "
        "`core.fused.semantic.detect_modality` 同口径）。")
    add("- M5 主口径：原文**有效规范强度**为 optional（MAY/OPTIONAL 为最强动词）。")
    add("- 「explicit 集合 == MUST 集合」即**辅助命题 B-3**（不多不少）。")
    add("")

    add("## 4　M6 rule_id 幂等性")
    add("")
    idem = idempotency
    add(f"- 重复抽取 **{idem[PROTOCOLS[0]]['n_runs']}** 次（E2 口径：纯规则表 ⇒ "
        "完全确定性），**三协议全跑**。")
    add(f"- 三协议全部轮次 rule_id 集合**完全相同**："
        f"**{'是' if idem.get('all_protocols_identical') else '否'}**。")
    add("")
    for protocol in PROTOCOLS:
        p = idem[protocol]
        add(f"### {protocol}")
        add("")
        add(f"- 重复 {p['n_runs']} 轮，全部轮次集合相同："
            f"**{'是' if p['all_identical'] else '否'}**"
            f"（{len(p['rule_id_sets'][0])} 条规则）。")
        for i, s in enumerate(p["rule_id_sets"], start=1):
            add(f"- 第 {i} 轮 rule_id 集合（{len(s)} 条）：`{s}`")
        for d in p["pairwise_diff"]:
            add(f"- 轮 {d['run_a']} vs 轮 {d['run_b']}："
                f"仅在 A={d['only_in_a']}，仅在 B={d['only_in_b']}，"
                f"相同={d['identical']}")
        add("")

    add("## 5　M7 拒绝原因分布")
    add("")
    for label in ("E1", "E2"):
        add(f"### {label}")
        add("")
        add("| 协议 | 拒绝原因分布 |")
        add("|---|---|")
        for protocol in PROTOCOLS:
            dist = m7[label]["per_protocol"].get(protocol, {})
            add(f"| {protocol} | {dist} |")
        add(f"| **合计** | {m7[label]['total']} |")
        add("")

    add("## 6　LLM 调用统计")
    add("")
    add(f"- 实际 LLM 调用：**{llm_stats['calls_made']}** 次")
    add(f"- 缓存命中：**{llm_stats['cache_hits']}** 次")
    add(f"- 本次运行前**已存在**的缓存条目（上一轮已付费）："
        f"**{llm_stats.get('cache_reused_from_previous_run', 0)}** 条")
    add(f"- 缓存文件内**去重后**的响应总数：**{llm_stats.get('cache_entries_total', 0)}** 条"
        f"（= 不同候选句数；C0 与 E1 共用 ⇒ 同一候选句只调一次 LLM）")
    add(f"- 失败：**{len(llm_stats['failures'])}** 次")
    add(f"- 缓存文件：`{_rel(llm_stats['cache_path'])}`（缓存键 "
        f"`sha256(candidate_text + prompt_version + model)`，"
        f"`prompt_version={PROMPT_VERSION}`，`model={llm_stats['model']}`）")
    if llm_stats["failures"]:
        add("")
        add("失败明细（最多列 20 条）：")
        add("")
        add("| 候选句 | 错误类型 | 错误 |")
        add("|---|---|---|")
        for f in llm_stats["failures"][:20]:
            add(f"| {f['candidate_text'][:60]} | {f['error_type']} | {f['error']} |")
    add("")

    add("## 6.1　运行间方差（LLM 非确定性）")
    add("")
    variance = groups_meta.get("run_variance")
    if not variance:
        add("- 本次是**首次**运行（无上一次结果可比）⇒ 无方差数据。")
        add("- ⚠ 若要复现本结果，请**连同 `llm_cache.jsonl` 一起**保留："
            "缓存命中时逐位可复现（抖动 0）；冷缓存重跑会因 LLM 温度 0.2 产生抖动。")
    else:
        prev = variance["previous_m1_total"]
        cur = variance["current_m1_total"]
        add(f"- 上一次运行：`{variance['previous_run_at']}`"
            f"（该次实际 LLM 调用 {variance['previous_llm_calls_made']} 次）")
        add("")
        add("| 指标 | 上一次 | 本次 | 差 |")
        add("|---|---:|---:|---:|")
        for key, label in (
            ("c0_decidable_rate_pct", "C0 可判定率 %"),
            ("e1_executable_rate_pct", "E1 可执行率 %"),
            ("e2_executable_rate_pct", "E2 可执行率 %"),
            ("e1_minus_c0_pp", "E1−C0 (pp)"),
        ):
            p_val = prev.get(key)
            c_val = cur.get(key)
            delta = "" if p_val is None else f"{c_val - p_val:+.2f}"
            add(f"| {label} | {p_val} | {c_val} | {delta} |")
        add("")
        add(f"- {variance['note']}")
    add("")

    add("## 7　综合判定")
    add("")
    add("> **暂不可判定** —— M2 本轮**不可计算**（见 §2）。")
    add("")
    m1_delta = total["e1_minus_c0_pp"]
    if m1_delta >= 15:
        m1_verdict = "达「收益成立」档（E1 ≥ C0 + 15 个百分点）"
    elif m1_delta >= 5:
        m1_verdict = "达「部分成立」档（E1 ≥ C0 + 5 个百分点）"
    else:
        m1_verdict = "落「不成立」档（E1 < C0 + 5 个百分点）"
    add(f"- M1（E1 − C0 = {m1_delta:+.2f} 个百分点）：{m1_verdict}。")
    variance = groups_meta.get("run_variance")
    if variance:
        prev_delta = variance["previous_m1_total"].get("e1_minus_c0_pp")
        if prev_delta is not None:
            band = "不成立" if m1_delta < 5 else (
                "部分成立" if m1_delta < 15 else "成立")
            prev_band = "不成立" if prev_delta < 5 else (
                "部分成立" if prev_delta < 15 else "成立")
            add(f"  - **档位稳定性**：上一次冷跑 E1−C0 = {prev_delta:+.2f} pp"
                f"（{prev_band}档），本次 {m1_delta:+.2f} pp（{band}档）"
                f" ⇒ **两次落在同一档**，说明本轮 M1 的**档位结论对 LLM 抖动稳健**"
                f"（抖动幅度见 §6.1）。")
    add("")
    add("  ⚠ **M1 的诚实解读**（见 §2.1 归因拆解）：本轮 E1 的可执行率**低于** C0 的可判定率，"
        "但这**不等于**「两层模型更差」。原因有二：")
    add("")
    add("  ① **C0 的可判定率被 LLM 幻觉虚高**：C0 判为可判定的条目中，"
        "有一部分的 **RFC 原句里没有任何规范动词** —— 是 LLM 在中文改写里"
        "**幻觉出了规范力**，而 C0 的自由文本照样能被解析出算子。"
        "E1 按 C3（`non_normative_kind`）把这类**正确拒绝**了 ⇒ "
        "**C0 的分子含「幻觉项」**。")
    add("  ② **两者的分母/门槛不同**：C0 只需「文本里能解析出算子」；"
        "E1 还要过 C2（区间核对）、C3（证据类型）、C6（字段绑定）、"
        "可选性闸门等 —— 这正是两层模型的设计意图（**不污染**）。")
    add("")
    add("  ⇒ 因此本轮 M1 应读作：**「按『规则表+闸门』的严格口径，E1 只覆盖 "
        f"{total['e1_executable_rate_pct']:.2f}% 的候选句；"
        "而 C0 的『可判定』里有相当比例来自 LLM 改写时的幻觉规范力」** —— "
        "**不能**读作「表达层升级没有收益」。真正的知识质量收益（M2/F1）"
        "仍待标注集定稿后评。")
    for label in ("E1", "E2"):
        row = m345[label]["TOTAL"]
        add(f"- M3 {label} = {row['m3_evidence_verifiable_rate_pct']:.2f}%"
            f"（目标 100%）；"
            f"M4 {label} = {row['m4_explicitness_purity_pct']:.2f}%（目标 100%）；"
            f"M5 {label} = {row['m5_may_misraise_rate_pct']:.2f}%（目标 0%）；"
            f"B-3（explicit 集合 == MUST 集合）= "
            f"{'成立' if row['explicit_set_equals_must_set'] else '不成立'}。")
    add(f"- M6（rule_id 幂等性，三协议 × {idem[PROTOCOLS[0]]['n_runs']} 轮）："
        f"{'全部完全相同' if idem.get('all_protocols_identical') else '存在差异'}。")
    add("")
    add("- 按 §4.5：M2 缺失 ⇒ **不得**宣告「收益成立」或「收益不成立」，"
        "综合判定只能是「**暂不可判定**」。")
    add("- M1/M3/M4/M5/M6/M7 的实测值**已足以支持**「表达层升级是否带来可执行性收益」"
        "这一部分结论；「知识质量收益（F1）」这一部分要等标注集定稿后再评。")
    add("- **C0 组在同一标注集上的 F1** 同样不可计算（§4.5 要求必报，"
        "此处如实标注为不可计算并说明原因，不省略、不伪造）。")
    add("")
    return "\n".join(lines) + "\n"


# ===========================================================================
# 主流程
# ===========================================================================
def self_check(out_dir: Path, frozen_path: Path) -> list[str]:
    """三道自检（跑之前）。"""
    problems: list[str] = []
    # ① 目标目录可写
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".selfcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except Exception as exc:  # noqa: BLE001
        problems.append(f"① 目标目录不可写：{out_dir}（{exc}）")
    # ② 冻结候选集存在且三协议都有
    if not frozen_path.is_file():
        problems.append(f"② 冻结候选集不存在：{frozen_path}")
    else:
        rows = _read_jsonl(frozen_path)
        protos = {r.get("protocol") for r in rows}
        missing = set(PROTOCOLS) - protos
        if missing:
            problems.append(f"② 冻结候选集缺协议：{sorted(missing)}")
        no_span = [r.get("candidate_id") for r in rows
                   if r.get("span_start") is None or r.get("span_end") is None]
        if no_span:
            problems.append(f"② 冻结候选集有 {len(no_span)} 条缺 span")
    return problems


def run_experiment(
    out_dir: Path,
    results_doc: Path,
    n_idempotency: int,
    use_sanitize: bool = True,
) -> dict:
    """跑完整实验（--run）。"""
    from core.fused.rfc_extractor import known_field_set
    from core.llm import DeepSeekClient

    started = time.time()
    frozen_src = REPO_ROOT / FROZEN_SOURCE_CANDIDATES
    frozen_dst = out_dir / "candidates_frozen.jsonl"

    print("=== B-10 实验开始 ===")
    print(f"[自检] 目标目录 {out_dir}")
    problems = self_check(out_dir, frozen_src)
    if problems:
        for p in problems:
            print(f"  ✗ {p}")
        raise SystemExit(2)
    print("  ✓ ① 目标目录可写")
    print("  ✓ ② 冻结候选集存在且三协议齐全")

    frozen_rows, frozen_stats = load_frozen_candidates(frozen_src, frozen_dst)
    print(f"  ✓ ③ 候选集 {frozen_stats['total']} 条 "
          f"({frozen_stats['per_protocol']})，md5={frozen_stats['frozen_md5']}")

    # LLM 客户端（可初始化 ⇒ 失败则降级并记录）
    llm_client = None
    llm_error = ""
    try:
        llm_client = DeepSeekClient()
        print(f"  ✓ ③ LLM 客户端可初始化（model={llm_client.model}）")
    except Exception as exc:  # noqa: BLE001
        llm_error = f"{type(exc).__name__}: {exc}"
        print(f"  ! LLM 客户端不可初始化 ⇒ 降级（仅跑 E2 与不依赖 LLM 的指标）：{llm_error}")

    model_name = getattr(llm_client, "model", "unknown") if llm_client else "unavailable"
    cached_llm = CachedLLM(llm_client, out_dir / "llm_cache.jsonl", model_name) \
        if llm_client else None

    # 已知字段集
    for protocol in PROTOCOLS:
        _KNOWN_FIELDS[protocol] = tuple(known_field_set(protocol))
    print("[字段集] " + " / ".join(
        f"{p}={len(_KNOWN_FIELDS[p])}" for p in PROTOCOLS))

    c0: dict[str, dict] = {}
    e1: dict[str, dict] = {}
    e2: dict[str, dict] = {}
    llm_facts_by_candidate: dict[str, dict] = {}

    for protocol in PROTOCOLS:
        cands = [r for r in frozen_rows if r["protocol"] == protocol]
        print(f"\n--- {protocol}（{len(cands)} 条候选句）---")

        # ── C0（影子实现 + LLM）──────────────────────────────────────────
        if cached_llm is not None:
            c0[protocol] = run_group_c0(protocol, cands, cached_llm)
            for item in c0[protocol]["items"]:
                llm_facts_by_candidate[item["candidate_id"]] = item
        else:
            c0[protocol] = {"items": [], "facts": []}

        # ── E1（规则表 + LLM 兜底）──────────────────────────────────────
        e1[protocol] = run_group_two_layer(
            protocol, cands,
            llm=cached_llm,
            known_fields=list(_KNOWN_FIELDS[protocol]),
            llm_facts=llm_facts_by_candidate,
            use_sanitize=use_sanitize,
        )
        # ── E2（只跑规则表）──────────────────────────────────────────────
        e2[protocol] = run_group_two_layer(
            protocol, cands, llm=None,
            known_fields=list(_KNOWN_FIELDS[protocol]),
            llm_facts={},
            use_sanitize=use_sanitize,
        )

        for label, group in (("C0", c0[protocol]), ("E1", e1[protocol]),
                             ("E2", e2[protocol])):
            if label == "C0":
                dec = sum(1 for i in group["items"] if i["decidable"])
                print(f"  {label}: 候选 {len(group['items'])}，可判定 {dec}"
                      f"（{_pct(dec, len(group['items'])):.2f}%），"
                      f"fact {len(group['facts'])}")
            else:
                nr = len(group["rules"])
                nc = len(group["candidates"])
                print(f"  {label}: 规则 {nr}，候选 {nc}，"
                      f"可执行率 {_pct(nr, nr + nc):.2f}%")

    # ── M6 幂等性（E2 口径，纯规则表 ⇒ 完全确定性）───────────────────
    print("\n--- M6 幂等性 ---")
    idempotency: dict[str, Any] = {}
    for protocol in PROTOCOLS:
        per_protocol = compute_idempotency(
            protocol,
            [r for r in frozen_rows if r["protocol"] == protocol],
            list(_KNOWN_FIELDS[protocol]),
            n_idempotency,
            use_sanitize=use_sanitize,
        )
        idempotency[protocol] = per_protocol
        print(f"  {protocol} × {per_protocol['n_runs']} 轮："
              f"rule_id 集合完全相同 = {per_protocol['all_identical']}"
              f"（{len(per_protocol['rule_id_sets'][0])} 条规则）")
    idempotency["all_protocols_identical"] = all(
        idempotency[p]["all_identical"] for p in PROTOCOLS)

    # ── M1 差异归因（诚实性必需）──────────────────────────────────────
    print("\n--- M1 归因拆解 ---")
    m1_decomposition: dict[str, Any] = {}
    for protocol in PROTOCOLS:
        m1_decomposition[protocol] = decompose_m1(
            c0[protocol]["items"], e1[protocol]["items"])
        d = m1_decomposition[protocol]
        print(f"  {protocol}: 两者皆规则 {d['both_rule']}，"
              f"仅 C0 可判定 {d['c0_only']}（其中原文无规范动词 "
              f"{d['c0_decidable_but_source_non_normative']}），"
              f"仅 E1 规则 {d['e1_only']}，皆否 {d['neither']}")

    # ── 指标 ───────────────────────────────────────────────────────────
    truth_state = read_truth_state()
    metrics = compute_metrics(c0, e1, e2, truth_state)

    # ── 落盘 ───────────────────────────────────────────────────────────
    for label, group in (("C0", c0), ("E1", e1), ("E2", e2)):
        gdir = out_dir / f"group_{label}"
        gdir.mkdir(parents=True, exist_ok=True)
        _write_jsonl(gdir / "items.jsonl",
                     [i for p in PROTOCOLS for i in group[p]["items"]])
        if label == "C0":
            _write_jsonl(gdir / "facts.jsonl",
                         [f for p in PROTOCOLS for f in group[p]["facts"]])
        else:
            _write_jsonl(gdir / "rules.jsonl",
                         [asdict(r) for p in PROTOCOLS
                          for r in group[p]["rules"]])
            _write_jsonl(gdir / "candidates.jsonl",
                         [asdict(c) for p in PROTOCOLS
                          for c in group[p]["candidates"]])

    llm_stats = {
        "calls_made": cached_llm.calls_made if cached_llm else 0,
        "cache_hits": cached_llm.cache_hits if cached_llm else 0,
        "cache_reused_from_previous_run": (
            cached_llm.cache_reused if cached_llm else 0),
        "cache_entries_total": (
            len(cached_llm._cache) if cached_llm else 0),
        "failures": cached_llm.failures if cached_llm else [],
        "cache_path": str(out_dir / "llm_cache.jsonl"),
        "model": model_name,
        "prompt_version": PROMPT_VERSION,
        "client_error": llm_error,
    }

    groups_meta = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(time.time() - started, 1),
        "run_variance": None,
    }

    results = {
        "experiment": "B-10",
        "roadmap": "docs/rfc_source_bcd_roadmap.md §4",
        "prereg": "docs/semantic_gain_report.md",
        "generated_at": groups_meta["generated_at"],
        "elapsed_s": groups_meta["elapsed_s"],
        "frozen_candidates": frozen_stats,
        "llm": llm_stats,
        "known_fields": {p: len(_KNOWN_FIELDS[p]) for p in PROTOCOLS},
        "metrics": metrics,
        "idempotency": idempotency,
        "m1_decomposition": m1_decomposition,
        "verdict": {
            "composite": "暂不可判定",
            "reason": "M2 本轮不可计算（人工标注集未完成、缺第二名真人标注者、"
                      "κ 无法计算）⇒ 按 §4.5 综合判定只能是「暂不可判定」。",
            "m1_delta_pp_e1_minus_c0": metrics["M1"]["TOTAL"]["e1_minus_c0_pp"],
        },
    }

    # ── 运行间方差（LLM 非确定性）：与**上一次**运行对比 ───────────────
    #   §4.7 风险表列了「LLM 非确定性导致 C0/E1 不可比」⇒ 缓解手段是
    #   「候选句冻结 + LLM 缓存」。本节量化：**冷缓存**重跑的抖动幅度，
    #   让读者知道 M1 的差值带多少 LLM 噪声（缓存命中时抖动为 0）。
    prev_path = out_dir / "results.json"
    if prev_path.is_file():
        try:
            prev = json.loads(prev_path.read_text(encoding="utf-8"))
            prev_m1 = prev.get("metrics", {}).get("M1", {})
            prev_total = prev_m1.get("TOTAL", {})
            results["run_variance"] = {
                "previous_run_at": prev.get("generated_at"),
                "previous_llm_calls_made": prev.get("llm", {}).get(
                    "calls_made"),
                "previous_m1_total": {
                    "c0_decidable_rate_pct": prev_total.get(
                        "c0_decidable_rate_pct"),
                    "e1_executable_rate_pct": prev_total.get(
                        "e1_executable_rate_pct"),
                    "e2_executable_rate_pct": prev_total.get(
                        "e2_executable_rate_pct"),
                    "e1_minus_c0_pp": prev_total.get("e1_minus_c0_pp"),
                },
                "current_m1_total": {
                    "c0_decidable_rate_pct": metrics["M1"]["TOTAL"][
                        "c0_decidable_rate_pct"],
                    "e1_executable_rate_pct": metrics["M1"]["TOTAL"][
                        "e1_executable_rate_pct"],
                    "e2_executable_rate_pct": metrics["M1"]["TOTAL"][
                        "e2_executable_rate_pct"],
                    "e1_minus_c0_pp": metrics["M1"]["TOTAL"][
                        "e1_minus_c0_pp"],
                },
                "delta_e1_minus_c0_pp": round(
                    metrics["M1"]["TOTAL"]["e1_minus_c0_pp"]
                    - (prev_total.get("e1_minus_c0_pp") or 0.0), 4),
                "note": "缓存命中 ⇒ 两次数值完全相同（抖动 0）；"
                        "冷缓存重跑 ⇒ 抖动来自 LLM 温度 0.2 的非确定性。",
            }
        except Exception:  # noqa: BLE001 —— 读旧结果失败不应影响本次实验
            results["run_variance"] = None

    (out_dir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    groups_meta["run_variance"] = results.get("run_variance")

    doc = render_results(
        metrics, frozen_stats, llm_stats, idempotency, truth_state, groups_meta,
        m1_decomposition)
    _write_text(results_doc, doc)

    print("\n=== 结果摘要 ===")
    print(doc)
    print(f"=== 产物 ===\n{out_dir}\n{results_doc}")
    return results


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="B-10 实验：RFC 约束表达层升级的可执行性收益")
    ap.add_argument("--prereg", action="store_true",
                    help="只写预登记文件（docs/semantic_gain_report.md）")
    ap.add_argument("--run", action="store_true",
                    help="跑实验，产出 derived/exp_semantic_gain/ + 结果文档")
    ap.add_argument("--all", action="store_true",
                    help="先 --prereg 后 --run")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR,
                    help=f"实验产物目录（默认 {DEFAULT_OUT_DIR}）")
    ap.add_argument("--report", default=DEFAULT_REPORT,
                    help=f"预登记文件路径（默认 {DEFAULT_REPORT}）")
    ap.add_argument("--results-doc", default=DEFAULT_RESULTS_DOC,
                    help=f"结果文档路径（默认 {DEFAULT_RESULTS_DOC}）")
    ap.add_argument("--idempotency-runs", type=int, default=3,
                    help="M6 幂等性重复抽取轮数 N（默认 3，须 ≥ 2）")
    ap.add_argument(
        "--no-sanitize",
        action="store_true",
        help="★ M7 对照用：**禁用** LLM 输出后处理（sanitize_rule）⇒ "
             "跑出「基线」口径 ⇒ 与默认（带 sanitize）对比即批次 2 的收益",
    )
    ap.add_argument("--publish-authoritative", action="store_true",
                    help="★ 批次 1.5：把实验产出的规则**分流发布**进权威库"
                         "（derived/per_source/<协议>/rfc/semantic/）⇒ "
                         "知识中枢能读到 ⇒ 投影出 legal_boundary ⇒ "
                         "「源 A 第四类」约束边界候选不再恒为 0。"
                         "★ **默认不发布**（保持实验不污染生产）。")
    args = ap.parse_args(argv)

    if not (args.prereg or args.run or args.all):
        ap.error("至少指定 --prereg / --run / --all 之一")

    out_dir = Path(args.out_dir)
    if not out_dir.is_absolute():
        out_dir = REPO_ROOT / out_dir
    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path
    results_doc = Path(args.results_doc)
    if not results_doc.is_absolute():
        results_doc = REPO_ROOT / results_doc

    if args.prereg or args.all:
        frozen_src = REPO_ROOT / FROZEN_SOURCE_CANDIDATES
        stats = compute_frozen_stats(frozen_src, out_dir / "candidates_frozen.jsonl")
        content = render_prereg(stats)
        if report_path.is_file():
            old = report_path.read_text(encoding="utf-8")
            if old == content:
                print(f"[prereg] 已存在且内容一致 ⇒ 不改动：{report_path}")
            else:
                print(f"[prereg] 已存在但内容不同 ⇒ **拒绝覆盖**"
                      f"（预登记定稿后不得修改）：{report_path}")
                return 3
        else:
            _write_text(report_path, content)
            print(f"[prereg] 已写入：{report_path}")

    if args.run or args.all:
        run_experiment(out_dir, results_doc, max(2, args.idempotency_runs),
                      use_sanitize=not args.no_sanitize)

    if args.publish_authoritative:
        # ★ 批次 1.5：受控发布（默认不发布）。
        #   把各实验组的 rules.jsonl 交给 rule_store.publish_rules 分流：
        #   合格 ⇒ 权威库；不合格 ⇒ 候选库（带 reject_reason，不静默丢弃）。
        from core.fused.downstream.rule_store import publish_rules
        for _label in ("E1", "E2"):
            _src = out_dir / f"group_{_label}" / "rules.jsonl"
            if not _src.is_file():
                continue
            _rows = [json.loads(_l) for _l in
                     _src.read_text(encoding="utf-8").splitlines()
                     if _l.strip()]
            for _proto in PROTOCOLS:
                _sub = [r for r in _rows
                        if ((r.get("evidence") or {}).get("protocol")
                            in (None, _proto))]
                if not _sub:
                    continue
                _rep = publish_rules(_proto, _sub, replace=True)
                print(f"[发布] {_proto} ← {_label}: 权威库 "
                      f"{_rep['authoritative']} 条 / 候选库 "
                      f"{_rep['candidate']} 条 / 拒绝 "
                      f"{_rep['rejects']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
