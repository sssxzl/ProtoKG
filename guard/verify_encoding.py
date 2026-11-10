# -*- coding: utf-8 -*-
"""guard/verify_encoding.py —— **编码卫生护栏**（UTF-8 统一 / 防乱码复发）。

★ 为什么需要它
  批次 2.5 收尾时发现：**部分 UTF-8 文本在读写或解码环节被按错误字符集解析**，
  产生 mojibake（典型症状：``锟斤拷`` / ``Ã©`` / ``æ—¶`` / ``⚶``）。
  根因有两类：
    ① **读时用错字符集**：文件以 latin-1/cp1252 读入、再以 UTF-8 写出
       ⇒ 字节层面 ``b"\\xc3\\x83\\xc2\\xa1"``（= ``MihÃ¡ly``）⇒ 可逆还原。
    ② **上游原生混合编码**：第三方源码（如 kamailio）本就是 latin-1
       ⇒ **不是我们的 mojibake**，改它反而偏离上游 ⇒ 登记豁免、只报告不改。

★ 本护栏检四项
  E1 mojibake      —— 文件含**可逆**的 latin-1/cp1252→UTF-8 双重编码痕迹
  E2 非法 UTF-8    —— 文件不能整体按 UTF-8 解码（且不在豁免清单）
  E3 混合行尾      —— 同一文件里 CRLF 与裸 LF 混用（跨平台换行不一致）
  E4 缺 encoding   —— 文本读写调用未显式指定 ``encoding="utf-8"``
                     （在 Windows 上默认走 locale 编码 cp936 ⇒ 换机器就炸）

★ 用法
  python guard/verify_encoding.py                # 只检查，退出码 0=干净 1=有违规
  python guard/verify_encoding.py --json out.json # 机器可读结果
  python guard/verify_encoding.py --fix          # 修复可逆 mojibake + 混合行尾
                                                       （★ 不动 E2 的上游原生文件）

★ 豁免清单：``guard/baseline/encoding_known_issues.txt``
  每行 ``<相对路径>\\t<原因>``（``#`` 开头为注释）⇒ 这些路径的 E2 不算违规。
"""
from __future__ import annotations

import argparse
import ast
import json
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: 不扫描的目录（构建产物 / 缓存 / 生成物 / VCS）
SKIP_DIRS = {
    ".git", "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache",
    "out", "guard", "derived", "node_modules", "local/encoding_backup",
    "local/guard_out",
    # ★ IDE 工作区文件（**不入库**，内容随编辑器状态漂移 ⇒ 扫描它们只会噪声）
    #   实测踩到：PyCharm 写 ``.idea/workspace.xml``（混合行尾）⇒ 护栏判红
    ".idea", ".vscode",
}
#: 不扫描的路径前缀（相对仓库根）
SKIP_PREFIX = ("out/", "guard/", "derived/", ".ruff_cache/", "local/encoding_backup/")

#: 按文本处理的扩展名（``""`` 表示无扩展名的 README 等）
TEXT_EXT = {
    ".py", ".md", ".json", ".jsonl", ".sh", ".txt", ".yaml", ".yml", ".ini",
    ".cfg", ".sql", ".c", ".h", ".cpp", ".js", ".html", ".xml", ".csv", ".rst",
    ".conf", ".toml", "",
}
#: 单文件大小上限（跳过超大文件，避免体检本身变慢）
MAX_BYTES = 50_000_000

#: mojibake 标记字符（latin-1/cp1252 → UTF-8 双重编码的典型残留）
_MOJI_MARK = set("ÃÂÅÐÞ")
_MOJI_MARK2 = set("€„™œšž")
#: 往返时优先尝试的字符集（cp1252 能编码 0x80-0x9F 的特殊码位，latin-1 不能）
_ROUNDTRIP_ENCODINGS = ("cp1252", "latin-1")


def _suspect(text: str) -> int:
    """mojibake 标记字符数（启发式：双重编码的残留特征）。"""
    n = 0
    for ch in text:
        o = ord(ch)
        if 0x80 <= o <= 0x9F or ch in _MOJI_MARK or ch in _MOJI_MARK2:
            n += 1
    return n


def _try_decode(chunk: str) -> str | None:
    """把一段文本按 cp1252/latin-1 编码回字节再按 UTF-8 解码（往返还原）。"""
    for enc in _ROUNDTRIP_ENCODINGS:
        try:
            raw = chunk.encode(enc)
        except UnicodeEncodeError:
            continue
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            continue
    return None


