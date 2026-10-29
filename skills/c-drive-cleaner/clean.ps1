#Requires -Version 5.1
<#
    clean.ps1 — c-drive-cleaner 受控清理执行器

    默认只预览，绝不删除。必须显式加 -ReallyDelete 才动手。
    所有路径必须在 safety\allowed-targets.json 白名单内，不在名单内一律拒绝。

    用法：
      .\clean.ps1                                  # 预览 tier1
      .\clean.ps1 -Profile tier1,browser,windows    # 预览三组
      .\clean.ps1 -Profile tier1 -ReallyDelete      # 真正删除
      .\clean.ps1 -Profile browser -ReallyDelete -Quarantine   # 移到 D 盘隔离区而非删除
      .\restore.ps1 -Manifest reports\clean-xxx.json           # 从隔离区还原
#>
[CmdletBinding()]
param(
    [string[]]$Profile = @('tier1'),
    [switch]$ReallyDelete,
    [switch]$Quarantine,
    [string]$QuarantineRoot = 'D:\C-Quarantine',
    [switch]$EmptyTrash,
    [switch]$Json,
    [int]$MaxSecondsPerTarget = 600
)

$ErrorActionPreference = 'Continue'
$SkillRoot = $PSScriptRoot
$whitelistPath = Join-Path $SkillRoot 'safety\allowed-targets.json'
$reportsDir = Join-Path $SkillRoot 'reports'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$manifestPath = Join-Path $reportsDir "clean-$stamp.json"

# ---------- 基础工具 ----------

