# Orca 视口逐帧采集（2026-11-20）

Hyper-V 客机 `win11-test` 的两组负载沿用 [大模型主流程示例](heavy-project-showcase-2026-11-20.md)。使用独立 Orca 构建和每场景独立的测试配置。每条记录含视口开始渲染、调用 `SwapBuffers()` 前和调用返回后的 QPC 时间戳，并通过驱动的 QPC 同步点与录屏和资源采样对齐。

## 构建与回收

- 测试驱动为 `glm` 的 `add7fe175f5645071746c240846b4259b6da7f38`。
- 可运行的插桩构建基于 `56e82d53c85457f530827d2488664015b2eae08e`。宿主和客机上次跑通的 EXE 与 DLL 分别核对了 SHA-256。测试 DLL 从该提交的独立源码副本重编译 `GLCanvas3D.cpp`，链接时复用配套编译产物。导出序号、符号和 DLL 依赖列表与原 DLL 一致。
- 测试 DLL 的 SHA-256 为 `fe978b06cae707b40965e38104ac995eb592983a73708d639a2f2dfd384fd583`。

```powershell
& runner\hv_go.ps1 -Cases m2_perf_showcase -Perf -PerfViewport -PerfCycles 2 -PresentMonExe $guestPresentMon -FrameTraceExe $guestInstrumentedExe
& runner\hv_harvest.ps1 -PerfBatchId $batch
Get-ChildItem "artifacts\perf_harvest\$batch" -Filter *.jsonl |
    ForEach-Object { python -B tools/perf_report.py $_.FullName }
```

## 试跑记录

- `19ba1747df034f31a1541b6476fe263e` 使用 `dd1bbce173474215430e57935af8bb9a68d7062a` 的测试 DLL。两个进程在第一次交换缓冲之前退出，退出码为 `0x80070057`。回收的两个原生文件均只有头部。JUnit RED。
- `23cdfd2625d94dfea4e22a357c1f04cc` 使用匹配上一次示例的测试 DLL。两个进程各采集到 17 条逐帧记录，均正常收尾，采样器的丢记录计数为 0。失败录像显示 Windows 防火墙权限对话框占据前台，两个场景均停在窗口前置。JUnit RED。重跑前仅对客机隔离目录的测试 EXE 设置程序级入站阻止规则。
