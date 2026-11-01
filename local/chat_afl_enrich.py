# -*- coding: utf-8 -*-
"""手动重建 ChatAFL 的 LLM 种子增强流程（忠实复用其 prompt 模板与逻辑）。

绕过 afl-fuzz C 代码的 json-c 解析 bug，直接用 DeepSeek 走代理复现：
1. 语法提取：5 次迭代 x(templates + remaining) 两次调用，提取消息类型全集
2. 种子增强：对每条种子识别缺失消息类型，C(n,2) 子集逐个调 LLM 生成增强序列
3. 落盘非空增强种子，统计 Time/Tokens/种子数

用法: python chat_afl_enrich.py <target> <proto> <seed_dir> <dict_path> <out_dir>
  proto: FTP / SMTP / SIP
"""
import json
import re
import sys
import time
import urllib.request
import urllib.error
from itertools import combinations
from pathlib import Path

PROXY = "http://192.168.37.1:18080/chat/completions"
MODEL = "deepseek-chat"
MAX_TOKENS = 2048
TEMPERATURE = 0.5
RETRIES = 5
TEMPLATE_CONSISTENCY_COUNT = 5   # ChatAFL 的 TEMPLATE_CONSISTENCY_COUNT
MAX_ENRICHMENT_MESSAGE_TYPES = 2 # 每次补 2 个缺失类型
MAX_ENRICHMENT_CORPUS_SIZE = 10  # 缺失类型最多 10 个

# 累积 token 统计
token_stats = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}


