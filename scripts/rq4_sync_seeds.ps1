<#
.SYNOPSIS
    RQ4 种子同步脚本（本机 → VM）。

.DESCRIPTION
    把本机的 ProtoRAG 种子目录同步到 VM 的 /home/zxy/rq4/seeds/<proto>/。

    ★ 关键要求：**必须保持字节一致**（scp 保持字节；禁止 git/zip 转换行尾）。
      种子用 CRLF 行尾（AFLNet 的协议分区器按 \r\n 切消息），若被转成 LF，
      分区器会把整条种子当成一个 region → 状态机无法推进（静默失效，很难发现）。

    同步后做三层校验：
      1. 文件数一致
      2. 每个文件 MD5 一致（生成 MANIFEST.md5 双份比对）
      3. 行尾仍为 CRLF（抽样 + 全量字节检查）

    同步前先在本地跑 rq4_verify_seeds.py 自检（CRLF / 分区数 / 会话可播 / 方法可识别）。

.PARAMETER Protocol
    要同步的协议：rtsp / sip / smtp（可多选，逗号分隔）。默认全部。

.PARAMETER SeedRoot
    本机种子根目录。默认 derived/seeds。

.PARAMETER RemoteHost
    VM 主机。默认 zxy@192.168.37.130。

.PARAMETER RemoteRoot
    VM 上的种子根目录。默认 /home/zxy/rq4/seeds。

.PARAMETER SkipVerify
    跳过同步前的本地自检（不推荐）。

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\rq4_sync_seeds.ps1 -Protocol rtsp,sip,smtp
#>
[CmdletBinding()]
param(
    [string] $Protocol = 'rtsp,sip,smtp',
    [string] $SeedRoot = 'derived/seeds',
    [string] $RemoteHost = 'zxy@192.168.37.130',
    [string] $RemoteRoot = '/home/zxy/rq4/seeds',
    [string] $SeedSet = 'rq4_B',
    [string] $IdentityFile = "$HOME/.ssh/vm_ubuntu_zxy",
    [switch] $SkipVerify
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

# 协议列表：接受逗号分隔或空格分隔（PowerShell 5.1 传数组会退化成单个字符串）
$Protocols = @($Protocol -split '[,\s]+' | Where-Object { $_ -ne '' })

$Python = 'E:\app\Anaconda3\python.exe'
$Scp    = 'scp'
$Ssh    = 'ssh'
$SshOpt = @('-i', $IdentityFile, '-o', 'StrictHostKeyChecking=no', '-o', 'BatchMode=yes')
$ScpOpt = @('-i', $IdentityFile, '-o', 'StrictHostKeyChecking=no')

function Write-Step([string]$Text) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Text" -ForegroundColor Cyan
}

function Write-Ok([string]$Text) {
    Write-Host "  OK  $Text" -ForegroundColor Green
}

function Write-Err([string]$Text) {
    Write-Host "  ERR $Text" -ForegroundColor Red
}

function Get-Md5([string]$Path) {
    (Get-FileHash -Algorithm MD5 -Path $Path).Hash.ToLower()
}

Write-Step "RQ4 种子同步：$($Protocol -join ', ')  →  ${RemoteHost}:${RemoteRoot}"

# ---------------------------------------------------------------------
# 1. 同步前本地自检（CRLF / 分区数 / 会话可播 / 方法可识别）
# ---------------------------------------------------------------------
if (-not $SkipVerify) {
    Write-Step "本地结构自检（rq4_verify_seeds.py）..."
    foreach ($p in $Protocols) {
        $dir = Join-Path $SeedRoot "$p/$SeedSet"
        if (-not (Test-Path $dir)) {
            Write-Err "种子目录不存在: $dir —— 先跑 seedgen.py 生成"
            exit 2
        }
        & $Python 'scripts\rq4_verify_seeds.py' --seed-dir $dir --protocol $p
        if ($LASTEXITCODE -ne 0) {
            Write-Err "本地自检未通过: $p —— 拒绝同步（避免把坏种子送上 VM）"
            exit 1
        }
        Write-Ok "本地自检通过: $p"
    }
}