def fix_mojibake(text: str, max_len: int = 8) -> tuple[str, int]:
    """逐位置尝试「最长片段按 UTF-8 还原」，仅当可疑字符数下降才采纳。

    迭代使用（文件可能被反复以错误字符集处理过 ⇒ 单轮还原不彻底）。
    """
    total = 0
    for _ in range(6):
        out: list[str] = []
        i = 0
        fixes = 0
        while i < len(text):
            applied = False
            for length in range(max_len, 1, -1):
                chunk = text[i:i + length]
                decoded = _try_decode(chunk)
                if decoded is not None and _suspect(decoded) < _suspect(chunk):
                    out.append(decoded)
                    i += length
                    fixes += 1
                    applied = True
                    break
            if not applied:
                out.append(text[i])
                i += 1
        text = "".join(out)
        total += fixes
        if fixes == 0:
            break
    return text, total


def _iter_text_files(root: Path):
    """遍历需要体检的文本文件（跳过目录/扩展名/超大文件）。"""
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if any(rel.startswith(pref) for pref in SKIP_PREFIX):
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            if p.stat().st_size > MAX_BYTES:
                continue
        except OSError:
            continue
        yield p, rel


def _missing_encoding_calls(path: Path) -> list[tuple[int, str]]:
    """AST 扫描：未显式指定 encoding 的文本读写调用。

    ★ 只认**内置** ``open()``（排除 ``tarfile.open`` / ``zipfile.open`` 等）。
    ★ 用 ``ast.parse(bytes)`` ⇒ 偏移是 **UTF-8 字节偏移**，与字符串切片一致。
    """
    try:
        raw = path.read_bytes()
        with warnings.catch_warnings():
            # 第三方源码可能有非法转义序列 ⇒ 只警告不报错（与被测对象无关）
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(raw)
    except (SyntaxError, OSError):
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if any(k.arg == "encoding" for k in node.keywords):
            continue
        fn = node.func
        if isinstance(fn, ast.Name) and fn.id == "open":
            modes = [a.value for a in node.args
                     if isinstance(a, ast.Constant) and isinstance(a.value, str)
                     and len(a.value) <= 3 and set(a.value) <= set("rwbta+")]
            if "b" in (modes[0] if modes else "r"):
                continue          # 二进制模式 ⇒ 无编码问题
            hits.append((node.lineno, "open()"))
        elif isinstance(fn, ast.Attribute) and fn.attr in ("read_text", "write_text"):
            hits.append((node.lineno, fn.attr + "()"))
    return hits


def read_known_issues(path: Path) -> dict[str, str]:
    """读豁免清单：``<相对路径>\\t<原因>``。"""
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [x.strip() for x in line.split("\t")]
        rel = parts[0]
        if len(parts) >= 3:
            # 精细豁免：<路径>\t<违规码>\t<原因>（只豁免指定码）
            out[f"{rel}\t{parts[1]}"] = parts[2]
        else:
            out[rel] = parts[1] if len(parts) > 1 else "已登记"
    return out


