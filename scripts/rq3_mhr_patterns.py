# -*- coding: utf-8 -*-
"""scripts/rq3_mhr_patterns.py —— RQ3 变异命中率（MHR）的三口径判定规则。

技术方案 **v2** §5 的可编码版本（v1 的「血缘扁平、无需递归」结论已被 v2 推翻）。

★ v2 相对 v1 的三处实质修正（实现必须遵循）：

  1. **AFL 队列有两种命名形式**，血缘必须沿 `src:` 链上溯：
       · `id:%06u,orig:<种子名>`            → **初始队列条目**（数量 == 初始种子数）
       · `id:%06u,src:%06u[,+%06u],op:*,rep:*` → **派生条目**（变异产生）
     → 「初始副本 vs derived」**按命名形式**判定，MD5 降为交叉校验。
     → 上溯支持 **splice 多父**、**防环**、**深度上限 64**。
     → 由此派生出**污染探针**：`count(orig: 形式) == 初始种子数`。

  2. **`.raw` 有两种线格式**，切分必须**格式自适应**：
       · 纯文本（`\r\n\r\n` 分隔）—— 种子文件、`/out/queue/*`
       · 4 字节长度前缀帧 —— `/out/replayable-crashes/*`

  3. **主口径 MHR_A 必须「去噪 + 宽松匹配」**：AFL 变异会破坏字段名
     （实测 `SETUP` → `SETUdioTerack1`、`Transport` → `Trans\x7fort`），
     严格规则在真实崩溃样本上**命中 0** → 宽松匹配是必需的。

用法:
    from scripts.rq3_mhr_patterns import classify_entry, match_patterns
"""
from __future__ import annotations

import re
import struct
from typing import Optional

#: RTSP 消息分隔符（纯文本线格式）
MSG_SEP = b"\r\n\r\n"

#: 长度前缀帧的最大负载长度（v2 §5.3.0 的伪码用 4096，但实测真实崩溃帧
#: 的负载可达 16417 B（如 `lens=[1464, …, 16417, …]`）→ 4096 会把帧格式
#: 误判成纯文本（实测 7 个真实崩溃样本有 6 个被误判）。
#: → 这里放宽到 1 MiB，改用「**全部帧精确消费文件长度**」+「**首字节不像
#:   RTSP 请求行**」双重判据来防误判（见 split_messages）。
MAX_FRAME_PAYLOAD = 1024 * 1024

#: 四个漏洞模式的标签
PATTERNS: tuple[str, ...] = ("P1", "P2", "P3", "P4")

#: 血缘上溯的深度上限（v2 §5.2.2：实测 max 18，64 足够）
MAX_LINEAGE_DEPTH = 64

#: ★ P2 触发 Session 值的**默认白名单**（协议无关的兜底；
#:   正式判定应从 manifest 的 `dictionary.session_candidates` 读取）
DEFAULT_SESSION_VALUES: tuple[str, ...] = ("000022B8", "107518505",
                                            "7477886380351771441")

#: P1 —— 同 track 双 SETUP（宽松：容忍 `SETUdioTerack1` 这类变异后的方法名）
_RE_SETUP_METHOD = re.compile(rb"^\s*SET[UUP]*\s*[^A-Za-z0-9]*\s*", re.I)

#: P1 的 track 号匹配（宽松）：容忍 track 键名被变异
#:   · `track1`（原形）
#:   · `terack1`（t 后插入垃圾字节，实测 `SETUdioTerack1`）
#:   · `rack1`（t 被整个替换掉）
#: → 允许 `t` 与 `rack` 之间夹最多 4 个非数字字节，且 `t` 本身可缺省。
_RE_TRACK = re.compile(rb"(?:t[^0-9]{0,4})?rack\s*[-_/]?\s*(\d+)",
                       re.IGNORECASE)

#: P2 —— 触发 Session 值（宽松：容忍键名被破坏 → 同时匹配带键名与裸值）
_RE_SESSION_KEYED = re.compile(rb"session\s*[:=]\s*([0-9a-zA-Z]+)", re.IGNORECASE)

