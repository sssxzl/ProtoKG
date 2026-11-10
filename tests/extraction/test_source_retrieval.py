"""tests/fused/test_source_retrieval.py —— AutoSeeder 检索层（切片/query/后处理）。"""
from __future__ import annotations

import tempfile
from pathlib import Path

from core.fused.extraction.source_retrieval import (
    slice_code, _postprocess, AUTOSEEDER_QUERIES,
)


def _make_tree(root: Path):
    """构造多目标协议源码树：扁平文件 + 子目录文件。"""
    (root / "top.c").write_text("int state = 0;\n" * 50, encoding="utf-8")
    sub = root / "implA"
    sub.mkdir()
    (sub / "main.c").write_text("void handle_cmd() {}\n" * 50, encoding="utf-8")
    sub2 = root / "implB"
    sub2.mkdir()
    (sub2 / "main.c").write_text("int session_state;\n" * 50, encoding="utf-8")
    return root


def test_slice_code_recurses_subdirs():
    """多目标协议：源码在子目录（ftp/bftpd 等），递归切片不能漏。"""
    with tempfile.TemporaryDirectory() as d:
        root = _make_tree(Path(d))
        chunks = slice_code(root)
    files = {c["file"] for c in chunks}
    # 顶层 + 子目录都要覆盖，且子目录文件用相对路径区分（避免同名 main.c 混淆）
    assert "top.c" in files
    assert "implA/main.c" in files
    assert "implB/main.c" in files
    assert len(chunks) > 0


def test_slice_code_preserves_subdir_in_file_field():
    """两个子目录的同名 main.c 必须靠相对路径区分。"""
    with tempfile.TemporaryDirectory() as d:
        root = _make_tree(Path(d))
        chunks = slice_code(root)
    main_files = {c["file"] for c in chunks if c["file"].endswith("main.c")}
    assert main_files == {"implA/main.c", "implB/main.c"}


def test_queries_are_protocol_agnostic():
    """7 条 query 协议无关（不含具体协议名，换协议零配置）。"""
    assert len(AUTOSEEDER_QUERIES) == 7
    joined = " ".join(AUTOSEEDER_QUERIES).lower()
    for proto in ("rtsp", "smtp", "ftp", "sip", "http", "dns"):
        assert proto not in joined


def test_postprocess_dedup_and_merge():
    blocks = [
        {"file": "a.c", "start": 0, "text": "x" * 100},
        {"file": "a.c", "start": 0, "text": "x" * 100},  # 重复
        {"file": "b.c", "start": 0, "text": "y" * 100},
    ]
    out = _postprocess(blocks, max_block_chars=1000)
    texts = "".join(b["text"] for b in out)
    assert texts.count("x" * 100) == 1  # 去重
    assert "y" * 100 in texts
