"""core/fused/semantic/llm_ensemble.py —— 多模型投票（默认关闭）。

★ 当前只落地 D-6 的**开关位**：语义规则是否参与生成。
  投票本体（D-1~D-5、D-7）属于 D 阶段其余任务，**在 B-10 实验判定
  「收益成立」之前不应投入**（见 docs/实施/路线与里程碑/RFC源里程碑路线图.md §6）。

开关位的准确语义
----------------
「开关关闭」= **不自动引入语义规则**：

  · ``assemble_bundle`` **不主动去读权威规则库**；
  · 消费路径（``load_semantic_rules`` + ``project_semantic_rules``）**0 次调用**；
  · 产物里**不含** ``semantic_rules`` / ``bundle_schema_version`` 两个新键
    ⇒ 默认产物与 B-8 之前**逐字节一致**（D-6 的核心验收）。

「显式传入 ``semantic_rules=``」= **调用方的显式授权**（程序化 API 层面的
直接输入），**优先于开关**：照常装载 + 投影 —— **不得**静默丢弃显式传入的规则
（否则 B-8 已落库的契约会被破坏）。

判定顺序（**每次调用时**判定，**不在 import 时缓存** ⇒ 测试可随时切换）：

  ① 进程内覆盖（``set_semantic_rules_enabled``）—— 最高优先级；
  ② 环境变量 ``PROTORAG_SEMANTIC_RULES``：``1/true/yes/on``（大小写不敏感）
     ⇒ True；**其它一切（含未设置）⇒ False**；
  ③ 其它 ⇒ False（**默认关闭**）。

★ 进程内覆盖**不写全局环境变量**（避免污染其它进程/用例）；
  需要跨进程生效时由调用方自行设置环境变量（如 ``scripts/build_hub.py``）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from core.fused.semantic.semantic import EvidenceAnchor, SemanticRule

#: 语义规则参与生成的环境变量名。
ENV_KEY = "PROTORAG_SEMANTIC_RULES"

#: 多模型投票的环境变量名（**只占位**：投票本体尚未实现，见 §6 的「不应投入」）。
VOTING_ENV_KEY = "PROTORAG_VOTING"

#: 视为「开」的环境变量取值（比较前先 strip + 小写 ⇒ 大小写不敏感）。
_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})

#: 进程内覆盖（``None`` = 未覆盖 ⇒ 回落到环境变量判定）。
_semantic_rules_override: Optional[bool] = None
_voting_override: Optional[bool] = None


def _env_flag(key: str) -> bool:
    """读环境变量并判定布尔值。

    ★ **每次调用都重新读**（不在 import 时缓存成常量）⇒ 测试/CLI 可随时切换。

    Args:
        key: 环境变量名。

    Returns:
        取值属于 ``1/true/yes/on``（大小写不敏感）⇒ True；
        **其它一切（含未设置）⇒ False**。
    """
    raw = os.environ.get(key)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUE_VALUES


def semantic_rules_enabled() -> bool:
    """语义规则是否参与生成（**默认 False**）。

    Returns:
        True 当且仅当「进程内覆盖为 True」或「环境变量取真值」；
        **其它一切 ⇒ False**（含未设置 ⇒ 默认关闭）。
    """
    if _semantic_rules_override is not None:
        return _semantic_rules_override
    return _env_flag(ENV_KEY)


def set_semantic_rules_enabled(flag: Optional[bool]) -> None:
    """进程内显式覆盖开关状态（**不写全局环境变量**）。

    Args:
        flag: True/False = 强制开/关；``None`` = **清除覆盖**，
            回到「环境变量判定」。

    ★ 进程内状态只活在当前进程 ⇒ 不会污染其它进程或其它用例。
    """
    global _semantic_rules_override
    _semantic_rules_override = None if flag is None else bool(flag)


def reset_semantic_rules_enabled() -> None:
    """清除进程内覆盖 ⇒ 回到「环境变量判定」。"""
    set_semantic_rules_enabled(None)


def voting_enabled() -> bool:
    """多模型投票是否开启（**默认 False**，机制与语义规则开关相同）。

    ★ 投票本体（D-1~D-5）**尚未实现**（§6：在 B-10 实验判定「收益成立」
      之前不应投入）—— 本函数只**占住开关位与命名**。
    """
    if _voting_override is not None:
        return _voting_override
    return _env_flag(VOTING_ENV_KEY)


def set_voting_enabled(flag: Optional[bool]) -> None:
    """进程内显式覆盖投票开关（``None`` = 清除覆盖）。"""
    global _voting_override
    _voting_override = None if flag is None else bool(flag)


def reset_voting_enabled() -> None:
    """清除进程内投票开关覆盖 ⇒ 回到「环境变量判定」。"""
    set_voting_enabled(None)


# ═══════════════════════════════════════════════════════════════════════════
# D-1 / D-4 / D-7：投票候选包装层 + 对齐判据
#
# ★ **本段只落「判据」，不落「投票」** ——
#   投票本体（D-2 计票 / D-3 quorum / D-5 uncertain 队列）按
#   `docs/实施/路线与里程碑/RFC源里程碑路线图.md` §6 推迟到 B-10 判定「收益成立」之后。
#   这里先把**对齐判据**写死并测 ⇒ D 阶段一旦启动，对齐口径不再临时拍脑袋。
#
# ★ **θ 的来源（这是本段的实证依据）**：
#   SpecGPT（arXiv 2510.14348）实测一条转移被判定为「正确」的条件是
#     「initial / next state **精确匹配**」且「condition 与 action 的
#       **span 重叠 ≥ 75%**」
#   ⇒ 本仓 `docs/实施/路线与里程碑/RFC源知识抽取改造方案.md` §3.3 里那个 `theta=0.75`
#     **与 SpecGPT 的实测阈值数值一致** —— 两边独立得出同一个数
#     ⇒ θ 不再是拍脑袋的常数，而是**有外部实证支撑**的参数。
# ═══════════════════════════════════════════════════════════════════════════

#: span 重叠**辅助阈值**（θ）。★ 语义见 `align_by_structural_equality` 的 docstring。
DEFAULT_THETA = 0.75


@dataclass(frozen=True)
class Candidate:
    """投票候选 = 规则 + 本次生成的**运行时身份**。

    ★ 模型身份 / run_id 属于**运行时信息**，**不属于规范规则本身**
      ⇒ 不放进 `SemanticRule`（否则同一个规则会因为「哪个模型抽的」而有两个 id
      ⇒ `rule_id` 的稳定性契约就破了）。
    """

    rule: SemanticRule
    model_id: str
    run_id: str


@dataclass(frozen=True)
class Alignment:
    """一次对齐判定的结果（可观测 ⇒ 投票的分歧明细能直接引用）。"""

    aligned: bool
    overlap: float
    reason: str


def rule_content_identity(rule: SemanticRule) -> tuple:
    """规则的**内容身份**（主判据的一半）。

    逐项比对：主体类型 / 主体名 / 算子 / 操作数 / 操作数来源 / 操作数引用 /
    期望行为 / 适用状态 / 适用方法。

    ★ **不含**证据位置（`span_*`）—— 证据位置由 `evidence_overlap` 单独比，
      理由见 `align_by_structural_equality`。
    """
    c = rule.constraint
    if c is None:
        # 不可转换的规则没有可执行内容 ⇒ 内容身份只由主体决定
        return (rule.subject_type, rule.subject_name)
    return (
        rule.subject_type,
        rule.subject_name,
        c.target_field,
        c.operator,
        tuple(c.operand),
        c.operand_source,
        c.operand_ref,
        c.expected_behavior,
        tuple(c.applies_to_state),
        tuple(c.applies_to_method),
    )


def _source_file(anchor: str) -> str:
    """从 `source_anchor`（形如 `file:rfc3261.txt#@10560`）取出文件部分。"""
    return (anchor or "").split("#", 1)[0]


def _longest_common_substring(a: str, b: str) -> int:
    """两个字符串的最长公共子串长度（O(len(a)·len(b)) 动态规划，够用）。"""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


def evidence_overlap(a: EvidenceAnchor, b: EvidenceAnchor) -> float:
    """两条证据的**重叠率**（辅助量，取值 [0, 1]）。

    口径 = **包含率** = 交集长度 / **较短者**长度
    （对证据 span 而言，「b 完全落在 a 里」就说明二者指向同一段文本）。

    ★ **是包含率、不是 Jaccard** —— 差别是实质性的：
      - ``a=[100,200)``, ``b=[150,200)``（b 完全落在 a 内）⇒ **1.0**
        （Jaccard 会给 0.5）
      - ``a=[100,200)``, ``b=[150,250)``（各伸出一半）⇒ 0.5
      - ``a=[100,200)``, ``b=[110,210)`` ⇒ 0.9
      ⇒ 判据要回答的是「二者是不是**指着同一段文本**」，不是「两个集合有多像」。

    - 同一源文件且两侧都有字符区间 ⇒ 用**字符区间**算（精确）
    - 否则 ⇒ 退回**文本**的最长公共子串 / 较短文本长度（近似）

    ★ **只作辅助**：它**永远不能**单独把两条规则判为对齐（见
      `align_by_structural_equality`）。
    """
    same_file = _source_file(a.source_anchor) == _source_file(b.source_anchor)
    if (same_file and a.span_start is not None and a.span_end is not None
            and b.span_start is not None and b.span_end is not None):
        lo = max(a.span_start, b.span_start)
        hi = min(a.span_end, b.span_end)
        inter = max(0, hi - lo)
        shorter = min(a.span_end - a.span_start, b.span_end - b.span_start)
        return (inter / shorter) if shorter > 0 else 0.0
    ta, tb = a.span_text or "", b.span_text or ""
    shorter = min(len(ta), len(tb))
    if shorter <= 0:
        return 0.0
    return _longest_common_substring(ta, tb) / shorter


def align_by_structural_equality(
    a: SemanticRule,
    b: SemanticRule,
    theta: float = DEFAULT_THETA,
) -> Alignment:
    """两条语义规则**是否对齐**（D-4 主判据 + D-7 θ 语义）。

    ── 判定结构（两层，顺序不可调换）──────────────────────────────
      ① **主判据：内容身份全等** —— `rule_content_identity(a) == rule_content_identity(b)`
         （主体类型/主体名/目标字段/算子/操作数/操作数来源/操作数引用/
           期望行为/适用状态/适用方法）
      ② **辅助条件：证据重叠 ≥ θ**（默认 0.75）—— 证据位置**不要求字符串相等**
         （不同模型会摘到同一句话的不同片段），改用**重叠率**比较。

    ★ **span 重叠永远不能单独造成对齐**：内容身份不同的两条规则，
      **哪怕证据重叠 0.9，也判为不对齐**（评审 T1 第三点）。
      ⇒ 反过来，θ 也不是「越低越好」：θ=0 会让证据位置**完全退出判定**。

    ── θ 的确切语义（D-7 清理审计项 I-7）───────────────────────────
      θ = 「**证据 span 重叠的辅助阈值**」，**主判据始终是结构化全等**。
      θ 的作用范围只有一个：**当两条规则的内容全等、但证据摘录位置不同时**，
      决定「它们是否算同一条规则的不同证据」。
      - θ = 0.75（默认，SpecGPT 实测值）⇒ 要求两者证据高度重叠
      - θ = 0 ⇒ 证据位置**完全不参与**判定（只比内容）
      - θ = 1 ⇒ 要求证据**几乎完全重合**（近乎同一片段）

    ── ★ 已知且**刻意保留**的非传递性 ─────────────────────────────
      对齐是**成对判定**，**不是传递闭包**：
      内容全等时，可能出现 overlap(A,B) ≥ θ 且 overlap(B,C) ≥ θ，
      但 overlap(A,C) < θ ⇒ align(A,C) 为假。
      ⇒ **投票实现不得依赖对齐关系的传递闭包**（那会把互相矛盾的证据并成一组
        —— 评审 T1 第三点指出的正是这个坑）。
      本模块**刻意不做**传递闭包，故此性质是**被测试钉住的已知行为**，不是潜在 bug。
    """
    if rule_content_identity(a) != rule_content_identity(b):
        return Alignment(False, 0.0, "content_mismatch")
    overlap = evidence_overlap(a.evidence, b.evidence)
    if overlap + 1e-9 < theta:
        return Alignment(False, overlap, f"evidence_overlap_below_theta({overlap:.3f}<{theta})")
    return Alignment(True, overlap, "aligned")


__all__ = [
    "ENV_KEY",
    "VOTING_ENV_KEY",
    "semantic_rules_enabled",
    "set_semantic_rules_enabled",
    "reset_semantic_rules_enabled",
    "voting_enabled",
    "set_voting_enabled",
    "reset_voting_enabled",
    "DEFAULT_THETA",
    "Candidate",
    "Alignment",
    "rule_content_identity",
    "evidence_overlap",
    "align_by_structural_equality",
]

