# grammar Value 最小契约变更建议

## 一、现状判断

- 结构上已可承载（8 项测试通过）；
- 缺的不是"支持 grammar"，而是"区分合法与非法 type"。

## 二、建议（按顺序）

1. **类型注册表**：在 `hub/models.py` 增加 `KNOWN_VALUE_TYPES = {scalar, enum, set, sequence, range, pattern, struct, text, grammar}`，写入时校验，未知 type 报错。
   - 只加校验，不改任何既有值；
   - 历史数据全部是已知类型，不受影响。
2. **grammar 的 data 结构约束**：`{rule:str, expr:str, deps:list[str]}`，deps 保序不去重。
3. **subject 类型**：等 `field`/`grammar_rule` 单独批，不与本项合并。

## 三、不建议

- 新增第 22 个 aspect；
- 为 grammar 单独造一套 Fact 类型；
- 现在就把 H2 改成 grammar 并重算身份。

## 四、下一步

先做第 1 步（注册表 + 校验），跑一遍现有 21 类 value 的回归，确认无副作用；再谈 H2 迁移。

```
grammar_value_isolated_readback_verified
grammar_value_contract_change_proposed
```
