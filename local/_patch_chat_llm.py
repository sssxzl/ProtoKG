#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性精确补丁：chat-llm.c 的 LLM URL 改为 getenv + 默认容器内回环。

用法（容器内）：python3 /tmp/_patch_chat_llm.py
安全：仅做「存在性检查 + 单次替换」，不匹配则直接报错退出，绝不静默破坏。
"""
import sys

PATH = "/home/ubuntu/chatafl/chat-llm.c"

with open(PATH, "r") as f:
    src = f.read()

# 1) 确保 getenv 所需 <stdlib.h> 已包含（幂等）。
if "#include <stdlib.h>" not in src:
    if "#include <unistd.h>" not in src:
        print("ERROR: 找不到 #include <unistd.h>，中止")
        sys.exit(1)
    src = src.replace(
        "#include <unistd.h>",
        "#include <unistd.h>\n#include <stdlib.h>",
        1,
    )

# 2) 精确替换 URL 分支（instruct/turbo 两分支硬编码相同）。
old = r'''    char *url = NULL;
    if (strcmp(model, "instruct") == 0)
    {
        url = "http://192.168.37.1:18080/chat/completions";
    }
    else
    {
        url = "http://192.168.37.1:18080/chat/completions";
    }
'''
new = r'''    char *url = getenv("CHATAFL_LLM_URL");
    if (url == NULL || url[0] == '\0')
        url = "http://127.0.0.1:18080/chat/completions";
'''

if old not in src:
    print("ERROR: 未精确匹配到旧 URL 分支，中止")
    sys.exit(1)

src = src.replace(old, new, 1)

with open(PATH, "w") as f:
    f.write(src)

print("patch applied OK")
