# R24 补充：审计哈希的计算口径（★ Git blob LF 与工作区 CRLF 的区分）

> ★ 依审查方第 6 项要求 ｜★ commit `ac343e2eaa5c4e20d86ca001b89a9747586db93b`

---

## 一、★ 口径约定（★ 冻结哈希必须写明计算对象）

| 口径 | 定义 | 用途 |
|---|---|---|
| ★ **Git blob（LF）** | ★ `git show <commit>:<path>` 的**原始字节**；★ 文本文件按 `.gitattributes` 的 `* text=auto eol=lf` 存为 LF | ★ **★ 冻结哈希一律指此口径**；★ 跨平台可复现 |
| ★ 工作区字节 | ★ Windows checkout 后磁盘上的实际字节；★ 可能因 `core.autocrlf` 物化为 CRLF | ★ **仅作对照**；★ **不得与 blob 哈希混用** |

★ ★ **★ 审计报告中出现的每个 SHA256 都必须标明是哪一个口径。**

---

## 二、★ 实测对照

| 文件 | ★ Git blob（LF）SHA256 | ★ 工作区 SHA256 | ★ blob CRLF 数 | ★ 工作区 CRLF 数 | ★ 规范化到 LF 后相同 |
|---|---|---|---|---|---|
| `core/fused/extraction/rfc_extractor.py` | `7b91622987e89438…` | `7b91622987e89438…` | 0 | 0 | **True** |
| `core/fused/hub/canonical.py` | `82f233a7d69c9174…` | `1a679696be07e98b…` | 0 | 161 | **True** |
| `core/fused/hub/knowledge_slots.json` | `955f5368865063b5…` | `955f5368865063b5…` | 0 | 0 | **True** |
| `docs/audits/R24/R24_交付索引README.md` | `9368c8ef164b4f80…` | `5505931c8c0ad657…` | 0 | 67 | **True** |
| `docs/audits/R24/R24_影子修复逐记录对账.jsonl` | `6a71706a4e6d7d92…` | `9ac5ae95754fe50f…` | 0 | 0 | **False** |
| `guard/run_guarded_pytest.py` | `070418f8c22e62d5…` | `070418f8c22e62d5…` | 0 | 0 | **True** |
| `.github/workflows/ci.yml` | `20ebfae3f3ae6c85…` | `20ebfae3f3ae6c85…` | 0 | 0 | **True** |

---

## 三、★ 差异的两类成因（★ 必须区分）

### 3.1 纯行尾差异（★ checkout 物化）

★ `core/fused/hub/canonical.py`：★ blob 0 CRLF、★ 工作区 161 CRLF；
★ **规范化到 LF 后两者 SHA256 完全相同** ⇒ ★ 纯行尾差异。

★ 成因：★ `.gitattributes` 的 `* text=auto eol=lf` 只保证**入库**与**新检出**为 LF；
★ ★ 已存在的 CRLF 工作区文件**不会被自动重写**（★ 需 `git checkout -f` 或删除后重新物化）。

### 3.2 ★ 内容差异（★ 工作区已领先于 commit）

★ `R24_影子修复逐记录对账.jsonl`：★ blob 108,755 字节、★ 工作区 283,950 字节；
★ **规范化后仍不同** ⇒ ★ **内容本身不同**。

★ ⇒ ★ **★ 这正是本轮第 4 项的重写结果**：★ 工作区是**新版**，
★ ★ commit `ac343e2eaa5c4e20d86ca001b89a9747586db93b` 里是**旧版**（★ 241 行全标 retained 的那一版）。

★ ★ **★ 因此：★ 不得用工作区哈希代表 commit 的冻结哈希。**
★ ★ **★ 审查包（★ ZIP）取自 commit blob，★ 其 manifest 中的 SHA256 是 blob 口径。**

---

## 四、★ `.gitattributes` 的现有规则

    * text=auto eol=lf
    kb/** text=auto eol=lf
    *.dict -text
    *.raw -text
    *.sip -text
    derived/exp_semantic/candidates_frozen.jsonl -text
    derived/exp_semantic/candidates_train.jsonl -text
    derived/exp_semantic/candidates_holdout.jsonl -text
    derived/exp_semantic/truth/*.json -text

★ `* text=auto eol=lf` 与 `kb/** text=auto eol=lf` ⇒ ★ 文本文件入库为 LF、检出为 LF；
★ `*.dict` / `*.raw` / `*.sip` 等 `-text` ⇒ ★ 字节保护，★ 不做转换。

---

## 五、★ 复算方法

```bash
# ★ blob 口径（★ 推荐，★ 跨平台一致）
git show {COMMIT}:core/fused/hub/canonical.py | sha256sum

# ★ 工作区口径（★ 本机相关）
sha256sum core/fused/hub/canonical.py

# ★ 归一化后比较
git show {COMMIT}:core/fused/hub/canonical.py | tr -d '\r' | sha256sum
```

★ **★ 审查方在 ZIP 内校验文件时：★ 应使用 manifest 中的 blob 口径 SHA256。**
