# Run in an authorized Hyper-V management session. GUI work stays inside hv_go.
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}$')][string]$CandidateId,
    [ValidateSet('Both', 'Baseline', 'Edited')][string]$Phase = 'Both',
    [string]$GuestCheckout = $env:ORCA_BB_GUEST_SANDBOX
)
$ErrorActionPreference = 'Stop'
$previousCheckout = $env:ORCA_BB_GUEST_SANDBOX
$repo = Split-Path $PSScriptRoot -Parent
$fixtureHash = (Get-FileHash -LiteralPath (Join-Path $repo 'fixtures/agent_layer_cube.3mf')).Hash.ToLowerInvariant()
if (!$GuestCheckout) { $GuestCheckout = 'C:\coil\orca-blackbox-v3-r1' }

function Read-GuestBuild {
    Invoke-Command -VMName $vm -Credential $cred -ErrorAction Stop -ScriptBlock {
        param($checkout, $python, $git)
        Push-Location -LiteralPath $checkout
        try {
            $exe = & $python -B -c 'from harness.launcher import default_exe; print(default_exe())'
            if ($LASTEXITCODE -ne 0) { throw 'Unable to resolve the guest SUT' }
            $detected = & $python -B -c 'from harness.host_guard import in_guest; print(int(in_guest()))'
            if ($LASTEXITCODE -ne 0) { throw 'Unable to query the guest guard' }
            $head = & $git rev-parse HEAD
            if ($LASTEXITCODE -ne 0) { throw 'Guest checkout has no readable HEAD' }
            $changes = @(& $git status --porcelain --untracked-files=no)
            if ($LASTEXITCODE -ne 0) { throw 'Unable to inspect tracked guest files' }
            $file = Get-Item -LiteralPath $exe
            $dll = Join-Path $file.DirectoryName 'Snapmaker_Orca.dll'
            $taskState = [string](Get-ScheduledTask -TaskName suite -ErrorAction SilentlyContinue).State
            $processCount = @(Get-Process snapmaker-orca -ErrorAction SilentlyContinue).Count
            [pscustomobject]@{
                sut_version = $file.VersionInfo.ProductVersion
                file_version = $file.VersionInfo.FileVersion
                sut_sha256 = (Get-FileHash -LiteralPath $file.FullName).Hash.ToLowerInvariant()
                dll_sha256 = (Get-FileHash -LiteralPath $dll).Hash.ToLowerInvariant()
                fixture_sha256 = (Get-FileHash -LiteralPath 'fixtures/agent_layer_cube.3mf').Hash.ToLowerInvariant()
                guest_source = "$head"
                dirty = $changes.Count
                detected = ("$detected" -eq '1')
                suite = $taskState
                orca_count = $processCount
                busy = ($taskState -eq 'Running' -or $processCount -gt 0)
                sampled_at = [DateTime]::UtcNow.ToString('o')
            }
        } finally { Pop-Location }
    } -ArgumentList $guestSandbox,$guestPython,$guestGit
}

