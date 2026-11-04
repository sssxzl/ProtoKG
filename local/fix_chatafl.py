# -*- coding: utf-8 -*-
"""通用修复 ProFuzzBench 镜像内 chatafl 的 3 个 bug（对任意目标镜像通用）。

1. DEEPSEEK_TOKEN 被脱敏 → 补全完整 token
2. URL 直连 DeepSeek → 改走代理 http://192.168.37.1:18080；MODEL deepseek-v4-flash → deepseek-chat
3. 3 处 JSON 转义 bug + enrich_sequence instruct→chat 模式 + 语法提取 prompt 纯格式约束

在容器内运行：python3 fix_chatafl.py
"""
import os
import re

CHAT_LLM_H = "/home/ubuntu/chatafl/chat-llm.h"
CHAT_LLM_C = "/home/ubuntu/chatafl/chat-llm.c"
# ★ 安全整改（2026-11-01）：API key 改从环境变量读（原为硬编码，会随版本库泄露）
TOKEN = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("CHAT_AFL_TOKEN", "")
PROXY = "http://192.168.37.1:18080/chat/completions"

# ---- 1. token 补全（chat-llm.h，含 DEEPSEEK_TOKEN 或 OPENAI_TOKEN）----
s = open(CHAT_LLM_H, encoding="utf-8").read()
s = re.sub(r'#define (?:DEEPSEEK_TOKEN|OPENAI_TOKEN) "[^"]*"',
           '#define \\1 "' + TOKEN + '"', s)
open(CHAT_LLM_H, "w", encoding="utf-8").write(s)

# ---- 2~7. chat-llm.c 修复 ----
s = open(CHAT_LLM_C, encoding="utf-8").read()

# 2. URL 改代理（两个端点都改）
s = s.replace("https://api.deepseek.com/v1/chat/completions", PROXY)
s = s.replace("https://api.deepseek.com/v1/completions", PROXY)

# 3. MODEL 改 deepseek-chat
s = s.replace("deepseek-v4-flash", "deepseek-chat")

# 4. enrich_sequence：instruct → chat 模式 + JSON 转义
old4 = '    char *response = chat_with_llm(prompt, "instruct", ENRICHMENT_RETRIES, 0.5);\n\n    free(prompt);\n\n    return response;'
new4 = ('    json_object *prompt_json = json_object_new_string(prompt);\n'
        '    const char *prompt_escaped = json_object_to_json_string(prompt_json);\n'
        '    char *messages_prompt = NULL;\n'
        '    asprintf(&messages_prompt, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": %s}]", prompt_escaped);\n'
        '    json_object_put(prompt_json);\n'
        '    char *response = chat_with_llm(messages_prompt, "turbo", ENRICHMENT_RETRIES, 0.5);\n'
        '    free(messages_prompt);\n\n'
        '    free(prompt);\n\n'
        '    return response;')
if old4 in s:
    s = s.replace(old4, new4)
else:
    print("[warn] enrich_sequence instruct 模式未找到，可能已修复或结构不同")

# 5. 语法提取 prompt 纯格式约束
old5 = 'all of client request templates are :"'
new5 = 'all of client request templates are :\\nOutput ONLY the templates, one per line, in the format COMMAND: [\\"...\\"]. Do not use markdown code fences, do not add any explanation or preamble."'
if old5 in s:
    s = s.replace(old5, new5)
else:
    print("[warn] 语法提取 prompt 锚点未找到，可能已修复")

# 6. construct_prompt_for_templates 的 prompt_grammars JSON 转义
old6 = '    asprintf(&prompt_grammars, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": \\"%s\\"}]", msg);'
new6 = ('    json_object *msg_json = json_object_new_string(msg);\n'
        '    const char *msg_escaped = json_object_to_json_string(msg_json);\n'
        '    asprintf(&prompt_grammars, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": %s}]", msg_escaped);\n'
        '    json_object_put(msg_json);')
if old6 in s:
    s = s.replace(old6, new6)
else:
    print("[warn] prompt_grammars 锚点未找到，可能已修复")

# 7. construct_prompt_for_remaining_templates 的 first_question JSON 转义
old7 = ('             "{\\"role\\": \\"user\\", \\"content\\": \\"%s\\"},\n'
        '             "{\\"role\\": \\"assistant\\", \\"content\\": %s },\n'
        '             "{\\"role\\": \\"user\\", \\"content\\": \\"%s\\"}"\n'
        '             "]",\n'
        '             first_question, answer_str_escaped, second_question);')
new7 = ('             "{\\"role\\": \\"user\\", \\"content\\": %s},\n'
        '             "{\\"role\\": \\"assistant\\", \\"content\\": %s },\n'
        '             "{\\"role\\": \\"user\\", \\"content\\": \\"%s\\"}"\n'
        '             "]",\n'
        '             question_escaped, answer_str_escaped, second_question);')
if old7 in s:
    s = s.replace(old7, new7)
    # 在 asprintf 前插入 question 转义
    anchor = '    char *prompt = NULL;\n\n    asprintf(&prompt,'
    if anchor in s:
        s = s.replace(anchor,
                      '    char *prompt = NULL;\n\n'
                      '    json_object *question_str = json_object_new_string(first_question);\n'
                      '    const char *question_escaped = json_object_to_json_string(question_str);\n\n'
                      '    asprintf(&prompt,')
    # 在 json_object_put(answer_str) 后补 put(question_str)
    s = s.replace('    json_object_put(answer_str);',
                  '    json_object_put(answer_str);\n    json_object_put(question_str);')
else:
    print("[warn] remaining_templates first_question 锚点未找到，可能已修复")

open(CHAT_LLM_C, "w", encoding="utf-8").write(s)
print("chatafl 修复完成")
