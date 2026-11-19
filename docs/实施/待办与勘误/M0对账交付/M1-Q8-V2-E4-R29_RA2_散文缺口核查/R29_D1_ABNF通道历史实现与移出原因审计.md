# D1 ABNF 通道历史实现与移出原因审计

## 一、历史实现确实存在，但只在字段形态

`core/fused/extraction/rfc_extractor.py:1159` 起：

```python
_RE_ABNF_FIELD = re.compile(
    r'^[ \t]+[a-z][a-z0-9-]*[ \t]+=[ \t]+"([A-Za-z][A-Za-z0-9_-]*):"'
    r'(?P<rhs>[^"]*)$', re.MULTILINE)
```

`_extract_abnf_fields()` 只识别「`rule = "Field-Name:" value`」这种**头字段形态**（为 RFC 5322 设计），不解析通用 ABNF 文法规则。

## 二、能力边界

| 能力 | 是否有 |
|---|---|
| 头字段 ABNF | 有 |
| 通用规则（`request-line = method SP …`） | **无** |
| 跨行续写 | 无 |
| 表格 / 位域 | 无 |
| 原文行号映射 | 部分（仅按行遍历） |
| 输出 Canonical 契约 | 是（走既有 field Norm） |

## 三、移出原因

代码注释记录：`正文含 ABNF 语法块 → method` 的分类规则**被实测证伪后移除**（`rfc_extractor.py:899`）。也就是说被移出的是**分类启发式**，不是这个字段抽取器本身——字段抽取器仍在，只是覆盖面窄。

## 四、结论

「恢复 ABNF 通道」不等于恢复某段被删代码：**通用规则解析此前根本不存在**，需要新写最小实现，而不是回滚。
