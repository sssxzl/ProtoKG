# -*- coding: utf-8 -*-
"""回填 RQ1 详细版 docx 的 6 张种子构造效率表格（LightFTP/Bftpd/PureFTPD/ProFTPD/Kamailio/Exim）。"""
import json
import subprocess

FILE_ID = "44d7f21c-863a-4459-b773-2ee1f0614a2f"
EDSDK = r"D:\app\WorkBuddy\resources\app.asar.unpacked\resources\plugins\workbuddy-builtin\skills\workbuddy-local-office-edit\edsdk.py"
PY = r"E:\python\python.exe"

# 每张表：table_id + 各方法行的 5 列数据（种子数/Time/Tokens/Rv/Veff）
# row2=Manual, row3=SeedReuse, row4=ChatAFL, row5=Fuzz4All(留空), row6=ProtoRAG
tables = {
    "LightFTP": {
        "id": "bkyd3ixk",
        "seed_reuse": 2,
        "chatafl": (90, "1.51", "18,851", "100%", "59.6"),
        "protorag": (6, "2.86", "43,338", "100%", "2.1"),
    },
    "Bftpd": {
        "id": "jtbwym7d",
        "seed_reuse": 13,
        "chatafl": (585, "9.56", "99,602", "100%", "61.2"),
        "protorag": (6, "2.86", "43,338", "100%", "2.1"),
    },
    "PureFTPD": {
        "id": "kjoztn2c",
        "seed_reuse": 13,
        "chatafl": (585, "9.57", "102,930", "94%", "57.5"),
        "protorag": (6, "2.86", "43,338", "100%", "2.1"),
    },
    "ProFTPD": {
        "id": "36oh0dnt",
        "seed_reuse": 13,
        "chatafl": (585, "9.56", "99,602", "100%", "61.2"),
        "protorag": (6, "2.86", "43,338", "100%", "2.1"),
    },
    "Kamailio": {
        "id": "eyicl8qm",
        "seed_reuse": 1,
        "chatafl": (45, "3.40", "107,593", "100%", "13.2"),
        "protorag": (17, "8.74", "67,316", "100%", "1.9"),
    },
    "Exim": {
        "id": "v1nf5330",
        "seed_reuse": 2,
        "chatafl": (81, "1.37", "15,206", "100%", "59.1"),
        "protorag": (85, "2.69", "53,432", "100%", "31.6"),
    },
}


def make_cells(name, info):
    sr = info["seed_reuse"]
    ca = info["chatafl"]
    pr = info["protorag"]
    cells = []
    # row2 Manual
    cells += [
        {"row": 2, "col": 2, "text": "1"},
        {"row": 2, "col": 3, "text": "人工"},
        {"row": 2, "col": 4, "text": "0"},
        {"row": 2, "col": 5, "text": "100%"},
        {"row": 2, "col": 6, "text": "—"},
    ]
    # row3 Seed Reuse
    cells += [
        {"row": 3, "col": 2, "text": str(sr)},
        {"row": 3, "col": 3, "text": "不评估"},
        {"row": 3, "col": 4, "text": "0"},
        {"row": 3, "col": 5, "text": "100%"},
        {"row": 3, "col": 6, "text": "—"},
    ]
    # row4 ChatAFL
    cells += [
        {"row": 4, "col": 2, "text": str(ca[0])},
        {"row": 4, "col": 3, "text": ca[1]},
        {"row": 4, "col": 4, "text": ca[2]},
        {"row": 4, "col": 5, "text": ca[3]},
        {"row": 4, "col": 6, "text": ca[4]},
    ]
    # row6 ProtoRAG
    cells += [
        {"row": 6, "col": 2, "text": str(pr[0])},
        {"row": 6, "col": 3, "text": pr[1]},
        {"row": 6, "col": 4, "text": pr[2]},
        {"row": 6, "col": 5, "text": pr[3]},
        {"row": 6, "col": 6, "text": pr[4]},
    ]
    return cells


for name, info in tables.items():
    cells = make_cells(name, info)
    args = json.dumps({"file_id": FILE_ID, "table_id": info["id"], "cells": cells}, ensure_ascii=False)
    r = subprocess.run([PY, EDSDK, "call", "doc_set_table_cells", "--json", args],
                       capture_output=True, text=True, encoding="utf-8")
    out = (r.stdout or r.stderr).strip()
    ok = "ok" in out.lower() or "success" in out.lower() or "table_id" in out
    print(f"[{name}] {info['id']}: {'OK' if ok else out[:200]}")

print("回填完成")
