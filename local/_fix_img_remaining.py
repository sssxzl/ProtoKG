# -*- coding: utf-8 -*-
# 修复 construct_prompt_for_remaining_templates 的 first_question JSON 转义
p = "/home/ubuntu/chatafl/chat-llm.c"
s = open(p).read()

old = '''    asprintf(&prompt,
             "["
             "{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"},"
             "{\\"role\\": \\"user\\", \\"content\\": \\"%s\\"},"
             "{\\"role\\": \\"assistant\\", \\"content\\": %s },"
             "{\\"role\\": \\"user\\", \\"content\\": \\"%s\\"}"
             "]",
             first_question, answer_str_escaped, second_question);'''

new = '''    json_object *question_str = json_object_new_string(first_question);
    const char *question_escaped = json_object_to_json_string(question_str);

    asprintf(&prompt,
             "["
             "{\\"role\\": \\"system\\", \\"content\\": \\"You are a helpful assistant.\\"},"
             "{\\"role\\": \\"user\\", \\"content\\": %s},"
             "{\\"role\\": \\"assistant\\", \\"content\\": %s },"
             "{\\"role\\": \\"user\\", \\"content\\": \\"%s\\"}"
             "]",
             question_escaped, answer_str_escaped, second_question);

    json_object_put(question_str);'''

assert old in s, "old not found"
s = s.replace(old, new)
open(p, "w").write(s)
print("remaining_templates JSON 转义修复完成")
