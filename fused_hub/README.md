# Fused Knowledge Hub

> 结构化知识中枢模块
> 当前版本：结构化知识中枢（registry `core_version` 1.0 / 3 个注册表 / 4 份设计文档）

## 一、中枢定位

本目录是结构化知识中枢模块的文档与配置。中枢**按协议目标信息组织，不按知识源组织**。

> ⚠️ 这句话的范围是**本目录（中枢部件内部）**：指中枢的判定契约与目标配置按协议维度组织
> ——`schema/` 的三个注册表里**没有** `rfc`/`traffic`/`vuln` 这些源名桶（源在归一过程中被消解为
> `authority` 溯源字段）。而**知识输入与抽取产物**（`kb/`、`derived/per_source/`）本来就是
> **协议优先、源在第二层**的两维结构，两者不矛盾。

中枢的核心职责：

1. 把 RFC / expert_note / traffic / vuln / source 五源对同一协议事实空间的不同陈述归一到 canonical 协议结论
2. 每条归一过程可审计、可重放、可复核
3. 不为提高下游可用率而降低知识判定标准

## 二、目录导航

```
fused_hub/
├── README.md            ← 本文件
├── docs/                ← 四份设计文档
│   ├── fused_knowledge_hub_design.md     ← v2 Layer 0 设计真源（知识原子 / 防矛盾 / LLM 安全）
│   ├── fused_canonical_spec.md           ← canonical 序列化规范 + 确定性 ID
│   ├── fused_compatibility_mapping.md    ← 早期 → 当前 映射规则
│   └── RTSP协议档案草案.md           ← Layer 1 Profile 首个实例（草案）
├── schema/              ← 3 个注册表 JSON（core_version 均为 "1.0"）
│   ├── subject_type_registry.json       (1211 B, 7 个 subject type)
│   ├── aspect_registry.json             (5148 B, 19 个 aspect)
│   └── epistemic_type_registry.json     (965 B, 4 个 epistemic type)
└── targets/             ← per-protocol Profile（4 协议）
    ├── ftp/profile.json + ftp_base.dict
    ├── rtsp/profile.json + rtsp_base.dict
    │   + rtsp_playable_streams.json + rtsp_request_templates.json
    ├── sip/profile.json
    ├── smtp/profile.json
    ├── rtsp_request_templates.json
    └── rtsp_streams.json
```

> ⚠️ `schema/` 当前是**单协议平铺**结构：`core/fused/registry.py:29-33` 按固定文件名加载三个注册表。
> 新增协议需先改造为 per-protocol 目录约定（如 `fused_hub/schema/<协议>/`），并让 `load_registry`
> 支持 `base_dir` 切换（`Registry.__init__` 已接受该参数）。

## 三、资产分布

中枢的代码、测试、构建产物分布：

| 资产类型 | 路径 | 当前状态 |
|----------|------|----------|
| 代码 | `core/fused/` | ✅ 已落地（33 个 .py：顶层 22 + `downstream/` 11）|
| 测试 | `tests/fused/` | ✅ 已落地（37 个测试文件；全量 **560 passed / 0 skipped / 0 failed**）|
| 构建产物（v2） | `derived/per_source/<协议>/<源>/facts/` | ✅ 已落地（4 协议 × 五源）|
| 构建产物（v1 遗留） | `derived/hub/` | ✅ 存在但为 v1 格式（131 facts / 81 entities / 34135 claims）|

## 四、与项目其他目录的关系

| 上游                                          | 下游                                                           |
| ------------------------------------------- | ------------------------------------------------------------ |
| `kb/<协议>/<源>/`（read-only 五源）                | `derived/per_source/<协议>/<源>/facts/<源>.jsonl`（v2 单源事实） |
| `derived/per_source/`                 | `core/fused/downstream/` 三层检索 → `scripts/seedgen.py`         |
| `derived/hub/`（v1 遗留融合产物）             | `core/fused/compat.py` 双轨映射（fact → Fact）                     |
| `fused_hub/targets/<协议>/profile.json`       | `scripts/seedgen.py`（per-protocol 参数与字典）                     |
| `derived/spec/<协议>/norms/norms.jsonl` | `core/fused/norm.py`（v1 norm → Fact）                         |

## 五、当前状态（2026-10-30）

**契约与配置（已就位）**
- ✅ `docs/` 4 份设计文档就位：`fused_knowledge_hub_design`（v2 Layer 0 真源）/ `fused_canonical_spec` /
  `fused_compatibility_mapping` / `rtsp_profile_v1_draft`（后三份为 Draft / 草案，尚未冻结）
- ✅ `schema/` 3 个注册表 JSON 就位（`core_version: "1.0"`）：`subject_type_registry`（7 type）/
  `aspect_registry`（19 aspect）/ `epistemic_type_registry`（4 type）

**代码与测试（已落地）**
- ✅ 代码 `core/fused/`：33 个 .py —— 顶层 22 个（models / canonical / registry / validation / export /
  compat / norm / expert_note / vuln / source / traffic 等）+ `downstream/` 11 个（edge_cover /
  generic_danger / boundary_probe / rag_seedgen / selector / strategy / source_availability /
  source_retrieval / resolver / seed_manifest / target_env）
- ✅ v1 的 reader / writer / runtime / pipeline 及其规则集已于 2026-10-09 退役并移除
- ✅ 测试 `tests/`：全量 **560 passed / 0 skipped / 0 failed**

**构建产物（已落地）**
- ✅ `derived/per_source/`：4 协议（ftp / rtsp / sip / smtp）× 五源（rfc / expert_note / traffic / vuln /
  source）共 20 组 v2 事实，fact_key 为 v2 六元组格式（`protocol`/`version`/`subject`/`aspect`/`condition`）
- ✅ `derived/hub/`：v1 时代遗留的融合产物（131 facts / 81 entities / 34135 claims，
  `fusion_version: fusion_v3+rules.sha256:43f7c7fe6`），fact_key 仍是 v1 扁平 `kind`/`property` 格式，
  由 `core/fused/compat.py` 做双轨映射
- 入口（**一次一个协议 x 一个知识源**）：
  `python scripts/build_hub.py --sources rfc --protocol rtsp`
  （每个源单独跑一次；`--sources` 只接受单个源，`--protocol` 必须显式指定）
- ⚠️ v2 脚本会真实写入 `derived/per_source/`（且默认先清空该协议旧 facts）；`derived/hub/` 为 v1 遗留产物，
  v2 脚本不再更新

**下游**
- ✅ `core/fused/downstream/` 11 个消费模块：三层检索（edge_cover / generic_danger / boundary_probe）+
  语料选择（selector）+ 冲突消解（resolver）+ 源可用性（source_availability）+ 种子生成（rag_seedgen）
- ✅ `scripts/seedgen.py`：产出 `.raw` + `<协议>.dict` 定向字典；`core/fused/downstream/source_availability.py`
  提供方法白名单降级链（`profile.allowed_methods` → `observed ∪ declared` → 兜底全部已知方法）

## 六、协议覆盖

| 维度 | 覆盖 | 说明 |
|------|------|------|
| `kb/` 知识库 | 8 协议 | dns / dtls / ftp / rtsp / sip / smtp / ssh / tls，每协议 5 源齐全 |
| `fused_hub/targets/` | 4 协议 | ftp / rtsp / sip / smtp（已建 Profile，可跑种子生成）|
| `derived/per_source/` | 4 协议 | ftp / rtsp / sip / smtp × 五源 |

`kb/sip/_bak_pjproject/` 是源码备份目录，非五源之一。
