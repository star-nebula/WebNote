<#
.SYNOPSIS
  合并分窗采集结果 —— 按块唯一键去重 + 恢复阅读顺序。

.DESCRIPTION
  分窗采集会产生大量重复块（同一块在多个窗口都可见）。合并规则：
    1. 以块唯一标识（data-block-uuid）为键去重
    2. 同一块出现多次时，取「信息更完整」的版本：
       - 有 runs/lines 的优于只有纯文本的
       - 都有则取文本更长的（可能是渲染更完整的版本）
    3. 按顺序键（data-cangjie-key）重排 —— 这是真实阅读顺序，
       不能用「窗口顺序 + 窗口内顺序」，否则会出现段落错位
    4. 打印标题大纲，让人一眼看出章节是否齐全

.PARAMETER Dir
  harvest.ps1 的 OutDir（含 {Prefix}_wN.json）

.EXAMPLE
  powershell -File merge-blocks.ps1 -Dir ..\work -Prefix doc1
#>
param(
  [Parameter(Mandatory=$true)][string]$Dir,
  [Parameter(Mandatory=$true)][string]$Prefix
)

$ErrorActionPreference = 'Stop'
$Dir = (Resolve-Path $Dir).Path

$files = Get-ChildItem -Path $Dir -Filter ("{0}_w*.json" -f $Prefix) |
  Sort-Object { [int]([regex]::Match($_.BaseName, '_w(\d+)$').Groups[1].Value) }
if (-not $files) { Write-Host "[merge] 未找到 $Prefix`_w*.json（目录: $Dir）"; exit 1 }
Write-Host "[merge] 输入窗口文件: $($files.Count)"

$blockMap = @{}   # u -> block
$tableMap = @{}   # u -> table
$skipped  = 0

foreach ($f in $files) {
  $raw = [System.IO.File]::ReadAllText($f.FullName, [System.Text.Encoding]::UTF8)
  $j = $null
  try { $j = $raw | ConvertFrom-Json } catch { Write-Host "[merge] SKIP $($f.Name): JSON 解析失败"; $skipped++; continue }
  if ($j.err) { Write-Host "[merge] SKIP $($f.Name): $($j.err)"; $skipped++; continue }

  foreach ($b in @($j.blocks)) {
    if (-not $b.u) { continue }
    $existing = $blockMap[$b.u]
    if (-not $existing) { $blockMap[$b.u] = $b; continue }

    # 择优：有结构化 runs/lines 的优先
    $newHasStruct = ($null -ne $b.runs) -or ($null -ne $b.lines)
    $oldHasStruct = ($null -ne $existing.runs) -or ($null -ne $existing.lines)
    if ($newHasStruct -and -not $oldHasStruct) { $blockMap[$b.u] = $b; continue }
    if ($oldHasStruct -and -not $newHasStruct) { continue }
    # 同为结构化：取文本更长的（渲染更完整）
    $newLen = if ($b.text) { $b.text.Length } else { 0 }
    $oldLen = if ($existing.text) { $existing.text.Length } else { 0 }
    if ($newLen -gt $oldLen) { $blockMap[$b.u] = $b }
  }

  foreach ($t in @($j.tables)) { if ($t.u) { $tableMap[$t.u] = $t } }
}

# 按顺序键重排；无顺序键的排在最后（保持相对稳定）
$sortExpr = { if ($_.k -ge 0) { [int]$_.k } else { [int]::MaxValue } }
$blocks   = @($blockMap.Values | Sort-Object -Property $sortExpr)
$tables   = @($tableMap.Values | Sort-Object -Property $sortExpr)

Write-Host "[merge] 去重后: blocks=$($blocks.Count)  tables=$($tables.Count)  (跳过窗口 $skipped)"

$payload = @{ blocks = $blocks; tables = $tables } | ConvertTo-Json -Depth 14 -Compress

$outAll = Join-Path $Dir 'merged.json'
$outPfx = Join-Path $Dir ("merged_{0}.json" -f $Prefix)
[System.IO.File]::WriteAllText($outAll, $payload, [System.Text.Encoding]::UTF8)
[System.IO.File]::WriteAllText($outPfx, $payload, [System.Text.Encoding]::UTF8)
Write-Host ("[merge] 写出 $outPfx ({0} KB)" -f [Math]::Round((Get-Item $outPfx).Length / 1KB))

# 标题大纲 —— 人工核对章节完整性用
$heads = $blocks | Where-Object { $_.ty -match '^heading' -or $_.ty -match 'heading|title' }
Write-Host "[merge] 标题大纲 ($($heads.Count)):"
foreach ($h in $heads) {
  $lvl = if ("$($h.ty)" -match '^heading-(\d)$') { [int]$Matches[1] } else { 1 }
  $pad = ' ' * (($lvl - 1) * 2)
  $txt = if ($h.text) { ($h.text -replace '\s+', ' ').Trim() } else { '(空)' }
  if ($txt.Length -gt 70) { $txt = $txt.Substring(0, 70) + '…' }
  Write-Host "  $pad- $txt"
}
