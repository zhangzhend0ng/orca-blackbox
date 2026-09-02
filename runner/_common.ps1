# _common.ps1 — shared runner parameters; dot-source from sibling scripts:
#   . (Join-Path $PSScriptRoot '_common.ps1')
#
# Every value comes from the environment with the CURRENT LIVE RIG default,
# so these snapshots run the rig they were ported from unchanged, while a
# new host/guest only needs env overrides (no script edits):
#   ORCA_BB_VM            guest VM name              (default win11-test)
#   ORCA_BB_GUEST_USER    guest autologon user       (default test)
#   ORCA_BB_GUEST_PASS    guest autologon password   (default 123456 —
#                         throwaway isolated Hyper-V guest, NOT a secret;
#                         override for any real machine)
#   ORCA_BB_GUEST_SANDBOX guest-side suite checkout  (default: the monorepo
#                         worktree the suite still runs from; migrate the
#                         guest layout to an orca-blackbox checkout to repoint)
#   ORCA_BB_GUEST_PYTHON  guest python               (default C:\Python311\python.exe)
#   ORCA_BB_GUEST_TOOLS   guest-side relay tools dir (default C:\coil\vm_setup_guest)

$vm = $(if ($env:ORCA_BB_VM) { $env:ORCA_BB_VM } else { 'win11-test' })
$guestUser = $(if ($env:ORCA_BB_GUEST_USER) { $env:ORCA_BB_GUEST_USER } else { 'test' })
$guestPass = $(if ($env:ORCA_BB_GUEST_PASS) { $env:ORCA_BB_GUEST_PASS } else { '123456' })
$guestSandbox = $(if ($env:ORCA_BB_GUEST_SANDBOX) { $env:ORCA_BB_GUEST_SANDBOX } else { 'C:\coil\Projects\SnapmakerOrca_dev\.worktrees\vision-gui-blackbox\sandboxes\vision_gui' })
$guestPython = $(if ($env:ORCA_BB_GUEST_PYTHON) { $env:ORCA_BB_GUEST_PYTHON } else { 'C:\Python311\python.exe' })
$guestTools = $(if ($env:ORCA_BB_GUEST_TOOLS) { $env:ORCA_BB_GUEST_TOOLS } else { 'C:\coil\vm_setup_guest' })
$cred = New-Object System.Management.Automation.PSCredential($guestUser, (ConvertTo-SecureString $guestPass -AsPlainText -Force))