function Wait-GuestResult([string]$Id) {
    $deadline = [DateTime]::UtcNow.AddMinutes(15)
    do {
        $status = Invoke-Command -VMName $vm -Credential $cred -ErrorAction Stop -ScriptBlock {
            param($checkout, $runId)
            $runner = 'C:\coil\run_suite.ps1'
            $bound = (Test-Path -LiteralPath $runner) -and [IO.File]::ReadAllText($runner).Contains($runId)
            [pscustomobject]@{
                ours = $bound
                running = (Get-ScheduledTask -TaskName suite -ErrorAction Stop).State -eq 'Running'
                result = Test-Path -LiteralPath (Join-Path $checkout "artifacts/v3/$runId/result.json")
            }
        } -ArgumentList $guestSandbox,$Id
        if (!$status.ours) { throw 'Scheduled task no longer belongs to this request' }
        if (!$status.running) { return $status.result }
        Start-Sleep -Seconds 3
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Guest case still running after 15 minutes'
}

$mutex = $null
$ownsMutex = $false
try {
    $env:ORCA_BB_GUEST_SANDBOX = $GuestCheckout
    . (Join-Path $PSScriptRoot '_common.ps1')
    if ($vm -ne 'win11-test') { throw 'This pilot requires win11-test' }
    $baseline = 'uia_replay_save'
    $edited = 'uia_replay_layer'
    $scenarios = switch ($Phase) { Baseline { $baseline }; Edited { $edited }; Both { $baseline; $edited } }
    $first = $null
    foreach ($scenario in $scenarios) {
        $id = [guid]::NewGuid().ToString('N')
        $dest = Join-Path $repo "artifacts/windows_mcp_harvest/$id"
        New-Item -ItemType Directory -Path $dest -ErrorAction Stop | Out-Null
        Write-Host "$scenario $id -> $dest"
        $stage = 'guest.preflight'
        $guiStarted = $false
        try {
            if (!$ownsMutex) {
                $mutex = [Threading.Mutex]::new($false, 'Global\OrcaBlackbox.WindowsLayerEvidence.win11-test')
                try { $ownsMutex = $mutex.WaitOne(0) }
                catch [Threading.AbandonedMutexException] { $ownsMutex = $true }
                if (!$ownsMutex) { throw 'Another Windows layer capture owns the guest' }
            }
            $pre = Read-GuestBuild
            $binding = [ordered]@{
                run_id = $id; candidate_id = $CandidateId; scenario = $scenario; vm = $vm
                sut_version = $pre.sut_version; file_version = $pre.file_version
                sut_sha256 = $pre.sut_sha256; dll_sha256 = $pre.dll_sha256
                fixture_sha256 = $pre.fixture_sha256; guest_source = $pre.guest_source; at_utc = $pre.sampled_at
                guest_dirty = $pre.dirty; runtime_guest = $pre.detected; suite = $pre.suite; orca_count = $pre.orca_count
            }
            $binding | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dest 'binding.json') -Encoding UTF8
            if ($pre.dirty -or $pre.busy) { throw 'Guest checkout has tracked changes or the test desktop is busy' }
            if ($pre.fixture_sha256 -ne $fixtureHash) { throw 'Guest baseline fixture differs from the host' }
            if ($first -and ($first.sut_sha256 -ne $pre.sut_sha256 -or $first.dll_sha256 -ne $pre.dll_sha256 -or
                             $first.guest_source -ne $pre.guest_source)) { throw 'Guest build changed between phases' }
            $first = $pre
            $stage = 'guest.host_guard'
            if (!$pre.detected) { throw 'The guest runtime cannot identify its Hyper-V session' }
            $stage = 'guest.launch'
            $guiStarted = $null
            & (Join-Path $PSScriptRoot 'hv_go.ps1') -NoSync -WindowsMcpProbe -NativeSave -ProbeRunId $id `
                -NativeActor script -NativeScenario $scenario *> (Join-Path $dest 'launch.log')
            $stage = 'guest.run'
            $hasResult = Wait-GuestResult $id
            $stage = 'guest.harvest'
            & (Join-Path $PSScriptRoot 'hv_harvest.ps1') -NativeSave -WindowsMcpRunId $id
            if (!$hasResult) {
                $stage = 'guest.startup'
                throw 'Scheduled task exited without a runtime result; see harvested startup evidence'
            }
            $stage = 'guest.verify'
            $setup = Get-Content -LiteralPath (Join-Path $dest 'setup.json') -Raw | ConvertFrom-Json
            if ($setup.run_id -eq $id -and $setup.app_pid -gt 0) { $guiStarted = $true }
            $post = Read-GuestBuild
            $proof = Get-Content -LiteralPath (Join-Path $dest 'proof.json') -Raw | ConvertFrom-Json
            $result = Get-Content -LiteralPath (Join-Path $dest 'result.json') -Raw | ConvertFrom-Json
            if ($setup.run_id -ne $id -or $setup.scenario -ne $scenario -or $proof.run_id -ne $id -or
                $proof.sut_sha256 -ne $pre.sut_sha256 -or $post.sut_sha256 -ne $pre.sut_sha256 -or
                $post.dll_sha256 -ne $pre.dll_sha256 -or $post.fixture_sha256 -ne $pre.fixture_sha256 -or
                $post.guest_source -ne $pre.guest_source -or $post.dirty -or $post.busy) {
                throw 'Run identity, guest build, fixture or final desktop state mismatch'
            }
            if ($result.verified_pass -ne $true -or $result.cleanup_confirmed -ne $true) {
                throw 'Guest verifier or cleanup failed; see the native result'
            }
            $binding.post_verified_at = $post.sampled_at
            $binding | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dest 'binding.json') -Encoding UTF8
            Write-Output (Join-Path $dest 'result.json')
        } catch {
            $failure = $_.Exception.Message
            if ($stage -eq 'guest.startup') {
                $startupLog = Join-Path $dest 'runner_startup_failure.log'
                if ((Test-Path -LiteralPath $startupLog) -and
                    (Select-String -LiteralPath $startupLog -SimpleMatch 'runtime: real execution requires a Hyper-V guest' -Quiet)) {
                    $stage = 'guest.host_guard'
                    $guiStarted = $false
                }
            }
            $verdict = if ($stage -in @('guest.preflight','guest.host_guard','guest.launch','guest.startup')) { 'BLOCKED' } else { 'NON_GREEN' }
            [ordered]@{run_id=$id;candidate_id=$CandidateId;scenario=$scenario;verdict=$verdict;
                failure_stage=$stage;error=$failure;gui_started=$guiStarted} |
                ConvertTo-Json | Set-Content -LiteralPath (Join-Path $dest 'attempt.json') -Encoding UTF8
            throw
        }
    }
} finally {
    if ($ownsMutex) { $mutex.ReleaseMutex() }
    if ($null -ne $mutex) { $mutex.Dispose() }
    $env:ORCA_BB_GUEST_SANDBOX = $previousCheckout
}
