# T0-A 全产物隔离路径核验（G2）

## 一、隔离根

`run(protocol, doc, client, root)` 的 `root` 是唯一写入面。`root` 必须绝对路径、不含 `..`、非符号链接，否则返回 `preflight_failed`。

## 二、各产物落点

| 产物 | 路径 |
|---|---|
| 散文缓存 | `<root>/cache/<proto>.prose.d/<doc>.json` |
| Raw / 诊断 | `<root>/evidence/result.json`、`guard.json`（原子写：`.tmp` + `replace`） |
| Fact JSONL | `<root>/per_source/facts/definition.jsonl` |
| Hub 实体索引 | `<root>/hub/entities.jsonl`（经 `isolated_hub`） |

## 三、路径注入是否会被提前绑定破坏

| 函数 | 绑定方式 | 结论 |
|---|---|---|
| `hub_entities.load_facts` | 函数体内 `from core import paths` | 每次调用取模块最新属性，替换有效 |
| `hub_entities.write_entity_index` | 函数体内 `from core.paths import hub_index_dir` | 同上 |
| `prose_semantics._cache_path` | 模块级函数，`run()` 直接替换 | 有效 |

没有发现「模块导入时已经绑定函数对象」的情况，因此替换不会被绕过。这一点是逐函数看源码确认的，不是假设。

## 四、验证

| 场景 | 结果 |
|---|---|
| 正常执行 | 正式目录 0 写入 |
| 第二批失败 | 正式目录 0 写入 |
| 中途异常（Canonical / Hub 注入失败） | 正式目录 0 写入 |
| 危险 root（相对路径 / `..`） | `preflight_failed`，不执行 |
| 退出后恢复 | `isolated_hub` 用 `finally` 还原三个路径函数 |

## 五、边界

- 单进程假设，未验证并发；
- `T0AClient` 由调用方注入，若换成会写文件的客户端，需另行证明。
