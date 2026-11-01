# -*- coding: utf-8 -*-
"""给 chat_with_llm 的 curl 加超时（否则 LLM API 挂起时无限等）。"""
import io

p = 'chat-llm.c'
s = io.open(p, encoding='utf-8').read()

old = '''            curl_easy_setopt(curl, CURLOPT_URL, url);
            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, chat_with_llm_helper);'''

new = '''            curl_easy_setopt(curl, CURLOPT_URL, url);
            curl_easy_setopt(curl, CURLOPT_TIMEOUT, 60);
            curl_easy_setopt(curl, CURLOPT_CONNECTTIMEOUT, 15);
            curl_easy_setopt(curl, CURLOPT_WRITEFUNCTION, chat_with_llm_helper);'''

assert old in s, 'target not found'
s = s.replace(old, new, 1)
io.open(p, 'w', encoding='utf-8').write(s)
print('curl timeout fix OK')
