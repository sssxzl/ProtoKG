# -*- coding: utf-8 -*-
"""ChatAFL LLM 转发代理：把虚拟机 ChatAFL 的请求转发到 DeepSeek，绕过其 libcurl 毛病。

监听 192.168.37.1:18080（VMnet8，虚拟机可达），收到 POST 后原样转发到 DeepSeek
（用本机成熟的 urllib + 超时 + 重试），回传响应。在响应回传前插入「响应改写层」：
根据请求路径（增强/stall/语法抽取）对散文回答做条件剥离，只保留纯 RTSP/FTP 报文
（按请求内嵌的协议报文特征自动选择抽取器），避免 deepseek-chat 的聊天风格散文
污染 fuzzing 语料。

用法:
    python llm_proxy.py
    # 或自定义（均可选）：
    LLM_PROXY_HOST=192.168.37.1 LLM_PROXY_PORT=18080 \
    LLM_PROXY_MODEL=deepseek-chat LLM_PROXY_REWRITE=1 \
    python llm_proxy.py
"""
import json
import logging
import os
import sys
import time
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# 保证无论从哪个目录启动，都能 import 到同目录的 response_rewriter.py。
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from response_rewriter import (  # noqa: E402
    ACTION_REWRITTEN, ACTION_EMPTIED, rewrite_response,
    classify_request, extract_user_text, ENRICH,
)

# ---------------------------------------------------------------------------
# 可配置项（环境变量优先，默认值保持与原有行为一致）
# ---------------------------------------------------------------------------
# ★ 安全整改（2026-11-01）：API key **不再硬编码**在源码里。
#   原来的兜底默认值是真实密钥，会随版本库分发 ⇒ 泄露风险。
#   现在的取值优先级：
#     ① 环境变量 LLM_PROXY_DEEPSEEK_KEY
#     ② 环境变量 DEEPSEEK_API_KEY
#     ③ 项目根 .env 里的 DEEPSEEK_API_KEY（复用 core.llm 的轻量解析器）
#   ④ 都没有 → 启动即报错（**不静默用空 key 去请求**）
_ENV_FILE = {}
try:                                    # 复用 core.llm 的 .env 解析（无额外依赖）
    from core.llm import _load_env_file as _load_env_file  # type: ignore
    _ENV_FILE = _load_env_file()
except Exception:                       # core 不可用时静默降级为「仅环境变量」
    _ENV_FILE = {}

DEEPSEEK_URL = os.environ.get(
    "LLM_PROXY_DEEPSEEK_URL", "https://api.deepseek.com/v1/chat/completions")
DEEPSEEK_KEY = (
    os.environ.get("LLM_PROXY_DEEPSEEK_KEY")
    or os.environ.get("DEEPSEEK_API_KEY")
    or str(_ENV_FILE.get("DEEPSEEK_API_KEY") or "")
    or ""
)
if not DEEPSEEK_KEY:
    raise SystemExit(
        "缺少 DeepSeek API key。请设置环境变量 LLM_PROXY_DEEPSEEK_KEY 或 "
        "DEEPSEEK_API_KEY，或在项目根 .env 里写 DEEPSEEK_API_KEY=... "
        "（参考 .env.example）。"
    )
LISTEN_HOST = os.environ.get("LLM_PROXY_HOST", "192.168.37.1")
LISTEN_PORT = int(os.environ.get("LLM_PROXY_PORT", "18080"))

# deepseek-flash / deepseek-v4-pro 是 reasoning 模型，会把 token 全耗在
# reasoning_content 上导致 content 为空（ChatAFL 只读 content）。这里强制改写为
# 非 reasoning 的 deepseek-chat，保证 content 字段有最终答案。
# 设为空字符串可关闭 model 覆盖。
MODEL_OVERRIDE = os.environ.get("LLM_PROXY_MODEL", "deepseek-chat")

# 响应改写开关：1/true/yes/on 开启（默认），0/false/no/off 关闭。
REWRITE_ENABLED = os.environ.get(
    "LLM_PROXY_REWRITE", "1").strip().lower() not in ("0", "false", "no", "off")

# 转发超时与重试：对 429 / 5xx / 网络异常做有限次重试（线性退避）。
TIMEOUT = int(os.environ.get("LLM_PROXY_TIMEOUT", "180"))
MAX_RETRIES = int(os.environ.get("LLM_PROXY_RETRIES", "2"))
RETRY_BACKOFF = float(os.environ.get("LLM_PROXY_RETRY_BACKOFF", "2.0"))
RETRYABLE_STATUS = (429, 500, 502, 503, 504)

