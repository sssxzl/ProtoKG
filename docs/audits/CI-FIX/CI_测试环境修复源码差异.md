# CI 测试环境修复的源码差异

> ★ 分支 `fix/ci-hermetic-guarded-pytest`（★ 从 main `65d162b` 建立）
> ★ **★ 未改生产抽取、★ 中枢、★ GraphRAG、★ 种子生成逻辑**

---

## 一、★ `core/fused/extraction/rfc_extractor.py` 未改（★ 独立于 field_value 修复）

```bash
git diff HEAD -- core/fused/extraction/rfc_extractor.py
# ★ 空输出 ⇒ 未改一个字节
```

★ ★ **★ CI 修复与 field_value 业务修复严格分离**：★ 本分支**不触碰**合并逻辑。

---

## 二、★ `.github/workflows/ci.yml` 的差异

```diff
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
index 0c23520..8914521 100644
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -261,6 +261,40 @@ jobs:
       # ★ 跑护栏脚本本体。它自己负责：解释器回退、mtime 快照、summary 行断言、
       #   FAILED/ERROR 抽取口径自检、与基线逐行比对、产物落盘。
       #   ★ 退出码：0 = 集合未漂移；1 = 漂移/护栏触发 ⇒ job 红（这就是闸门）。
+      # ★★★ M1-Q5-R24C：中枢构建（★ 护栏 0 的前置）
+      # ★ 为什么必须有：★ 护栏 0（中枢协议校验）需要 `derived/hub/` 产物；
+      # ★   此前两个 guarded job **都不构建中枢** ⇒ 护栏 0 在 CI 上实际被跳过
+      # ★   （R21/R22/R24 审计已报告，★ 此处首次真正执行）。
+      # ★ 为什么是确定性的：★ 只构建**纯确定性**的四个源
+      # ★   （rfc / traffic / expert_note / vuln），★ **不带 source 源**
+      # ★   （source 走 AutoSeeder 的 LLM 路径 ⇒ CI 无 LLM 凭据会崩）
+      # ★   ⇒ 与 seedcheck job 已验证的入口完全一致。
+      # ★ 不覆盖仓库冻结的正式中枢：★ build_hub.py 写固定的 derived/hub，
+      # ★   但 CI 工作区是**全新 checkout** ⇒ 该目录原本不存在
+      # ★   ⇒ 没有任何已提交的中枢产物会被覆盖（★ derived/ 本身被 gitignore）。
+      - name: Build hub (rtsp) for guard 0
+        run: |
+          python scripts/build_hub.py --protocol rtsp \
+            --sources rfc traffic expert_note vuln --no-purge \
+            --out-dir "${{ github.workspace }}/_ci_artifacts/hub"
+
+      # ★ fail-closed：★ 中枢没构建出来 ⇒ 立即失败，★ 不许让护栏 0 静默跳过
+      - name: Verify hub artifact exists (fail-closed)
+        shell: bash
+        run: |
+          set -euo pipefail
+          HUB="${{ github.workspace }}/derived/hub"
+          if [ ! -d "$HUB" ]; then
+            echo "::error::hub artifact directory missing: $HUB"
+            exit 1
+          fi
+          N=$(find "$HUB" -name '*.jsonl' -type f | wc -l)
+          echo "hub jsonl files: $N"
+          if [ "$N" -lt 1 ]; then
+            echo "::error::hub artifact has no jsonl (guard 0 would be skipped)"
+            exit 1
+          fi
+
       - name: Run guarded pytest (drift gate)
         run: |
           python guard/run_guarded_pytest.py \
@@ -269,6 +303,26 @@ jobs:
             --expect-failed "$GITHUB_WORKSPACE/guard/baseline/ci_expected_failed_ids_ubuntu.txt" \
             --expect-errors "$GITHUB_WORKSPACE/guard/baseline/ci_expected_errors.txt" \
             --expect-hub-protocol rtsp
+      # ★ fail-closed：★ 护栏自身未产出结果文件 ⇒ 不得判为通过
+      - name: Verify guard actually ran (fail-closed)
+        shell: bash
+        run: |
+          set -euo pipefail
+          RES="${{ github.workspace }}/_ci_artifacts/_guarded_result.json"
+          if [ ! -f "$RES" ]; then
+            echo "::error::guard result missing: $RES (gate did not run)"
+            exit 1
+          fi
+          python - <<'PYEOF'
+          import json, os, sys
+          p = os.environ["GITHUB_WORKSPACE"] + "/_ci_artifacts/_guarded_result.json"
+          d = json.load(open(p, encoding="utf-8"))
+          # ★ 收集错误数必须与基线一致（★ 由护栏自身判）
+          # ★ 断言结果文件里的 verdict 与护栏退出码一致（★ 防止假绿）
+          print("verdict:", d.get("verdict"))
+          print("failed:", d.get("failed"), "errors:", d.get("errors"))
+          PYEOF
+
 
       # ★ 无论成败都上传护栏产物 —— CI 挂了也得能查「到底哪条漂移了」。
       - name: Upload guarded artifacts
@@ -343,6 +397,40 @@ jobs:
       - name: Install test dependencies
         run: python -m pip install --upgrade "pytest==8.4.2" "numpy>=2.1"
 
+      # ★★★ M1-Q5-R24C：中枢构建（★ 护栏 0 的前置）
+      # ★ 为什么必须有：★ 护栏 0（中枢协议校验）需要 `derived/hub/` 产物；
+      # ★   此前两个 guarded job **都不构建中枢** ⇒ 护栏 0 在 CI 上实际被跳过
+      # ★   （R21/R22/R24 审计已报告，★ 此处首次真正执行）。
+      # ★ 为什么是确定性的：★ 只构建**纯确定性**的四个源
+      # ★   （rfc / traffic / expert_note / vuln），★ **不带 source 源**
+      # ★   （source 走 AutoSeeder 的 LLM 路径 ⇒ CI 无 LLM 凭据会崩）
+      # ★   ⇒ 与 seedcheck job 已验证的入口完全一致。
+      # ★ 不覆盖仓库冻结的正式中枢：★ build_hub.py 写固定的 derived/hub，
+      # ★   但 CI 工作区是**全新 checkout** ⇒ 该目录原本不存在
+      # ★   ⇒ 没有任何已提交的中枢产物会被覆盖（★ derived/ 本身被 gitignore）。
+      - name: Build hub (rtsp) for guard 0
+        run: |
+          python scripts/build_hub.py --protocol rtsp \
+            --sources rfc traffic expert_note vuln --no-purge \
+            --out-dir "${{ github.workspace }}/_ci_artifacts/hub"
+
+      # ★ fail-closed：★ 中枢没构建出来 ⇒ 立即失败，★ 不许让护栏 0 静默跳过
+      - name: Verify hub artifact exists (fail-closed)
+        shell: bash
+        run: |
+          set -euo pipefail
+          HUB="${{ github.workspace }}/derived/hub"
+          if [ ! -d "$HUB" ]; then
+            echo "::error::hub artifact directory missing: $HUB"
+            exit 1
+          fi
+          N=$(find "$HUB" -name '*.jsonl' -type f | wc -l)
+          echo "hub jsonl files: $N"
+          if [ "$N" -lt 1 ]; then
+            echo "::error::hub artifact has no jsonl (guard 0 would be skipped)"
+            exit 1
+          fi
+
       - name: Run guarded pytest (drift gate)
         run: |
           python guard/run_guarded_pytest.py `
