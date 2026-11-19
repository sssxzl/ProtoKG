# T0-A 真实响应离线回放与最小修正

## 一、回放输入

| 项 | 值 |
|---|---|
| 缓存 | `T0A_实跑_20261119/cache_rfc3207.json`（22 条 item，doc 全为 rfc3207） |
| 原文 | `kb/smtp/spec/rfc3207.txt`，SHA256 `b004a203…` |
| 切块 | 6 块，与首次运行一致 |
| 模型调用 | 0 次 |

## 二、回放结果

| 项 | 值 |
|---|---|
| Norm | 13（与真实运行一致） |
| Fact | 13（不增不减） |
| Aspect | legal_boundary 8 / definition 5 |
| Subject | actor 9 / protocol 4，**0 个 header** |
| Evidence | 仍为 `file:rfc3207.txt#@<行号>`，锚点与真实运行相同 |

## 三、验证了哪几件事

1. 原有真实输出没有丢失：Norm/Fact 计数与词条一一对应；
2. 错误 header 身份被纠正，且没有把 STARTTLS 这类扩展名误标成头字段；
3. 不同 aspect 按既有规则映射：有 action/object 的约束进 legal_boundary，纯描述进 definition；
4. 真 Header 知识不受损：`field` Norm 仍产出 `header` + `syntax`；
5. 证据仍可回到原文行号；
6. 隔离 Hub 用回放 Fact 重建，可读回。

## 四、Gold 仍是 0/2

回放不改变 Gold 结果：模型原始输出里就没有 30-35 的条目，映射修正无法凭空造出知识。

## 五、最小补丁

`T0A_Subject与Aspect最小修正.patch`（95 行，仅 `norm.py`）：

- 新增 `_prose_subject_type`；
- 三处 `Subject(type="header")` 改用它；
- 两处兜底 `definition` 改 `legal_boundary`。
