# -*- coding: utf-8 -*-
# 修复 ChatAFL chat-llm.c 的 construct_prompt_for_templates JSON 转义 bug
p = "/home/zxy/chatafl历史版本/ChatAFL-Pure/ChatAFL/chat-llm.c"
s = open(p, encoding="utf-8").read()

old = '''    asprintf(&prompt_grammars, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": \\"%s\\"}]", msg);

    return prompt_grammars;'''

new = '''    json_object *msg_json = json_object_new_string(msg);
    const char *msg_escaped = json_object_to_json_string(msg_json);
    asprintf(&prompt_grammars, "[{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"}, {\\"role\\": \\"user\\", \\"content\\": %s}]", msg_escaped);
    json_object_put(msg_json);

    return prompt_grammars;'''

assert old in s, "old not found"
s = s.replace(old, new)
open(p, "w", encoding="utf-8").write(s)
print("chat-llm.c JSON 转义修复完成")
