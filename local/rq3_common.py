# -*- coding: utf-8 -*-
"""local/rq3_common.py —— RQ3「种子聚焦」消融实验的共享常量与工具。

设计原则（对齐技术方案 §11.7 跨文件硬约定）：

  C1 配置单一来源      → 所有数值配置只写在 `local/rq3_config.json`，本模块只读取。
  C2 命名函数单一来源  → 容器名 / 输出目录 / 语料路径 / CSV 表头 **只在本模块定义**，
                         其他脚本一律 `import rq3_common`，禁止散落硬编码。
  C3 字典唯一权威      → 字典的期望 token 数与 MD5 记在 rq3_config.json，
                         由编排预检核对 → `DICT_FROZEN.json` 归档 → 论文引用。
  C4 manifest 是归因唯一依据 → 跨组归因以 MD5 为主键，禁止按文件名猜测层归属。
  C5 数值缺失写 `NA`   → 不写 0、不写空。

本模块**不依赖任何第三方库**（仅标准库），以便在 VM 上直接以 `python3` 运行。
"""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional, Sequence

#: 项目根（local/rq3_common.py -> local -> <project>/）
PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: RQ3 产物根目录
RQ3_ROOT = PROJECT_ROOT / "derived" / "rq3"

#: RQ3 集中配置文件（唯一配置源）
CONFIG_PATH = Path(__file__).resolve().parent / "rq3_config.json"

#: 数值缺失的统一占位符（约定 C5）
NA = "NA"

#: manifest schema 版本
MANIFEST_SCHEMA_VERSION = "1.0"

#: RQ3 的四个聚焦组（论文表 18 的 A/B/C 三行 + 附录 D 组）
GROUPS: tuple[str, ...] = ("A", "B", "C", "D")

#: 两个 fuzzer（Wave 1 = chatafl，Wave 2 = aflnet）
FUZZERS: tuple[str, ...] = ("chatafl", "aflnet")

#: manifest 每条种子必须具备的字段（验收断言用）
REQUIRED_SEED_FIELDS: tuple[str, ...] = (
    "index", "rank", "filename", "md5", "bytes", "layer", "layer_name",
    "generated_by", "score", "description", "legal_illegal", "pattern_tags",
    "stream", "methods", "group",
)

# ===========================================================================
# CSV / TSV 表头（约定 §11.4「固定，不得改动」）
# ===========================================================================

P1_HEADER: tuple[str, ...] = (
    "group", "rep", "fuzzer", "n_states", "n_edges", "paths_total_at_p1",
    "init_queue_count",
)

P2_HEADER: tuple[str, ...] = (
    "group", "rep", "fuzzer", "n_states", "n_edges", "bitmap_cvg",
    "unique_crashes", "unique_hangs", "paths_total", "execs_done",
    "chat_times_max",
)

SUMMARY_HEADER: tuple[str, ...] = (
    "group", "fuzzer", "metric", "n_reps", "mean", "std", "raw_values",
)

TIMESERIES_HEADER: tuple[str, ...] = (
    "group", "fuzzer", "rep", "unix_time", "rel_hours", "cycles_done",
    "paths_total", "map_size", "unique_crashes", "unique_hangs", "max_depth",
    "execs_per_sec", "n_nodes", "n_edges", "chat_times",
)

QUEUE_INDEX_HEADER: tuple[str, ...] = (
    "container", "group", "fuzzer", "rep", "snapshot_tag", "entry_name",
    "entry_md5", "root_seed", "kind", "hit_P1", "hit_P2", "hit_P3", "hit_P4",
    "layer",
)

CRASHES_INDEX_HEADER: tuple[str, ...] = (
    "container", "group", "fuzzer", "rep", "entry_name", "entry_md5",
    "root_seed", "layer",
)

ENRICHMENT_AUDIT_HEADER: tuple[str, ...] = (
    "container", "group", "fuzzer", "rep", "enriched_in_seeds",
    "enriched_in_queue", "queue_total", "chat_times_max", "verdict",
)

#: dry-run 判定结果 TSV 表头
DRYRUN_HEADER: tuple[str, ...] = (
    "filename", "layer", "score", "legal_illegal_expected", "verdict",
    "retries_used", "note",
)

#: 队列快照标签（约定 §11.4）
SNAPSHOT_TAGS: tuple[str, ...] = ("T3600s", "T7200s", "final")

#: 队列条目类别
QUEUE_KINDS: tuple[str, ...] = ("initial_copy", "derived")


# ===========================================================================
# 命名（约定 C2：命名函数单一来源）
# ===========================================================================

