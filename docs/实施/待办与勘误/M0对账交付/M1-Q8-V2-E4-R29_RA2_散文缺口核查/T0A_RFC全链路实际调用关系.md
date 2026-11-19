# T0-A RFC 全链路实际调用关系（源码证据）

所有行号取自当前影子 worktree（= main + F2 三段补丁 + 本轮增量），未凭函数名推测。

| # | 环节 | 实际入口 | 证据 |
|---|---|---|---|
| 1 | RFC 读取与原始 SHA256 | `prose_semantics._collect_blocks` | `prose_semantics.py:740` 读 `read_text`；本轮在其中加 `_src_sha = sha256(f.read_bytes())` 并写入每个块 |
| 2 | 确定性知识抽取 | `rfc_extractor.extract_rfc_norms` → `_extract_rfc_file` | `rfc_extractor.py:4061` / `:1611`；散文路径不经过它 |
| 3 | 散文块选择与调度 | `_split_blocks` + `select_block_density` | `prose_semantics.py` 内 `_MAX_BLOCK_CHARS=3500`；`_collect_blocks:740` 调 `_split_blocks` |
| 4 | 散文抽取入口 | `_extract_blocks` | `prose_semantics.py:856`；`extract_prose_norms:1455` 是文件级包装 |
| 5 | Raw 结果解析 | `_extract_blocks` 内 `json.loads(out)` 段 | 约 `:1190-1230`；本轮加 `finish_reason != stop ⇒ 失败` |
| 6 | 来源证据关联 | `normative_extract.build_evidence` / `resolve_span_evidence` | 在 `_extract_blocks` 顶部 `from ... import` 处；产出 `evidence_id`、`document=file:rfc#@line` |
| 7 | Norm 构建 | 同一函数内 `_norm(...)` 组装 | norm 字典含 `source`、`span_line`、`evidence_quote` 等 30+ 字段 |
| 8 | Norm→Fact | `norm.map_norm_to_facts` | `norm.py:628`；`RFC_KIND_MAP:602` 登记 `prose_semantics`；映射函数 `:496` |
| 9 | Canonical 身份 | `hub.canonical.compute_fact_id` | `canonical.py:132`；Fact/Claim/Evidence 为 `models.py` 数据类 |
| 10 | 中枢接入 | `scripts/build_hub.py` | 只写 `derived/per_source/<protocol>/`，无 `--out-dir` 参数 |

## 接入方式

T0-A 不在运行器里重写抽取，而是把适配器作为 `llm` 传入 `_extract_blocks`：

```python
PS._MAX_TOKENS = 4000          # 固定单次上限
os.environ["PROSE_NO_RETRY"] = "1"
norms, stats = PS._extract_blocks("smtp", blocks, llm=T0AClient(key))
```

下游 Norm/Fact/Evidence 全部由既有函数产出，运行器不复制任何 ID 计算。

## 两个必须说明的改动

1. `PS._MAX_TOKENS` 是模块常量，链路内 payload 用它；T0-A 在隔离进程里把它设为 4000，否则适配器会因「收到 16000」拒绝。这个常量同时进缓存键，因此 T0-A 的缓存与生产缓存天然不互通。
2. `PROSE_NO_RETRY=1` 关闭链路内的 2 次重试，保证真实请求数可控。
