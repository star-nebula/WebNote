<#
.SYNOPSIS
  把合并结果渲染成结构化 Markdown —— 格式无损的输出端。

.DESCRIPTION
  按块类型逐块渲染，而不是拼文本：
    heading-N  -> # ~ ######
    列表        -> 依据 list-symbol 转 - 或 1.（保留缩进层级）
    引用        -> >
    表格        -> 标准 Markdown 表；单元格内多段用 <br> 连接
    代码块      -> 围栏代码块 + 语言标注；剥离行号
    图片        -> ![](...)
    分割线      -> ---
  并处理三类易错点：
    1. 表格单元格内的 | 必须转义
    2. 行内代码里的反引号必须成对转义
    3. 页面把 Mermaid 渲染成 data:image/svg+xml 时，给出图注提示（真图源码需另行取回）

  文档头部固定写入 标题 / 来源 / 提取时间。

.EXAMPLE
  powershell -File render-md.ps1 -MergedPath ..\work\merged_doc1.json `
    -Title "某文档" -Source "https://alidocs.dingtalk.com/i/nodes/XXX" -OutPath ..\out\doc1.md
#>
param(
  [Parameter(Mandatory=$true)][string]$MergedPath,
  [Parameter(Mandatory=$true)][string]$Title,
  [Parameter(Mandatory=$true)][string]$Source,
  [Parameter(Mandatory=$true)][string]$OutPath,
  [switch]$NoTimestamp
)

$ErrorActionPreference = 'Stop'

# ---------- 行内 run -> Markdown ----------
function Convert-Runs {
  # SuppressBold: 标题/表头本身就已是粗体语义，块内再套 ** 属于纯噪音
  param([object[]]$Runs, [bool]$InTable = $false, [switch]$SuppressBold)
  $sb = New-Object System.Text.StringBuilder
  foreach ($r in @($Runs)) {
    if ($null -eq $r) { continue }
    if ($r.br) { [void]$sb.Append("`n"); continue }
    if ($r.img) {
      $src = [string]$r.img
      [void]$sb.Append('![](' + $src + ')')
      continue
    }
    $t = [string]$r.t
    if ([string]::IsNullOrEmpty($t)) { continue }

    if ($r.c) {
      # 行内代码：先转义内部反引号，再包反引号
      $bt = [char]0x60
      $t = $t.Replace([string]$bt, ([string]$bt + [string]$bt))
      $t = [string]$bt + $t + [string]$bt
      if ($InTable) { $t = $t -replace '\|', '\|' }
      [void]$sb.Append($t)
      continue
    }

    $txt = $t
    if ($InTable) { $txt = $txt -replace '\|', '\|' }
    if ($r.b) { if (-not $SuppressBold) { $txt = '**' + $txt + '**' } }
    elseif ($r.i) { $txt = '*' + $txt + '*' }
    elseif ($r.s) { $txt = '~~' + $txt + '~~' }
    [void]$sb.Append($txt)
  }
  return $sb.ToString()
}