def container_name(group: str, fuzzer: str, rep: int) -> str:
    """RQ3 容器名：`rq3_{group}_{fuzzer}_r{rep}`（例 `rq3_C_chatafl_r3`）。"""
    return f"rq3_{group}_{fuzzer}_r{int(rep)}"


def out_dir_name(group: str, fuzzer: str) -> str:
    """容器输出目录名：`{group}_{fuzzer}`（例 `C_chatafl`）。"""
    return f"{group}_{fuzzer}"


def group_label(group: str) -> str:
    """论文表 18 / 附录里的组名（中文标签）。"""
    return {
        "A": "A 守正",
        "B": "B 漏洞导向",
        "C": "C 完整聚焦",
        "D": "D 解耦（附录）",
    }.get(group, group)


def fuzzer_label(fuzzer: str) -> str:
    """fuzzer 的论文展示名。"""
    return {"chatafl": "Chatafl", "aflnet": "aflnet"}.get(fuzzer, fuzzer)


# ===========================================================================
# 路径
# ===========================================================================

def rq3_dir(*parts: str) -> Path:
    """RQ3 产物根下的路径（自动创建父目录）。"""
    p = RQ3_ROOT.joinpath(*parts)
    return p


def group_seed_dir(group: str, create: bool = False) -> Path:
    """某组的语料目录 `derived/rq3/<group>/seeds/`。"""
    p = RQ3_ROOT / group / "seeds"
    if create:
        p.mkdir(parents=True, exist_ok=True)
    return p


def group_manifest_path(group: str) -> Path:
    """某组的 manifest 路径 `derived/rq3/<group>/manifest.json`。"""
    return RQ3_ROOT / group / "manifest.json"


def dict_dir() -> Path:
    """冻结字典目录 `derived/rq3/dict/`。"""
    return RQ3_ROOT / "dict"


def collect_dir(timestamp: str) -> Path:
    """采集产物目录 `derived/rq3/collect/<ts>/`。"""
    return RQ3_ROOT / "collect" / timestamp


def groups_json_path() -> Path:
    """组 → 容器 / 字典 / 条数 的映射文件（编排脚本的唯一输入）。"""
    return RQ3_ROOT / "groups.json"


def dict_frozen_path() -> Path:
    """字典冻结记录。"""
    return dict_dir() / "DICT_FROZEN.json"


# ===========================================================================
# 配置
# ===========================================================================

def load_config(path: Optional[Path] = None) -> dict:
    """读取 `local/rq3_config.json`（RQ3 唯一配置源）。"""
    cfg_path = Path(path) if path else CONFIG_PATH
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ===========================================================================
# MD5 / 摘要工具
# ===========================================================================

def md5_bytes(data: bytes) -> str:
    """字节流的 MD5（32 位小写 hex）。"""
    return hashlib.md5(data).hexdigest()


def md5_file(path: Path) -> str:
    """文件的 MD5。"""
    return md5_bytes(Path(path).read_bytes())


def md5_dir(directory: Path, pattern: str = "*.raw") -> dict[str, str]:
    """目录下匹配文件的 `{文件名: MD5}` 映射。"""
    out: dict[str, str] = {}
    for f in sorted(Path(directory).glob(pattern)):
        if f.is_file():
            out[f.name] = md5_file(f)
    return out


def md5_set(directory: Path, pattern: str = "*.raw") -> set[str]:
    """目录下匹配文件的 MD5 **集合**（跨组归因的主键集合）。"""
    return set(md5_dir(directory, pattern).values())


def dict_token_count(path: Path) -> int:
    """字典文件的 token 数（非空行数）。"""
    text = Path(path).read_text(encoding="utf-8")
    return len([ln for ln in text.splitlines() if ln.strip()])


def dict_tokens(path: Path) -> set[str]:
    """字典文件的 token 集合（去掉外层引号）。"""
    text = Path(path).read_text(encoding="utf-8")
    return {ln.strip().strip('"') for ln in text.splitlines() if ln.strip()}


# ===========================================================================
# 统计（ddof=1；缺失值不参与计算）
# ===========================================================================

def mean_std(values: Iterable[Any]) -> tuple[Optional[float], Optional[float]]:
    """返回 `(mean, std)`；std 使用样本标准差（ddof=1）。无有效值时返回 `(None, None)`。

    `None` / `NA` / 空串 / 非数值一律视为缺失（约定 C5）。
    """
    nums: list[float] = []
    for v in values:
        if v is None:
            continue
        if isinstance(v, str):
            v = v.strip()
            if v == "" or v == NA:
                continue
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return (None, None)
    m = statistics.mean(nums)
    sd = statistics.stdev(nums) if len(nums) > 1 else 0.0
    return (m, sd)


