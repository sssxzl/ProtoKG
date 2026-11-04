#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重建 ChatAFL 种子增强（enrich_sequence）的精确 prompt 并实测 token 用量。

背景：ChatAFL 的 C 代码（chat-llm.c）不输出 token 用量，故按其源码逐字重建
enrich_sequence 的 prompt 模板，用同一 DeepSeek API 实测 usage（prompt_tokens +
completion_tokens），得到「种子增强」这一步的真实 LLM token 用量。

prompt 模板（chat-llm.c 第 916 行 enrich_sequence）:
    "The following is one sequence of client requests:\n"
    "%.*s\n"      <- 序列内容（JSON 转义后）
    "Please add the %.*s client requests in the proper locations, "
    "and the modified sequence of client requests is:"
调用（chat-llm.c 第 65 行）:
    POST https://api.deepseek.com/beta/completions
    {"model":"deepseek-chat","prompt":"<prompt>","max_tokens":2048,"temperature":0.5}

用法:
    python3 reconstruct_enrich_tokens.py <seed_dir> <message_types_file> [--dry]
    默认只打印每个种子的 missing 类型 + 重建的 prompt 长度 + 预期调用数，
    加 --run 才真正调用 DeepSeek 求和 token（慢，约 147 次调用）。
"""
import os
import json
import re
import sys
import urllib.request

# ★ 安全整改（2026-11-01）：API key 改从环境变量读（原为硬编码，会随版本库泄露）
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_URL = "https://api.deepseek.com/beta/completions"

PROMPT_TEMPLATE = (
    "The following is one sequence of client requests:\n"
    "%s\n"
    "Please add the %s client requests in the proper locations, "
    "and the modified sequence of client requests is:"
)


def read_seed(path):
    with open(path, "rb") as f:
        return f.read().decode("utf-8", errors="replace")


def present_types(seq):
    """从种子序列里提取出现过的消息类型（请求行第一个 token）。"""
    types = set()
    for line in seq.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "//")):
            continue
        # 请求行形如 "METHOD url RTSP/1.0"
        m = re.match(r"^([A-Za-z_]+)\s+\S+\s+RTSP", line)
        if m:
            types.add(m.group(1).upper())
    return types


def subsets(missing, size=2, cap=10):
    """生成缺失类型的【大小恰为 size】的组合（对齐 C 代码 message_combinations：
    只生成 size=2 的组合，不生成 size=1 的）。cap 限制缺失类型数（MAX_ENRICHMENT_CORPUS_SIZE）。"""
    items = sorted(missing)[:cap]
    res = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            res.append([items[i], items[j]])
    return res


def call_llm(prompt):
    data = json.dumps({"model": "deepseek-chat", "prompt": prompt,
                       "max_tokens": 2048, "temperature": 0.5}).encode()
    req = urllib.request.Request(
        API_URL, data=data, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + API_KEY})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def main():
    if len(sys.argv) < 3:
        print("usage: reconstruct_enrich_tokens.py <seed_dir> <msg_types> [--run]")
        sys.exit(2)
    seed_dir = sys.argv[1]
    msg_types = [t.strip().upper() for t in
                 open(sys.argv[2], encoding="utf-8").read().split(",") if t.strip()]
    do_run = "--run" in sys.argv

    import glob
    seeds = sorted(glob.glob(seed_dir + "/*.raw"))
    seeds = [s for s in seeds if "enriched" not in s]

    total_in = 0
    total_out = 0
    total_calls = 0
    for s in seeds:
        seq = read_seed(s)
        present = present_types(seq)
        missing = set(msg_types) - present
        subs = subsets(missing)
        print(f"{s.split('/')[-1]}: present={sorted(present)} "
              f"missing={sorted(missing)} subsets={len(subs)}")
        for sub in subs:
            missing_str = ", ".join(sub)
            prompt = PROMPT_TEMPLATE % (seq, missing_str)
            total_calls += 1
            if do_run:
                try:
                    resp = call_llm(prompt)
                    u = resp.get("usage", {}) or {}
                    total_in += u.get("prompt_tokens", 0) or 0
                    total_out += u.get("completion_tokens", 0) or 0
                except Exception as e:  # noqa: BLE001
                    print(f"  call failed: {e}")
    print("=" * 60)
    print(f"总 LLM 调用数: {total_calls}")
    if do_run:
        print(f"input_tokens:  {total_in}")
        print(f"output_tokens: {total_out}")
        print(f"total_tokens:  {total_in + total_out}")
    else:
        print("(未 --run，仅打印调用数与 prompt 结构；加 --run 实测 token)")


if __name__ == "__main__":
    main()
