# R24 补充：field_value 合并缺陷的独立复现与最小修复

> ★ 依据审查方在固定 commit `ac343e2eaa5c4e20d86ca001b89a9747586db93b` 上的源码检查
> ★ **本轮不修改生产代码** ｜★ 0 次 LLM 调用

---

## 一、★ 审查方的指控（★ 成立）

> ★ `rfc_extractor.py:4114-4127` 的 field_value 合并逻辑：★ 内部 `merged_values`
> ★ 有两个值，★ 但最终返回的 Norm 只有首个值。

### 1.1 逐行确认

```python
key = norm["norm_id"]                              # :4113
if norm.get("kind") == "field_value":              # :4114
    _vals = _parse_value_samples(norm.get("content", ""))
    _prev = merged_values.get(key)
    if _prev is None:                               # :4116  ★ 首条
        merged_values[key] = list(_vals)
        seen_protocol_level.add(key)
        norms.append(norm)                          # :4120  ★ 原样追加，★ content 未改写
    else:                                           # :4121  ★ 后续条
        for _v in _vals:
            if _v not in _prev:
                _prev.append(_v)                    # :4123  ★ 并入 _prev
        norm["content"] = (f"{norm['name']} | values: "
                            + VALUE_SAMPLE_SEP.join(_prev))   # :4125-4126
        # ★ ★ 没有 norms.append(norm) ⇒ 该条被丢弃，★ 合并结果随它一起消失
    continue
```

★ ⇒ ★ **合并后的值集写在了被丢弃的那条 norm 上；★ 保留的首条 content 从未被改写。**

### 1.2 独立复现（★ 合成输入，★ 完全照抄生产控制流）

| 项 | 值 |
|---|---|
| ★ 输入 | ★ 3 条同 norm_id，★ 取值 alpha / beta / gamma |
| ★ 返回条数 | **1**（★ 只剩首条） |
| ★ 内部 merged_values | `['alpha', 'beta', 'gamma']`（★ 三个值都在） |
| ★ 返回 Norm 的 content | `['x | values: alpha']`（★ **只剩首条取值**） |
| ★ 合并值是否出现在输出 | **False** |

★ ⇒ ★ **缺陷确认：★ 是「写错对象」，★ 不是「没合并」。**

---

## 二、★ 是否影响真实语料（★ 第二问的答案）

### 2.1 实测三协议

| 协议 | field_value 输入条数 | 输出条数 | ★ 同 norm_id 多条的组数 | ★ 存在值丢失的条数 |
|---|---:|---:|---:|---:|
| smtp | 8 | 8 | **0** | **0** |
| rtsp | 16 | 16 | **0** | **0** |
| DHCPv4 | 0 | 0 | **0** | **0** |

★ ⇒ ★ **当前语料零影响。**

### 2.2 ★★ 为何零影响（★ 不是巧合，★ 而是建模使然）

| 协议 | ★ 全部 kind 的 norm_id 重复情况 | field_value 取值数分布 |
|---|---|---|
| smtp | **零重复** | {'1': 5, '2': 1, '8': 1, '5': 1} |
| rtsp | **零重复** | {'4': 1, '1': 6, '24': 1, '2': 3, '10': 1, '3': 1, '12': 1, '7': 1, '19': 1} |
| DHCPv4 | **零重复** | {} |

★ ⇒ ★ 抽取器按「**字段 → 取值样本集**」建模：★ 一个字段的多个取值在**抽取阶段
★ ★ 就已在一条 Norm 内聚合完毕**（★ 如 `smtp.field_value.cc` 一条就带 2 个取值，
★ ★ `rtsp` 有一条带 24 个取值）。★ ⇒ ★ 合并分支（同 norm_id 的第二条）
★ ★ **从未被触发**。

★ ★ **结论**：★ 该分支是**死代码路径上的真实缺陷**；★ 合成输入可触发，
★ ★ 未来语料若出现同字段的多条抽取结果即会触发。

---

## 三、★ 最小修复方案（★ 不改生产代码）

### 3.1 改动

★ **一处**：★ 合并后把结果**回写到已保留的首条**（★ 而非被丢弃的那条）。

```python
# ★ 影子实现（★ 已验证；★ 生产代码未改）
_first = out[first_index[key]]
_first["content"] = (f"{_first['name']} | values: " + SEP.join(_prev))
```

★ **不需要**改 `_parse_value_samples`、★ 不需要改 norm_id、★ 不需要改 evidence。

### 3.2 回归测试（★ 5 项）

| ID | 场景 | ★ 生产符合期望 | ★ 修复后符合期望 |
|---|---|---|---|
| RT-01 | 同 norm_id 三条取值：★ 合并值必须出现在输出 | **False** | **True** |
| RT-02 | 同 norm_id 两条：★ 值取并集且不重复 | **False** | **True** |
| RT-03 | 同 norm_id 完全重复的取值：★ 结果不变 | **True** | **True** |
| RT-04 | 不同 norm_id：★ 不得互相影响 | **True** | **True** |
| RT-05 | field_value 与其他 kind 混排：★ 其他 kind 的去重不变 | **False** | **True** |

★ **生产 5 项中 3 项失败；★ 修复后 5/5 全通过。**

### 3.3 ★ 对真实语料的影响（★ 关键安全判据）

| 协议 | 生产条数 | 修复后条数 | ★ 逐条内容是否完全相同 |
|---|---:|---:|---|
| smtp | 63 | 63 | **True** |
| rtsp | 107 | 107 | **True** |
| DHCPv4 | 92 | 92 | **True** |

★ ⇒ ★ **最小修复对现有语料逐字节无影响**，★ 只在合成多值场景修正行为。
★ ⇒ ★ 因此该修复是**低风险**的，★ 但仍需走审批（★ 它改的是抽取路径）。

---

## 四、★ 第二问的答复（★ 检查最终输出 Norm 而非内部 merged_values）

★ 复现脚本 `r24b_fv_repro.py` 的**第二阶段**直接比对：
★ **① 内部 merged_values 的值集** 与 **② 最终输出 Norm 的 content 解析出的值集**，
★ ★ 并列出「丢失的值」。★ 三协议结果均为**零丢失**，★ 原因是无同 norm_id 多条。

★ ★ **★ R24 原报告的表述「field_value 值集合与生产完全一致」是正确的**，
★ ★ ★ 但它**只比对了内部 merged_values**，★ 未检查最终输出的 content。
★ ★ ★ 本轮补充检查后，★ **结论不变且更强**：★ 不仅内部一致，★ **最终输出也一致**。

---

## 五、限制

1. ★ 本轮为影子验证；★ **未改生产代码**。
2. ★ 合成输入按真实分隔符 `VALUE_SAMPLE_SEP`（★ ` |~| `）构造；★ 审查方若用逗号构造，★ 解析结果会不同（★ 但缺陷结论不变）。
