# -*- coding: utf-8 -*-
"""★ H0 §三 P0：★ **来源身份解析与 SHA256 保全契约**（★ 影子层，★ 不改生产）。

★ 契约：``source_reference → normalized_document_id → source_file → source_sha256``

★ 六条硬要求（★ 用户 §三）：
  1. ★ 保留原始 source_reference，★ 不覆盖
  2. ★ 规范化结果必须**可复算**
  3. ★ **不允许通过模糊文件名匹配**选择错误 RFC
  4. ★ 文件找不到 ⇒ 明确记 **unresolved**，★ **不得假造 SHA256**
  5. ★ **不得接受越界路径或任意文件访问**
  6. ★ 原始证据与来源文档版本必须绑定
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import urllib.parse

RESOLVED = "resolved"
UNRESOLVED = "unresolved"
AMBIGUOUS = "ambiguous"

# ★ 已知 source 形态（★ 审计自生产源码）
#   · prose_semantics : "file:<doc>#@<line>"
#   · rfc_extractor   : "file:<doc>#<section>"
#   · coverage_ledger : 裸路径或 file: 前缀
_RE_FILE_PREFIX = re.compile(r"^file:\s*", re.I)
_RE_SPLIT_AT = re.compile(r"#@")
_RE_SPLIT_HASH = re.compile(r"#(?!\@)")


def _strip_prefix(ref: str) -> str:
    return _RE_FILE_PREFIX.sub("", str(ref or "").strip())


def _split_locator(ref: str):
    """★ 拆出「文档部分」与「定位部分」（★ 保留原始形态供审计）。"""
    _r = _strip_prefix(ref)
    if "#@" in _r:
        _doc, _loc = _r.split("#@", 1)
        return _doc, _loc, "#@"
    if "#" in _r:
        _doc, _loc = _r.split("#", 1)
        return _doc, _loc, "#"
    return _r, "", ""


def normalize_document_id(source_reference: str) -> dict:
    """★ 规范化（★ **纯函数，★ 可复算，★ 不访问文件系统**）。

    Returns ``{source_reference, normalized_document_id, locator, locator_kind, notes}``
    """
    _ref = str(source_reference or "")
    _doc, _loc, _kind = _split_locator(_ref)
    _notes = []
    # ★ URI 解码（★ 百分号编码）
    if "%" in _doc:
        _dec = urllib.parse.unquote(_doc)
        if _dec != _doc:
            _notes.append("★ URI 百分号解码")
        _doc = _dec
    # ★ 路径规范化（★ 不解析 symlink，★ 只做词法规范化）
    _norm = pathlib.PurePosixPath(_doc)
    _parts = []
    for _p in _norm.parts:
        if _p == ".":
            continue
        if _p == "..":
            if _parts:
                _parts.pop()
            else:
                _notes.append("★ 上跳越界段被丢弃")
            continue
        _parts.append(_p)
    _doc_norm = "/".join(_parts)
    # ★ 绝对路径 ⇒ 相对化（★ 只保留末两段：protocol/spec/doc）
    if _doc_norm.startswith("/"):
        _notes.append("★ 绝对路径 ⇒ 已相对化")
        _segs = [x for x in _doc_norm.split("/") if x]
        _doc_norm = "/".join(_segs[-3:]) if len(_segs) >= 3 else "/".join(_segs)
    return {
        "source_reference": _ref,
        "normalized_document_id": _doc_norm,
        "locator": _loc,
        "locator_kind": _kind or "(无定位)",
        "notes": _notes,
    }


def resolve_source(source_reference: str, *, kb_root) -> dict:
    """★ 解析 source ⇒ 定位源文件并计算 SHA256（★ **不模糊匹配**）。

    ★ 定位规则（★ 确定性）：
      ① ``normalized_document_id`` 若是相对路径（★ 含 protocol/spec/）⇒ 直接拼接
      ② 若是裸文件名 ⇒ 在 ``<kb_root>/<protocol>/spec/`` 下按**精确名**查找
      ③ ★ **多协议同名** ⇒ **ambiguous**（★ **绝不任选一个**）
      ④ ★ 找不到 ⇒ **unresolved**（★ **不假造 SHA256**）
      ⑤ ★ **越界**（``..`` 逃出 kb_root）⇒ **unresolved**
    """
    _out = normalize_document_id(source_reference)
    _kb = pathlib.Path(kb_root).resolve()
    _doc = _out["normalized_document_id"]
    _cands = []
    _why = []
    if not _doc:
        _out.update({"status": UNRESOLVED, "source_file": None,
                     "source_sha256": None,
                     "reason": "★ 文档部分为空 ⇒ unresolved"})
        return _out
    if _doc.startswith("/"):
        _why.append("★ 绝对路径已相对化")
    _parts = _doc.split("/")
    if len(_parts) >= 3 and _parts[0] != ".":
        _p = _kb / _doc
        if _p.is_file():
            _cands = [_p]
        else:
            # ★ 可能是 protocol/spec/doc 三段已带，★ 也可能是 protocol/doc
            _p2 = _kb / _parts[0] / "spec" / _parts[-1]
            if _p2.is_file():
                _cands = [_p2]
    else:
        # ★ 裸文件名 ⇒ 逐协议精确查找
        for _proto in sorted(p.name for p in _kb.iterdir() if p.is_dir()):
            _p = _kb / _proto / "spec" / _doc
            if _p.is_file():
                _cands.append(_p)
    # ★ 越界检查
    _cands = [c for c in _cands if _is_inside(_kb, c)]
    if not _cands:
        _out.update({"status": UNRESOLVED, "source_file": None,
                     "source_sha256": None,
                     "reason": "★ 源文件未定位 ⇒ unresolved（★ **不假造 SHA256**）"
                               + (f"（★ {_why}）" if _why else "")})
        return _out
    if len(_cands) > 1:
        _out.update({"status": AMBIGUOUS,
                     "source_file": None, "source_sha256": None,
                     "reason": f"★ 同名文件出现在 {len(_cands)} 个协议下 ⇒ "
                               "★ **ambiguous（★ 绝不任选一个）**",
                     "candidates": [str(c.relative_to(_kb)) for c in _cands]})
        return _out
    _f = _cands[0]
    _out.update({
        "status": RESOLVED,
        "source_file": str(_f.relative_to(_kb)),
        "source_sha256": hashlib.sha256(_f.read_bytes()).hexdigest(),
        "reason": "★ 已定位并绑定版本哈希" + (f"（★ {_why}）" if _why else "")})
    return _out


def _is_inside(root: pathlib.Path, p: pathlib.Path) -> bool:
    """★ 越界检查（★ 防止 ``..`` 逃逸或任意文件访问）。"""
    try:
        _r = p.resolve()
        _r.relative_to(root)
        return True
    except (ValueError, OSError):
        return False


__all__ = ["RESOLVED", "UNRESOLVED", "AMBIGUOUS",
           "normalize_document_id", "resolve_source"]
