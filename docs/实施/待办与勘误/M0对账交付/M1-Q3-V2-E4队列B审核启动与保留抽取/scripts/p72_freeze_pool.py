# -*- coding: utf-8 -*-
"""★ V2-E4：★ 候选池独立评估冻结清单 ＋ 人工标注回收校验程序。

★ ① 候选池冻结清单（H3 全部候选，★ **优先覆盖全部符合条件者**）
★ ② 回收校验程序（★ 结构校验 ＋ **不可编辑字段逐单元格比较** ＋ SHA256 重记）
"""
import csv
import hashlib
import io
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[4]
E4 = ROOT / "guard/_out/_n1c_v2/e4"
DELIV = (ROOT / "docs/实施/待办与勘误/M0对账交付"
         / "M1-Q3-V2-E4队列B审核启动与保留抽取")
E3 = (ROOT / "docs/实施/待办与勘误/M0对账交付"
      / "M1-Q3-V2-E3队列B盲审发放与保留来源预案")

# ══ ① 候选池冻结清单 ══
_cands = [json.loads(l) for l in
          (E4 / "pool/V2-E4_H3新增候选原始.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()]
_pool = []
for _c in _cands:
    _pool.append({
        "gold_candidate_id": _c["★ candidate_id"],
        "★ 来源批次": "★ H3（★ 本轮 9 份保留 RFC，★ 隔离候选池）",
        "document_id": _c["★ document_id"], "protocol": _c["★ protocol"],
        "source_sha256": _c["★ source_sha256"],
        "chunk_id": _c["★ chunk_id"], "chunk_hash": _c["★ chunk_hash"],
        "source_span": _c["★ source_span"],
        "proposed_knowledge_kind": _c["★ proposed_knowledge_kind"],
        "model": _c["★ model"], "prompt_digest": _c["★ prompt_digest"],
        "schema_version": _c["★ schema_version"],
        "★ 状态": "★ shadow/proposed（★ 未进正式 Fact 空间）",
        "★ 证据原文": None,
    })
# ★ 补证据原文（★ 从原 RFC 取，★ 保证人工审核可核对）
for _p in _pool:
    _pp = ROOT / f'kb/{_p["protocol"]}/spec/{_p["document_id"]}'
    if not _pp.is_file() or not _p["source_span"][0]:
        continue
    _L = _pp.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").split("\n")
    _lo, _hi = _p["source_span"]
    _p["★ 证据原文"] = " ".join(_L[_lo - 1:_hi])
    _p["★ 证据原文 sha256"] = hashlib.sha256(
        _p["★ 证据原文"].encode()).hexdigest()

with (DELIV / "V2-E4_候选池独立评估冻结清单.jsonl").open("w", encoding="utf-8") as f:
    for _p in _pool:
        f.write(json.dumps(_p, ensure_ascii=False) + "\n")
_h = hashlib.sha256((DELIV / "V2-E4_候选池独立评估冻结清单.jsonl").read_bytes()).hexdigest()
print(f"  ★ 候选池冻结清单：{len(_pool)} 条｜sha256={_h[:16]}")
print(f"  ★ 类型分布：{dict(__import__('collections').Counter(p['proposed_knowledge_kind'] for p in _pool))}")


# ══ ② 回收校验程序 ══
def verify_recovered(recovered_path, tag):
    """★ 校验回收文件（★ 结构 ＋ **不可编辑字段逐单元格比较** ＋ SHA256）。

    Returns ``(ok, report)``
    """
    _base = {json.loads(l)["snippet_id"]: json.loads(l) for l in
             (E3 / "V2-E3_原文与证据不可编辑字段基线.jsonl")
             .read_text(encoding="utf-8").splitlines() if l.strip()}
    _txt = pathlib.Path(recovered_path).read_text(encoding="utf-8")
    _rows = list(csv.DictReader(io.StringIO(_txt)))
    _errs = []
    _ids = [r.get("snippet_id") for r in _rows]
    if len(_ids) != len(set(_ids)):
        _errs.append("★ snippet_id 重复")
    for _r in _rows:
        _b = _base.get(_r.get("snippet_id"))
        if not _b:
            _errs.append(f'★ 未知 snippet_id：{_r.get("snippet_id")}')
            continue
        if (_r.get("rfc_sha256") or "") != _b["rfc_sha256"]:
            _errs.append(f'★ { _r["snippet_id"] }：rfc_sha256 不一致（★ 证据被改）')
        if (_r.get("★ 原文（不可编辑）") or "") != _b["★ 证据原文"]:
            _errs.append(f'★ {_r["snippet_id"]}：原文与基线不一致（★ 证据被改）')
        if (_r.get("★ 证据跨度（行号）") or "") != \
                f'{_b["★ 证据跨度（行号）"][0]}-{_b["★ 证据跨度（行号）"][1]}':
            _errs.append(f'★ {_r["snippet_id"]}：证据跨度不一致')
        if (_r.get("★ 章节类型") or "") != _b["★ 章节类型"]:
            _errs.append(f'★ {_r["snippet_id"]}：章节类型不一致')
    return (not _errs), {"★ 文件": tag, "★ 行数": len(_rows),
                        "★ 错误数": len(_errs), "★ 错误（前 10）": _errs[:10],
                        "★ 回收文件 SHA256": hashlib.sha256(
                            pathlib.Path(recovered_path).read_bytes()).hexdigest()}


if __name__ == "__main__":
    import argparse
    _ap = argparse.ArgumentParser()
    _ap.add_argument("--verify", nargs="*", default=[],
                    help="★ 回收文件路径（★ 可多个）")
    _a = _ap.parse_args()
    if _a.verify:
        _all_ok = True
        for _p in _a.verify:
            _ok, _rep = verify_recovered(_p, pathlib.Path(_p).name)
            _all_ok = _all_ok and _ok
            print(f"  ★ {_rep['★ 文件']}: 行 {_rep['★ 行数']}｜错误 {_rep['★ 错误数']}"
                  f"｜sha256 {_rep['★ 回收文件 SHA256'][:16]}")
            for _e in _rep["★ 错误（前 10）"]:
                print(f"      - {_e}")
        print(f"  ★★ 回收校验：{'✅ 全部通过' if _all_ok else '❌ 存在差异 ⇒ 须停止后续评估'}")
        sys.exit(0 if _all_ok else 1)
    print("  ★ 用法：python p72_freeze_pool.py --verify <回收文件...>")