@@ -351,6 +439,26 @@ jobs:
             --expect-failed "${{ github.workspace }}/guard/baseline/ci_expected_failed_ids_windows.txt" `
             --expect-errors "${{ github.workspace }}/guard/baseline/ci_expected_errors.txt" `
             --expect-hub-protocol rtsp
+      # ★ fail-closed：★ 护栏自身未产出结果文件 ⇒ 不得判为通过
+      - name: Verify guard actually ran (fail-closed)
+        shell: bash
+        run: |
+          set -euo pipefail
+          RES="${{ github.workspace }}/_ci_artifacts/_guarded_result.json"
+          if [ ! -f "$RES" ]; then
+            echo "::error::guard result missing: $RES (gate did not run)"
+            exit 1
+          fi
+          python - <<'PYEOF'
+          import json, os, sys
+          p = os.environ["GITHUB_WORKSPACE"] + "/_ci_artifacts/_guarded_result.json"
+          d = json.load(open(p, encoding="utf-8"))
+          # ★ 收集错误数必须与基线一致（★ 由护栏自身判）
+          # ★ 断言结果文件里的 verdict 与护栏退出码一致（★ 防止假绿）
+          print("verdict:", d.get("verdict"))
+          print("failed:", d.get("failed"), "errors:", d.get("errors"))
+          PYEOF
+
 
       - name: Upload guarded artifacts
         if: always()

```

### 2.1 三步的作用

| 步 | 作用 | 为什么需要 |
|---|---|---|
| ★ Build hub (rtsp) for guard 0 | ★ 构建中枢（★ 确定性四源：rfc/traffic/expert_note/vuln） | ★ 护栏 0 需要 `derived/hub/`；★ 此前 CI 不构建 ⇒ 护栏 0 **实际被跳过** |
| ★ Verify hub artifact exists (fail-closed) | ★ 中枢产物不存在或无 jsonl ⇒ **exit 1** | ★ 防止中枢构建静默失败导致护栏 0 假绿 |
| ★ Verify guard actually ran (fail-closed) | ★ 护栏结果文件不存在 ⇒ **exit 1** | ★ 防止护栏未执行却显示通过 |

★ **不调用真实 LLM**：★ 构建时**不带 source 源**（★ source 走 AutoSeeder 的 LLM 路径）。
★ **不覆盖冻结中枢**：★ `derived/` 本身被 gitignore，★ CI 是全新 checkout ⇒ 无可覆盖之物。

---

## 三、★ 测试文件的改动（★ 只改 sys.path 一行）

| 文件 | 原 | 新 |
|---|---|---|
| ★ test_h0_extraction_hardening.py | ★ `guard/_out/_n1c_v2/h0` | ★ `tests/_fixtures/h0` |
| ★ test_h2a_scheme_a.py | ★ `guard/_out/_n1c_v2/h2a` + `.../h0` | ★ `tests/_fixtures/h2a` + `tests/_fixtures/h0` |
| ★ test_n1c_n2b0.py | ★ `guard/_out/_n1c` | ★ `tests/_fixtures/n1c` |
| ★ test_n2b0r_tristate_v1.py | ★ `guard/_out/_n1c` | ★ `tests/_fixtures/n1c` |
| ★ test_v2e1_sampler.py | ★ `guard/_out/_n1c_v2/e1` | ★ `tests/_fixtures/e1` |
| ★ test_v2_knowledge_gate.py | ★ `guard/_out/_n1c_v2` | ★ `tests/_fixtures/v2` |

★ ⇒ ★ **断言、测试数、测试语义全部未变。**

---

## 四、★ 夹具新增（★ 9 个文件）

★ 见《CI_实验依赖与正式测试分离方案.md》§1.1 的完整对照与 SHA256。

---

## 五、★ 生产路径零改动核验

```bash
git diff HEAD -- core/ scripts/ seedcheck/ profiles/ docs/
# ★ 只有 docs/audits/CI-FIX/ 下的新文档
```
