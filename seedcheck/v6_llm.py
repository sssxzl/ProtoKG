# -*- coding: utf-8 -*-
"""seedcheck/v6_llm.py —— **V6 语义合理性**（LLM 审查，**只报告不阻断**）。

★ 为什么只报告
  LLM 判定**有抖动**（同输入可能不同输出）⇒ 若当硬闸 ⇒ 每天随机红 ⇒
  ⇒ 与 fail-closed 的初衷（防**静默退化**）背道而驰。
  ⇒ 本层的产出是**报告**（供人工看 / 论文分析 / 回归对比），**不进失败集合**。

★ 配置沿用 build_hub 的传参（用户 2026-11-11 定）
  ``--api-key/--model/--base-url`` 与 ``build_hub.py`` **完全同构**：
  显式参数 > 环境变量 ``LLM_API_KEY/LLM_MODEL/LLM_BASE_URL`` > 项目根 ``.env``。
  ⇒ 同一次 shell 会话里跑 build_hub 再跑 seedcheck ⇒ **无需重复配置**。

★ 审查什么
  「这条报文序列在协议语义上是否合理（非机械拼凑）」—— 例如：
  · 在未 SETUP 就 PLAY（语义倒置）
  · TEARDOWN 之后又 PLAY
  · 头值明显不合协议（如 CSeq 非数字）
  ⇒ 输出每条种子的判定 + 理由 + 分数。
"""
from __future__ import annotations

import json
import os
from typing import Any

from .knowledge import Knowledge
from .model import SeedRecord

#: 审查 prompt（要求**结构化 JSON 输出** ⇒ 便于机器消费）
PROMPT = """你是协议模糊测试的种子审查员。下面给出某协议的一条报文序列（fuzzing 初始种子）。
请判断它在**协议语义**上是否合理（即：一个正常客户端会不会这样发）。

协议：{protocol}
已知状态机边（from --method--> to）：{fsm}
已知必填头：{required}

报文序列：
{seed}

判定要点（逐条检查）：
1. 消息顺序是否违反状态机（如未 SETUP 就 PLAY、TEARDOWN 后继续）
2. 头是否缺失/多余/取值明显不合理
3. 序列是否像机械拼凑（如重复同一方法毫无变化）
4. 是否包含**故意**的协议违反（这类**不算错**，反而是 fuzzing 想要的面）

输出**严格 JSON**（不要任何额外文字）：
{{"reasonable": true/false, "score": 0-100, "issues": ["简短问题", ...], "note": "一句话说明"}}"""


def _resolve_llm_config(args: Any) -> dict[str, Any]:
    """解析 LLM 配置（与 build_hub 同构：显式参数 > LLM_* 环境变量 > .env）。"""
    def _env(name: str) -> str | None:
        v = os.environ.get(name)
        if v:
            return v
        # 项目根 .env
        env_file = os.environ.get("PROTOKG_ENV_FILE")
        path = env_file or ".env"
        try:
            for ln in open(path, encoding="utf-8"):
                ln = ln.strip()
                if not ln or ln.startswith("#") or "=" not in ln:
                    continue
                k, v = ln.split("=", 1)
                if k.strip() == name:
                    return v.strip()
        except OSError:
            pass
        return None

    key = getattr(args, "api_key", None) or _env("LLM_API_KEY")
    model = getattr(args, "model", None) or _env("LLM_MODEL") or "deepseek-chat"
    base = getattr(args, "base_url", None) or _env("LLM_BASE_URL")
    return {"api_key": key, "model": model, "base_url": base}


def _seed_text(seed: SeedRecord) -> str:
    lines: list[str] = []
    for m in seed.messages:
        hs = "\n".join(f"{k}: {v}" for k, v in (m.get("headers") or {}).items())
        lines.append(f"{m.get('method','')} {m.get('uri','')} {m.get('version','')}\n{hs}".rstrip())
    return "\n\n".join(lines)


def review(seeds: list[SeedRecord], k: Knowledge, args: Any) -> dict[str, Any]:
    """跑 LLM 审查 ⇒ 返回摘要 dict（**不抛异常、不阻断**）。"""
    cfg = _resolve_llm_config(args)
    if not cfg.get("api_key"):
        return {"status": "skipped", "reason": "无 LLM 凭据（未设 LLM_API_KEY / --api-key）"}
    try:
        from core.llm import DeepSeekClient
    except ImportError as exc:
        return {"status": "error", "reason": f"core.llm 不可用：{exc}"}

    client = DeepSeekClient(api_key=cfg.get("api_key"),
                            model=cfg.get("model"),
                            base_url=cfg.get("base_url"))
    fsm = sorted(k.fsm_edges)[:40]
    req = k.required_headers

    results: list[dict[str, Any]] = []
    unreasonable = 0
    for s in seeds:
        prompt = PROMPT.format(
            protocol=k.protocol,
            fsm="; ".join(f"{a} --{b}--> {c}" for a, b, c in fsm) or "(无)",
            required=json.dumps(req, ensure_ascii=False)[:800],
            seed=_seed_text(s))
        try:
            out = client.chat_json([{"role": "user", "content": prompt}])
        except Exception as exc:                       # noqa: BLE001
            results.append({"seed": s.filename, "error": f"{type(exc).__name__}: {exc}"})
            continue
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except json.JSONDecodeError:
                out = {"raw": out[:200]}
        if not out.get("reasonable", True):
            unreasonable += 1
        results.append({"seed": s.filename, **out})
    return {
        "status": "ok",
        "model": cfg.get("model"),
        "base_url": cfg.get("base_url"),
        "seed_count": len(seeds),
        "unreasonable_count": unreasonable,
        "unreasonable_rate": round(unreasonable / len(seeds), 4) if seeds else 0.0,
        "results": results,
        "note": "★ 只报告不阻断（LLM 判定有抖动 ⇒ 不进失败集合）",
    }
