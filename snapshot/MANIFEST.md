# ProtoRAG 全项目快照（清理前）· 回退说明

> ★ **存放位置：git 分支 `snapshot/pre-cleanup-20261102`（不是 Release）**
> 原因：GitHub 的 `uploads.github.com` 资产端点只接受 multipart，且会把**整个
> multipart body**（含 boundary 与 part 头）**原样存成资产** ⇒ 下载回来多 243 字节的
> 包装、`tar` 解不开（实测）。⇒ 改用 **git 原生 blob**：md5 可校验、`git checkout`
> 直接恢复、无需解压。

> 快照时间：**2026-11-02 17:0x**　|　仓库：`https://github.com/sssxzl/ProtoRAG`
> 目的：在执行 `derived/` 清理与三项缺陷修复**之前**，把**整个项目**（含 gitignore 的产物）留一份可回退副本。

## 一、这个分支里有什么

| 文件（`snapshot/` 下） | 内容 | 原始体积 | 压缩后 |
|---|---|---|---|
| `derived_and_backups.tar.gz` | **整个 `derived/` 目录**（2701 个文件，与磁盘逐一对应）—— 知识中枢原料、已发表语料、语义规则库、实验与分析产物、历史残留 | 126 MB | **22 MB** |
| `cleanup_backup_20261102.tar.gz` | 2026-11-02 16:05 那轮清理的**全部备份**（16 个 `__pycache__`、`.pytest_cache`、`.ruff_cache`、一次性探针 `_crlf_probe_44148`、8 个根目录临时日志、两个过期备份目录、6 个 kamailio 深处字节码缓存） | 6 MB | 2 MB |
| `kb_ignored_files.tar.gz` | `kb/` 下被 gitignore 的 25 个文件（13 个 `client.log` 流量日志 + 11 个 kamailio TLS 测试证书 + 1 个 `pdb-server.init.d` + 1 个 `test.log`） | < 1 MB | 34 KB |
| `MANIFEST.md` | 本文件 | — | — |

> ★ **校验过的**：这 4 个文件的远端 blob md5 与本地**逐一一致**；
> 且远端 `derived_and_backups.tar.gz` 解包后为 **2701 个文件**（与磁盘一致）。

**代码本体不在这里** —— 它在 git 里，由 tag **`pre-cleanup-20261102`** 指向（commit `e611dd0`）。

## 二、覆盖范围核对

| 部分 | 是否在 GitHub | 位置 |
|---|---|---|
| 源码（`core/` `scripts/` `tests/` `tools/` `docs/` `fused_hub/`） | ✅ | git tag `pre-cleanup-20261102`（= `e611dd0`） |
| `kb/` 研究素材（RFC 原文、协议实现源码、历史漏洞、流量、专家笔记） | ✅ | git（6632 个文件已跟踪） |
| `derived/exp_semantic/`、`derived/exp_semantic_gain/` | ✅ | git（`.gitignore` 白名单放行，20 个文件已跟踪） |
| **`derived/` 其余 12 个子目录** | ⚠️ **不在 git**（被 `.gitignore:41` 的 `derived/*` 忽略） | **本 Release 的 `derived_and_backups.tar.gz`** |
| 仓库外清理备份 | ⚠️ 不在 git | **本 Release 的 `cleanup_backup_20261102.tar.gz`** |
| `kb/` 的 25 个 gitignore 文件 | ⚠️ 不在 git | **本 Release 的 `kb_ignored_files.tar.gz`** |

⇒ **三个 Asset 合起来 = git 之外的全部内容** ⇒ 回退后与快照时刻**逐字节等价**。

## 三、怎么回退

### 3.1 只回退代码（最常见）

```bash
git fetch origin
git checkout pre-cleanup-20261102        # 或：git reset --hard pre-cleanup-20261102
```

### 3.2 回退 `derived/` 产物

```bash
# ① 从快照分支取出压缩包（不下载，走 git）
git checkout snapshot/pre-cleanup-20261102 -- snapshot/derived_and_backups.tar.gz
# ② 解压回仓库根目录（tar 会保留原相对路径）
tar -xzf snapshot/derived_and_backups.tar.gz -C /e/科研/想法idea/rag-chatafl/
```

### 3.3 回退清理备份 / kb 未入库文件

```bash
tar -xzf cleanup_backup_20261102.tar.gz -C /e/科研/想法idea/
tar -xzf kb_ignored_files.tar.gz       -C /e/科研/想法idea/rag-chatafl/
```

### 3.4 一键全量回退（推荐）

```bash
cd /e/科研/想法idea/rag-chatafl
git fetch origin
git reset --hard pre-cleanup-20261102          # 代码回退
tar -xzf <下载目录>/derived_and_backups.tar.gz -C .    # derived/ 回退
tar -xzf <下载目录>/cleanup_backup_20261102.tar.gz -C /e/科研/想法idea/
tar -xzf <下载目录>/kb_ignored_files.tar.gz -C .
```

## 四、⚠️ 注意事项

1. **`derived/` 被 gitignore ⇒ 删除不可逆、无版本回退。** 这是本快照存在的唯一理由。
   `docs/kb_scope_trim_cleanup_plan.md:522`（R8）已登记同一风险。
2. **`derived/per_source/**/facts/` 与 `derived/seeds/` 没有任何其它备份机制**
   （`local/` 里的决策记录只记路径、不含内容）⇒ 清理前**必须**先解包本 Release。
3. `derived/exp_semantic/` 与 `derived/exp_semantic_gain/` **已入库**，即使误删也能 `git checkout` 恢复。
4. 恢复后建议跑一次护栏确认基线一致：
   ```bash
   E:/app/Anaconda3/python.exe tools/qa/run_guarded_pytest.py --out-dir <输出目录>
   # 期望：37 failed / 1445 passed / 20 errors / 1 skipped（FAILED 与 ERROR 集合新增 0 / 消失 0）
   ```

## 五、快照时刻的代码状态（`e611dd0`）

```
e611dd0 chore: 清理根目录三个一次性修复脚本（零引用，改用后未再使用）
de7d5f9 fix(action-seq): 批次 1.5 改动 4/5 —— 让 ⑤ 层种子真正「服务端可收」
955e325 feat(semantic): 批次 1.5 —— 打通「RFC 源 → 知识中枢 → 消费」链路（三级断链）
ae7dd1c fix(seed): P2-5 文件名编号宽度不得随总条数变化（基准层文件名必须稳定）
39ef9ef fix(action-seq): 修 R-3（P0，⑤ 种子漏跑 prologue）+ G2 比率口径 + P2-6/P2-7
470775a fix(action-seq): 修完批次 1 第二轮 QA 复验查出的 5 个开放缺陷（R-1/R-2/P1-2/P2-1~P2-3）
```

护栏基线：**37 failed / 1445 passed / 20 errors / 1 skipped**（FAILED 与 ERROR 集合**新增 0 / 消失 0**）。
