# D4 field content 格式错误：根因与修复

## 一、解析契约

`core/fused/extraction/norm.py:96`：

```python
parse_field_content("语法 | <modality>: 语义") -> (syntax, modality, semantic)
```

分隔点是**最后一个 `| <word>:`**，不是任意 `|`。

## 二、修复前的错误

| 项 | 内容 |
|---|---|
| 我写的内容 | `siaddr | 4 | IP address of next server to use in bootstrap` |
| 解析结果 | 找不到 `| word:` ⇒ 整串当 syntax，semantic 为空 |
| 结果 | 只有 syntax Fact，definition 缺失 |

## 三、修复后的内容

```
4 | optional: IP address of next server to use in bootstrap
```

- syntax = `4`
- modality = `optional`
- semantic = `IP address of next server to use in bootstrap`

## 四、为什么 syntax 保住了而 definition 没有

`syntax` 取的是分隔点之前的全部文本，即使格式错也会得到非空字符串（`siaddr | 4 | …` 整串）；`semantic` 取分隔点之后，没有分隔点就是空串 ⇒ definition 被跳过。

## 五、性质

**实现错误**，不是契约缺陷。解析器行为符合其文档，是我构造 Norm 时用错了格式。修复不需要改解析器，也未添加 `siaddr` 硬编码。
