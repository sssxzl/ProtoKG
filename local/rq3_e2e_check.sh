#!/bin/bash
# ★ RQ3 端到端自检 —— 语料 → 干跑 → 预检 → 编排 dry 模式 → 采集 → 指标 → 回填（dry）
#
# 用法（在 Windows 本机，Git Bash / WSL 均可；VM 相关步骤需 ssh 可达）：
#     bash local/rq3_e2e_check.sh
#
# 退出码: 0 = 全部环节通过；非 0 = 有环节失败
#
# ★ 本脚本**不启动正式实验**：编排只做 dry 模式（校验命令拼装，不实际 docker run），
#   回填只做 dry-run（打印目标文本，不写 docx）。
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# ★ Python 解释器：优先用 RQ3_PYTHON，其次探测 Anaconda（managed python 无 pytest），
#   最后退回 python3。Windows 下路径含盘符，Git Bash 需转成 /e/... 形式。
PY="${RQ3_PYTHON:-}"
if [ -z "$PY" ]; then
  for cand in "E:/app/Anaconda3/python.exe" "/e/app/Anaconda3/python.exe" \
              "E:/python/python.exe" "/e/python/python.exe"; do
    if [ -x "$cand" ]; then PY="$cand"; break; fi
  done
fi
[ -z "$PY" ] && PY="python3"
SSH_KEY="${RQ3_SSH_KEY:-$HOME/.ssh/vm_ubuntu_zxy}"
VM="${RQ3_VM:-zxy@192.168.37.130}"
FAIL=0

step()  { echo; echo "=== $1 ==="; }
ok()    { echo "  [PASS] $1"; }
bad()   { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

cd "$ROOT"
echo "解释器: $PY"

# ---- 1. 语料构建 + 断言 ----
step "1/8 语料构建 + A1–A10 断言"
if "$PY" scripts/rq3_build_corpus.py > /tmp/rq3_e2e_build.log 2>&1; then
  ok "语料构建成功（A1–A10 全绿）"
  grep -E "^  A |^  B |^  C |^  D |断言:" /tmp/rq3_e2e_build.log | sed 's/^/  /'
else
  bad "语料构建失败（见 /tmp/rq3_e2e_build.log）"
  tail -20 /tmp/rq3_e2e_build.log | sed 's/^/  /'
fi

# ---- 2. 定向字典严格超集 ----
step "2/8 定向字典严格超集（D→C 单变量的前提）"
"$PY" - <<'PYEOF'
import sys
sys.path.insert(0, "local")
import rq3_common as C
base = C.dict_tokens(C.dict_dir() / "rtsp_base.dict")
tgt = C.dict_tokens(C.dict_dir() / "c_targeted.dict")
print(f"  base={len(base)} targeted={len(tgt)} new={len(tgt-base)}")
assert base < tgt, "定向字典必须是基础字典的严格超集"
print("  严格超集 ✓")
PYEOF
[ $? -eq 0 ] && ok "定向字典是基础字典的严格超集" || bad "定向字典超集性质不成立"

# ---- 3. 单元测试 ----
step "3/8 单元测试"
if "$PY" -m pytest tests/ -q > /tmp/rq3_e2e_pytest.log 2>&1; then
  ok "pytest 全绿：$(tail -1 /tmp/rq3_e2e_pytest.log)"
else
  bad "pytest 有失败（见 /tmp/rq3_e2e_pytest.log）"
  tail -20 /tmp/rq3_e2e_pytest.log | sed 's/^/  /'
fi

# ---- 4. shell 语法检查 ----
step "4/8 VM 脚本语法检查"
for f in local/rq3_preflight.sh local/rq3_orchestrate.sh local/rq3_snapshot.sh \
         local/rq3_collect_live555.sh local/rq3_oracle_batch.sh \
         local/rq3_smoke_test.sh; do
  if bash -n "$f" 2>/dev/null; then ok "$(basename "$f") 语法 OK"
  else bad "$(basename "$f") 语法错误"; fi
done

# ---- 5. VM 预检 ----
step "5/8 VM 预检（H1–H12）"
if ssh -i "$SSH_KEY" "$VM" 'cd /home/zxy && bash rq3_preflight.sh' \
     > /tmp/rq3_e2e_preflight.log 2>&1; then
  ok "VM 预检全部通过"
  grep -cE '^\[PASS\]' /tmp/rq3_e2e_preflight.log | sed 's/^/  PASS 项数: /'
else
  bad "VM 预检有 FAIL（见 /tmp/rq3_e2e_preflight.log）"
  grep -E '^\[FAIL\]|^\[INFO\]' /tmp/rq3_e2e_preflight.log | sed 's/^/  /'
fi

# ---- 6. 编排 dry 模式（不实际启动容器）----
step "6/8 编排 dry 模式（校验命令拼装）"
DRY_OUT=$(bash local/rq3_orchestrate.sh --dry-run 2>&1)
if echo "$DRY_OUT" | grep -q -- "--network none"; then
  ok "编排命令含 --network none（关闭 ChatAFL 增强）"
else
  bad "编排命令缺 --network none"
fi
for g in A B C D; do
  n=$(echo "$DRY_OUT" | grep -c "rq3_${g}_" || true)
  [ "$n" -gt 0 ] && ok "组 $g 的容器命令已生成（$n 条）" \
                || bad "组 $g 未生成容器命令"
done
echo "$DRY_OUT" | grep -E "rq3_[ABCD]_" | head -4 | sed 's/^/  /'

# ---- 7. 采集脚本 dry 模式 ----
step "7/8 采集脚本 dry 模式"
if bash local/rq3_collect_live555.sh --dry-run > /tmp/rq3_e2e_collect.log 2>&1; then
  ok "采集脚本 dry 模式通过"
else
  bad "采集脚本 dry 模式失败（见 /tmp/rq3_e2e_collect.log）"
  tail -10 /tmp/rq3_e2e_collect.log | sed 's/^/  /'
fi

# ---- 8. docx 回填 dry 模式 ----
step "8/8 docx 表 18 回填 dry 模式（不写文件）"
if "$PY" local/_fill_rq3_docx.py --dry-run > /tmp/rq3_e2e_docx.log 2>&1; then
  ok "回填 dry 模式通过（目标单元格已计算）"
  grep -A6 "待写单元格" /tmp/rq3_e2e_docx.log | sed 's/^/  /'
else
  bad "回填 dry 模式失败（见 /tmp/rq3_e2e_docx.log）"
  tail -10 /tmp/rq3_e2e_docx.log | sed 's/^/  /'
fi

# ---- 汇总 ----
echo
echo "================ E2E 自检结论 ================"
if [ "$FAIL" -eq 0 ]; then
  echo "全部环节通过 ✓"
  exit 0
fi
echo "失败环节数: $FAIL"
exit 1