def fmt(value: Optional[float], spec: str = "{:.2f}") -> str:
    """格式化数值；缺失写 `NA`。"""
    if value is None:
        return NA
    return spec.format(value)


def paired_win_rate(diffs: Sequence[float]) -> tuple[int, int]:
    """配对差值的胜率（`> 0` 计胜；`== 0` 计平，不计胜）。"""
    wins = sum(1 for d in diffs if d > 0)
    return (wins, len(diffs))


# ===========================================================================
# CSV / TSV 读写（幂等：先写临时文件再 mv）
# ===========================================================================

def _atomic_write(path: Path, text: str, encoding: str = "utf-8") -> Path:
    """原子写：先写 `<path>.tmp` 再 `mv` 覆盖（约定 C6）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding, newline="")
    tmp.replace(path)
    return path


def write_csv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Path:
    """写 CSV（原子替换）。数值统一 `str()`；None → `NA`。"""
    import io
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(list(header))
    for r in rows:
        w.writerow([NA if v is None else v for v in r])
    return _atomic_write(Path(path), buf.getvalue())


def read_csv(path: Path) -> list[dict]:
    """读 CSV → list[dict]。"""
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_tsv(path: Path, header: Sequence[str], rows: Iterable[Sequence[Any]]) -> Path:
    """写 TSV（原子替换）。"""
    import io
    buf = io.StringIO()
    w = csv.writer(buf, delimiter="\t", lineterminator="\n")
    w.writerow(list(header))
    for r in rows:
        w.writerow([NA if v is None else v for v in r])
    return _atomic_write(Path(path), buf.getvalue())


def read_tsv(path: Path) -> list[dict]:
    """读 TSV → list[dict]。"""
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_json(path: Path, payload: Any) -> Path:
    """写 JSON（原子替换，UTF-8 不转义中文，缩进 2）。"""
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    return _atomic_write(Path(path), text)


def read_json(path: Path) -> Any:
    """读 JSON。"""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ===========================================================================
# manifest 读写（约定 C4：manifest 是归因的唯一依据）
# ===========================================================================

def load_manifest(group: str) -> dict:
    """读取某组的 manifest.json。"""
    return read_json(group_manifest_path(group))


def iter_manifest_seeds(manifest: dict) -> Iterator[dict]:
    """遍历 manifest 的种子条目。"""
    for s in manifest.get("seeds", []):
        yield s


def manifest_by_filename(manifest: dict) -> dict[str, dict]:
    """`{文件名: 种子条目}`。"""
    return {s["filename"]: s for s in manifest.get("seeds", [])}


def manifest_by_md5(manifest: dict) -> dict[str, dict]:
    """`{MD5: 种子条目}`（跨组归因主键）。"""
    return {s["md5"]: s for s in manifest.get("seeds", [])}


def manifest_by_index(manifest: dict) -> dict[str, dict]:
    """`{两位序号: 种子条目}`（血缘兜底解析用）。"""
    return {f"{int(s['index']):02d}": s for s in manifest.get("seeds", [])}


__all__ = [
    "PROJECT_ROOT", "RQ3_ROOT", "CONFIG_PATH", "NA", "MANIFEST_SCHEMA_VERSION",
    "GROUPS", "FUZZERS", "REQUIRED_SEED_FIELDS",
    "P1_HEADER", "P2_HEADER", "SUMMARY_HEADER", "TIMESERIES_HEADER",
    "QUEUE_INDEX_HEADER", "CRASHES_INDEX_HEADER", "ENRICHMENT_AUDIT_HEADER",
    "DRYRUN_HEADER", "SNAPSHOT_TAGS", "QUEUE_KINDS",
    "container_name", "out_dir_name", "group_label", "fuzzer_label",
    "rq3_dir", "group_seed_dir", "group_manifest_path", "dict_dir",
    "collect_dir", "groups_json_path", "dict_frozen_path",
    "load_config",
    "md5_bytes", "md5_file", "md5_dir", "md5_set",
    "dict_token_count", "dict_tokens",
    "mean_std", "fmt", "paired_win_rate",
    "write_csv", "read_csv", "write_tsv", "read_tsv", "write_json", "read_json",
    "load_manifest", "iter_manifest_seeds", "manifest_by_filename",
    "manifest_by_md5", "manifest_by_index",
]
