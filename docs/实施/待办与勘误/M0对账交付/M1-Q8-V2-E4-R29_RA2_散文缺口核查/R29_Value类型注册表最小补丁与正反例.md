# 注册表最小补丁与正反例

## 一、实现

`scripts/value_types.py`：

```python
DECLARED = (scalar, enum, set, sequence, range, pattern,
            struct, ref, observation, binary, union, text)
LEGACY  = ("str",)
KNOWN_VALUE_TYPES = frozenset(DECLARED + LEGACY)
def validate_value_type(t) -> str: ...
```

写入点：`norm._make_fact()` 在构造 Fact 前调用 `_validate_value(value)`，集中一处，不散落。

## 二、正反例

| 输入 | 结果 |
|---|---|
| `text` | 通过 |
| `str`（legacy） | 通过 |
| `grammr` | 抛 `ValueTypeError` |
| 空串 | 抛错 |
| `None` | 抛错 |

不降级为 text；不修改 `canonical_serialize`；不修改 FactID/ClaimID 算法。

## 三、兼容性

历史读取路径不经过 `_make_fact`（`load_facts` 直接 `json.loads`），所以旧数据不受影响。