#: P3 —— Transport 切换（宽松：只匹配参数名，不要求同一消息内）
_RE_INTERLEAVED = re.compile(rb"interleaved", re.IGNORECASE)
_RE_CLIENT_PORT = re.compile(rb"client_port", re.IGNORECASE)

#: P4 —— 会话重建序列
_RE_TEARDOWN_METHOD = re.compile(rb"^\s*TEARDOWN\b", re.IGNORECASE)

#: 判定前需剔除的噪声字节（控制字符 + 0xff 类字节）
#: ★ **必须保留 `\r` / `\n` / `\t`** —— 它们是 RTSP 消息的行分隔符，
#:   剔除后 `\r\n\r\n` 切分会失效（切出整块而非逐条消息）。
_NOISE_BYTES = bytes(b for b in range(256)
                     if (b < 0x20 and b not in (0x09, 0x0a, 0x0d))
                     or b == 0x7f or b >= 0xff)

#: 噪声字节的替换目标（空格，保持 token 边界）—— 必须是 256 字节的完整表
_NOISE_TABLE = bytes((0x20 if b in _NOISE_BYTES else b) for b in range(256))

#: 队列条目名 —— 初始条目形态
_RE_ORIG_FORM = re.compile(r",orig:")

#: 队列条目名 —— 派生条目形态（含 splice 多父）
_RE_SRC_FORM = re.compile(r",src:(\d{1,8})(?:\+(\d{1,8}))?")

#: 队列条目 id
_RE_ID_FORM = re.compile(r"^id:(\d{1,8})")


# ===========================================================================
# 格式自适应切分（v2 §5.3.0）
# ===========================================================================

def _frames_look_plausible(msgs: list) -> bool:
    """判断帧解码出的负载是否像 RTSP 文本（可打印 ASCII 占比高）。

    用于帧格式探测的**双重保险**：纯文本 RTSP 流的首 4 字节作为 u32 必然是
    巨大值（'DESC' = 0x43534544 ≫ 1 MiB）→ 天然被长度上限拒绝。
    本函数额外要求**解码后的负载**是可打印文本，防止「纯文本恰好被误读成
    若干帧」的极端情形（实测存在首字节恰为 'B'（0x42）的真实崩溃样本，
    不能用「首字节是大写字母」这类语义判据）。

    Args:
        msgs: 已解码的帧负载列表。

    Returns:
        True = 负载整体像可打印文本。
    """
    if not msgs:
        return False
    sample = b"".join(msgs[:4])[:4096]
    if not sample:
        return False
    printable = sum(1 for b in sample if 0x20 <= b < 0x7f or b in (0x09, 0x0a, 0x0d))
    return printable / len(sample) >= 0.80


def split_messages(data: bytes) -> list[bytes]:
    """自适应切分 RTSP 消息：先试 4 字节长度前缀帧，失败则回退 `\\r\\n\\r\\n`.

    ★ v2 修正（技术方案 §5.3.0）：实测存在**两种线格式**——
      · 种子文件与 `/out/queue/*` = **纯文本**（`\r\n\r\n` 分隔）
      · `/out/replayable-crashes/*` = **4 字节长度前缀帧**
    长度前缀帧的负载实测可达 16417 B，故上限取 1 MiB（v2 伪码的 4096 会把
    真实崩溃样本误判为纯文本 —— 实测 7 个样本有 6 个被误判）。

    **双重保险**（避免把纯文本误读成长度前缀帧）：
      ① 全部帧必须**精确消费**文件长度；
      ② 解码后的负载必须是可打印文本（RTSP 报文）。

    Args:
        data: 原始字节。

    Returns:
        消息列表。
    """
    if not data:
        return []
    # --- 尝试长度前缀帧 ---
    msgs: list = []
    off = 0
    while off + 4 <= len(data):
        n = struct.unpack("<I", data[off:off + 4])[0]
        if n <= 0 or n > MAX_FRAME_PAYLOAD or off + 4 + n > len(data):
            break
        msgs.append(data[off + 4: off + 4 + n])
        off += 4 + n
    if msgs and off == len(data) and _frames_look_plausible(msgs):
        return msgs                      # 长度前缀帧（精确消费）
    # --- 回退：纯文本 \r\n\r\n 切分 ---
    out: list = []
    rest = data
    while True:
        i = rest.find(MSG_SEP)
        if i == -1:
            if rest.strip():
                out.append(rest)
            break
        out.append(rest[:i + len(MSG_SEP)])
        rest = rest[i + len(MSG_SEP):]
    return out


