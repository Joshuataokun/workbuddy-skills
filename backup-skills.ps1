<#
  把当前机器的技能重新打包（换机前、或改完技能后用）
  用法：双击 BACKUP.bat
#>
param(
    [string]$SourcePath = (Join-Path $env:USERPROFILE ".workbuddy\skills"),
    [string]$OutPath    = $PSScriptRoot
)

$ErrorActionPreference = "Stop"
Write-Host ""
Write-Host "=== 备份本机技能 ===" -ForegroundColor Cyan
Write-Host "来源: $SourcePath"

if (-not (Test-Path $SourcePath)) {
    Write-Host "找不到技能目录。" -ForegroundColor Red
    exit 1
}

$dest = Join-Path $OutPath "skills"
if (Test-Path $dest) { Remove-Item -Path $dest -Recurse -Force }
New-Item -ItemType Directory -Path $dest -Force | Out-Null

$n = 0
foreach ($s in (Get-ChildItem -Path $SourcePath -Directory)) {
    if (-not (Test-Path (Join-Path $s.FullName "SKILL.md"))) { continue }
    $target = Join-Path $dest $s.Name
    Copy-Item -Path $s.FullName -Destination $target -Recurse -Force
    # 剔除可重建/无需携带的内容
    foreach ($junk in @("node_modules", ".git", "__pycache__")) {
        $p = Join-Path $target $junk
        if (Test-Path $p) { Remove-Item -Path $p -Recurse -Force }
    }
    Get-ChildItem -Path $target -Filter "*.zip" -Recurse -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-Host ("  已收集: " + $s.Name) -ForegroundColor Green
    $n++
}

$size = (Get-ChildItem -Path $dest -Recurse -File | Measure-Object -Property Length -Sum).Sum
Write-Host ""
Write-Host ("打包完成: " + $n + " 个技能, " + [math]::Round($size / 1MB, 2) + " MB") -ForegroundColor Cyan
Write-Host "把整个文件夹（含 skills 子目录和两个 .bat）压缩带走即可。" -ForegroundColor DarkGray
Write-Host ""
