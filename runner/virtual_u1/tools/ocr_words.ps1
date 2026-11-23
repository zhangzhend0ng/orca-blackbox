param([string]$Path)
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation.Metadata, ContentType=WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation.Metadata, ContentType=WindowsRuntime]
$null = [Windows.Storage.StorageFile, Windows.Foundation.Metadata, ContentType=WindowsRuntime]
function Await($WinRtTask, $ResultType) {
  $asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask))
  $netTask.Wait(-1) | Out-Null
  $netTask.Result
}
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($Path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$ocr = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
$result = Await ($ocr.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
foreach ($line in $result.Lines) {
  $words = @()
  foreach ($w in $line.Words) {
    $r = $w.BoundingRect
    $words += ("{0}@{1},{2},{3}x{4}" -f $w.Text, [int]$r.X, [int]$r.Y, [int]$r.Width, [int]$r.Height)
  }
  Write-Output ($words -join ' ')
}
