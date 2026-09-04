$ErrorActionPreference = 'Stop'
$output = 'E:\PBL6_FINAL\report\word\ban-thuyet-minh-bounded-ai-planning-cyber-range.docx'
$assets = 'E:\PBL6_FINAL\report\word\assets'
$wdPageBreak = 7
$wdSectionBreakNextPage = 2
$wdFormatDocumentDefault = 16
$wdExportFormatPDF = 17
$wdPaperA4 = 7
$wdAlignLeft = 0
$wdAlignCenter = 1
$wdAlignJustify = 3
$wdLineSpaceExactly = 4
$wdFieldPage = 33
$wdFirstPageHeaderFooter = 2
$wdPrimaryFooter = 1
$wdStyleNormal = -1
$wdStyleHeading1 = -2
$wdStyleHeading2 = -3
$wdStyleHeading3 = -4
$wdToggle = -1
$wdTrue = -1
$wd = $null

function Release-ComObject($object) {
  if ($null -ne $object) { [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($object) }
}

$wd = New-Object -ComObject Word.Application
$wd.Visible = $false
$wd.DisplayAlerts = 0
try {
  $doc = $wd.Documents.Add()
  $section = $doc.Sections.Item(1)
  $setup = $section.PageSetup
  $setup.PaperSize = $wdPaperA4
  $setup.LeftMargin = $wd.CentimetersToPoints(3.5)
  $setup.RightMargin = $wd.CentimetersToPoints(2)
  $setup.TopMargin = $wd.CentimetersToPoints(2)
  $setup.BottomMargin = $wd.CentimetersToPoints(2)
  $setup.HeaderDistance = $wd.CentimetersToPoints(1.25)
  $setup.FooterDistance = $wd.CentimetersToPoints(1.25)
  $setup.DifferentFirstPageHeaderFooter = $false
  $section.Footers.Item($wdPrimaryFooter).Range.Text = ''

  $normal = $doc.Styles.Item($wdStyleNormal)
  $normal.Font.Name = 'Times New Roman'
  $normal.Font.Size = 13
  $normal.ParagraphFormat.Alignment = $wdAlignJustify
  $normal.ParagraphFormat.LineSpacingRule = $wdLineSpaceExactly
  $normal.ParagraphFormat.LineSpacing = 19.5
  $normal.ParagraphFormat.FirstLineIndent = $wd.CentimetersToPoints(1)
  $normal.ParagraphFormat.SpaceAfter = 6

  foreach ($spec in @(@($wdStyleHeading1,16,$wdAlignCenter,18,12),@($wdStyleHeading2,14,$wdAlignLeft,12,6),@($wdStyleHeading3,13,$wdAlignLeft,9,4))) {
    $style = $doc.Styles.Item($spec[0]); $style.Font.Name = 'Times New Roman'; $style.Font.Size = $spec[1]; $style.Font.Bold = $wdTrue
    $style.ParagraphFormat.Alignment = $spec[2]; $style.ParagraphFormat.SpaceBefore = $spec[3]; $style.ParagraphFormat.SpaceAfter = $spec[4]; $style.ParagraphFormat.FirstLineIndent = 0
  }

  function Set-CleanParagraph($range, [int]$style = -1, [bool]$pageBreakBefore = $false, [bool]$keepWithNext = $false) {
    try { $range.ListFormat.RemoveNumbers() | Out-Null } catch {}
    $range.Style = $doc.Styles.Item($style)
    $range.ParagraphFormat.PageBreakBefore = [bool]$pageBreakBefore
    $range.ParagraphFormat.KeepWithNext = [bool]$keepWithNext
    $range.ParagraphFormat.KeepTogether = $false
    $range.ParagraphFormat.LeftIndent = 0
    $range.ParagraphFormat.FirstLineIndent = 0
  }

  function New-CleanParagraph([int]$style = -1, [bool]$pageBreakBefore = $false, [bool]$keepWithNext = $false) {
    $range = $doc.Content
    $range.Collapse(0)
    $range.Text = "`r"
    $range.Collapse(0)
    Set-CleanParagraph $range $style $pageBreakBefore $keepWithNext
    return $range
  }

  function Add-Paragraph([string]$text, [int]$style = -1, [int]$alignment = -1, [bool]$pageBreakBefore = $false, [bool]$italic = $false) {
    $isHeading = $style -in @($wdStyleHeading1, $wdStyleHeading2, $wdStyleHeading3)
    $range = New-CleanParagraph $style $pageBreakBefore $isHeading
    $range.Text = $text
    Set-CleanParagraph $range $style $pageBreakBefore $isHeading
    if ($alignment -ge 0) { $range.ParagraphFormat.Alignment = $alignment }
    if ($italic) { $range.Font.Italic = $wdTrue }
  }

  function Add-Bullet([string]$text) {
    $range = New-CleanParagraph $wdStyleNormal $false $false
    $range.Text = $text
    Set-CleanParagraph $range $wdStyleNormal $false $false
    $range.ParagraphFormat.LeftIndent = $wd.CentimetersToPoints(0.7)
    $range.ParagraphFormat.FirstLineIndent = $wd.CentimetersToPoints(-0.4)
    $range.ListFormat.ApplyBulletDefault() | Out-Null
  }

  function Add-Caption([string]$text) {
    $range = New-CleanParagraph $wdStyleNormal $false $false
    $range.Text = $text
    Set-CleanParagraph $range $wdStyleNormal $false $false
    $range.Font.Name = 'Times New Roman'
    $range.Font.Size = 12
    $range.Font.Italic = $wdTrue
    $range.ParagraphFormat.Alignment = $wdAlignCenter
    $range.ParagraphFormat.SpaceAfter = 12
  }

  function Add-Table([string[]]$headers, [object[]]$rows, [double[]]$widths) {
    $anchor = New-CleanParagraph $wdStyleNormal $false $false
    $table = $doc.Tables.Add($anchor, $rows.Count + 1, $headers.Count)
    $table.Borders.Enable = $wdTrue
    $table.Range.Font.Name = 'Times New Roman'
    $table.Range.Font.Size = 11
    $table.AllowAutoFit = $false
    $table.Rows.Alignment = $wdAlignLeft
    for ($c = 1; $c -le $headers.Count; $c++) {
      $cellRange = $table.Cell(1,$c).Range
      $cellRange.End = $cellRange.End - 1
      $cellRange.Text = $headers[$c - 1]
      Set-CleanParagraph $cellRange $wdStyleNormal $false $false
      $cellRange.Font.Bold = $wdTrue
      $cellRange.ParagraphFormat.Alignment = $wdAlignCenter
      $table.Columns.Item($c).Width = $wd.CentimetersToPoints($widths[$c - 1])
    }
    for ($r = 0; $r -lt $rows.Count; $r++) {
      for ($c = 0; $c -lt $headers.Count; $c++) {
        $cellRange = $table.Cell($r + 2,$c + 1).Range
        $cellRange.End = $cellRange.End - 1
        $cellRange.Text = [string]$rows[$r][$c]
        Set-CleanParagraph $cellRange $wdStyleNormal $false $false
        $cellRange.ParagraphFormat.Alignment = $wdAlignLeft
      }
    }
    $after = New-CleanParagraph $wdStyleNormal $false $false
  }

  function Add-Figure([string]$file, [string]$caption, [double]$widthCm) {
    $range = New-CleanParagraph $wdStyleNormal $false $true
    $range.ParagraphFormat.Alignment = $wdAlignCenter
    $shape = $range.InlineShapes.AddPicture($file, $false, $true, $range)
    $shape.LockAspectRatio = $wdTrue
    $shape.Width = $wd.CentimetersToPoints($widthCm)
    try { $shape.AlternativeText = $caption } catch {}
    Add-Caption $caption
  }

  # BIA
  Add-Paragraph '[TEN TRUONG DAI HOC]' $wdStyleNormal $wdAlignCenter
  $last = $doc.Paragraphs.Item($doc.Paragraphs.Count); $last.Range.Font.Bold = $wdTrue; $last.Range.Font.Size = 14
  Add-Paragraph '[KHOA / VIEN]' $wdStyleNormal $wdAlignCenter
  $last = $doc.Paragraphs.Item($doc.Paragraphs.Count); $last.Range.Font.Bold = $wdTrue; $last.Range.Font.Size = 14
  1..2 | ForEach-Object { Add-Paragraph '' $wdStyleNormal $wdAlignCenter }
  Add-Paragraph 'BAN THUYET MINH THIET KE' $wdStyleNormal $wdAlignCenter
  $last = $doc.Paragraphs.Item($doc.Paragraphs.Count); $last.Range.Font.Bold = $wdTrue; $last.Range.Font.Size = 18
  Add-Paragraph 'SU DUNG AI LAP KE HOACH VA TAN CONG TRONG ISOLATED WEB CYBER RANGE' $wdStyleNormal $wdAlignCenter
  $last = $doc.Paragraphs.Item($doc.Paragraphs.Count); $last.Range.Font.Bold = $wdTrue; $last.Range.Font.Size = 20
  Add-Paragraph '(Pham vi SQL Injection, Cross-Site Scripting va Path Traversal)' $wdStyleNormal $wdAlignCenter
  $last = $doc.Paragraphs.Item($doc.Paragraphs.Count); $last.Range.Font.Italic = $wdTrue; $last.Range.Font.Size = 14
  1..3 | ForEach-Object { Add-Paragraph '' $wdStyleNormal $wdAlignCenter }
  foreach ($line in @('Sinh vien thuc hien: [HO VA TEN]','Ma so sinh vien: [MSSV]','Lop: [LOP]','Giang vien huong dan: [HO VA TEN GVHD]')) {
    Add-Paragraph $line $wdStyleNormal $wdAlignLeft
    $last = $doc.Paragraphs.Item($doc.Paragraphs.Count); $last.Range.ParagraphFormat.LeftIndent = $wd.CentimetersToPoints(6)
  }
  1..1 | ForEach-Object { Add-Paragraph '' $wdStyleNormal $wdAlignCenter }
  Add-Paragraph '[Noi -- Nam]' $wdStyleNormal $wdAlignCenter

  $sectionBreakRange = $doc.Content
  $sectionBreakRange.Collapse(0)
  $sectionBreakRange.InsertBreak($wdSectionBreakNextPage) | Out-Null

  $contentSection = $doc.Sections.Item(2)
  $contentSection.PageSetup.PaperSize = $wdPaperA4
  $contentSection.PageSetup.LeftMargin = $wd.CentimetersToPoints(3.5)
  $contentSection.PageSetup.RightMargin = $wd.CentimetersToPoints(2)
  $contentSection.PageSetup.TopMargin = $wd.CentimetersToPoints(2)
  $contentSection.PageSetup.BottomMargin = $wd.CentimetersToPoints(2)
  $contentSection.Footers.Item($wdPrimaryFooter).LinkToPrevious = $false
  $contentSection.Footers.Item($wdPrimaryFooter).Range.Text = ''
  $contentSection.Footers.Item($wdPrimaryFooter).Range.ParagraphFormat.Alignment = $wdAlignCenter
  $contentSection.Footers.Item($wdPrimaryFooter).PageNumbers.RestartNumberingAtSection = $true
  $contentSection.Footers.Item($wdPrimaryFooter).PageNumbers.StartingNumber = 1
  $contentSection.Footers.Item($wdPrimaryFooter).PageNumbers.Add() | Out-Null

  # Load noi dung tieng Viet tu file rieng de tranh encoding issue trong PS heredoc
  $contentFile = Join-Path (Split-Path $output) 'content_viet.ps1'
  . $contentFile

  $doc.Repaginate()
  $toc.Update() | Out-Null
  $toc.UpdatePageNumbers() | Out-Null
  $doc.Fields.Update() | Out-Null
  $doc.SaveAs([ref]$output, [ref]$wdFormatDocumentDefault)
  $doc.ExportAsFixedFormat([System.IO.Path]::ChangeExtension($output, '.pdf'), $wdExportFormatPDF)
  $doc.Close()
} finally {
  if ($null -ne $wd) { $wd.Quit(); Release-ComObject $wd }
}