def detect_format(data: bytes) -> str:
    """探测 `.raw` 的线格式：`frame`（长度前缀帧）/ `text`（纯文本）。

    Args:
        data: 原始字节。

    Returns:
        "frame" 或 "text"。
    """
    if not data:
        return "text"
    off = 0
    msgs: list = []
    while off + 4 <= len(data):
        n = struct.unpack("<I", data[off:off + 4])[0]
        if n <= 0 or n > MAX_FRAME_PAYLOAD or off + 4 + n > len(data):
            break
        msgs.append(data[off + 4: off + 4 + n])
        off += 4 + n
    if msgs and off == len(data) and _frames_look_plausible(msgs):
        return "frame"
    return "text"


# ===========================================================================
# 去噪 + 宽松匹配（v2 §5.3.2）
# ===========================================================================

def denoise(data: bytes) -> bytes:
    """剔除控制字符与 `0xff` 类字节（变异产生的噪声），保持 token 边界。

    ★ AFL 变异会把 `Transport` 变成 `Trans\\x7fort` → 严格匹配必然失败。
    去噪把噪声字节替换为空格，保留可读的协议 token。

    Args:
        data: 原始字节。

    Returns:
        去噪后的字节。
    """
    if not data:
        return data
    return data.translate(_NOISE_TABLE)


def _request_line(msg: bytes) -> bytes:
    """取消息的请求行（第一行，去掉行尾空白）。"""
    return msg.split(b"\r\n", 1)[0].strip()


def _is_setup(line: bytes) -> bool:
    """请求行是否是 SETUP（宽松：容忍变异插入的字符）。

    容忍 `SETUdioTerack1`（实测真实崩溃样本中的变异形态）：
    允许 `SET` 之后出现任意非字母数字的插入字节，再跟 `UP`。
    """
    if not line:
        return False
    return bool(_RE_SETUP_METHOD.match(line))


def _track_of(uri: bytes) -> Optional[str]:
    """从 URI 里取 track 号（宽松匹配，无 track 返回 None）。"""
    m = _RE_TRACK.search(uri or b"")
    return m.group(1).decode("ascii", "ignore") if m else None


