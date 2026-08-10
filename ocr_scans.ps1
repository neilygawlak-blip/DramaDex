# ocr_scans.ps1 - offline OCR for photographed script pages.
#
# Uses the OCR engine built into Windows (Windows.Media.Ocr). No install, no
# network, nothing leaves the machine.
#
#   powershell -File ocr_scans.ps1 -In private\scans -Out private\see_how_they_run
#
# Writes two files next to -Out:
#   <Out>_lines.json  every OCR line with its position on the page
#   <Out>_flat.txt    the same text, one line per line, for eyeballing
#
# Then run:  python assemble_script.py <Out>_lines.json <Out>_raw.txt
# which turns the positioned lines into speech paragraphs the parser can read.
#
# Pages are read in filename order, so name them page_001.jpg, page_002.jpg...

param(
    [Parameter(Mandatory=$true)][string]$In,
    [Parameter(Mandatory=$true)][string]$Out
)

Add-Type -AssemblyName System.Runtime.WindowsRuntime

# WinRT calls are async; PowerShell 5.1 needs this shim to wait on them.
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object {
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'
})[0]

function Await($op, $type) {
    $task = $asTaskGeneric.MakeGenericMethod($type).Invoke($null, @($op))
    $task.Wait(-1) | Out-Null
    $task.Result
}

$null = [Windows.Storage.StorageFile,Windows.Storage,ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder,Windows.Graphics.Imaging,ContentType=WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine,Windows.Foundation,ContentType=WindowsRuntime]

$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if (-not $engine) { throw "No OCR language pack available." }
Write-Host ("OCR language: " + $engine.RecognizerLanguage.DisplayName)

$dir = Resolve-Path $In
$pages = Get-ChildItem -Path $dir -Include *.jpg,*.jpeg,*.png,*.bmp,*.tif,*.tiff -File -Recurse |
         Sort-Object Name
if ($pages.Count -eq 0) { throw "No images found in $dir" }

$allLines = New-Object System.Collections.ArrayList
$flat = New-Object System.Text.StringBuilder
$n = 0

foreach ($p in $pages) {
    $n++
    Write-Host ("[{0}/{1}] {2}" -f $n, $pages.Count, $p.Name)

    $file    = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($p.FullName)) ([Windows.Storage.StorageFile])
    $stream  = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bitmap  = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $result  = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])

    $pw = $decoder.PixelWidth
    $ph = $decoder.PixelHeight

    [void]$flat.AppendLine(("[[page {0}: {1}]]" -f $n, $p.Name))

    foreach ($line in $result.Lines) {
        # A line's own box is not exposed, so derive it from its words.
        $left = [double]::MaxValue; $top = [double]::MaxValue
        $right = 0.0; $bottom = 0.0
        foreach ($w in $line.Words) {
            $r = $w.BoundingRect
            if ($r.X -lt $left) { $left = $r.X }
            if ($r.Y -lt $top) { $top = $r.Y }
            if (($r.X + $r.Width) -gt $right) { $right = $r.X + $r.Width }
            if (($r.Y + $r.Height) -gt $bottom) { $bottom = $r.Y + $r.Height }
        }
        if ($line.Words.Count -eq 0) { continue }

        [void]$allLines.Add([pscustomobject]@{
            page = $n
            file = $p.Name
            text = $line.Text
            left = [math]::Round($left, 1)
            top = [math]::Round($top, 1)
            right = [math]::Round($right, 1)
            bottom = [math]::Round($bottom, 1)
            page_w = $pw
            page_h = $ph
        })
        [void]$flat.AppendLine($line.Text)
    }
    [void]$flat.AppendLine("")

    $bitmap.Dispose()
    $stream.Dispose()
}

$outDir = Split-Path -Parent $Out
if ($outDir -and -not (Test-Path $outDir)) { New-Item -ItemType Directory -Force $outDir | Out-Null }

$utf8 = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText("${Out}_lines.json", ($allLines | ConvertTo-Json -Depth 4), $utf8)
[System.IO.File]::WriteAllText("${Out}_flat.txt", $flat.ToString(), $utf8)

Write-Host ("Read {0} pages, {1} lines." -f $pages.Count, $allLines.Count)
Write-Host ("  ${Out}_lines.json")
Write-Host ("  ${Out}_flat.txt")
Write-Host ("Next: python assemble_script.py ${Out}_lines.json ${Out}_raw.txt")
