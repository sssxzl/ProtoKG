# T0-A Hub 隔离入口源码核查

## 一、事实

| 检查项 | 结论 | 证据 |
|---|---|---|
| Fact 读取位置 | `paths.per_source_aspect_facts_dir(protocol)` 下的 `*.jsonl` | `hub_entities.load_facts:262` |
| 输入格式 | 每行一个 Fact JSON（`fact_id`、`fact_key` 等） | 同上 |
| 实体索引构建 | `build_entity_index(facts)` 纯函数，只吃列表 | `hub_entities.py:88` |
| 实体落盘 | `write_entity_index(protocol, entities)`，路径来自 `paths.hub_index_dir()` | `hub_entities.py:250` |
| 清理入口 | `_clean_per_source` / `_purge_hub_for_batch`，均写 `paths.per_source_root` / hub 根 | `build_hub.py:207` / `:297` |
| 危险点 | `build_hub.main` 默认会清空 `derived/per_source/<proto>/` | `build_hub.py:18` 注释 |

## 二、没有改 build_hub.py 的原因

真正会写盘的是三个函数，它们都通过 `core.paths` 取路径：

- `load_facts` → `paths.per_source_aspect_facts_dir`
- `write_entity_index` → `paths.hub_index_dir`
- 清理函数 → `paths.per_source_root`

只要在隔离测试进程内把这三个函数指向临时根，现有构建逻辑就整体落在隔离目录里。这比给 `build_hub.py` 加参数更小：

- 不给正式入口增加任何新代码路径，默认行为零变化；
- 不存在「忘记传 out-dir 就回落到正式目录」的风险；
- 也不需要改 CLI。

因此本轮**未提交 build_hub.py 的改动**，`T0A_Hub最小隔离接口.patch` 记录的是该结论对应的最小代码面（仅缓存拒收修正），并在文档里说明隔离通过路径注入实现。

## 三、隔离约束落实

| 约束 | 落实 |
|---|---|
| 输入/输出目录预先给定 | 临时目录 `mkdtemp`，测试开始即确定 |
| 删除与写入限制在隔离根 | 全程只写临时目录；未调用任何清理函数 |
| 路径逃逸检查 | 写入路径均由 `out / ...` 拼接，不含 `..`；未使用符号链接 |
| 不回退正式目录 | 三个路径函数在 `try/finally` 内替换，异常也恢复 |
| 不安全即拒绝 | 若临时目录创建失败，脚本直接退出，不退回正式路径 |
