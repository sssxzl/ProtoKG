# profiles/ —— 协议接入档案（项目侧）

> ★ 本目录回答「**怎么测这个协议**」，不是「这个协议是什么」。
> ★ 「协议是什么」在 `kb/<协议>/<源>/`（**外部提供的知识库**，随提供方更换）。

## 目录结构

```
profiles/<协议>/
├── profile.json         协议接入参数（transport/encoding/allowed_methods/raw_format…）
│                          + 投放配置（default_url/resources_file/boundary_probe…）
├── skeleton.json        人工逆向的协议结构（状态机 / 字段语义）
├── rfc_config.json      抽取配置（规范的哪些章节算方法 / 字段定义）
├── <协议>.dict          定向字典（投放物）
└── <协议>_streams.json  目标服务的资源清单（投放物）
```

## 与其它目录的分工

| 目录 | 回答 | 谁提供 | 随知识库更换？ |
|---|---|---|---|
| `kb/<协议>/<源>/` | 协议**是什么** | 外部 | ❌ 会换 |
| `kb/templates/` | 怎么填注记 | 项目 | ❌ 保留 |
| `profiles/<协议>/` | **怎么测**它 | 项目 | ❌ 保留 |
| `core/fused/hub/` | 中枢**怎么组织知识**（含契约 JSON） | 项目 | ❌ 保留 |

## 中枢契约在哪

契约（`knowledge_slots.json` / 3 个注册表 / `graph_schema.json`）**已按层归位到代码包**：

```
core/fused/hub/knowledge_slots.json        ③ 中枢：知识分类 A~F + 槽位 + aspect_map
core/fused/hub/registry/*.json              ③ 中枢：subject / aspect / epistemic 三个注册表
core/fused/graph/graph_schema.json          ④ 图层：节点类型 / 边类型 / 遍历规则
```

⇒ 契约与实现同处 ⇒ 改契约时不会漏改代码；加载路径用 `__file__` 相对 ⇒ **不依赖进程 cwd**。

## 两阶段接入

| 阶段 | 内容 | 状态检查 |
|---|---|---|
| **I · 知识接入** | 放 `kb/<协议>/{spec,协议实现源码,数据流量,历史漏洞,expert_note}/` ⇒ ②抽取 ③中枢 ④知识图 | `python scripts/check_protocol_ready.py --protocol <协议>` |
| **II · 测试接入** | 准备 `profiles/<协议>/` ⇒ ⑤种子生成 | 同上（同一命令报告两阶段） |

⇒ 阶段 I 可以**完全自动**；阶段 II 的 `profile.json` **八成可由
`python scripts/onboard_protocol.py --protocol <协议>` 从规范自动生成**，
剩 3 项必须人工：`url_placeholders` / `resources_file` / `boundary_probe`。
