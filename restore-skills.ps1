<#
  恢复技能到本机 WorkBuddy
  用法：双击 RESTORE.bat，或在 PowerShell 里执行：
        powershell -NoProfile -ExecutionPolicy Bypass -File .\restore-skills.ps1
  可选参数：
        -DryRun     只演练，不写文件
        -SkipNpm    跳过 npm install
        -TargetPath 指定目标目录（默认 %USERPROFILE%\.workbuddy\skills）
#>
param(
    [string]$TargetPath = (Join-Path $env:USERPROFILE ".workbuddy\skills"),
    [switch]$DryRun,
    [switch]$SkipNpm
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$src  = Join-Path $root "skills"

Write-Host ""
Write-Host "=== WorkBuddy 技能恢复 ===" -ForegroundColor Cyan
Write-Host "来源: $src"
Write-Host "目标: $TargetPath"
if ($DryRun) { Write-Host "模式: 演练（不写任何文件）" -ForegroundColor Yellow }
Write-Host ""

if (-not (Test-Path $src)) {
    Write-Host "找不到 skills 目录，请确认压缩包已完整解压。" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path $TargetPath)) {
    if ($DryRun) {
        Write-Host "目标目录不存在（正式运行时会自动创建）" -ForegroundColor Yellow
    } else {
        New-Item -ItemType Directory -Path $TargetPath -Force | Out-Null
        Write-Host "已创建目标目录" -ForegroundColor Green
    }
}

$stamp     = Get-Date -Format "yyyyMMdd-HHmmss"
$oldDir    = Join-Path ([System.IO.Path]::GetTempPath()) ("wb_skills_replaced_" + $stamp)
$skills    = Get-ChildItem -Path $src -Directory
$ok = 0; $skip = 0; $npmList = @()

foreach ($s in $skills) {
    $dest = Join-Path $TargetPath $s.Name
    if (Test-Path $dest) {
        if ($DryRun) {
            Write-Host ("  [演练] 已存在，将先备份再覆盖: " + $s.Name) -ForegroundColor Yellow
            $skip++
        } else {
            New-Item -ItemType Directory -Path $oldDir -Force | Out-Null
            Move-Item -Path $dest -Destination (Join-Path $oldDir $s.Name) -Force
            Write-Host ("  已备份旧版: " + $s.Name + " -> " + $oldDir) -ForegroundColor DarkGray
        }
    }
    if (-not $DryRun) {
        Copy-Item -Path $s.FullName -Destination $dest -Recurse -Force
        Write-Host ("  已安装: " + $s.Name) -ForegroundColor Green
    }
    $ok++
    if ((Test-Path (Join-Path $s.FullName "package.json")) -and (-not $SkipNpm)) {
        $npmList += $dest
    }
}

Write-Host ""
Write-Host ("技能处理完成: " + $ok + " 个" + $(if ($skip -gt 0) { "（其中 " + $skip + " 个已存在）" } else { "" })) -ForegroundColor Cyan

if ($npmList.Count -gt 0) {
    $npm = Get-Command npm -ErrorAction SilentlyContinue
    if ($null -eq $npm) {
        Write-Host ""
        Write-Host "以下技能依赖 node 包，但本机没有 npm，需先装 Node.js 再执行 npm install：" -ForegroundColor Yellow
        foreach ($d in $npmList) { Write-Host ("   " + $d) }
    } elseif (-not $DryRun) {
        Write-Host ""
        Write-Host "开始安装 node 依赖（可能需要几分钟）..." -ForegroundColor Cyan
        foreach ($d in $npmList) {
            Write-Host ("   npm install @ " + $d)
            Push-Location $d
            try { & npm install --omit=dev --no-audit --no-fund } catch { Write-Host ("   失败: " + $_.Exception.Message) -ForegroundColor Red }
            Pop-Location
        }
    }
}

Write-Host ""
Write-Host "下一步：重启 WorkBuddy，技能列表才会刷新。" -ForegroundColor Cyan
if (Test-Path $oldDir) {
    Write-Host ("旧版本备份在: " + $oldDir) -ForegroundColor DarkGray
    Write-Host "确认新版本正常后，可手动删除该备份目录。" -ForegroundColor DarkGray
}
Write-Host ""
