# Hub 兼容与绕行路径

## 一、Hub

- `load_facts`：`json.loads`，不做类型校验 ⇒ 历史 `str` 类型正常读取；
- `build_entity_index`：只读 `fact_key.subject`，与 value 无关；
- `get_fact_view`：原样透传。

## 二、绕行路径（**存在**）

| 路径 | 是否经门禁 |
|---|---|
| `norm._make_fact` | 是 |
| 直接构造 `Fact(...)`（如测试、脚本） | **否** |
| `Fact` 反序列化（load_facts） | 否（有意保留） |
| `rfc_forms` 等直接 `Value(...)` 后自建 Fact | **否**（未核完） |

## 三、因此验收只能判"部分通过"

```
value_type_registry_partial
```

理由：写入点未做到唯一收敛，仍有构造 Fact 的旁路。要真正闭合，需要把校验下沉到 `Fact.__post_init__`，那会触及 models 的构造语义，需单独批准。
