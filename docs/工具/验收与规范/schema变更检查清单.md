# schema 变更检查清单（**由 guard/verify_docs_consistency.py --schema-map 自动生成**）

## 改 `aspect_registry.json` 时 ⇒ 必须同步检查

- [ ] knowledge_slots.json 的 aspect_map（每个 aspect 要有落位）
- [ ] 抽取器产出的 aspect 名（core/fused/extraction/）
- [ ] 消费端桶映射（core/fused/hub/hub_view.py 的 _BUCKET_BY_*）
- [ ] resolver 的消解语义（core/fused/downstream/resolver.py 的 _ASPECT_SEMANTICS）
- [ ] 契约文档（docs/设计/顶层设计/结构化知识中枢设计.md）

## 改 `subject_type_registry.json` 时 ⇒ 必须同步检查

- [ ] hub_view 的桶映射与主体类型判断
- [ ] 抽取器能产出的 subject.type
- [ ] 校验器的合法主体类型集（knowledge_slots.validate_slots）

## 改 `epistemic_type_registry.json` 时 ⇒ 必须同步检查

- [ ] resolver 的 SOURCE_PRIORITY（认识论优先级）
- [ ] 抽取器产出的 epistemic_type
- [ ] hub_view 的认识论类型投影

## 通用规则（见 `docs/工具/验收与规范/agent长期工作约束.md`）

- 改 `core/fused/hub/registry/` 任何 JSON ⇒ 跑 `pytest tests/hub/ -q` + **全量护栏**
- 改 `core/fused/` 任何文件 ⇒ 跑 **全量护栏**（判据「新增 0 / 消失 0」）
- 改 `core/paths.py` / `scripts/*` 入口 ⇒ 护栏 + **一条真实命令**（如 `--list-sources`）
- 改 `tests/**` ⇒ 该目录 pytest（期望集 id 含路径 ⇒ 移动文件即漂移）
- 改 `.gitignore` / `.gitattributes` ⇒ **删一次 `guard/` 与 `tests/guard/` 再克隆验证**
- 纯文档 / 注释 ⇒ 可免（但要跑编码护栏）

★ **删除或改名任何路径/符号时 ⇒ 在 `guard/verify_docs_consistency.py` 的
  `RESIDUALS` 里加一条** ⇒ 否则文档里的引用不会被发现。