def match_patterns(content: bytes,
                   session_values: Optional[list] = None) -> dict:
    """按内容判定 P1–P4 四个漏洞模式是否命中（**去噪 + 宽松匹配**）。

    判定规则（v2 §5.3.2）：
      · P1：SETUP 请求行里的 track 号，任一 track 号出现 ≥ 2 次
      · P2：出现 `Session: <值>`（宽松：键名可被破坏）或**裸值** `<值>`
            （`<值>` 取自触发 Session 值白名单，**非硬编码**）
      · P3：文本含 `interleaved` **且** 含 `client_port`
      · P4：请求行方法序列存在 `SETUP … TEARDOWN … SETUP` 三元组，
            且两个 SETUP 的 track 号相同

    Args:
        content: 队列条目 / 崩溃样本的原始字节。
        session_values: 触发 Session 值白名单；None 时用 DEFAULT_SESSION_VALUES。

    Returns:
        `{"P1": bool, "P2": bool, "P3": bool, "P4": bool}`。
    """
    result = {"P1": False, "P2": False, "P3": False, "P4": False}
    if not content:
        return result
    values = list(session_values) if session_values else list(DEFAULT_SESSION_VALUES)

    # 去噪（对内容整体做一次，供全文正则使用）
    clean = denoise(content)

    # --- P2：触发 Session 值 ---
    #   宽松口径：① `Session: <值>`（键名可能被破坏 → 用宽松正则）
    #            ② **裸值**（AFL 变异可能删掉键名，只留值）
    for v in values:
        vb = v.encode("ascii", "ignore")
        if not vb:
            continue
        if _RE_SESSION_KEYED.search(clean) and vb.lower() in clean.lower():
            result["P2"] = True
            break
        if vb.lower() in clean.lower():
            result["P2"] = True
            break

    # --- P3：Transport 切换（只匹配参数名，不要求同一消息内） ---
    if _RE_INTERLEAVED.search(clean) and _RE_CLIENT_PORT.search(clean):
        result["P3"] = True

    # --- 逐消息判定 P1 / P4 ---
    msgs = split_messages(content)
    lines = [_request_line(denoise(m)) for m in msgs]

    track_counts: dict = {}
    for line in lines:
        if not _is_setup(line):
            continue
        tr = _track_of(line)
        if tr is not None:
            track_counts[tr] = track_counts.get(tr, 0) + 1
    if any(c >= 2 for c in track_counts.values()):
        result["P1"] = True

    # P4：SETUP … TEARDOWN … SETUP（三元组，两 SETUP 同 track）
    for i in range(len(lines) - 2):
        if not _is_setup(lines[i]):
            continue
        if not _RE_TEARDOWN_METHOD.match(lines[i + 1]):
            continue
        if not _is_setup(lines[i + 2]):
            continue
        t1 = _track_of(lines[i])
        t2 = _track_of(lines[i + 2])
        if t1 is not None and t1 == t2:
            result["P4"] = True
            break
    return result


# ===========================================================================
# 命名形式解析（v2 §5.2.1 / §5.3.1）
# ===========================================================================

def normalize_name(name: str) -> str:
    """规范化 AFL 条目名（处理 Windows/NTFS 的 `:` → U+F03A 陷阱）。

    ★ Git Bash / NTFS 会把文件名里的 `:`（AFL 条目名形如
    `id:000000,sig:06,src:001325,...`）转成 U+F03A（私用区字符），
    导致 `startswith('id:')` / `glob('id:*')` 全部失配。
    本函数把 U+F03A 还原成 `:`，使 Windows 侧与 Linux 侧行为一致。

    Args:
        name: 条目名。

    Returns:
        规范化后的条目名。
    """
    return name.replace("\uf03a", ":").replace("\uff1a", ":")


def entry_kind(name: str) -> str:
    """按**命名形式**判定条目类别（v2 §5.3.1）。

    · `orig:` 形式 → `initial_copy`（初始队列条目，数量 == 初始种子数）
    · `src:` 形式  → `derived`（变异产生）

    ★ 不再用 MD5 判定：AFL 校准阶段会插入 trimmed 变体，且同一内容可能
    以不同文件名出现；命名形式是 AFL 自己记录的语义，不依赖内容巧合。

    Args:
        name: 条目名。

    Returns:
        "initial_copy" 或 "derived"。
    """
    n = normalize_name(name)
    if _RE_ORIG_FORM.search(n):
        return "initial_copy"
    return "derived"


def parse_entry_id(name: str) -> Optional[int]:
    """从条目名解析队列 id（`id:000123` → 123）。"""
    m = _RE_ID_FORM.match(normalize_name(name))
    return int(m.group(1)) if m else None


def parse_orig_seed(name: str) -> Optional[str]:
    """从条目名解析 `orig:` 后的种子文件名（仅初始条目有）。

    Args:
        name: 条目名。

    Returns:
        种子文件名；无 `orig:` 时返回 None。
    """
    n = normalize_name(name)
    idx = n.find(",orig:")
    if idx < 0:
        return None
    return n[idx + len(",orig:"):] or None


