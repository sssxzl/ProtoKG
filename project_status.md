# 项目状态

> 生成时间：2026-11-09（**只保留当前状态**；历史过程见 git 提交记录）
> 项目根目录：`E:\科研\想法idea\rag-chatafl`
> 项目名：**ProtoKG**（Protocol Knowledge Graph for Fuzzing Seed Generation）

---

## 一、项目目标

面向目标协议实现的协议模糊测试：从**五源协议知识**构建**可检索的协议知识图**，
用它生成**高价值初始种子**（`.raw` + 定向字典）。

---

## 二、当前架构（六层，单向依赖）

```
① 知识源层   kb/<协议>/<源>/                  只读（规范 / 源码 / 流量 / 漏洞 / 专家注记）
      ↓ ② 抽取层   core/fused/rfc_extractor.py 等 20 个模块   → fact
      ↓ ③ 中枢层   core/fused/{models,canonical,knowledge_slots,hub_entities,hub_layout}.py
      ↓ ③' 视图层  core/fused/hub_view.py         读中枢 ⇒ 组装视图（16 桶 + 分类视图 + 实体视图）
      ↓ ④ 知识图层 core/fused/graph_*.py          实体图 + 社区 + 社区报告
      ↓ ⑤ 消费层   core/fused/downstream/ + scripts/seedgen.py   → 种子
⑥ 护栏层      guard/ + tests/                期望集比对 / 编码卫生 / 分布校验
```

★ **④⑤ 并列依赖 ③'**（互不依赖）⇒ 层次无倒置。
★ **协议无关主程序**：协议特定配置全在 `profiles/<协议>/profile.json`。

---

## 三、当前状态（2026-11-09）

| 层 | 状态 | 关键产物 |
|---|---|---|
| ① 知识源 | ✅ | `kb/{rtsp,sip,smtp,DHCPv4}/<源>/` |
| ② 抽取 | ✅ | 五源抽取 + 23 种 RFC 内容形态判据 + LLM 状态机通道 |
| ③ 中枢 | ✅ | 按**知识分类 A~F** 落盘 + 实体主表 + 语义四库并入 |
| ③' 视图 | ✅ | 16 桶（对外契约不变）+ `by_category` + `entities` + `entity_by_name` |
| ④ 知识图 | ✅ | 实体图（带 `entity_id`）+ 社区（rtsp 4 / sip 4 / smtp 4 / dhcpv4 2） |
| ⑤ 消费 | ✅ | 五层种子：结构覆盖 / 通用危险 / 漏洞边界 / 目标聚焦 / 动作序列 |
| ⑥ 护栏 | ✅ | **7 failed / 1442 passed / 0 errors**（新增 0 / 消失 0） |

### 中枢的六个知识分类

| 分类 | 问句 | 内容 |
|---|---|---|
| `A_structure` | 由什么构成 | 方法 / 头 / 状态码 / 状态 |
| `B_interaction` | 怎么连 | 状态迁移 / 方法序列 / 报文实例 |
| `C_constraints` | 必须 / 不许 | 必填头 / 值域约束 / 语义规则 |
| `D_construction` | 怎么写出来 | 二进制布局 / 选项布局 |
| `E_observation` | 实际什么样 | 出现频次 |
| `F_security` | 哪里可能出错 | 安全属性 / 漏洞模式 |

---

## 四、下一步

| 项 | 内容 | 状态 |
|---|---|---|
| **E** | 纯度闸落地（删 `rag_seedgen.py` 的无条件放行）+ `profile` 源消解 | ⬜ |
| 收尾 | `derived/exp_semantic/`（2 个 xlsx）被 Excel 占用 ⇒ **关闭 Excel 后手动删** | 🔴 待用户 |
| GitHub | 仓库名 `ProtoRAG` → `ProtoKG`（仓库内已改完，**仓库名需手动改**） | 🔴 待用户 |
| 记忆 | `.workbuddy/memory/MEMORY.md` 需同步新结构与新名 | ⬜ |

---

## 五、真源索引

| 内容 | 真源 |
|---|---|
| 中枢契约（分类/槽位/属性/图/判据） | `core/fused/hub/registry/*.json` |
| 协议档案 | `profiles/<协议>/profile.json` |
| 项目结构逐文件说明 | `docs/工具/项目结构说明.md` |
| 中枢重设计实施总纲 + 进度 | `docs/设计/顶层设计/顶层设计/中枢重设计改造方案.md` |
| agent 长期约束 | `docs/工具/验收与规范/agent长期工作约束.md` |
| 交接入口 | `docs/工具/交接文档.md` |
| 验收口径 | `docs/工具/验收与规范/CI与验收说明.md` |
