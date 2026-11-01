#!/bin/bash
# ★ RQ1.2 Live555 有效性实验 —— P1/P2 全量数据采集（20 容器）
#
# 用法（在 VM 上）：./rq1_collect_live555.sh
# 输出：
#   /home/zxy/rq1_2_p1.csv     P1：初始种子/dry-run 刚结束时的 n_states/n_edges
#   /home/zxy/rq1_2_p2.csv     P2：24h 结束时的 n_states/n_edges/覆盖率/崩溃/路径
#   /home/zxy/rq1_2_summary.csv  按 (group, fuzzer) 聚合的均值表（可直接填 docx 表4）
#
# 数据来源与依据：
#   · plot_data 末行的 n_nodes/n_edges 与 ipsm.dot grep 计数【已实测 4/4 容器完全相等】，
#     故 P1 取 plot_data 首行、P2 取 plot_data 末行，不依赖易丢失的 ipsm.dot 快照。
#   · plot_data 列（chatafl 14 列 / aflnet 13 列）：
#     0 unix_time, 1 cycles_done, 2 cur_path, 3 paths_total, 4 pending_total,
#     5 pending_favs, 6 map_size, 7 unique_crashes, 8 unique_hangs, 9 max_depth,
#     10 execs_per_sec, 11 n_nodes, 12 n_edges, [13 chat_times 仅 chatafl]
#   · fuzzer_stats 作为覆盖率/崩溃/路径的交叉校验源。

set -u
OUT_P1=/home/zxy/rq1_2_p1.csv
OUT_P2=/home/zxy/rq1_2_p2.csv
OUT_SUM=/home/zxy/rq1_2_summary.csv
# 注意：不可用 GROUPS 作变量名——它是 bash 内建特殊变量（当前用户的组 ID 数组），赋值无效。
GRP_LIST="seed_reuse_chatafl seed_reuse_aflnet protorag_chatafl protorag_aflnet"
REPS="1 2 3 4 5"

# 容器内 plot_data 首行/末行
# ★ v2 修复（容器已停止时的采集）：实验结束后容器已 Exited → `docker exec` 无法进入
#   （报 "is not running"）→ 原实现会把所有字段读成 NA。
#   改为：**容器在跑时走 docker exec；容器已停时直接读宿主挂载目录**
#   /home/zxy/rq2_out/<grp>_<fuzzer>/r<n>/{plot_data,fuzzer_stats}
#   （容器以 root 运行 → 宿主普通用户无读权限，需 sudo -n；文件内容与容器内完全一致）。
plot_first() { docker exec "$1" bash -c 'grep -v "^#" /out/plot_data 2>/dev/null | head -1' 2>/dev/null; }
plot_last()  { docker exec "$1" bash -c 'grep -v "^#" /out/plot_data 2>/dev/null | tail -1' 2>/dev/null; }
# 容器内 fuzzer_stats 单字段
fs_field() {
  docker exec "$1" bash -c "grep '^$2' /out/fuzzer_stats 2>/dev/null | awk '{print \$3}'" 2>/dev/null
}

# ---- 宿主挂载目录回退（容器已停止时使用）----
# 容器名 rq2_<grp>_<fuzzer>_r<n> → 宿主目录 /home/zxy/rq2_out/<grp>_<fuzzer>/r<n>
host_dir_of() {
  local c="$1" rest
  rest="${c#rq2_}"
  echo "/home/zxy/rq2_out/${rest%_r*}/r${rest##*_r}"
}
# 读 plot_data（首行/末行），容器不可用时回退宿主目录
host_plot() {
  local c="$1" mode="$2" f
  f="$(host_dir_of "$c")/plot_data"
  sudo -n cat "$f" 2>/dev/null | grep -v "^#" | { [ "$mode" = "first" ] && head -1 || tail -1; }
}
# 读 fuzzer_stats 单字段，容器不可用时回退宿主目录
host_fs() {
  local c="$1" field="$2"
  sudo -n cat "$(host_dir_of "$c")/fuzzer_stats" 2>/dev/null \
    | grep "^$field" | awk '{print $3}'
}
# 统一入口：优先容器内，其次宿主目录
plot_first_of() { local v; v=$(plot_first "$1"); [ -z "$v" ] && v=$(host_plot "$1" first); printf '%s' "$v"; }
plot_last_of()  { local v; v=$(plot_last  "$1"); [ -z "$v" ] && v=$(host_plot "$1" last);  printf '%s' "$v"; }
fs_field_of()   { local v; v=$(fs_field  "$1" "$2"); [ -z "$v" ] && v=$(host_fs "$1" "$2"); printf '%s' "$v"; }

