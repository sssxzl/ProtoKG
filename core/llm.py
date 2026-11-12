"""ProtoKG LLM 客户端(异化实现)。

模块分层:
  - LLMClient:         Protocol 接口(内联在本模块, v1 退役后从 interfaces.py 移入)
  - StubLLMClient:     测试用,返回固定响应
  - DeepSeekClient:    DeepSeek API(主用,M3 阶段实现)
  - FixtureStubLLM:   strict fixture replay（v2.1.1，fixture 缺失即抛错）

本模块只负责 LLM 传输层（chat_json / chat_text / key 管理），不含 prompt 模板；prompt 模板见 core/fused/downstream/rag_seedgen.py 与 strategy.py。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

log = logging.getLogger("protorag.llm")


@runtime_checkable
class LLMClient(Protocol):
    """LLM 客户端接口（内联，原在 interfaces.py，v1 退役后移入）。"""

    def chat_json(self, *, system: str, user: str,
                  temperature: float = 0.2,
                  max_tokens: int = 4000) -> dict | list:
        """调 LLM, 要求返回 JSON（自动 parse）。

        返回类型说明：声明为 dict | list 仅为兼容 StubLLMClient（测试可返回任意
        固定响应）；真实实现 DeepSeekClient 因 response_format=json_object 只返回
        dict。故所有生产 prompt 必须要求 LLM 输出 JSON object（不要输出纯数组）。
        """
        ...

    def chat_text(self, *, system: str, user: str,
                  temperature: float = 0.2,
                  max_tokens: int = 4000) -> str:
        """调 LLM, 返回纯文本（不强制 JSON）。"""
        ...


# ============================================================================
# ⚠️ API key 安全（2026-10-21 整改）
#   - 原硬编码 key 已迁移到项目根 .env（已在 .gitignore 中，不进 git）
#   - 读取优先级：构造参数 api_key > 环境变量 DEEPSEEK_API_KEY > .env 文件
#   - 若三处都无 key，DeepSeekClient 实例化时抛 ValueError（提示配置）
#   - key 泄露后请去 https://platform.deepseek.com 重新生成
# ============================================================================
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

#: ★ **通用** LLM 配置的环境变量名（**OpenAI 兼容协议** ⇒ 换厂商只改这三个）
#:   · ``LLM_API_KEY``   —— 凭据
#:   · ``LLM_BASE_URL``  —— endpoint（DeepSeek / OpenAI / ollama / vLLM …）
#:   · ``LLM_MODEL``     —— 模型名
#:   读取优先级：**构造参数 > ``LLM_*`` > ``DEEPSEEK_*``（兼容别名）> ``.env``**
#:   ⇒ ``DEEPSEEK_*`` 仅作**向后兼容**，新代码一律用 ``LLM_*``。


# ============================================================================
# FixtureStubLLM — strict fixture replay (v2.1.1)
# ============================================================================
# dispatcher 默认 llm=None 时实际等于 heuristic (RFCNormExtractor 不调 LLM).
# v2.1.1: dispatcher 默认 llm = FixtureStubLLM() → strict fixture replay,
#   fixture 命中返 response, 缺 fixture 抛 LLMFixtureMissingError (避免假绿).
# ============================================================================

class LLMFixtureMissingError(AssertionError):
    """fixture 缺失 — strict 模式应该 fail, 不应该 skip."""
    pass


# fixture 目录。★ 该目录当前**不存在**（仓库中无 tests/integration/ 或 tests/fixtures/），
# 且 FixtureStubLLM 目前无生产调用方 —— 保留常量仅为接口预留。
# 启用前需先补齐 fixture 文件，或改指向实际目录。
_FIXTURE_REPLAY_DIR = Path(__file__).resolve().parents[1] / "tests" / "integration" / "_fixtures" / "llm_replay"


class FixtureStubLLM:
    """strict fixture replay stub. 永不调真 LLM.

    用法:
        llm = FixtureStubLLM()  # 默认 protocol=rtsp, step=rfc_extract
        r = llm.chat_json(system=..., user=..., temperature=0.1, max_tokens=4000)

    fixture 文件命名: <protocol>_<step>_<prompt_hash8>.json
    fixture 目录: tests/fixtures/llm_replay/

    缺 fixture 抛 LLMFixtureMissingError (strict).
    """

    def __init__(self, protocol: str = "rtsp", step: str = "rfc_extract",
                 fixture_dir: Optional[Path] = None):
        self.protocol = protocol
        self.step = step
        self.fixture_dir = fixture_dir or _FIXTURE_REPLAY_DIR

    def chat_json(self, *, system: str, user: str,
                  temperature: float = 0.1, max_tokens: int = 4000):
        import hashlib
        prompt_str = system + user
        prompt_hash = hashlib.sha256(prompt_str.encode("utf-8")).hexdigest()[:8]
        fixture_path = self.fixture_dir / f"{self.protocol}_{self.step}_{prompt_hash}.json"
        if not fixture_path.exists():
            raise LLMFixtureMissingError(
                f"LLM fixture missing: {fixture_path}. "
                f"prompt_hash={prompt_hash} protocol={self.protocol} step={self.step}. "
                f"需先跑 scripts/record_llm_fixtures.py 录 fixture."
            )
        try:
            return json.loads(fixture_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise LLMFixtureMissingError(
                f"LLM fixture 损坏: {fixture_path.name}: {e}"
            )


def _load_env_file(path: Optional[Path] = None) -> dict:
    """轻量 .env 解析(避免引入 python-dotenv 依赖)。

    Args:
        path: 自定义路径,默认从项目根(本文件的 3 层父目录)/.env 读
    Returns:
        dict 形式的 env 变量
    """
    if path is None:
        # core/llm.py → core/ → <project_root>/
        path = Path(__file__).resolve().parents[1] / ".env"
    if not path.exists():
        return {}
    out: dict = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            # 去掉引号
            if (v.startswith('"') and v.endswith('"')) or \
               (v.startswith("'") and v.endswith("'")):
                v = v[1:-1]
            out[k] = v
    except Exception as e:
        log.warning("[llm] failed to load .env from %s: %s", path, e)
    return out


# ============================================================================
# Stub LLM(测试 / dry-run 用)
# ============================================================================

class StubLLMClient:
    """不调真 LLM,返回固定响应。用于测试和 dry-run。"""

    def __init__(self, response: object = None):
        self._response = response or []
        self.calls: list[dict] = []  # 记录所有调用(便于测试)
        # 兼容 DeepSeekClient.last_call_meta 接口(供下游统计用)
        self.last_call_meta: dict = {}

    def chat_json(self, *, system: str, user: str,
                  temperature: float = 0.2,
                  max_tokens: int = 4000):
        self.calls.append({"system": system, "user": user,
                           "temperature": temperature, "max_tokens": max_tokens})
        return self._response

    def chat_text(self, *, system: str, user: str,
                  temperature: float = 0.2,
                  max_tokens: int = 4000) -> str:
        self.calls.append({"system": system, "user": user,
                           "temperature": temperature, "max_tokens": max_tokens})
        if isinstance(self._response, (list, dict)):
            return json.dumps(self._response, ensure_ascii=False)
        return str(self._response)


# ============================================================================
# DeepSeek 客户端(主用,M3 阶段实现)
# ============================================================================

class DeepSeekClient:
    """DeepSeek API 客户端(OpenAI 兼容协议)。

    读取 key 顺序(后者覆盖前者):
      1. 构造参数 api_key
      2. 环境变量 ``LLM_API_KEY``（通用）⇒ ``DEEPSEEK_API_KEY``（兼容别名）
      3. 项目根 .env 文件中的同名变量

    ★ **OpenAI 兼容协议** ⇒ 换厂商/模型只改三个变量即可：
      ``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL``

    .env 格式:
      LLM_API_KEY=sk-xxxx
      LLM_BASE_URL=https://api.deepseek.com
      LLM_MODEL=deepseek-chat
    """

    def __init__(self, api_key: Optional[str] = None,
                 base_url: Optional[str] = None,
                 model: Optional[str] = None,
                 timeout: float = 60.0,
                 env_file: Optional[Path] = None):
        # 读取 key 优先级: 构造参数 > 环境变量 > .env 文件
        self.api_key = (
            api_key
            or os.getenv("LLM_API_KEY")
            or os.getenv("DEEPSEEK_API_KEY")
            or _load_env_file(env_file).get("LLM_API_KEY")
            or _load_env_file(env_file).get("DEEPSEEK_API_KEY")
        )
        if not self.api_key:
            raise ValueError(
                "DEEPSEEK_API_KEY not set. "
                "Set env var DEEPSEEK_API_KEY, write to .env (see .env.example), "
                "or pass api_key explicitly."
            )
        # base_url + model (同样的优先级, fallback 到顶部硬编码常量)
        self.base_url = (
            base_url
            or os.getenv("LLM_BASE_URL")
            or os.getenv("DEEPSEEK_BASE_URL")
            or _load_env_file(env_file).get("LLM_BASE_URL")
            or _load_env_file(env_file).get("DEEPSEEK_BASE_URL")
            or DEEPSEEK_BASE_URL
        )
        self.model = (
            model
            or os.getenv("LLM_MODEL")
            or os.getenv("DEEPSEEK_MODEL")
            or _load_env_file(env_file).get("LLM_MODEL")
            or _load_env_file(env_file).get("DEEPSEEK_MODEL")
            or DEEPSEEK_MODEL
        )
        self.timeout = timeout
        # 每次 chat_json() 调用后填充,供调用方累计统计用
        # key: status(int) / elapsed_s(float) / input_tokens(int) / output_tokens(int) / response_chars(int)
        self.last_call_meta: dict = {}

    def _post(self, payload: dict) -> dict:
        """POST to /v1/chat/completions。"""
        import urllib.request
        import urllib.error
        url = f"{self.base_url}/v1/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"DeepSeek API error {e.code}: {e.read().decode('utf-8')}"
            )
        except urllib.error.URLError as e:
            raise RuntimeError(f"DeepSeek API unreachable: {e}")

    def _post_with_status(self, payload: dict) -> tuple[int, dict]:
        """同 _post,但额外返回 HTTP status code。"""
        import urllib.request
        import urllib.error
        url = f"{self.base_url}/v1/chat/completions"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=body, method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(
                f"DeepSeek API error {e.code}: {e.read().decode('utf-8')}"
            )
        except urllib.error.URLError as e:
            raise RuntimeError(f"DeepSeek API unreachable: {e}")

    def chat_json(self, *, system: str, user: str,
                  temperature: float = 0.2,
                  max_tokens: int = 4000):
        """调 LLM,自动 parse JSON(优先 response_format=json_object)。

        ★★ **推理模型（reasoning）的 max_tokens 陷阱**（2026-11-12 实测）：
        deepseek-**flash** 是**推理模型** ⇒ 它的 ``reasoning_tokens`` 会**先**
        吃掉 ``max_tokens`` ⇒ 若给 4000 ⇒ 实测 ``finish_reason="length"`` 且
        **正式输出为空字符串** ⇒ ⇒ JSON 解析必然失败（``Expecting value: line 1
        column 1``）⇒ 看起来像「LLM 没返回」。
        ⇒ ★ 用**推理模型**时 ``max_tokens`` 必须**留足推理空间**
        （实测 16000 才正常：30s/次、产出带 span 的条目）。
        ⇒ 非推理模型（``deepseek-chat``）用 2000~4000 正常 ⇒ **既有通道不受影响**。

        详细日志(每次调用打 4-5 行):
          [LLM]   → POST <url>
          [LLM]     model=..., max_tokens=..., T=...
          [LLM]     payload: N chars (system X + user Y)
          [LLM]     ... waiting ...
          [LLM]   ← 200 OK in 6.42s | resp N chars | tokens X in / Y out
        """
        import time
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        # 1. 准备阶段(发请求前)
        sys_chars = len(system)
        user_chars = len(user)
        url = f"{self.base_url}/v1/chat/completions"
        log.info("[LLM]   → POST %s", url)
        log.info("[LLM]     model=%s, max_tokens=%d, T=%.2f",
                 self.model, max_tokens, temperature)
        log.info("[LLM]     payload: %d chars (system %d + user %d)",
                 sys_chars + user_chars, sys_chars, user_chars)
        log.info("[LLM]     ... waiting ...")

        # 2. 发请求 + 计时
        t0 = time.time()
        try:
            status, resp_dict = self._post_with_status(payload)
        except Exception as e:
            elapsed = time.time() - t0
            log.warning("[LLM]   ✗ FAILED in %.2fs: %s", elapsed, e)
            raise
        elapsed = time.time() - t0

        # 3. 响应回包 + usage
        text = resp_dict["choices"][0]["message"]["content"]
        usage = resp_dict.get("usage", {}) or {}
        in_tok = usage.get("prompt_tokens", 0) or 0
        out_tok = usage.get("completion_tokens", 0) or 0
        log.info("[LLM]   ← %d in %.2fs | resp %d chars | tokens %d in / %d out",
                 status, elapsed, len(text), in_tok, out_tok)

        # 4. 填充 last_call_meta(供调用方累计)
        self.last_call_meta = {
            "status": status,
            "elapsed_s": elapsed,
            "input_tokens": in_tok,
            "output_tokens": out_tok,
            "response_chars": len(text),
        }
        return _safe_json_parse(text)

    def chat_text(self, *, system: str, user: str,
                  temperature: float = 0.2,
                  max_tokens: int = 4000) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        resp = self._post(payload)
        return resp["choices"][0]["message"]["content"]


def _safe_json_parse(text: str):
    """从 LLM 输出里抠 JSON(可能被 markdown 包裹)。"""
    text = text.strip()
    # 去除 markdown 包裹
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 尝试找第一个 { 或 [ 开始的位置
        for i, c in enumerate(text):
            if c in "{[":
                try:
                    return json.loads(text[i:])
                except json.JSONDecodeError:
                    continue
        raise


# 验证接口
assert isinstance(StubLLMClient(), LLMClient)
# DeepSeekClient 在调用时才检查 api_key(不实例化时不算)


__all__ = [
    "LLMClient",
    "StubLLMClient",
    "DeepSeekClient",
]
