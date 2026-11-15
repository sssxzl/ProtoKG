# -*- coding: utf-8 -*-
"""★ N0.2 前置：★ 冻结「去重前」的行为基线（★ 用于事后证明等价）。

★ 基线内容：
  ① 每个重复函数的**最后一个定义**的代码 sha（★ 去重后必须逐一相同）
  ② `_collect_blocks` 对四个协议**真实 RFC** 的输出（★ 块集合/起始行/文本哈希）
  ③ 三个开关路径的实测行为（★ 默认关 / kind review 开 / block selection 开）
"""
import ast
import collections
import hashlib
import importlib
import json
import os
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
P = ROOT / "core/fused/extraction/prose_semantics.py"
OUT = ROOT / "guard/_out/n0"
OUT.mkdir(parents=True, exist_ok=True)

src = P.read_text(encoding="utf-8")
tree = ast.parse(src)
defs = collections.defaultdict(list)
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        defs[node.name].append(node)

# ★ ① 最后定义的代码 sha
sha_map = {}
for name, nodes in defs.items():
    last = nodes[-1]
    code = ast.unparse(last)
    sha_map[name] = hashlib.sha256(code.encode()).hexdigest()
dups = {k: [n.lineno for n in v] for k, v in defs.items() if len(v) > 1}
print(f"  ★ 重复定义函数：{len(dups)} 个｜总定义数 {sum(len(v) for v in defs.values())}")

# ★ ② _collect_blocks 对真实 RFC 的输出
from core import paths
from core.fused.extraction import prose_semantics as ps

_real = {}
for proto in ("rtsp", "sip", "smtp", "DHCPv4"):
    _files = sorted(paths.kb_source_dir(proto, "rfc").glob("*.txt"))
    _blocks = ps._collect_blocks(_files)
    _real[proto] = {
        "n": len(_blocks),
        "items": [{"doc": b["doc"], "start": b["start"],
                   "text_sha": hashlib.sha256(b["text"].encode()).hexdigest()[:16]}
                  for b in _blocks],
    }
    print(f"  ★ {proto}: {_real[proto]['n']} 块｜sha {hashlib.sha256(str(_real[proto]).encode()).hexdigest()[:12]}")

# ★ ③ 三条开关路径
def _probe(tag, env):
    for _k in ("PROSE_KIND_REVIEW", "PROSE_BLOCK_SELECTION",
               "PROSE_BLOCKS_PER_DOC"):
        os.environ.pop(_k, None)
    os.environ.update(env)
    importlib.reload(ps)
    _files = sorted(paths.kb_source_dir("DHCPv4", "rfc").glob("*.txt"))
    _b = ps._collect_blocks(_files)
    return {"tag": tag, "env": env, "n_blocks": len(_b),
            "docs": len({x["doc"] for x in _b}),
            "first": [(x["doc"], x["start"]) for x in _b[:3]],
            "kind_review": ps._kind_review_enabled(),
            "selection": ps._block_selection_mode()}


paths_probe = [
    _probe("默认关闭", {}),
    _probe("kind review 开启", {"PROSE_KIND_REVIEW": "1",
                                "PROSE_BLOCKS_PER_DOC": "1"}),
    _probe("block selection 开启", {"PROSE_BLOCK_SELECTION": "block_density",
                                    "PROSE_BLOCKS_PER_DOC": "16"}),
]
for _p in paths_probe:
    print(f"  ★ {_p['tag']}: {_p['n_blocks']} 块 / {_p['docs']} 文档"
          f"｜kind={_p['kind_review']}｜sel={_p['selection']!r}")

baseline = {
    "★ git_commit": __import__("subprocess").run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(ROOT)).stdout.strip(),
    "★ file_sha256": hashlib.sha256(P.read_bytes()).hexdigest(),
    "★ 重复定义": dups,
    "★ 最后定义代码 sha": sha_map,
    "★ 真实输出基线": _real,
    "★ 三路径行为": paths_probe,
}
(OUT / "n0_baseline_before_dedup.json").write_text(
    json.dumps(baseline, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n  ⇒ {OUT/'n0_baseline_before_dedup.json'}")
