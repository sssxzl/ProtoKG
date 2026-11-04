# -*- coding: utf-8 -*-
# 修复镜像内 chatafl 的语法提取 prompt（纯格式约束 + JSON 转义）
p = "/home/ubuntu/chatafl/chat-llm.c"
s = open(p, encoding="utf-8").read()

# 1. msg 加纯格式约束（让 deepseek-chat 返回纯 COMMAND: [...] 格式，避免 markdown）
old1 = 'all of client request templates are :"'
new1 = 'all of client request templates are :\\nOutput ONLY the templates, one per line, in the format COMMAND: [\\"...\\"]. Do not use markdown code fences, do not add any explanation or preamble."'
assert old1 in s, "old1 not found"
s = s.replace(old1, new1)

# 2. prompt_grammars 用 json_object 转义 msg（避免 msg 里的换行导致 JSON 非法）
old2 = '    asprintf(&prompt_grammars, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": \\"%s\\"}]", msg);'
new2 = '    json_object *msg_json = json_object_new_string(msg);\n    const char *msg_escaped = json_object_to_json_string(msg_json);\n    asprintf(&prompt_grammars, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": %s}]", msg_escaped);\n    json_object_put(msg_json);'
assert old2 in s, "old2 not found"
s = s.replace(old2, new2)

open(p, "w", encoding="utf-8").write(s)
print("两处修复完成")