echo "group,rep,fuzzer,n_states,n_edges" > "$OUT_P1"
echo "group,rep,fuzzer,n_states,n_edges,bitmap_cvg,unique_crashes,unique_hangs,paths_total,execs_done" > "$OUT_P2"

for g in $GRP_LIST; do
  fuzzer=$(echo "$g" | sed 's/.*_//')
  # 短组名（seed_reuse / protorag），用于与 docx 表4 行映射对齐
  g_short=$(echo "$g" | sed 's/_chatafl$//; s/_aflnet$//')
  for r in $REPS; do
    c="rq2_${g}_r${r}"

    # ---- P1：plot_data 首行（dry-run 刚结束的状态机快照）----
    p1=$(plot_first_of "$c")
    if [ -n "$p1" ]; then
      IFS=',' read -r _t _cyc _cp _paths _pend _pf _cvg _cr _hg _dep _eps _n_st _n_ed _rest <<< "$p1"
      echo "$g_short,$r,$fuzzer,${_n_st:-NA},${_n_ed:-NA}" >> "$OUT_P1"
    else
      echo "$g,$r,$fuzzer,NA,NA" >> "$OUT_P1"
    fi

    # ---- P2：plot_data 末行 + fuzzer_stats 交叉校验 ----
    p2=$(plot_last_of "$c")
    if [ -n "$p2" ]; then
      IFS=',' read -r _t _cyc _cp _paths _pend _pf _cvg _cr _hg _dep _eps _n_st _n_ed _rest <<< "$p2"
      fs_cvg=$(fs_field_of "$c" bitmap_cvg)
      fs_cr=$(fs_field_of "$c" unique_crashes)
      fs_hg=$(fs_field_of "$c" unique_hangs)
      fs_paths=$(fs_field_of "$c" paths_total)
      fs_execs=$(fs_field_of "$c" execs_done)
      echo "$g_short,$r,$fuzzer,${_n_st:-NA},${_n_ed:-NA},${_cvg:-NA},${_cr:-NA},${_hg:-NA},${_paths:-NA},${fs_execs:-NA}" >> "$OUT_P2"
    else
      echo "$g_short,$r,$fuzzer,NA,NA,NA,NA,NA,NA,NA" >> "$OUT_P2"
    fi
  done
done

echo
echo "=== P1 (n_states/n_edges @ dry-run 结束) ==="
cat "$OUT_P1"
echo
echo "=== P2 (24h 末) ==="
cat "$OUT_P2"

# ---- 聚合：按 group+fuzzer 求均值/标准差，供 docx 表4 回填 ----
python3 - "$OUT_P1" "$OUT_P2" "$OUT_SUM" <<'PYEOF'
import csv, statistics, sys

def load(p):
    rows = []
    with open(p) as f:
        for r in csv.DictReader(f):
            # plot_data 用 ", " 分隔，切出的字段带前导空格 → 统一 strip
            for k in ('n_states','n_edges','bitmap_cvg','unique_crashes',
                      'unique_hangs','paths_total','execs_done'):
                if k in r and r[k] is not None:
                    v = str(r[k]).strip().replace('%','')
                    try: r[k] = float(v)
                    except ValueError: r[k] = None
            if 'rep' in r and r['rep'] is not None:
                try: r['rep'] = int(str(r['rep']).strip())
                except ValueError: pass
            rows.append(r)
    return rows

def agg(rows, keys):
    out = {}
    for r in rows:
        out.setdefault(tuple(r[k] for k in keys), []).append(r)
    return out

p1 = load(sys.argv[1]); p2 = load(sys.argv[2]); sump = sys.argv[3]

