# run_suite.ps1 — fa706g3 physical Win10 suite runner (Task C)
# Executes INSIDE interactive console session 1 via scheduled task.
# Reads cases.txt (one case per line: name|script_rel|extra_args),
# runs each case sequentially with a fresh per-case datadir, records
# exit code / timing / orphan sweep into results.tsv + per-case logs.
# Completion marker: DONE_<batchId> written at the very end.
param([string]$BatchId = "b")

$ErrorActionPreference = 'Continue'
$base = 'C:\coil\fa706g3_runs'
$repo = 'C:\coil\orca-blackbox'
$py   = Join-Path $repo '.venv\Scripts\python.exe'
$exe  = 'C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe'

$env:ORCA_BB_ALLOW_HOST = '1'   # host run explicitly ordered by control (Task C)
$env:ORCA_VISION_APP_EXE = $exe
$env:PYTHONIOENCODING = 'utf-8'
$env:PATH = 'C:\Program Files\Tesseract-OCR;' + $env:PATH

if (-not $BatchId -or $BatchId -eq 'b') { $BatchId = 'b' + (Get-Date -Format 'HHmmss') }
New-Item -ItemType Directory -Force -Path "$base\logs" | Out-Null
$doneMarker = Join-Path $base "DONE_$BatchId"
if (Test-Path $doneMarker) { Remove-Item $doneMarker -Force }

"batch=$BatchId start=$(Get-Date -Format o) user=$env:USERNAME" |
    Out-File -FilePath "$base\results.tsv" -Append -Encoding utf8

Get-Content (Join-Path $base 'cases.txt') | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    $parts = $line -split '\|', 3
    $name = $parts[0]; $script = $parts[1]; $extra = $parts[2]

    # pre-clean: no stale app, no stale datadir (fresh per case)
    $preOrphans = @(Get-Process snapmaker-orca -ErrorAction SilentlyContinue)
    if ($preOrphans.Count -gt 0) {
        $preOrphans | Stop-Process -Force
        Start-Sleep -Seconds 2
    }
    $dd = Join-Path $base "datadir_$name"
    if (Test-Path $dd) { Remove-Item -Recurse -Force $dd }

    $logOut = "$base\logs\$name.out.log"
    $logErr = "$base\logs\$name.err.log"
    $argList = @('-B', (Join-Path $repo $script),
                 '--exe', $exe, '--datadir', $dd) + ($extra -split ' ') |
               Where-Object { $_ -ne '' }
    $t0 = Get-Date
    try {
        $p = Start-Process -FilePath $py -ArgumentList $argList `
              -WorkingDirectory $repo -NoNewWindow -PassThru `
              -RedirectStandardOutput $logOut -RedirectStandardError $logErr
        $null = $p.Handle   # keep the process handle alive so ExitCode survives exit
        if (-not $p.WaitForExit(2400000)) {   # 40 min hard cap per case
            $p.Kill()
            "case=$name exit=TIMEOUT2400s" |
                Out-File -FilePath "$base\results.tsv" -Append -Encoding utf8
            return
        }
        $code = $p.ExitCode
    } catch {
        $code = -1
        "SPAWN_ERROR: $_" | Out-File -FilePath $logErr -Append -Encoding utf8
    }
    $t1 = Get-Date
    $dur = [int]($t1 - $t0).TotalSeconds

    # post-case orphan sweep + confirmation
    Start-Sleep -Seconds 1
    $orphans = @(Get-Process snapmaker-orca -ErrorAction SilentlyContinue)
    $orphanNote = 'none'
    if ($orphans.Count -gt 0) {
        $orphans | Stop-Process -Force
        Start-Sleep -Seconds 1
        $left = @(Get-Process snapmaker-orca -ErrorAction SilentlyContinue).Count
        $orphanNote = "killed($($orphans.Count))left=$left"
    }
    $row = "case=$name exit=$code dur=${dur}s start=$($t0.ToString('HH:mm:ss')) " +
           "end=$($t1.ToString('HH:mm:ss')) orphans=$orphanNote prekill=$($preOrphans.Count)"
    $row | Out-File -FilePath "$base\results.tsv" -Append -Encoding utf8
}

"batch=$BatchId end=$(Get-Date -Format o)" |
    Out-File -FilePath "$base\results.tsv" -Append -Encoding utf8
'DONE' | Out-File -FilePath $doneMarker -Encoding utf8
