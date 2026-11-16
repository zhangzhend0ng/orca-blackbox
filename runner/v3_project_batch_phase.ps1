# Fixed child phases. No GUI launch except the official hv_go entry point.
param([ValidatePattern('^[a-z0-9_]{1,48}$')][string]$BatchId,
      [ValidateRange(1,5)][int]$Slot,[ValidateSet('setup','cancel','harvest')][string]$Phase,
      [ValidatePattern('^[0-9a-f]{64}$')][string]$PlanSha256)
$ErrorActionPreference='Stop'; Set-StrictMode -Version Latest
$repo=Split-Path $PSScriptRoot -Parent; $batch=Join-Path $repo ('artifacts\v3_batches\'+$BatchId)
$planPath=Join-Path $batch 'plan.json'; $status=Join-Path $batch ($Slot.ToString()+'_'+$Phase+'.json')
function Safe([string]$path) {
  $p=[IO.Path]::GetFullPath($path)
  while($p) { if((Test-Path -LiteralPath $p) -and ((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)){throw 'reparse_rejected'}; $n=[IO.Path]::GetDirectoryName($p); if($n -eq $p){break}; $p=$n }
}
function Once([string]$path,[byte[]]$bytes) { Safe $path; $f=[IO.File]::Open($path,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None); try{$f.Write($bytes,0,$bytes.Length);$f.Flush($true)}finally{$f.Dispose()} }
function Publish($data) { $pending=$status+'.pending'; Once $pending ([Text.Encoding]::UTF8.GetBytes(($data|ConvertTo-Json -Depth 10 -Compress)+"`n"));[IO.File]::Move($pending,$status) }
$row=$null; $session=$null
try {
  Safe $planPath; Safe $status
  if((Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant() -cne $PlanSha256){throw 'plan_hash'}
  $plan=[IO.File]::ReadAllText($planPath)|ConvertFrom-Json; $row=$plan.slots[$Slot-1]
  if($plan.batch_id -cne $BatchId -or $plan.case_id -cne 'm3g_export_3mf' -or $row.index -ne $Slot -or $row.run_id -cnotmatch '^[0-9a-f]{32}$' -or $plan.guest_root -cne 'C:\coil\orca-blackbox-v3-r1'){throw 'plan_identity'}
  $env:ORCA_BB_GUEST_SANDBOX='C:\coil\orca-blackbox-v3-r1'
  . (Join-Path $PSScriptRoot '_common.ps1')
  if($vm -cne 'win11-test'){throw 'vm_identity'}
  $session=New-PSSession -VMName $vm -Credential $cred -ErrorAction Stop
  if($Phase -eq 'setup') {
    $bundle=Join-Path $batch 'update.bundle'; Safe $bundle
    if((Get-Item -LiteralPath $bundle).Length -gt 314572800 -or (Get-FileHash -LiteralPath $bundle -Algorithm SHA256).Hash.ToLowerInvariant() -cne $plan.bundle_sha256){throw 'bundle_hash'}
    $encoded=[Convert]::ToBase64String([IO.File]::ReadAllBytes($bundle))
    $facts=Invoke-Command -Session $session -ScriptBlock {
      param($batch,$index,$run,$base,$head,$bundleSha,$encoded,$fixtureSha,$contractSha)
      $ErrorActionPreference='Stop'; $checkout='C:\coil\orca-blackbox-v3-r1';$git='C:\coil\tools\mingit\cmd\git.exe'
      function Safe([string]$path){$p=[IO.Path]::GetFullPath($path);while($p){if((Test-Path -LiteralPath $p)-and((Get-Item -LiteralPath $p -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'reparse_rejected'};$n=[IO.Path]::GetDirectoryName($p);if($n-eq$p){break};$p=$n}}
      function Git([string[]]$a){$all=@($a)+@($args);$saved=$ErrorActionPreference;try{$ErrorActionPreference='Continue';$v=& $git -C $checkout @all 2>&1|ForEach-Object{"$_"};$code=$LASTEXITCODE}finally{$ErrorActionPreference=$saved};if($code-ne 0){throw 'git_failed'};$v}
      Safe $checkout
      if(@(Get-ScheduledTask|Where-Object{$_.TaskName-eq'suite'-and$_.State-eq'Running'}).Count -or @(Get-Process -Name snapmaker-orca -ErrorAction SilentlyContinue).Count){throw 'desktop_busy'}
      if(Test-Path -LiteralPath (Join-Path $checkout ('artifacts\v3\'+$run))){throw 'run_already_exists'}
      if(Git @('status','--porcelain')){throw 'guest_dirty'}
      if((Git @('branch','--show-current')) -cne 'software_testing'){throw 'guest_branch'}
      $current=Git @('rev-parse','HEAD');if($current -cne $base -and $current -cne $head){throw 'unexpected_guest_head'}
      $file='C:\coil\v3_'+$batch+'.bundle';Safe $file
      if(-not(Test-Path -LiteralPath $file)){$bytes=[Convert]::FromBase64String($encoded);$s=[IO.File]::Open($file,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$s.Write($bytes,0,$bytes.Length);$s.Flush($true)}finally{$s.Dispose()}}
      if((Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -cne $bundleSha){throw 'guest_bundle_hash'}
      $null=Git @('bundle','verify',$file)
      if($current -cne $head){$null=Git @('fetch',$file,'HEAD');$null=Git @('merge','--ff-only',$head)}
      if((Git @('rev-parse','HEAD')) -cne $head -or (Git @('status','--porcelain'))){throw 'guest_source_identity'}
      $sut='C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe'
      $sutHash=(Get-FileHash -LiteralPath $sut -Algorithm SHA256).Hash.ToLowerInvariant()
      if($sutHash -cne '5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf'){throw 'sut_drift'}
      if((Get-FileHash -LiteralPath (Join-Path $checkout 'fixtures\agent_layer_cube.3mf') -Algorithm SHA256).Hash.ToLowerInvariant() -cne $fixtureSha){throw 'fixture_drift'}
      $code="import sys;sys.path.insert(0,r'C:\coil\orca-blackbox-v3-r1');from harness.agent_session import agent_contract;from harness.run_verdict import contract_digest;print(contract_digest(agent_contract('m3g_export_3mf')))"
      $actual=& 'C:\Python311\python.exe' -B -c $code
      if($LASTEXITCODE-ne 0 -or $actual -cne $contractSha){throw 'guest_contract_identity'}
      [pscustomobject]@{head=$head;sut_sha256=$sutHash}
    } -ArgumentList $BatchId,$Slot,$row.run_id,$plan.guest_base_ref,$plan.head,$plan.bundle_sha256,$encoded,$plan.fixture_sha256,$plan.contract_sha256
    & (Join-Path $PSScriptRoot 'hv_go.ps1') -V3 -NoSync -V3Executor agent_mcp -V3RunId $row.run_id -Cases m3g_export_3mf | Out-Null
    Publish @{ok=$true;phase=$Phase;run_id=$row.run_id;head=$facts.head;sut_sha256=$facts.sut_sha256}
  } elseif($Phase -eq 'cancel') {
    $facts=Invoke-Command -Session $session -ScriptBlock {param($run)
      $ErrorActionPreference='Stop';$checkout='C:\coil\orca-blackbox-v3-r1';$root=Join-Path $checkout ('artifacts\v3\'+$run)
      $manifest=[IO.File]::ReadAllText((Join-Path $root 'manifest.json'))|ConvertFrom-Json
      if($manifest.run_id -cne $run -or $manifest.case_id -cne 'm3g_export_3mf'){throw 'cancel_identity'}
      $path=Join-Path $root 'artifacts\control_cancel.json';$p=$path
      while($p){if((Test-Path -LiteralPath $p)-and((Get-Item -LiteralPath $p -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'cancel_link'};$p=[IO.Path]::GetDirectoryName($p)}
      if(Test-Path -LiteralPath $path){$old=[IO.File]::ReadAllText($path)|ConvertFrom-Json;if($old.schema_version-ne 1-or$old.run_id-cne$run-or$old.reason-cne'host_stopped'){throw 'cancel_conflict'}}
      else{$raw=[Text.Encoding]::UTF8.GetBytes((@{schema_version=1;run_id=$run;reason='host_stopped'}|ConvertTo-Json -Compress));$pending=$path+'.pending';$s=[IO.File]::Open($pending,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None);try{$s.Write($raw,0,$raw.Length);$s.Flush($true)}finally{$s.Dispose()};[IO.File]::Move($pending,$path)}
      $head=& 'C:\coil\tools\mingit\cmd\git.exe' -C $checkout rev-parse HEAD;if($LASTEXITCODE-ne 0){throw 'git_failed'}
      [pscustomobject]@{head=$head;sut_sha256=(Get-FileHash -LiteralPath 'C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe' -Algorithm SHA256).Hash.ToLowerInvariant()}
    } -ArgumentList $row.run_id
    Publish @{ok=$true;phase=$Phase;run_id=$row.run_id;head=$facts.head;sut_sha256=$facts.sut_sha256}
  } else {
    $end=[DateTime]::UtcNow.AddSeconds(960)
    do {
      $idle=Invoke-Command -Session $session -ScriptBlock {param($run)
        $root='C:\coil\orca-blackbox-v3-r1\artifacts\v3\'+$run
        (@(Get-ScheduledTask|Where-Object{$_.TaskName-eq'suite'-and$_.State-eq'Running'}).Count-eq 0) -and (@(Get-Process -Name snapmaker-orca -ErrorAction SilentlyContinue).Count-eq 0) -and (Test-Path -LiteralPath ($root+'\result.json')) -and (Test-Path -LiteralPath ($root+'\artifacts\process.json'))
      } -ArgumentList $row.run_id
      if(-not$idle){if([DateTime]::UtcNow-ge$end){throw 'guest_cleanup_unconfirmed'};Start-Sleep -Milliseconds 500}
    } until($idle)
    $info=Invoke-Command -Session $session -ScriptBlock {param($run,$batch,$index)
      $ErrorActionPreference='Stop';$checkout='C:\coil\orca-blackbox-v3-r1';$root=Join-Path $checkout ('artifacts\v3\'+$run)
      function Safe([string]$p){while($p){if((Test-Path -LiteralPath $p)-and((Get-Item -LiteralPath $p -Force).Attributes-band[IO.FileAttributes]::ReparsePoint)){throw 'reparse_rejected'};$p=[IO.Path]::GetDirectoryName($p)}}
      $names=@('contract.json','manifest.json','events.ndjson','result.json','artifacts/agent.log','artifacts/ready.json','artifacts/agent_report.json','artifacts/process.json','artifacts/operation_receipts.ndjson','artifacts/trace.ndjson','artifacts/control_cancel.json','artifacts/close_windows.json','artifacts/input/fixture.3mf','artifacts/projects/0001.3mf','artifacts/exports/0001.gcode')
      1..12|ForEach-Object{$n='{0:0000}'-f$_;$names+=@("artifacts/mailbox/request_$n.json","artifacts/mailbox/response_$n.json","artifacts/frames/${n}_a.bmp","artifacts/frames/${n}_b.bmp","artifacts/frames/$n.png")}
      Add-Type -AssemblyName System.IO.Compression.FileSystem
      $zipPath='C:\coil\v3_'+$batch+'_'+$index+'.zip';Safe $zipPath
      $zip=[IO.Compression.ZipFile]::Open($zipPath,[IO.Compression.ZipArchiveMode]::Create);$total=0
      try {foreach($name in $names){$p=Join-Path $root ($name-replace'/','\');Safe $p;if(Test-Path -LiteralPath $p -PathType Leaf){$size=(Get-Item -LiteralPath $p).Length;$limit=67108864;if($name.EndsWith('.3mf')){$limit=16777216};$total+=$size;if($size-gt$limit-or$total-gt314572800){throw 'evidence_size'};[void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,$p,$name,[IO.Compression.CompressionLevel]::Optimal)}}}finally{$zip.Dispose()}
      $head=& 'C:\coil\tools\mingit\cmd\git.exe' -C $checkout rev-parse HEAD;if($LASTEXITCODE-ne 0){throw 'git_failed'}
      [pscustomobject]@{path=$zipPath;length=(Get-Item -LiteralPath $zipPath).Length;zip_sha256=(Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant();head=$head;sut_sha256=(Get-FileHash -LiteralPath 'C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\snapmaker-orca.exe' -Algorithm SHA256).Hash.ToLowerInvariant()}
    } -ArgumentList $row.run_id,$BatchId,$Slot
    if($info.length -gt 314572800 -or $info.path -cne ('C:\coil\v3_'+$BatchId+'_'+$Slot+'.zip') -or $info.head -cne $plan.head -or $info.sut_sha256 -cne $plan.sut_sha256){throw 'archive_identity'}
    $target=Join-Path $batch ($Slot.ToString()+'_evidence.zip');Safe $target
    $stream=[IO.File]::Open($target,[IO.FileMode]::CreateNew,[IO.FileAccess]::Write,[IO.FileShare]::None)
    try {for($offset=0;$offset-lt$info.length;$offset+=196608){$chunk=Invoke-Command -Session $session -ScriptBlock{param($p,$o)$f=[IO.File]::OpenRead($p);try{[void]$f.Seek($o,[IO.SeekOrigin]::Begin);$b=New-Object byte[] 196608;$n=$f.Read($b,0,$b.Length);[Convert]::ToBase64String($b,0,$n)}finally{$f.Dispose()}} -ArgumentList $info.path,$offset;$bytes=[Convert]::FromBase64String($chunk);$stream.Write($bytes,0,$bytes.Length)};$stream.Flush($true)}finally{$stream.Dispose()}
    if((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash.ToLowerInvariant() -cne $info.zip_sha256){throw 'host_zip_hash'}
    & (Join-Path $PSScriptRoot 'hv_harvest.ps1') -V3 | Out-Null
    Publish @{ok=$true;phase=$Phase;run_id=$row.run_id;head=$info.head;sut_sha256=$info.sut_sha256;zip_sha256=$info.zip_sha256}
  }
} catch { Publish @{ok=$false;phase=$Phase;run_id=$(if($null-ne$row){$row.run_id}else{''});error_type=$_.Exception.GetType().Name}; exit 2 }
finally {if($null-ne$session){Remove-PSSession $session}}