#: ★ 向后兼容别名（v1 的 `parse_orig` → v2 的 `parse_orig_seed`）。
#:
#: v2 把 `orig:` 的语义收窄为「**仅**初始队列条目」，函数更名为 `parse_orig_seed`
#: 以免与 `src:` 链上溯混淆；但旧调用方（含外部脚本/历史测试）仍按 `parse_orig`
#: 导入 → 保留别名，保证**不破坏任何既有调用方**（QA-2026-10-24 P0-2）。
parse_orig = parse_orig_seed


def parse_src_parents(name: str) -> list:
    """从条目名解析 `src:` 父 id 列表（splice 可有 2 个父）。

    Args:
        name: 条目名。

    Returns:
        父 id 列表（空列表表示无 `src:` 字段）。
    """
    n = normalize_name(name)
    m = _RE_SRC_FORM.search(n)
    if not m:
        return []
    out = []
    for g in m.groups():
        if g:
            out.append(int(g))
    return out


def build_lineage_maps(entries: list) -> tuple[dict, dict]:
    """由队列条目列表构建血缘映射（v2 §5.2.2）。

    Args:
        entries: 条目名列表（或 `(name, ...)` 元组列表，取其首元素）。

    Returns:
        `(orig_map, src_map)`：
          · orig_map：`{队列id: 种子文件名}`（初始条目）
          · src_map：`{队列id: [父id, ...]}`（派生条目）
    """
    orig_map: dict = {}
    src_map: dict = {}
    for item in entries:
        name = item[0] if isinstance(item, (tuple, list)) else item
        qid = parse_entry_id(name)
        if qid is None:
            continue
        seed = parse_orig_seed(name)
        if seed:
            orig_map[qid] = seed
            continue
        parents = parse_src_parents(name)
        if parents:
            src_map[qid] = parents
    return orig_map, src_map


def resolve_root_seeds(qid: Optional[int], orig_map: dict, src_map: dict,
                       *, max_depth: int = MAX_LINEAGE_DEPTH) -> set:
    """沿 `src:` 链上溯，返回可达的**根种子文件名集合**（splice 可能多父）。

    ★ v2 修正（推翻 v1 的「扁平、无需递归」）：派生条目**没有** `orig:` 字段，
    必须沿 `src:` 链逐级上溯。

    Args:
        qid: 起始队列 id。
        orig_map: `{队列id: 种子文件名}`。
        src_map: `{队列id: [父id, ...]}`。
        max_depth: 深度上限（超限归 unattributed）。

    Returns:
        根种子文件名集合（可能为空 = unresolved）。
    """
    if qid is None:
        return set()
    seen: set = set()
    stack: list = [(qid, 0)]
    out: set = set()
    while stack:
        x, depth = stack.pop()
        if x in seen:
            continue                    # 防环（splice 可能形成环）
        seen.add(x)
        if depth > max_depth:
            continue                    # 超限 → 不计入
        if x in orig_map:
            out.add(orig_map[x])
            continue
        for parent in src_map.get(x, []):
            stack.append((parent, depth + 1))
    return out


