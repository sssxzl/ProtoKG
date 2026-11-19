# T0-A Raw → Canonical 隔离集成报告

## 一、正常路径

用 RFC 3207 六块 + 确定性 Stub（返回 `STARTTLS` 一条、span=80），调用真实链路 `_extract_blocks`：

| 环节 | 实际产物 |
|---|---|
| Norm | 1 条，`kind=prose_semantics`，`source=file:rfc3207.txt#@80` |
| Fact | 1 条，`aspect=definition`，`subject=header/STARTTLS` |
| Claim | 1 条，带 Evidence |
| Evidence | `source_type=rfc`，`document=file:rfc3207.txt#@80`，`evidence_id=e2_4ce5…` |

Norm 字段实检：`norm_id / kind / name / content / source / span_line / evidence_quote / strength / polarity` 均存在，来源行号与块内起始行一致。

## 二、可追溯性

- Norm 的 `source` 直接给出文件与行号；
- Evidence 的 `document` 同格式，可回到原文第 80 行；
- `locator` 为空（与既有 C-3 问题同源），因此定位依赖 `document` 后缀的行号，不依赖 `locator` 字段。

## 三、Canonical 校验

`map_norm_to_facts` 通过 `RFC_KIND_MAP["prose_semantics"]` 分派，产出 FactID（`compute_fact_id`），未新增 kind、未改 aspect 集合。流程止于此，未构建中枢。

## 四、隔离性

- 所有运行在临时目录，`PS._cache_path` 指向 `mkdtemp`；
- 正式 `derived/per_source` 未写入；
- 正式 Norm 基线仍 63/107/92、Fact 82/152/99（本文件末尾复核）。

## 五、止点

链路走到 Canonical Fact 对象为止。**未进入知识中枢**，原因见 `T0A_隔离中枢接入结果.md`。
