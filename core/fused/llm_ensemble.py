"""core/fused/llm_ensemble.py —— 多模型投票（默认关闭）。

★ 当前只落地 D-6 的**开关位**：语义规则是否参与生成。
  投票本体（D-1~D-5、D-7）属于 D 阶段其余任务，**在 B-10 实验判定
  「收益成立」之前不应投入**（见 docs/rfc_source_bcd_roadmap.md §6）。

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
from typing import Optional

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


__all__ = [
    "ENV_KEY",
    "VOTING_ENV_KEY",
    "semantic_rules_enabled",
    "set_semantic_rules_enabled",
    "reset_semantic_rules_enabled",
    "voting_enabled",
    "set_voting_enabled",
    "reset_voting_enabled",
]
