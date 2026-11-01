# -*- coding: utf-8 -*-
# 修改 ChatAFL chat-llm.c 的两个 prompt
p = "/home/zxy/chatafl历史版本/ChatAFL-Pure/ChatAFL/chat-llm.c"
s = open(p, encoding="utf-8").read()

# 修改1：语法提取 prompt（在格式串结尾 : 后加约束）
old1 = 'all of client request templates are :"'
new1 = 'all of client request templates are :\\nOutput ONLY the templates, one per line, in the format COMMAND: [\\"...\\"]. Do not use markdown code fences, do not add any explanation or preamble."'
assert old1 in s, "old1 not found"
s = s.replace(old1, new1)

# 修改2：增强 prompt
old2 = 'the modified sequence of client requests is:"'
new2 = 'the modified sequence of client requests is:\\nOutput ONLY the modified sequence itself (raw client requests). Do not add any explanation, notes, rationale, or markdown formatting."'
assert old2 in s, "old2 not found"
s = s.replace(old2, new2)

open(p, "w", encoding="utf-8").write(s)
print("prompt 修改完成")