$MergedPath = (Resolve-Path $MergedPath).Path
$j = [System.IO.File]::ReadAllText($MergedPath, [System.Text.Encoding]::UTF8) | ConvertFrom-Json
$blocks = @($j.blocks | Sort-Object -Property { if ($_.k -ge 0) { [int]$_.k } else { [int]::MaxValue } })
$tableByU = @{}
foreach ($t in @($j.tables)) { if ($t.u) { $tableByU[$t.u] = $t } }

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add("# $Title")
$lines.Add("> 来源: $Source")
if (-not $NoTimestamp) {
  $lines.Add("> 提取时间: " + (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ss.fffZ'))
}
$lines.Add("")

$prevWasList = $false
$stats = @{ headings = 0; paragraphs = 0; lists = 0; quotes = 0; tables = 0; codes = 0; images = 0; hrs = 0 }

foreach ($b in $blocks) {
  $ty = [string]$b.ty
  $isList = ($null -ne $b.li -and "$($b.li)" -ne '')

  # --- 分割线 ---
  if ($ty -eq 'hr' -or $b.voidType -eq 'hr') {
    if ($lines[$lines.Count - 1] -ne '') { $lines.Add('') }
    $lines.Add('---'); $lines.Add('')
    $prevWasList = $false; $stats.hrs++
    continue
  }

  # --- 独立图片块 ---
  if (($b.voidType -eq 'image' -or $b.imgSrc) -and $ty -ne 'mermaid') {
    if ($b.imgSrc) {
      $lines.Add(''); $lines.Add('![](' + [string]$b.imgSrc + ')'); $lines.Add('')
      $stats.images++
    }
    $prevWasList = $false
    continue
  }

  # --- 标题 ---
  if ($ty -match '^heading-(\d)$') {
    $lvl = [int]$Matches[1]
    if ($lvl -lt 1) { $lvl = 1 }; if ($lvl -gt 6) { $lvl = 6 }
    $lines.Add(''); $lines.Add(('#' * $lvl) + ' ' + (Convert-Runs @($b.runs) -SuppressBold))
    $prevWasList = $false; $stats.headings++
    continue
  }

  # --- 代码块 ---
  if ($ty -eq 'mermaid') {
    $source = if ($b.mermaidSourceMissing) { '' } else { [string]$b.mermaid }
    if ([string]::IsNullOrWhiteSpace($source) -and -not $b.mermaidSourceMissing) { $source = [string]$b.text }
    if (-not [string]::IsNullOrWhiteSpace($source)) {
      $lines.Add(''); $lines.Add('```mermaid')
      foreach ($srcLine in ($source -split '\r?\n')) { $lines.Add($srcLine) }
      $lines.Add('```'); $lines.Add('')
      $stats.codes++
    } elseif ($b.imgSrc) {
      $lines.Add(''); $lines.Add('![](' + [string]$b.imgSrc + ')')
      $lines.Add('> Mermaid 源码未在 DOM 中暴露，以上为渲染图。')
      $stats.images++
    }
    $prevWasList = $false; $prevWasCode = $true
    continue
  }

  # --- 代码块 ---
  if ($ty -eq 'codeblock') {
    $lang = ([string]$b.lang).Trim().ToLower()
    $lang = $lang -replace '[^a-z0-9_+.#-]', ''

    $codeLines = @($b.lines)
    # 剥离纯行号行（很多编辑器把它渲染成独立行）
    while ($codeLines.Count -gt 0 -and ("$($codeLines[0])" -match '^\s*\d+\s*$')) {
      $codeLines = @($codeLines | Select-Object -Skip 1)
    }
    # 去尾部空行
    while ($codeLines.Count -gt 0 -and [string]::IsNullOrWhiteSpace("$($codeLines[$codeLines.Count - 1])")) {
      $codeLines = @($codeLines | Select-Object -First ($codeLines.Count - 1))
    }
    $lines.Add(''); $lines.Add('```' + $lang)
    foreach ($cl in $codeLines) { $lines.Add([string]$cl) }
    $lines.Add('```')
    $prevWasList = $false; $stats.codes++
    continue
  }

  # --- 表格 ---
  if ($ty -eq 'table') {
    $t = $tableByU[$b.u]
    if ($t -and @($t.rows).Count -gt 0) {
      $lines.Add('')
      $rows = @($t.rows)
      $grid = @{}
      $maxCols = 0
      for ($ri = 0; $ri -lt $rows.Count; $ri++) {
        $ci = 0
        foreach ($cell in @($rows[$ri])) {
          while ($grid.ContainsKey("${ri}:${ci}")) { $ci++ }
          $parts = foreach ($part in @($cell.runs)) {
            ((Convert-Runs @($part) $true -SuppressBold:($ri -eq 0)) -replace "`n", '<br>')
          }
          $content = ($parts -join '<br>')
          $rowSpan = [Math]::Max(1, [int]($cell.rs))
          $colSpan = [Math]::Max(1, [int]($cell.cs))
          for ($rr = 0; $rr -lt $rowSpan; $rr++) {
            for ($cc = 0; $cc -lt $colSpan; $cc++) {
              $grid["$($ri + $rr):$($ci + $cc)"] = $content
            }
          }
          $ci += $colSpan
          if ($ci -gt $maxCols) { $maxCols = $ci }
        }
      }
      $header = for ($c = 0; $c -lt $maxCols; $c++) { [string]$grid["0:$c"] }
      $lines.Add('| ' + ($header -join ' | ') + ' |')
      $lines.Add('| ' + ((1..$maxCols | ForEach-Object { '---' }) -join ' | ') + ' |')
      for ($r = 1; $r -lt $rows.Count; $r++) {
        $cells = for ($c = 0; $c -lt $maxCols; $c++) { [string]$grid["${r}:${c}"] }
        $lines.Add('| ' + ($cells -join ' | ') + ' |')
      }
      $stats.tables++
    }
    $prevWasList = $false
    continue
  }

  # --- 段落 / 引用 / 列表项 ---
  $inline = Convert-Runs @($b.runs)
  if ([string]::IsNullOrWhiteSpace($inline)) { $prevWasList = $false; continue }

  $isQuote = ($b.q -eq 1 -or $ty -eq 'quote')

  if ($isQuote) {
    $sub = $inline -split "`n"
    $quoted = ($sub | ForEach-Object { '> ' + $_ }) -join "`n"
    $lines.Add(''); $lines.Add($quoted)
    $prevWasList = $false; $stats.quotes++
    continue
  }

  if ($isList) {
    $sym = "$($b.li)"
    $bulletChars = @([char]0x25CF, [char]0x2022, [char]0x25E6, [char]0x25AA, [char]0x2043)
    $indent = ''
    if ($b.ind -gt 0) { $indent = ' ' * ([Math]::Min(8, [int]($b.ind / 12))) }
    if ($bulletChars -contains $sym) { $prefix = '- ' }
    elseif ($sym -match '^\d+[\.\)]?$') { $prefix = ($sym -replace '[\.\)]$', '') + '. ' }
    else { $prefix = '- ' }
    if (-not $prevWasList) { $lines.Add('') }
    $lines.Add($indent + $prefix + ($inline -replace "`n", ' '))
    $prevWasList = $true; $stats.lists++
  }
  else {
    $lines.Add(''); $lines.Add($inline)
    $prevWasList = $false; $stats.paragraphs++
  }
}

# 折叠连续空行
$out = New-Object System.Text.StringBuilder
$blankRun = 0
foreach ($ln in $lines) {
  if ($ln -eq '') { $blankRun++; if ($blankRun -le 1) { [void]$out.AppendLine() } }
  else { $blankRun = 0; [void]$out.AppendLine($ln) }
}

# 提示：页面把 Mermaid 渲染成 SVG data-uri 的情况
$svgCount = ([regex]::Matches($out.ToString(), '!\[\]\(data:image/svg\+xml')).Count
if ($svgCount -gt 0) {
  Write-Host "[render] 注意: 检出 $svgCount 处 SVG data-uri 图片（多为 Mermaid 图）。"
  Write-Host "         如需 Mermaid 源码，请在页面上定位该图块并另取源码文本后回填。"
}

$dir = Split-Path -Parent $OutPath
if ($dir -and -not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
[System.IO.File]::WriteAllText($OutPath, $out.ToString(), (New-Object System.Text.UTF8Encoding($true)))

Write-Host ("[render] 写出 $OutPath  ({0} bytes, {1} 行)" -f (Get-Item $OutPath).Length, $lines.Count)
Write-Host ("[render] 统计: 标题{0} 段落{1} 列表{2} 引用{3} 表格{4} 代码块{5} 图片{6} 分割线{7}" -f `
  $stats.headings, $stats.paragraphs, $stats.lists, $stats.quotes, $stats.tables, $stats.codes, $stats.images, $stats.hrs)