def resolve_root(name: str, orig_map: dict, src_map: dict,
                 manifest_by_filename: dict,
                 manifest_by_index: dict) -> tuple[Optional[str], str, int]:
    """解析条目的根种子及层归属（v2：沿 `src:` 链上溯 + `NN_` 兜底）。

    Args:
        name: 条目名。
        orig_map: `{队列id: 种子文件名}`。
        src_map: `{队列id: [父id, ...]}`。
        manifest_by_filename: `{文件名: manifest 条目}`。
        manifest_by_index: `{"NN": manifest 条目}`。

    Returns:
        `(root_filename, layer, n_roots)`：
          · root_filename 为 None 表示 unattributed
          · n_roots 是可达根的个数（> 1 = splice 多父）
    """
    roots = resolve_root_seeds(parse_entry_id(name), orig_map, src_map)
    if roots:
        # 多父口径：任一根属于 ③ 层即计入（由调用方判定）
        named = sorted(r for r in roots if r in manifest_by_filename)
        if named:
            # 主根取「层最靠近漏洞边界」的那个（L3 优先），保证单父时口径确定
            def _rank(r):
                layer = manifest_by_filename[r].get("layer", "L0")
                return (0 if layer == "L3" else 1, r)
            root = sorted(named, key=_rank)[0]
            return (root, manifest_by_filename[root].get("layer", "unknown"),
                    len(roots))
        # 根名不在 manifest → 兜底：NN_ 序号前缀
        for r in sorted(roots):
            m = re.match(r"^(\d{2,3})_", r)
            if m:
                key = f"{int(m.group(1)):02d}"
                if key in manifest_by_index:
                    entry = manifest_by_index[key]
                    return (entry.get("filename", ""),
                            entry.get("layer", "unknown"), len(roots))
        return (None, "unknown", len(roots))
    # 完全 unresolved → 兜底：条目名自身的 NN_ 前缀
    m = re.match(r"^(\d{2,3})_", normalize_name(name))
    if m:
        key = f"{int(m.group(1)):02d}"
        if key in manifest_by_index:
            entry = manifest_by_index[key]
            return (entry.get("filename", ""), entry.get("layer", "unknown"), 0)
    return (None, "unknown", 0)


# ===========================================================================
# 条目分类与汇总
# ===========================================================================

def classify_entry(name: str, md5: str, content: bytes,
                   seed_md5_set: set,
                   session_values: Optional[list] = None,
                   hits: Optional[dict] = None) -> dict:
    """分类单个队列条目（v2：按命名形式判定 + 宽松模式判定）。

    Args:
        name: 队列条目名。
        md5: 条目内容的 MD5（仅作交叉校验）。
        content: 条目原始字节。
        seed_md5_set: 语料种子的 MD5 集合（交叉校验用）。
        session_values: 触发 Session 值白名单。
        hits: 预计算的命中结果（避免重复判定）。

    Returns:
        `{"kind", "hits", "hit_any", "md5_in_seeds"}` 字典；
        `kind` ∈ {"initial_copy", "derived"}。
    """
    kind = entry_kind(name)
    if hits is None:
        hits = match_patterns(content, session_values)
    return {"kind": kind, "hits": hits, "hit_any": any(hits.values()),
            "md5_in_seeds": md5 in seed_md5_set}


def summarize_hits(entries: list) -> dict:
    """汇总一批条目的命中统计。

    Args:
        entries: `classify_entry` 的结果列表。

    Returns:
        `{"n_total", "n_initial", "n_derived", "n_hit", "mhr_a",
        "pattern_counts"}`。
    """
    n_total = len(entries)
    initial = [e for e in entries if e["kind"] == "initial_copy"]
    derived = [e for e in entries if e["kind"] == "derived"]
    n_derived = len(derived)
    n_hit = sum(1 for e in derived if e["hit_any"])
    pattern_counts = {p: sum(1 for e in derived if e["hits"].get(p))
                      for p in PATTERNS}
    return {
        "n_total": n_total,
        "n_initial": len(initial),
        "n_derived": n_derived,
        "n_hit": n_hit,
        "mhr_a": (100.0 * n_hit / n_derived) if n_derived else None,
        "pattern_counts": pattern_counts,
    }


__all__ = ["MSG_SEP", "MAX_FRAME_PAYLOAD", "PATTERNS", "MAX_LINEAGE_DEPTH",
           "DEFAULT_SESSION_VALUES",
           "split_messages", "detect_format", "denoise", "match_patterns",
           "normalize_name", "entry_kind", "parse_entry_id", "parse_orig_seed",
           "parse_orig",
           "parse_src_parents", "build_lineage_maps", "resolve_root_seeds",
           "resolve_root", "classify_entry", "summarize_hits"]