def call_llm(messages, temperature=TEMPERATURE):
    """调用 DeepSeek（走代理），返回 content；失败重试。"""
    body = {
        "model": MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "temperature": temperature,
    }
    req = urllib.request.Request(
        PROXY, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    last_err = None
    for _ in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.load(r)
            if "error" in d:
                last_err = d["error"].get("message", "unknown")
                continue
            usage = d.get("usage", {})
            token_stats["prompt_tokens"] += usage.get("prompt_tokens", 0)
            token_stats["completion_tokens"] += usage.get("completion_tokens", 0)
            token_stats["calls"] += 1
            msg = d["choices"][0]["message"]
            content = msg.get("content", "")
            if content:
                return content
            last_err = "empty content"
        except (urllib.error.HTTPError, urllib.error.URLError, Exception) as e:
            last_err = str(e)
            time.sleep(1)
    return None


def build_templates_prompt(proto):
    """重建 construct_prompt_for_templates 的 msg（含 RTSP/HTTP 示例 + 纯格式约束）。"""
    return (
        'For the RTSP protocol, the DESCRIBE client request template is:\n'
        'DESCRIBE: ["DESCRIBE <<VALUE>>\\r\\n","CSeq: <<VALUE>>\\r\\n",'
        '"User-Agent: <<VALUE>>\\r\\n","Accept: <<VALUE>>\\r\\n","\\r\\n"]\n'
        'For the HTTP protocol, the GET client request template is:\n'
        'GET: ["GET <<VALUE>>\\r\\n"]\n'
        f'For the {proto} protocol, all of client request templates are :\n'
        'Output ONLY the templates, one per line, in the format COMMAND: ["..."]. '
        'Do not use markdown code fences, do not add any explanation or preamble.'
    )


def build_remaining_prompt(proto, first_question, first_answer):
    """重建 construct_prompt_for_remaining_templates 的 prompt。"""
    return (
        first_question + "\n" + first_answer + "\n"
        f"For the {proto} protocol, other templates of client requests are:"
    )


# 语法提取 prompt 里用 RTSP/HTTP 作格式示例，LLM 有时会误把示例方法（DESCRIBE/GET 等）
# 当成目标协议的类型。这里过滤掉这些跨协议示例方法，保证类型全集干净。
_RTSP_HTTP_NOISE = {
    "DESCRIBE", "GET", "SETUP", "PLAY", "PAUSE", "TEARDOWN", "ANNOUNCE", "RECORD",
    "GET_PARAMETER", "SET_PARAMETER", "POST", "PUT", "DELETE", "HEAD", "PATCH",
}


def extract_commands(text):
    """从模板文本提取消息类型（COMMAND 名），对齐 extract_message_grammars 的 header 提取。"""
    cmds = set()
    for line in text.split("\n"):
        m = re.match(r"^\s*([A-Za-z][A-Za-z0-9]*)\s*:\s*\[", line)
        if m:
            cmd = m.group(1).upper()
            if cmd not in _RTSP_HTTP_NOISE:
                cmds.add(cmd)
    return cmds


def grammar_extraction(proto):
    """语法提取：5 次迭代 x(templates + remaining)，返回消息类型全集。"""
    first_question = build_templates_prompt(proto)
    all_cmds = set()
    for _ in range(TEMPLATE_CONSISTENCY_COUNT):
        templates_answer = call_llm([{"role": "user", "content": first_question}])
        if not templates_answer:
            continue
        remaining_prompt = build_remaining_prompt(proto, first_question, templates_answer)
        remaining_answer = call_llm([{"role": "user", "content": remaining_prompt}])
        combined = (templates_answer or "") + "\n" + (remaining_answer or "")
        all_cmds |= extract_commands(combined)
    return all_cmds


def seed_commands(content: bytes):
    """从种子字节流提取命令名（每行第一个 token），对齐 enrich_testcases 的 header 提取。"""
    cmds = set()
    for line in content.split(b"\r\n"):
        line = line.strip()
        if not line:
            continue
        token = line.split(b" ")[0].split(b"\t")[0]
        cmds.add(token.decode(errors="ignore").upper())
    return cmds


def build_enrich_prompt(sequence: str, missing_list):
    """重建 enrich_sequence 的 prompt_template（补 missing_list 里的类型，纯格式约束）。"""
    missing_str = ", ".join(missing_list)
    return (
        "The following is one sequence of client requests:\n"
        f"{sequence}\n"
        f"Please add the {missing_str} client requests in the proper locations, "
        "and the modified sequence of client requests is:\n"
        "Output ONLY the modified sequence itself (raw client requests). "
        "Do not add any explanation, notes, rationale, or markdown formatting."
    )


def enrich_seed(seed_path, msg_types, out_dir):
    """对单条种子做增强，返回该种子生成的非空增强数。"""
    content = seed_path.read_bytes()
    text = content.decode(errors="ignore")
    observed = seed_commands(content)
    missing = sorted(msg_types - observed)
    # 对齐 MAX_ENRICHMENT_CORPUS_SIZE 限制
    missing = missing[:MAX_ENRICHMENT_CORPUS_SIZE]
    if not missing:
        return 0

    n = 0
    # C(n, MAX_ENRICHMENT_MESSAGE_TYPES) 组合（= C(n,2)）
    for subset in combinations(missing, MAX_ENRICHMENT_MESSAGE_TYPES):
        prompt = build_enrich_prompt(text, list(subset))
        answer = call_llm([{"role": "user", "content": prompt}])
        if not answer:
            continue
        # 去前后空白，跳过空/与原文相同
        formatted = answer.strip()
        if not formatted or formatted.strip("\r\n ") == text.strip("\r\n "):
            continue
        # 落盘（补 \r\n\r\n 结尾，对齐 write_new_seeds）
        out_path = out_dir / f"enriched_{n}_{seed_path.name}"
        out_path.write_text(formatted + "\r\n\r\n", encoding="utf-8")
        n += 1
    return n


def main():
    target, proto, seed_dir, dict_path, out_dir = sys.argv[1:6]
    seed_dir = Path(seed_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    start = time.time()
    print(f"[{target}/{proto}] 语法提取开始...", flush=True)
    msg_types = grammar_extraction(proto)
    print(f"[{target}/{proto}] 消息类型全集 ({len(msg_types)}): {sorted(msg_types)}", flush=True)

    total = 0
    seeds = sorted(seed_dir.glob("*.raw"))
    for seed in seeds:
        if "enriched" in seed.name:
            continue
        cnt = enrich_seed(seed, msg_types, out_dir)
        total += cnt
        print(f"  种子 {seed.name}: 缺失类型后生成 {cnt} 个增强", flush=True)

    elapsed = time.time() - start
    print("=" * 50)
    print(f"TIME_MIN = {elapsed/60:.2f}")
    print(f"TOKENS = prompt {token_stats['prompt_tokens']} + completion {token_stats['completion_tokens']} "
          f"= {token_stats['prompt_tokens'] + token_stats['completion_tokens']}  ({token_stats['calls']} 次调用)")
    print(f"ENRICHED_NONEMPTY = {total}")
    print("=" * 50)


if __name__ == "__main__":
    main()
