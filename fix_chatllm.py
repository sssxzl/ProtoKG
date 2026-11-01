# -*- coding: utf-8 -*-
"""修复 ChatAFL chat-llm.c 里 asprintf 块的引号转义（本地写好避免 shell 转义混乱）。"""
import io

p = 'chat-llm.c'
s = io.open(p, encoding='utf-8').read()

# 错误块（引号未转义，C 编译报错）
bad = '''    asprintf(&messages_prompt,
             "[{"role": "system", "content": "You are a helpful assistant."}, "
             "{"role": "user", "content": %s}]", prompt_escaped);'''

# 正确块（引号用反斜杠转义）
good = r'''    asprintf(&messages_prompt,
             "[{\"role\": \"system\", \"content\": \"You are a helpful assistant.\"}, "
             "{\"role\": \"user\", \"content\": %s}]", prompt_escaped);'''

assert bad in s, 'bad block not found'
s = s.replace(bad, good, 1)
io.open(p, 'w', encoding='utf-8').write(s)
print('fixed OK')