print()
print("="*104)
print("RQ1.2 Live555 汇总（5 rep）—— 对应 docx 表4 Live555 行")
print("="*104)

def stat(vals, fmt='{:.1f}'):
    vals = [v for v in vals if v is not None]
    if not vals: return ('NA','NA')
    m = statistics.mean(vals)
    sd = statistics.stdev(vals) if len(vals) > 1 else 0.0
    return (fmt.format(m), fmt.format(sd))

# 映射到表4 的 4 行
#   表4 行2 = AFLNet 原始种子（in-rtsp）| Chatafl  → group=seed_reuse, fuzzer=chatafl
#   表4 行3 = AFLNet 原始种子（in-rtsp）| aflnet   → group=seed_reuse, fuzzer=aflnet
#   表4 行4 = ProtoRAG（实验组）          | Chatafl  → group=protorag,   fuzzer=chatafl
#   表4 行5 = ProtoRAG（实验组）          | aflnet   → group=protorag,   fuzzer=aflnet
ROWMAP = [
    ('AFLNet 原始种子（in-rtsp）','Chatafl','seed_reuse','chatafl'),
    ('AFLNet 原始种子（in-rtsp）','aflnet', 'seed_reuse','aflnet'),
    ('ProtoRAG（实验组）',         'Chatafl','protorag',  'chatafl'),
    ('ProtoRAG（实验组）',         'aflnet', 'protorag',  'aflnet'),
]

a1 = agg(p1, ['group','fuzzer'])
a2 = agg(p2, ['group','fuzzer'])

hdr = f"{'表4行':<5}{'种子来源':<26}{'Fuzzer':<9}{'n_st(P1)':>9}{'n_st(P2)':>9}{'n_ed(P1)':>9}{'n_ed(P2)':>9}{'覆盖%(P2)':>12}{'崩溃(P2)':>10}{'路径(P2)':>11}"
print(hdr); print("-"*len(hdr))
rows_out = []
for i,(src,fz_label,g,fz) in enumerate(ROWMAP, start=2):
    r1 = a1.get((g,fz), []); r2 = a2.get((g,fz), [])
    ns1,_ = stat([r['n_states'] for r in r1], '{:.1f}')
    ne1,_ = stat([r['n_edges']   for r in r1], '{:.1f}')
    ns2,_ = stat([r['n_states'] for r in r2], '{:.1f}')
    ne2,_ = stat([r['n_edges']   for r in r2], '{:.1f}')
    cg,_  = stat([r['bitmap_cvg'] for r in r2], '{:.2f}')
    cr,_  = stat([r['unique_crashes'] for r in r2], '{:.2f}')
    pt,_  = stat([r['paths_total'] for r in r2], '{:.0f}')
    print(f"{i:<5}{src:<26}{fz_label:<9}{ns1:>9}{ns2:>9}{ne1:>9}{ne2:>9}{cg+'%':>12}{cr:>10}{pt:>11}")
    rows_out.append([i,src,fz_label,ns1,ns2,ne1,ne2,cg+'%',cr,pt])

with open(sump,'w',newline='') as f:
    w = csv.writer(f)
    w.writerow(['docx_row','seed_source','fuzzer','n_states_P1','n_states_P2','n_edges_P1',
                'n_edges_P2','bitmap_cvg_P2','unique_crashes_P2','paths_total_P2'])
    w.writerows(rows_out)
print()
print("覆盖率反超核对（protorag vs seed_reuse，同 fuzzer 同 rep）：")
w = t = 0
diffs = []
for fz in ('chatafl','aflnet'):
    for rep in range(1,6):
        a = [r for r in p2 if r['group']=='protorag'  and r['fuzzer']==fz and r['rep']==rep]
        b = [r for r in p2 if r['group']=='seed_reuse' and r['fuzzer']==fz and r['rep']==rep]
        if a and b and a[0]['bitmap_cvg'] is not None and b[0]['bitmap_cvg'] is not None:
            t += 1
            d = a[0]['bitmap_cvg'] - b[0]['bitmap_cvg']
            diffs.append(d)
            if d > 0: w += 1
            print(f"    {fz:<8} r{rep}: protorag {a[0]['bitmap_cvg']:.2f}% - seed_reuse {b[0]['bitmap_cvg']:.2f}% = {d:+.2f}pp")
