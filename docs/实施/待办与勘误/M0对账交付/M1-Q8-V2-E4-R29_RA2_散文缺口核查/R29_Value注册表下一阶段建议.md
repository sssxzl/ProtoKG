# 下一阶段建议

## 一、当前成果

- 类型清单完整（含 74 条历史 `str`）；
- 门禁在 `_make_fact` 生效，正反例正确；
- 三协议回归无变化，序列化与身份字节未动。

## 二、未闭合

- 直接 `Fact(...)` 旁路未拦；
- `Fact.__post_init__` 下沉需批准（会改变所有构造点行为）。

## 三、建议

1. 批 `Fact.__post_init__` 校验（一次收敛所有入口）；
2. 之后跑一遍全量回归（含 21 aspects 映射）；
3. 再谈 grammar 正式注册与 H2 迁移。

## 四、状态

```
value_type_registry_partial
grammar_value_isolated_readback_verified   # 维持
```
