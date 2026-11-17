# -*- coding: utf-8 -*-
"""★ R2 工具：★ **统一 dict 键命名**（★ 去掉 `★ ` 前缀）。

★ ★ 为什么要做：★ `★` 前缀在展示层好看，★ 但在代码里极易写错
★ ★ （★ 如 `"★ 独立性等级"` vs `"独立性等级"`）⇒ ★ **内部一律用 ASCII/纯中文键，
★   展示时（★ XLSX 表头 / Markdown）再统一加前缀**。

用法：★ python normalize_keys.py <脚本路径...>
"""
import pathlib
import re
import sys

# ★ dict 字面量里的键："★ Xxx" ⇒ "Xxx"
_RE_KEY = re.compile(r'"★\s*([^"]+)"\s*:')
# ★ 访问处的键：["★ Xxx"] ⇒ ["Xxx"]
_RE_ACCESS = re.compile(r'\[\s*"★\s*([^"]+)"\s*\]')


def normalize(src: str) -> str:
    """★ 规整：★ 去掉键与访问处的 `★ ` 前缀（★ 只动引号内的内容，★ 不动字符串内容）。"""
    # ★ 先处理访问处（★ 避免被 key 规则误伤）
    src = _RE_ACCESS.sub(lambda m: f'["{m.group(1)}"]', src)
    # ★ 再处理 dict 键
    src = _RE_KEY.sub(lambda m: f'"{m.group(1)}":', src)
    return src


def main():
    if len(sys.argv) < 2:
        print("用法：python normalize_keys.py <脚本路径...>")
        return 1
    for _p in sys.argv[1:]:
        _f = pathlib.Path(_p)
        _src = _f.read_text(encoding="utf-8")
        _new = normalize(_src)
        if _new != _src:
            _f.write_text(_new, encoding="utf-8")
            print(f"  ★ 已规整：{_f.name}（★ {len(_src)} → {len(_new)} 字符）")
        else:
            print(f"  ★ 无需变更：{_f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