print(f"  -> 胜率 (win rate): {w}/{t}")
if len(diffs) > 1:
    print(f"  -> 配对差值 均值 {statistics.mean(diffs):+.3f}pp, 标准差 {statistics.stdev(diffs):.3f}pp")

# 逐指标配对统计（覆盖率之外的辅助指标一律带 win-rate + 配对差值±标准差）
print()
print("=== 逐指标配对统计（protorag - seed_reuse，同 fuzzer 同 rep 配对）===")
for metric, label, fmt in [('bitmap_cvg','分支覆盖%(pp)','{:+.2f}'),
                            ('n_edges','n_edges','{:+.1f}'),
                            ('paths_total','路径数','{:+.0f}'),
                            ('n_states','n_states','{:+.1f}')]:
    print(f"-- {label} --")
    for fz in ('chatafl','aflnet'):
        ds = []
        for rep in range(1,6):
            a = [r for r in p2 if r['group']=='protorag'  and r['fuzzer']==fz and r['rep']==rep]
            b = [r for r in p2 if r['group']=='seed_reuse' and r['fuzzer']==fz and r['rep']==rep]
            if a and b and a[0][metric] is not None and b[0][metric] is not None:
                ds.append(a[0][metric] - b[0][metric])
        if not ds: continue
        wr = sum(1 for d in ds if d > 0)
        sd = statistics.stdev(ds) if len(ds) > 1 else 0.0
        print(f"   {fz:<8} 胜率 {wr}/{len(ds)}  配对差值均值 {fmt.format(statistics.mean(ds))}  标准差 {sd:.2f}"
              f"  [{' '.join(fmt.format(d) for d in ds)}]")
PYEOF

echo
echo "=== 产出 ==="
ls -la "$OUT_P1" "$OUT_P2" "$OUT_SUM"

# ---- 时序覆盖率曲线（支撑「反超稳定」论断，也是 RQ3 早期指标口径的参考）----
OUT_TS=/home/zxy/rq1_2_timeseries.csv
python3 - "$OUT_TS" <<'PYEOF'
import csv, subprocess, sys

def series(container):
    out = subprocess.run(['docker','exec',container,'bash','-c',
                          'grep -v "^#" /out/plot_data'], capture_output=True, text=True).stdout
    rows = []
    for l in out.strip().split('\n'):
        if not l.strip(): continue
        p = [x.strip() for x in l.split(',')]
        if len(p) >= 13:
            try: rows.append((int(p[0]), float(p[6].replace('%','')), int(p[3])))
            except ValueError: pass
    return rows

rows_out = []
for g in ('seed_reuse','protorag'):
    for fz in ('chatafl','aflnet'):
        for rep in range(1,6):
            rs = series(f"rq2_{g}_{fz}_r{rep}")
            if not rs: continue
            t0 = rs[0][0]
            for t, cvg, paths in rs:
                rows_out.append([g, fz, rep, round((t-t0)/3600.0, 4), cvg, paths])

with open(sys.argv[1], 'w', newline='') as f:
    w = csv.writer(f)
    w.writerow(['group','fuzzer','rep','rel_hours','bitmap_cvg','paths_total'])
    w.writerows(rows_out)

import statistics
buckets = [0.5,1,2,4,6,8,12,24]
print()
print("=== 时序覆盖率均值（按小时分桶，5 rep 平均）===")
print(f"{'group':<12}{'fuzzer':<9}" + "".join(f"{h:>9}h" for h in buckets))
for g in ('seed_reuse','protorag'):
    for fz in ('chatafl','aflnet'):
        cells = []
        for h in buckets:
            vals = [r[4] for r in rows_out if r[0]==g and r[1]==fz and abs(r[3]-h) < 0.2]
            cells.append(f"{statistics.mean(vals):>10.2f}" if vals else f"{'NA':>10}")
        print(f"{g:<12}{fz:<9}" + "".join(cells))
print(f"\n产出: {sys.argv[1]}")
PYEOF
