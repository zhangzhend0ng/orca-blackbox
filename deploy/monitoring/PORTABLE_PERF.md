# Portable Orca performance runner

Build the Windows x64 single-file EXE with Python 3.11, PyInstaller, NumPy,
OpenCV, Pillow and pytesseract installed on the build worker.

```powershell
python tools/build_perf_exe.py --release $verifiedRelease `
  --instrumented $verifiedFrameDll --identities $binaryHashes `
  --runtime $vc143X64 --presentmon $presentMon --ffmpeg $ffmpeg `
  --orca-source $orcaSourceCommit --output $destination
```

The `--identities` JSON supplies SHA-256 digests in `base_exe`, `base_dll`
and `instrumented_dll`. Use the complete release directory from a verified run, including its exact
resources and profiles. Matching EXE and DLL digests does not establish that
the resources match. The packager replaces only the tested frame-trace DLL. The app-local VC++
x64 runtime travels with the bundled Orca build.

Double-click `OrcaPerfRunner.exe` as the signed-in desktop user. The
runner checks the desktop and uses screen input and recording during the
two test projects. The verified desktop setup is 1920×1080 at 100% scale.
The report opens after the run and links to raw recordings, JSONL and
application frame traces. Runs are stored in
`%LOCALAPPDATA%\OrcaPerfRunner\runs`. The local run is marked as a
diagnostic. The package uses the system OpenGL provider by default.
If PresentMon or WDDM does not return GPU or display observations, those
measurements remain missing in the report.

```powershell
& $portable --check
& runner\hv_go.ps1 -Cases m2_perf_showcase -Perf -PortablePerfExe $guestPortable -PortableMesaDir $guestMesa
& runner\hv_harvest.ps1 -PerfBatchId $batch
```

`--check` validates payload hashes, fixtures, imports and an MP4 codec
round trip without opening Orca. `--stage` extracts the bundled application
without starting it. The optional Mesa path selects an existing Mesa
OpenGL runtime for a software-rendered test worker. Real-machine GPU
coverage requires a separate measurement on a hardware OpenGL worker.

## Packaging validation

The first portable batch (`5127ffa890fb451dae3a5469fa894a40`) exited before
submitting the first frame. Its Snapmaker profiles differed from the proven
guest release. The rebuilt EXE uses the exact resources of the previous
successful guest build and launches Orca from the run directory with the
frozen process's DLL search override cleared.

The rebuilt EXE was checked on both Windows systems with Python removed
from PATH and with no external Python path override on the host. The
full guest verification uses software OpenGL. The results below refer to
the rebuilt executable with SHA-256
`fdfccb9ef76c728775b3fee1735c784b33e000494e9b59dccf75526ba391ff00`.

Batch `eae0a77e9e7c45aa8b6711f7e0aecd49` passed both projects. Ribbed Towers
recorded 165 successful application frame submissions and 100 G-code layer
markers. Snapmates recorded 315 successful submissions and 45 layer
markers. Both traces closed normally with no discarded records. The
generated HTML references resolved and both H.264 recordings decoded
in full. JUnit reports one passing showcase case, and the guest was
restored to `software_testing`.

## Physical Windows 10 evidence

The same EXE was staged and run on a Windows 10 x64 machine using the AMD
OpenGL driver. Orca process GPU engine and video memory counters were observed.
Ribbed Towers completed and its exported G-code was verified. Snapmates reached
slice readiness and failed preview validation. Elevated PresentMon traces did
not produce display-frame records. See the [physical Windows 10 run record](../../docs/runs/portable-perf-win10-2026-11-21.md)
for measurements, retries, and reproducible evidence.