log = logging.getLogger("llm-proxy")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def _unescape_sequence_text(text: str) -> str:
    """还原 ChatAFL 对协议报文的 JSON 转义（发给 DeepSeek 前）。

    ChatAFL 用 json-c 的 json_object_to_json_string 转义 sequence，其中 ``/`` 会被
    转义成 ``\\/``。DeepSeek 看到 ``SIP\\/2.0`` 这种带反斜杠斜杠的畸形报文会退回
    「分析」而非直接输出修改后的序列（实测 SIP：带 ``\\/`` 时 0 条 SIP 报文、纯散文；
    还原成 ``/`` 后直接输出 8 条 SIP）。

    ★ 只还原斜杠转义，不动 ``\\r\\n``/``\\n``：语法抽取 prompt 的模板示例里
    ``<<VALUE>>\\r\\n`` 是**字面量**（示意模板用 CRLF），若还原成真实换行会破坏示例
    格式，导致 extract_message_grammars 解析出非数组元素而崩溃（实测）。
    """
    if not isinstance(text, str) or not text:
        return text
    return text.replace("\\/", "/")


def _unescape_user_messages(req_obj) -> None:
    """就地还原请求体里 role=user 消息 content 的 JSON 转义（仅字符串 content）。"""
    messages = req_obj.get("messages") if isinstance(req_obj, dict) else None
    if not isinstance(messages, list):
        return
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = _unescape_sequence_text(content)


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _forward(self, body: bytes):
        """转发到 DeepSeek，返回 (data: bytes, status: int)。失败重试 + 502 兜底。"""
        last_data = json.dumps({"error": {"message": "proxy forward failed"}}).encode()
        last_status = 502
        for attempt in range(MAX_RETRIES + 1):
            req = urllib.request.Request(
                DEEPSEEK_URL, data=body, method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + DEEPSEEK_KEY,
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    return resp.read(), resp.status
            except urllib.error.HTTPError as e:
                data = e.read()
                status = e.code
                last_data = data
                last_status = status
                if status in RETRYABLE_STATUS and attempt < MAX_RETRIES:
                    delay = RETRY_BACKOFF * (attempt + 1)
                    log.warning("DeepSeek HTTP %d，%.1fs 后重试 (%d/%d)",
                                status, delay, attempt + 1, MAX_RETRIES)
                    time.sleep(delay)
                    continue
                return data, status
            except Exception as e:  # noqa: BLE001
                last_data = json.dumps({"error": {"message": str(e)}}).encode()
                last_status = 502
                if attempt < MAX_RETRIES:
                    delay = RETRY_BACKOFF * (attempt + 1)
                    log.warning("DeepSeek 请求异常 %s，%.1fs 后重试 (%d/%d)",
                                e, delay, attempt + 1, MAX_RETRIES)
                    time.sleep(delay)
                    continue
                return last_data, 502
        return last_data, last_status

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        body = self.rfile.read(length)

        # 请求体解析（供改写层判路径；失败则 req_obj=None → 改写层透传）
        req_obj = None
        try:
            parsed = json.loads(body)
            if isinstance(parsed, dict):
                req_obj = parsed
        except (ValueError, TypeError):
            pass

        # 还原 ChatAFL 对协议报文的 JSON 转义（\/、\r\n 等），让 DeepSeek 看到干净报文
        if req_obj is not None:
            _unescape_user_messages(req_obj)

        # 改写 model 字段，避免 reasoning 模型把 token 耗在 reasoning_content 上
        if MODEL_OVERRIDE and req_obj is not None and "model" in req_obj:
            req_obj["model"] = MODEL_OVERRIDE
            body = json.dumps(req_obj).encode()

        # 转发给 DeepSeek（本机稳定的 urllib + 超时 + 重试）
        data, status = self._forward(body)

        # 响应改写层：仅对 200 成功响应、且能解析出请求路径时执行
        if REWRITE_ENABLED and status == 200 and req_obj is not None:
            # DEBUG: 记录 enrich 请求的 user content 到 /tmp/enrich_debug.log（诊断用）
            if os.environ.get("LLM_PROXY_DEBUG_ENRICH") == "1" \
                    and classify_request(req_obj) == ENRICH:
                try:
                    with open("enrich_debug.log", "a", encoding="utf-8") as _df:
                        _df.write("===== ENRICH REQUEST =====\n")
                        _df.write(extract_user_text(req_obj))
                        _df.write("\n===== END =====\n")
                except OSError:
                    pass
            result = rewrite_response(req_obj, data)
            data = result.body
            if result.action == ACTION_REWRITTEN:
                log.info("改写[%s] 成功: %d -> %d 字节",
                         result.path, len(result.original_content.encode("utf-8")),
                         len(result.rewritten_content.encode("utf-8")))
            elif result.action == ACTION_EMPTIED:
                log.warning("改写[%s] 丢弃(无合法报文): %.200r",
                            result.path, result.original_content)
            else:
                log.info("改写[%s] 跳过: %s", result.path, result.note)

        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        log.info("POST -> %d  (%d bytes body, %d bytes resp)",
                 status, len(body), len(data))

    def log_message(self, *args):
        pass  # 静默默认访问日志


if __name__ == "__main__":
    srv = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    log.info("LLM 转发代理已启动: http://%s:%d -> %s (改写=%s)",
             LISTEN_HOST, LISTEN_PORT, DEEPSEEK_URL,
             "ON" if REWRITE_ENABLED else "OFF")
    srv.serve_forever()