function Expand-Literal {
    param([string]$Text)
    if ([string]::IsNullOrWhiteSpace($Text)) { return '' }
    $out = [Environment]::ExpandEnvironmentVariables($Text)
    if ($out.Length -gt 3) { $out = $out.TrimEnd('\') }
    return $out
}

function Get-NormalizedPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) { return '' }
    $full = [System.IO.Path]::GetFullPath($Path)
    if ($full.Length -gt 3) { $full = $full.TrimEnd('\') }
    return $full
}

function Test-UnderPath {
    param([string]$Child, [string]$Parent)
    if ([string]::IsNullOrWhiteSpace($Child) -or [string]::IsNullOrWhiteSpace($Parent)) { return $false }
    $c = $Child.TrimEnd('\')
    $p = $Parent.TrimEnd('\')
    if ($c.Equals($p, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    return $c.StartsWith($p + '\', [StringComparison]::OrdinalIgnoreCase)
}

function Test-ReparseAncestry {
    param([string]$Path)
    $cur = Get-NormalizedPath $Path
    $guard = 0
    while ($cur -and $guard -lt 64) {
        try {
            $item = Get-Item -LiteralPath $cur -Force -ErrorAction Stop
            if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                return $true
            }
        } catch { }
        $parent = Split-Path -Parent $cur
        if ([string]::IsNullOrWhiteSpace($parent)) { break }
        if ($parent -eq $cur) { break }
        $cur = $parent
        $guard = $guard + 1
    }
    return $false
}

function Get-DirStats {
    param([string]$Path)
    $files = 0
    $bytes = 0L
    try {
        $items = Get-ChildItem -LiteralPath $Path -Recurse -File -Force -ErrorAction SilentlyContinue
        if ($items) {
            foreach ($f in $items) {
                $files = $files + 1
                $bytes = $bytes + [long]$f.Length
            }
        }
    } catch { }
    return [PSCustomObject]@{ Files = $files; Bytes = $bytes }
}

function Format-Size {
    param([double]$Bytes)
    if ($Bytes -ge 1073741824) { return ('{0:N2} GB' -f ($Bytes / 1GB)) }
    if ($Bytes -ge 1048576) { return ('{0:N1} MB' -f ($Bytes / 1MB)) }
    if ($Bytes -ge 1024) { return ('{0:N0} KB' -f ($Bytes / 1KB)) }
    return ('{0:N0} B' -f $Bytes)
}

function Get-CFreeBytes {
    try {
        $d = Get-PSDrive C -ErrorAction Stop
        return [long]$d.Free
    } catch { return 0L }
}

function Get-RecycleBinBytes {
    # 只统计当前卷回收站里的数据文件（$R 前缀），用于判断清空是否真的生效
    $sum = 0L
    try {
        $items = Get-ChildItem -LiteralPath 'C:\$Recycle.Bin' -Recurse -File -Force -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like '$R*' }
        if ($items) {
            foreach ($i in $items) { $sum = $sum + [long]$i.Length }
        }
    } catch { }
    return $sum
}

# ---------- 白名单与守卫 ----------

if (-not (Test-Path -LiteralPath $whitelistPath)) {
    Write-Host "拒绝执行：找不到白名单 $whitelistPath" -ForegroundColor Red
    exit 2
}
$wl = Get-Content -LiteralPath $whitelistPath -Raw -Encoding UTF8 | ConvertFrom-Json

$protected = @()
foreach ($p in $wl.protected_roots) { $protected += (Get-NormalizedPath (Expand-Literal $p)) }

function Test-TargetAllowed {
    param([string]$ResolvedPath)

    if ([string]::IsNullOrWhiteSpace($ResolvedPath)) {
        return [PSCustomObject]@{ Ok = $false; Reason = '路径为空' }
    }
    if (-not [System.IO.Path]::IsPathRooted($ResolvedPath)) {
        return [PSCustomObject]@{ Ok = $false; Reason = '不是绝对路径' }
    }
    $drive = [System.IO.Path]::GetPathRoot($ResolvedPath)
    if (-not $drive.Equals('C:\', [StringComparison]::OrdinalIgnoreCase)) {
        return [PSCustomObject]@{ Ok = $false; Reason = "不在 C 盘（$drive）" }
    }
    foreach ($prot in $protected) {
        if (Test-UnderPath -Child $ResolvedPath -Parent $prot) {
            return [PSCustomObject]@{ Ok = $false; Reason = "命中受保护目录 $prot" }
        }
    }
    if (Test-ReparseAncestry -Path $ResolvedPath) {
        return [PSCustomObject]@{ Ok = $false; Reason = '路径祖先含 junction/符号链接，拒绝对 C 盘空间归属做假设' }
    }
    if (-not (Test-Path -LiteralPath $ResolvedPath)) {
        return [PSCustomObject]@{ Ok = $false; Reason = '路径不存在' }
    }
    return [PSCustomObject]@{ Ok = $true; Reason = '' }
}

# ---------- 执行体 ----------

function Invoke-PurgeChildren {
    param([string]$TargetPath, [int]$TimeoutSeconds)

    $ok = 0
    $fail = 0
    $failedSamples = New-Object System.Collections.ArrayList
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $timedOut = $false

    $children = @(Get-ChildItem -LiteralPath $TargetPath -Force -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        if ($sw.Elapsed.TotalSeconds -gt $TimeoutSeconds) { $timedOut = $true; break }
        try {
            Remove-Item -LiteralPath $child.FullName -Recurse -Force -ErrorAction Stop
            $ok = $ok + 1
        } catch {
            $fail = $fail + 1
            if ($failedSamples.Count -lt 8) { [void]$failedSamples.Add(($child.FullName + '  <' + $_.Exception.GetType().Name + '>')) }
        }
    }
    $sw.Stop()

    return [PSCustomObject]@{
        Ok          = $ok
        Fail        = $fail
        TimedOut    = $timedOut
        FailedItems = @($failedSamples)
        Seconds     = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    }
}

function Invoke-QuarantineChildren {
    param([string]$TargetPath, [string]$DestRoot, [int]$TimeoutSeconds)

    $ok = 0
    $fail = 0
    $failedSamples = New-Object System.Collections.ArrayList
    $moved = New-Object System.Collections.ArrayList
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $timedOut = $false

    if (-not (Test-Path -LiteralPath $DestRoot)) {
        New-Item -ItemType Directory -Path $DestRoot -Force | Out-Null
    }

    $children = @(Get-ChildItem -LiteralPath $TargetPath -Force -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        if ($sw.Elapsed.TotalSeconds -gt $TimeoutSeconds) { $timedOut = $true; break }
        try {
            $dest = Join-Path $DestRoot $child.Name
            if (Test-Path -LiteralPath $dest) {
                $dest = Join-Path $DestRoot (($child.Name) + '_' + (Get-Random -Maximum 99999))
            }
            Move-Item -LiteralPath $child.FullName -Destination $dest -Force -ErrorAction Stop
            $ok = $ok + 1
            [void]$moved.Add([PSCustomObject]@{ Original = $child.FullName; Quarantined = $dest })
        } catch {
            $fail = $fail + 1
            if ($failedSamples.Count -lt 8) { [void]$failedSamples.Add(($child.FullName + '  <' + $_.Exception.GetType().Name + '>')) }
        }
    }
    $sw.Stop()

    return [PSCustomObject]@{
        Ok          = $ok
        Fail        = $fail
        TimedOut    = $timedOut
        FailedItems = @($failedSamples)
        Moved       = @($moved)
        Seconds     = [math]::Round($sw.Elapsed.TotalSeconds, 1)
    }
}

# ---------- 主流程 ----------

if (-not (Test-Path -LiteralPath $reportsDir)) {
    New-Item -ItemType Directory -Path $reportsDir -Force | Out-Null
}

$isAdmin = $false
try {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $pr = New-Object Security.Principal.WindowsPrincipal($id)
    $isAdmin = $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
} catch { }

$modeText = '预览（不删除）'
if ($ReallyDelete) {
    if ($Quarantine) { $modeText = '执行：移动到隔离区' } else { $modeText = '执行：删除（本机经回收站）' }
}

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  c-drive-cleaner 受控清理' -ForegroundColor Cyan
Write-Host "  模式: $modeText" -ForegroundColor $(if ($ReallyDelete) { 'Yellow' } else { 'Green' })
Write-Host "  管理员: $isAdmin" -ForegroundColor DarkGray
Write-Host '========================================' -ForegroundColor Cyan

$pending = New-Object System.Collections.ArrayList
foreach ($pname in $Profile) {
    if (-not ($wl.profiles.PSObject.Properties.Name -contains $pname)) {
        Write-Host "  跳过未知组: $pname" -ForegroundColor Yellow
        continue
    }
    foreach ($t in $wl.profiles.$pname.targets) {
        [void]$pending.Add([PSCustomObject]@{ Profile = $pname; Target = $t })
    }
}

if ($pending.Count -eq 0) {
    Write-Host '  没有可处理的目标。' -ForegroundColor Yellow
    exit 0
}

# 先全部过守卫，有任何一项不合格就整体拒绝执行（fail closed）
$plan = New-Object System.Collections.ArrayList
$blocked = New-Object System.Collections.ArrayList
foreach ($entry in $pending) {
    $resolved = Get-NormalizedPath (Expand-Literal $entry.Target.path)
    $check = Test-TargetAllowed -ResolvedPath $resolved
    if (-not $check.Ok) {
        [void]$blocked.Add([PSCustomObject]@{ Name = $entry.Target.name; Path = $resolved; Reason = $check.Reason })
        continue
    }
    $stats = Get-DirStats -Path $resolved
    [void]$plan.Add([PSCustomObject]@{
        Profile = $entry.Profile
        Name    = $entry.Target.name
        Path    = $resolved
        Mode    = $entry.Target.mode
        Admin   = [bool]$entry.Target.admin
        Note    = $entry.Target.note
        Files   = $stats.Files
        Bytes   = $stats.Bytes
    })
}

if ($blocked.Count -gt 0) {
    Write-Host ''
    Write-Host '  以下目标未通过安全检查：' -ForegroundColor Red
    foreach ($b in $blocked) {
        Write-Host ("    [拒绝] {0} -> {1}" -f $b.Name, $b.Path) -ForegroundColor Red
        Write-Host ("           原因: {0}" -f $b.Reason) -ForegroundColor DarkRed
    }
}

if ($plan.Count -eq 0) {
    Write-Host ''
    Write-Host '  没有通过检查的目标，退出。' -ForegroundColor Yellow
    exit 1
}

$totalBytes = 0L
$totalFiles = 0
Write-Host ''
foreach ($p in $plan) {
    $totalBytes = $totalBytes + $p.Bytes
    $totalFiles = $totalFiles + $p.Files
    $adminTag = ''
    if ($p.Admin) { $adminTag = ' [需管理员]' }
    Write-Host ("  {0,-22} {1,10}  {2,7} 个文件{3}" -f $p.Name, (Format-Size $p.Bytes), $p.Files, $adminTag) -ForegroundColor White
    Write-Host ("    {0}" -f $p.Path) -ForegroundColor DarkGray
}

Write-Host ''
Write-Host ("  合计可处理: {0} / {1} 个文件" -f (Format-Size $totalBytes), $totalFiles) -ForegroundColor Cyan

if (-not $ReallyDelete) {
    Write-Host ''
    Write-Host '  这是预览。要真正执行，重新运行并加 -ReallyDelete。' -ForegroundColor Green
    if ($Quarantine) { Write-Host "  当前为隔离模式，会移动到 $QuarantineRoot" -ForegroundColor Green }
    Write-Host ''
    exit 0
}

# ---- 真正执行 ----
$needsAdmin = @($plan | Where-Object { $_.Admin })
if ($needsAdmin.Count -gt 0 -and -not $isAdmin) {
    Write-Host ''
    Write-Host '  拒绝执行：选中的目标需要管理员权限。' -ForegroundColor Red
    exit 3
}

Write-Host ''
Write-Host '  开始执行...' -ForegroundColor Yellow
Write-Host ''

$freeBefore = Get-CFreeBytes
$results = New-Object System.Collections.ArrayList
$manifest = [ordered]@{
    schema      = 'c-drive-cleaner clean-manifest v1'
    timestamp   = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    mode        = $modeText
    admin       = $isAdmin
    free_before = $freeBefore
    targets     = @()
}

foreach ($p in $plan) {
    Write-Host ("  >> {0}" -f $p.Name) -ForegroundColor Cyan
    $tFree = Get-CFreeBytes

    if ($Quarantine -and $p.Mode -eq 'purge-children') {
        $destRoot = Join-Path (Join-Path $QuarantineRoot $stamp) ($p.Name)
        $r = Invoke-QuarantineChildren -TargetPath $p.Path -DestRoot $destRoot -TimeoutSeconds $MaxSecondsPerTarget
        $entry = [ordered]@{
            name = $p.Name; path = $p.Path; action = 'quarantine'; dest = $destRoot
            ok = $r.Ok; fail = $r.Fail; timed_out = $r.TimedOut; seconds = $r.Seconds
            failed_items = $r.FailedItems; moved = $r.Moved
        }
    } else {
        $r = Invoke-PurgeChildren -TargetPath $p.Path -TimeoutSeconds $MaxSecondsPerTarget
        $entry = [ordered]@{
            name = $p.Name; path = $p.Path; action = 'purge'
            ok = $r.Ok; fail = $r.Fail; timed_out = $r.TimedOut; seconds = $r.Seconds
            failed_items = $r.FailedItems
        }
    }

    $tFree2 = Get-CFreeBytes
    $entry['free_delta_mb'] = [math]::Round(($tFree2 - $tFree) / 1MB, 1)
    $manifest.targets += $entry

    $color = 'Green'
    if ($r.Fail -gt 0 -or $r.TimedOut) { $color = 'Yellow' }
    Write-Host ("     成功 {0}，失败 {1}，耗时 {2}s，C 盘释放 {3} MB" -f $r.Ok, $r.Fail, $r.Seconds, $entry['free_delta_mb']) -ForegroundColor $color
    if ($r.Fail -gt 0) {
        foreach ($f in $r.FailedItems) {
            Write-Host ("       占用/失败: {0}" -f $f) -ForegroundColor DarkYellow
        }
    }
    if ($r.TimedOut) {
        Write-Host '       达到单项时间上限，剩余文件未处理（可重跑继续）。' -ForegroundColor Yellow
    }
}

$freeAfter = Get-CFreeBytes
$manifest['free_after'] = $freeAfter
$manifest['reclaimed_mb'] = [math]::Round(($freeAfter - $freeBefore) / 1MB, 1)

# 本机实测（2026-10-28）：Clear-RecycleBin 在本会话里不可用，恒定抛 Win32Exception。
# 不要用 C 盘可用空间差值冒充"清空回收站释放了多少" —— 空间变化可能来自别处。
# 判定标准只看一件事：回收站体积本身有没有下降。
$trashReclaimMB = 0
if ($EmptyTrash) {
    Write-Host ''
    Write-Host '  清空回收站...' -ForegroundColor Yellow
    $rbBefore = Get-RecycleBinBytes
    Write-Host ("     清空前回收站: {0}" -f (Format-Size $rbBefore)) -ForegroundColor DarkGray
    try {
        Clear-RecycleBin -DriveLetter C -Force -ErrorAction Stop
        Write-Host '     Clear-RecycleBin 返回成功' -ForegroundColor DarkGray
    } catch {
        Write-Host ("     Clear-RecycleBin 抛异常: {0}" -f $_.Exception.Message) -ForegroundColor DarkYellow
    }
    Start-Sleep -Seconds 2
    $rbAfter = Get-RecycleBinBytes
    Write-Host ("     清空后回收站: {0}" -f (Format-Size $rbAfter)) -ForegroundColor DarkGray

    if ($rbBefore -eq 0) {
        Write-Host '     回收站本来就是空的，无内容可清。' -ForegroundColor DarkGray
        $trashReclaimMB = 0
    } elseif ($rbAfter -ge $rbBefore) {
        Write-Host '     >> 清空未生效：回收站体积没有下降。' -ForegroundColor Red
        Write-Host '        本机 Clear-RecycleBin 被拦截，请用资源管理器或第三方工具（如火绒）手动清空。' -ForegroundColor Red
        $trashReclaimMB = 0
    } else {
        $trashReclaimMB = [math]::Round(($rbBefore - $rbAfter) / 1MB, 1)
        Write-Host ("     回收站体积下降 {0} MB，清空生效。" -f $trashReclaimMB) -ForegroundColor Green
    }
    $manifest['trash_before_bytes'] = $rbBefore
    $manifest['trash_after_bytes'] = $rbAfter
    $manifest['trash_reclaim_mb'] = $trashReclaimMB
}

$manifest['free_after'] = $freeAfter
$manifest | ConvertTo-Json -Depth 8 | Out-File -LiteralPath $manifestPath -Encoding UTF8

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ("  C 盘可用空间: {0} -> {1}" -f (Format-Size $freeBefore), (Format-Size $freeAfter)) -ForegroundColor White
Write-Host ("  实际释放: {0}" -f (Format-Size ($freeAfter - $freeBefore))) -ForegroundColor Green
Write-Host ("  清单: {0}" -f $manifestPath) -ForegroundColor DarkGray
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

if ($Quarantine) {
    Write-Host "  需要还原时： .\restore.ps1 -Manifest `"$manifestPath`"" -ForegroundColor Cyan
    Write-Host ''
}
