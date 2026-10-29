#Requires -Version 5.1
<#
    restore.ps1 — 从隔离区还原 clean.ps1 -Quarantine 移走的文件

    用法：
      .\restore.ps1 -Manifest .\reports\clean-20261028-121500.json
      .\restore.ps1 -Manifest .\reports\clean-20261028-121500.json -WhatIf
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Manifest,
    [switch]$WhatIf
)

$ErrorActionPreference = 'Continue'

if (-not (Test-Path -LiteralPath $Manifest)) {
    Write-Host "找不到清单: $Manifest" -ForegroundColor Red
    exit 2
}

$m = Get-Content -LiteralPath $Manifest -Raw -Encoding UTF8 | ConvertFrom-Json

Write-Host ''
Write-Host '========================================' -ForegroundColor Cyan
Write-Host '  c-drive-cleaner 隔离区还原' -ForegroundColor Cyan
Write-Host "  清单: $(Split-Path $Manifest -Leaf)" -ForegroundColor DarkGray
Write-Host "  时间: $($m.timestamp)" -ForegroundColor DarkGray
if ($WhatIf) { Write-Host '  模式: 预览（不移动）' -ForegroundColor Green }
Write-Host '========================================' -ForegroundColor Cyan
Write-Host ''

$okTotal = 0
$failTotal = 0
$skipTotal = 0

foreach ($t in $m.targets) {
    if ($t.action -ne 'quarantine') {
        Write-Host ("  跳过永久删除项: {0}" -f $t.name) -ForegroundColor DarkGray
        continue
    }
    if (-not $t.moved -or $t.moved.Count -eq 0) {
        Write-Host ("  无需还原: {0}" -f $t.name) -ForegroundColor DarkGray
        continue
    }

    Write-Host ("  >> {0}（{1} 项）" -f $t.name, $t.moved.Count) -ForegroundColor Cyan
    foreach ($item in $t.moved) {
        $orig = [string]$item.Original
        $src = [string]$item.Quarantined

        if (-not (Test-Path -LiteralPath $src)) {
            Write-Host ("     源已不在: {0}" -f $src) -ForegroundColor DarkYellow
            $skipTotal = $skipTotal + 1
            continue
        }
        $parent = Split-Path -Parent $orig
        if (-not (Test-Path -LiteralPath $parent)) {
            Write-Host ("     原目录不存在，先创建: {0}" -f $parent) -ForegroundColor Yellow
            if (-not $WhatIf) {
                try { New-Item -ItemType Directory -Path $parent -Force -ErrorAction Stop | Out-Null }
                catch { Write-Host '     创建失败，跳过' -ForegroundColor Red; $failTotal = $failTotal + 1; continue }
            }
        }
        if (Test-Path -LiteralPath $orig) {
            Write-Host ("     目标已存在，跳过: {0}" -f $orig) -ForegroundColor DarkYellow
            $skipTotal = $skipTotal + 1
            continue
        }
        if ($WhatIf) {
            Write-Host ("     [预览] {0} -> {1}" -f $src, $orig) -ForegroundColor Green
            $okTotal = $okTotal + 1
            continue
        }
        try {
            Move-Item -LiteralPath $src -Destination $orig -Force -ErrorAction Stop
            Write-Host ("     已还原: {0}" -f (Split-Path $orig -Leaf)) -ForegroundColor Green
            $okTotal = $okTotal + 1
        } catch {
            Write-Host ("     还原失败: {0} <{1}>" -f $orig, $_.Exception.GetType().Name) -ForegroundColor Red
            $failTotal = $failTotal + 1
        }
    }
}

Write-Host ''
Write-Host ("  还原 {0} 项，失败 {1} 项，跳过 {2} 项" -f $okTotal, $failTotal, $skipTotal) -ForegroundColor Cyan
Write-Host ''
