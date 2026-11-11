# -*- coding: utf-8 -*-
"""seedcheck/v3_env.py —— **V3 环境适配**（资源是否在目标环境可用）。

★ 处置：**只打标，不阻断**
  「URI 指向不存在的资源」⇒ 服务端返 404 ⇒ 可能触发**错误处理缺陷**
  ⇒ 属于有价值的输入面 ⇒ 只标注，不丢。

★ 判据来源
  · 指定了 ``--target-env`` ⇒ 用该环境的**可播子集**（``playable_resources_file``）
  · 未指定 ⇒ 用协议档案的**资源清单**（``resources_file``，源码级全集）
  · 两者都没有 ⇒ 跳过（无判据 ⇒ 不产生误报）
"""
from __future__ import annotations


from .knowledge import Knowledge
from .model import SeedRecord, Violation


def _resource_of(uri: str) -> str:
    """从 URI 里取资源名（末段，去掉 ``/trackN`` 之类）。

    ``rtsp://127.0.0.1:8554/mp3AudioTest/track1`` ⇒ ``mp3AudioTest``
    """
    if not uri:
        return ""
    path = uri.split("://", 1)[-1]
    path = path.split("/", 1)[1] if "/" in path else ""
    segs = [s for s in path.split("/") if s]
    if not segs:
        return ""
    # ★ 2026-11-11 修正：末段若是 ``trackN`` ⇒ 资源名是**它前面那段**（流名）
    #   （``/mp3AudioTest/track1`` ⇒ ``mp3AudioTest`` ⇒ 不是 ``track1``）
    if len(segs) >= 2 and segs[-1].lower().startswith("track"):
        return segs[-2]
    return segs[0]


def check(seed: SeedRecord, k: Knowledge, target_env: str | None) -> list[Violation]:
    """V3 检查 ⇒ 违规列表（打标）。"""
    if not target_env:
        return []
    allowed = k.env_resources.get(target_env)
    if not allowed:
        # 该环境没声明可播子集 ⇒ 无判据 ⇒ 不判（避免误报）
        return []
    allowed_set = {str(a) for a in allowed}
    out: list[Violation] = []
    for i, m in enumerate(seed.messages, 1):
        res = _resource_of(m.get("uri", ""))
        if not res or res in allowed_set:
            continue
        out.append(Violation(
            "V3", "resource_unavailable",
            f"第 {i} 个报文指向资源 {res}，不在环境 {target_env} 的可播集内",
            seed.filename, res,
            f"environments.{target_env}.playable_resources_file"))
    return out