# ---------------------------------------------------------------------
# 2. 逐协议 scp 同步 + 三层校验
# ---------------------------------------------------------------------
foreach ($p in $Protocols) {
    $src = Join-Path $SeedRoot "$p/$SeedSet"
    Write-Step "同步 $p : $src → ${RemoteHost}:${RemoteRoot}/$p/"

    # 远端目录先清空再传（避免残留上一轮的旧种子）
    # ★ 同时删掉 MANIFEST.md5 —— 它必须待在种子目录**之外**：
    #   AFLNet 的 read_testcases() 用 scandir() 遍历 -i 目录，会把所有常规非空文件
    #   都当测试用例读进来（只跳过 README.txt）→ 清单文件会污染种子集。
    & $Ssh @SshOpt $RemoteHost `
        "mkdir -p '${RemoteRoot}/$p' && rm -f '${RemoteRoot}/$p/'*.raw '${RemoteRoot}/$p'/MANIFEST.md5 '${RemoteRoot}/$p/'*.dict"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "远端清理失败: $p"
        exit 1
    }

    # scp 传 .raw（scp 保持字节，不做行尾转换）
    & $Scp @ScpOpt "$src/*.raw" "${RemoteHost}:${RemoteRoot}/$p/"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "scp 失败: $p"
        exit 1
    }

    # 本地生成 MANIFEST.md5（供远端比对）
    $local = @(Get-ChildItem -Path $src -Filter '*.raw' | Sort-Object Name)
    Write-Ok "已传 $($local.Count) 个 .raw"

    $manifestLines = @()
    foreach ($f in $local) {
        $manifestLines += ("{0} *{1}" -f (Get-Md5 $f.FullName), $f.Name)
    }
    $manifestText = ($manifestLines -join "`n") + "`n"

    # ★ 本地清单也写在种子目录**之外**（<seedset>.manifest.md5）——
    #   放在目录里会被 AFLNet 当成种子读进去（污染种子集）。
    $localManifest = "$src.manifest.md5"
    [System.IO.File]::WriteAllText($localManifest, $manifestText, (New-Object System.Text.UTF8Encoding($false)))

    # 远端也生成一份 MANIFEST.md5（远端自己算 MD5，与本地逐条比对）
    # 同样放在种子目录之外
    $remoteManifest = "${RemoteRoot}/$p.manifest.md5"
    $remoteCheck = @"
cd '${RemoteRoot}/$p' && md5sum *.raw > '${remoteManifest}' && cat '${remoteManifest}'
"@
    $remoteOut = & $Ssh @SshOpt $RemoteHost $remoteCheck
    if ($LASTEXITCODE -ne 0) {
        Write-Err "远端 MD5 生成失败: $p"
        exit 1
    }

    # ---- 校验 1：文件数一致 ----
    $remoteCount = ((& $Ssh @SshOpt $RemoteHost "ls -1 '${RemoteRoot}/$p/'*.raw | wc -l") | Out-String).Trim()
    if ([int]$remoteCount -ne $local.Count) {
        Write-Err "文件数不一致: 本地 $($local.Count) vs 远端 $remoteCount"
        exit 1
    }
    Write-Ok "文件数一致: $remoteCount"

    # ---- 校验 2：MD5 逐条一致 ----
    $remoteMap = @{}
    foreach ($line in ($remoteOut | Out-String).Trim() -split "`n") {
        $line = $line.Trim()
        if (-not $line) { continue }
        $parts = $line -split '\s+', 2
        if ($parts.Count -eq 2) {
            $remoteMap[$parts[1].Trim().TrimStart('*')] = $parts[0].Trim()
        }
    }
    $mismatch = @()
    foreach ($f in $local) {
        $expect = Get-Md5 $f.FullName
        $actual = $remoteMap[$f.Name]
        if ($actual -ne $expect) { $mismatch += $f.Name }
    }
    if ($mismatch.Count -gt 0) {
        Write-Err "MD5 不一致: $($mismatch -join ', ')"
        exit 1
    }
    Write-Ok "MD5 逐条一致（$($local.Count) 个）"

    # ---- 校验 3：远端行尾仍为 CRLF ----
    # 用独立脚本做（不内嵌 python 代码）：命令要穿过 PowerShell→ssh→bash→python3
    # 四层转义，内嵌多行 python 会被引号吃掉（实测 bash syntax error）。
    $checker = "${RemoteRoot}/rq4_check_crlf.py"
    & $Scp @ScpOpt 'scripts/rq4_check_crlf.py' "${RemoteHost}:${checker}"
    $crlfOut = (& $Ssh @SshOpt $RemoteHost "python3 ${checker} '${RemoteRoot}/$p'") | Out-String
    $crlfBad = ($crlfOut.Trim() -split '\s+')[-1]
    if ($crlfBad -ne '0') {
        Write-Err "远端有 $crlfBad 个种子行尾被转换（CRLF → LF）"
        exit 1
    }
    Write-Ok "远端行尾仍为 CRLF"
}

Write-Step "同步完成"
foreach ($p in $Protocols) {
    $n = ((& $Ssh @SshOpt $RemoteHost "ls -1 '${RemoteRoot}/$p/'*.raw | wc -l") | Out-String).Trim()
    Write-Host "  ${RemoteRoot}/$p/ → $n 个 .raw" -ForegroundColor Green
}
exit 0
