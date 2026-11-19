# T0-A 隔离中枢接入结果

## 一、结论

**未进入知识中枢。链路止于 Canonical Fact 对象。** 这不是本轮新增的阻断，而是现有下游缺少隔离入口。

## 二、为什么不能进

| 检查 | 结果 |
|---|---|
| `build_hub.py` 是否支持自定义输出目录 | 否，无 `--out-dir`；只写 `derived/per_source/<protocol>/` |
| 是否支持从内存 Fact 列表构建 | 否，按 `derived/per_source` 目录扫描 |
| 若强制运行 | 会清空并重写该协议的正式 `derived/per_source`，违反「不写正式产物」 |

因此本轮没有强行运行，只验证到 Canonical。

## 三、已验证到哪

| 节点 | 状态 |
|---|---|
| Raw items | 通过（Stub 产出被解析） |
| 证据关联 | 通过（evidence_id + document 行号） |
| Norm | 通过（prose_semantics，来源可回溯） |
| Canonical Fact | 通过（aspect=definition，FactID 由既有函数生成） |
| Claim / Evidence | 通过（数据类实例，可与 Fact 组合） |
| 中枢写入 | **未验证** |

## 四、若要做隔离中枢，需要什么

1. `build_hub.py` 增加可注入的 Fact 来源（内存或指定目录）；
2. 或提供一个 `build_from_facts(protocol, facts, out_dir)` 的最小接口；
3. 且不得清理正式 `per_source`。

三条都属于生产代码改动，需单独审批，本轮不做。

## 五、对结论的影响

不能声称「全链路通过」。准确表述是：**RFC → Norm → Fact/Evidence 已通过；Norm/Fact → 中枢未验证**。
