# -*- coding: utf-8 -*-
"""回填主文档 实验方案_详细版.docx 的 RQ1 6 张表（BFTPD/LightFTP/ProFTPD/PureFTPD/Exim/Kamailio）。"""
import json
import subprocess

FILE_ID = "f1f452f0-18e8-41b2-b89c-c72e83454fd6"
EDSDK = r"D:\app\WorkBuddy\resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills\workbuddy-local-office-edit\edsdk.py"
PY = r"E:\python\python.exe"

# table_id + 数据（顺序 BFTPD/LightFTP/ProFTPD/PureFTPD/Exim/Kamailio）
# 每表 4 行：row1=表头, row2=Seed Reuse, row3=ChatAFL, row4=ProtoRAG
# 每方法行 5 列数据：(种子数, Time, Tokens, Rv, Veff)
tables = [
    ("BFTPD", "3wvma8xm", 13, (585, "9.56", "99,602", "100%", "61.2"), (6, "2.86", "43,338", "100%", "2.1")),
    ("LightFTP", "pqgm5u65", 2, (90, "1.51", "18,851", "100%", "59.6"), (6, "2.86", "43,338", "100%", "2.1")),
    ("ProFTPD", "77czp037", 13, (585, "9.56", "99,602", "100%", "61.2"), (6, "2.86", "43,338", "100%", "2.1")),
    ("PureFTPD", "1dqo60t8", 13, (585, "9.57", "102,930", "94%", "57.5"), (6, "2.86", "43,338", "100%", "2.1")),
    ("Exim", "5n6ksnwx", 2, (81, "1.37", "15,206", "100%", "59.1"), (85, "2.69", "53,432", "100%", "31.6")),
    ("Kamailio", "ie3cn7bj", 1, (45, "3.40", "107,593", "100%", "13.2"), (17, "8.74", "67,316", "100%", "1.9")),
]


def make_cells(sr, ca, pr):
    cells = []
    # row2 Seed Reuse
    cells += [
        {"row": 2, "col": 2, "text": str(sr)},
        {"row": 2, "col": 3, "text": "不评估"},
        {"row": 2, "col": 4, "text": "0"},
        {"row": 2, "col": 5, "text": "100%"},
        {"row": 2, "col": 6, "text": "不评估"},
    ]
    # row3 ChatAFL
    cells += [
        {"row": 3, "col": 2, "text": str(ca[0])},
        {"row": 3, "col": 3, "text": ca[1]},
        {"row": 3, "col": 4, "text": ca[2]},
        {"row": 3, "col": 5, "text": ca[3]},
        {"row": 3, "col": 6, "text": ca[4]},
    ]
    # row4 ProtoRAG
    cells += [
        {"row": 4, "col": 2, "text": str(pr[0])},
        {"row": 4, "col": 3, "text": pr[1]},
        {"row": 4, "col": 4, "text": pr[2]},
        {"row": 4, "col": 5, "text": pr[3]},
        {"row": 4, "col": 6, "text": pr[4]},
    ]
    return cells


for name, tid, sr, ca, pr in tables:
    cells = make_cells(sr, ca, pr)
    args = json.dumps({"file_id": FILE_ID, "table_id": tid, "cells": cells}, ensure_ascii=False)
    r = subprocess.run([PY, EDSDK, "call", "doc_set_table_cells", "--json", args],
                       capture_output=True, text=True, encoding="utf-8")
    out = (r.stdout or r.stderr).strip()
    ok = "ok" in out.lower() or "success" in out.lower() or "table_id" in out
    print(f"[{name}] {tid}: {'OK' if ok else out[:200]}")

print("主文档回填完成")