def _exempt(known: dict[str, str], rel: str, code: str) -> str | None:
    """查豁免：先查「路径+码」的精细豁免，再查「整路径」豁免。"""
    return known.get(f"{rel}\t{code}") or known.get(rel)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="编码卫生护栏（UTF-8 统一 / 防乱码复发）")
    ap.add_argument("--root", default=str(ROOT), help="仓库根目录")
    ap.add_argument("--known-issues",
                    default=str(ROOT / "guard" / "baseline"
                                / "encoding_known_issues.txt"),
                    help="豁免清单（E2 上游原生非 UTF-8 文件）")
    ap.add_argument("--json", dest="json_out", help="机器可读结果输出路径")
    ap.add_argument("--fix", action="store_true",
                    help="修复可逆 mojibake 与混合行尾（不动 E2 上游文件）")
    args = ap.parse_args(argv)

    root = Path(args.root).resolve()
    known = read_known_issues(Path(args.known_issues))

    violations: list[dict] = []
    fixed_files: list[dict] = []
    stats = {"scanned": 0, "mojibake_files": 0, "non_utf8_files": 0,
             "mixed_eol_files": 0, "missing_encoding_calls": 0}

    for path, rel in _iter_text_files(root):
        stats["scanned"] += 1
        raw = path.read_bytes()
        if not raw:
            continue

        # ---- E1 / E2：解码与 mojibake ----
        valid_utf8 = True
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            valid_utf8 = False
            text = raw.decode("utf-8", errors="replace")

        if not valid_utf8:
            stats["non_utf8_files"] += 1
            reason = _exempt(known, rel, "E2")
            if reason is None:
                violations.append({
                    "code": "E2", "path": rel,
                    "detail": "文件不能整体按 UTF-8 解码（且未登记豁免）",
                })
            else:
                violations.append({
                    "code": "E2-exempt", "path": rel,
                    "detail": f"上游原生非 UTF-8（已登记豁免：{reason}）",
                })

        suspect = _suspect(text)
        if suspect:
            fixed_text, nfix = fix_mojibake(text)
            if nfix and _suspect(fixed_text) < suspect:
                stats["mojibake_files"] += 1
                if args.fix:
                    nb = fixed_text.encode("utf-8")
                    if nb.count(b"\r\n") == raw.count(b"\r\n") and \
                            nb.count(b"\n") == raw.count(b"\n"):
                        path.write_bytes(nb)
                        fixed_files.append({"path": rel, "fixes": nfix,
                                            "kind": "mojibake"})
                        text = fixed_text
                        suspect = _suspect(text)
                    else:
                        violations.append({
                            "code": "E1", "path": rel,
                            "detail": f"含 {nfix} 处可逆 mojibake，但行尾/行数会变 ⇒ 拒绝自动改",
                        })
                if suspect:
                    reason = _exempt(known, rel, "E1")
                    if reason is not None:
                        violations.append({
                            "code": "E1-exempt", "path": rel,
                            "detail": f"含 mojibake 标记 {suspect} 个"
                                      f"（已登记豁免：{reason}）",
                        })
                    else:
                        violations.append({
                            "code": "E1", "path": rel,
                            "detail": f"含 mojibake 标记 {suspect} 个"
                                      + (f"（可还原 {nfix} 处）" if nfix else "（不可还原）"),
                        })
            elif suspect:
                stats["mojibake_files"] += 1
                reason = _exempt(known, rel, "E1")
                if reason is not None:
                    violations.append({
                        "code": "E1-exempt", "path": rel,
                        "detail": f"含 mojibake 标记 {suspect} 个（已登记豁免：{reason}）",
                    })
                else:
                    violations.append({
                        "code": "E1", "path": rel,
                        "detail": f"含 mojibake 标记 {suspect} 个（不可还原）",
                    })

        # ---- E3：混合行尾 ----
        n_crlf = raw.count(b"\r\n")
        n_lf = raw.count(b"\n")
        if n_lf and n_crlf and n_crlf != n_lf:
            stats["mixed_eol_files"] += 1
            if args.fix:
                path.write_bytes(raw.replace(b"\r\n", b"\n"))
                fixed_files.append({"path": rel, "fixes": n_crlf, "kind": "mixed-eol"})
            else:
                violations.append({
                    "code": "E3", "path": rel,
                    "detail": f"混合行尾（CRLF {n_crlf} / 裸 LF {n_lf - n_crlf}）",
                })

        # ---- E4：缺 encoding ----
        if path.suffix.lower() == ".py":
            miss = _missing_encoding_calls(path)
            if miss:
                stats["missing_encoding_calls"] += len(miss)
                reason = _exempt(known, rel, "E4")
                if reason is not None:
                    violations.append({
                        "code": "E4-exempt", "path": rel,
                        "detail": f"{len(miss)} 处缺 encoding（已登记豁免：{reason}）",
                    })
                else:
                    violations.append({
                        "code": "E4", "path": rel,
                        "detail": f"{len(miss)} 处文本读写未指定 encoding："
                                  + ", ".join(f"{ln}:{lab}" for ln, lab in miss[:5]),
                    })

    real = [v for v in violations if not v["code"].endswith("-exempt")]
    result = {
        "root": str(root),
        "stats": stats,
        "violations": violations,
        "violation_count": len(real),
        "fixed": fixed_files,
        "verdict": "OK" if not real else "VIOLATIONS",
    }

    print("== 编码卫生护栏 ==")
    print(f"   扫描 {stats['scanned']} 个文本文件")
    print(f"   mojibake 文件 {stats['mojibake_files']} · 非 UTF-8 文件 "
          f"{stats['non_utf8_files']} · 混合行尾 {stats['mixed_eol_files']} · "
          f"缺 encoding {stats['missing_encoding_calls']} 处")
    if args.fix and fixed_files:
        print(f"   ★ 已修复 {len(fixed_files)} 个文件：")
        for f in fixed_files[:20]:
            print(f"      - {f['path']}  ({f['kind']}, {f['fixes']} 处)")
    if real:
        print(f"   ❌ 违规 {len(real)} 项：")
        for v in real[:30]:
            print(f"      [{v['code']}] {v['path']}  — {v['detail']}")
    exempt = [v for v in violations if v["code"].endswith("-exempt")]
    if exempt:
        print(f"   ⚑ 已登记豁免 {len(exempt)} 项（上游原生编码，不修改）：")
        for v in exempt[:10]:
            print(f"      ~ {v['path']}  — {v['detail']}")
    print(f"\n== 结论：{'✅ 编码卫生达标' if not real else '❌ 存在编码违规'} ==")

    if args.json_out:
        outp = Path(args.json_out)
        outp.parent.mkdir(parents=True, exist_ok=True)
        outp.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")

    return 0 if not real else 1


if __name__ == "__main__":
    sys.exit(main())
