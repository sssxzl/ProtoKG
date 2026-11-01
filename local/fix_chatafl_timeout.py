# -*- coding: utf-8 -*-
"""修复 chat-llm.c 两个问题（对黄金标准文件增量修复）：
1. curl 无超时 -> 加 CURLOPT_TIMEOUT=120 + CURLOPT_CONNECTTIMEOUT=30（根治 LLM 响应丢失导致的无限等待）
2. construct_prompt_stall 的 JSON 转义 bug -> 用 json_object 转义（进 fuzzing 后 stall 检测会踩的坑）
"""
import sys

p = sys.argv[1] if len(sys.argv) > 1 else "/home/zxy/rq2_chatafl_fix/chat-llm.c"
s = open(p).read()

# ---- 1. curl 超时 ----
old1 = '    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, chat_with_llm_helper);'
new1 = ('    curl_easy_setopt(curl, CURLOPT_TIMEOUT, 120);\n'
        '    curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 30);\n'
        '    curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, chat_with_llm_helper);')
if old1 in s:
    s = s.replace(old1, new1, 1)  # 只替换 chat_with_llm 里的第一处
    print("[ok] curl 超时已加")
else:
    print("[warn] curl 锚点未找到（可能已加过）")

# ---- 2. construct_prompt_stall JSON 转义 ----
old2 = '    asprintf(&final_prompt, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": \\"%s\\"}]", prompt);'
new2 = ('    json_object *prompt_json = json_object_new_string(prompt);\n'
        '    const char *prompt_escaped = json_object_to_json_string(prompt_json);\n'
        '    asprintf(&final_prompt, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": %s}]", prompt_escaped);\n'
        '    json_object_put(prompt_json);')
if old2 in s:
    s = s.replace(old2, new2, 1)
    print("[ok] construct_prompt_stall 转义已修复")
else:
    print("[warn] stall 锚点未找到（可能已修过）")

open(p, "w").write(s)
print("修复完成:", p)
