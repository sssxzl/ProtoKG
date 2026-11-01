#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冒烟测试客户端：向容器内代理 POST 增强 prompt，打印响应 content + 首行 + 散文检测。"""
import json
import urllib.request

URL = "http://127.0.0.1:18080/chat/completions"
with open("/tmp/req.json", "rb") as f:
    body = f.read()

req = urllib.request.Request(
    URL, data=body, method="POST",
    headers={"Content-Type": "application/json"},
)
with urllib.request.urlopen(req, timeout=200) as resp:
    data = resp.read()
    status = resp.status

obj = json.loads(data.decode("utf-8"))
content = ""
try:
    content = obj["choices"][0]["message"]["content"]
except (KeyError, IndexError, TypeError):
    pass

print("=== HTTP status ===")
print(status)
print("=== content (repr) ===")
print(repr(content))
print("=== content 首行 ===")
first_line = content.split("\n", 1)[0].strip() if content else "(empty)"
print(first_line)

prose_markers = ["Here is", "Here's", "Note:", "Explanation", "```", "Sure,", "Sure!", "I'll", "Below"]
hits = [m for m in prose_markers if m.lower() in content.lower()]
print("=== 散文检测 ===")
print("命中散文标记:", hits if hits else "无")
