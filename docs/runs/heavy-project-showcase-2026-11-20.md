# 大模型主流程性能示例（2026-11-20）

在 Win11 Hyper-V 客机 `win11-test` 串行运行 `glm` 的 `0d7186616e641321f5cb0cbf16e52cc3f4371bca`。每个场景使用独立的 Orca 进程与测试 profile。录屏与进程采样同时运行。两组项目的模型、盘数和工艺预设均不同。

```powershell
& runner\hv_go.ps1 -Cases m2_perf_showcase -Perf -PerfViewport -PerfCycles 2 -PresentMonExe $guestPresentMon
& runner\hv_harvest.ps1 -PerfBatchId $batch
```

| 负载 | 对象／盘 | 三角面 | 进程样本 | 启动到模型可见 | 切片到导出命令可用 | G-code 导出到文件稳定 | 私有内存峰值 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Ribbed Towers | 6／1 | 390,528 | 208 | 45.36 s | 8.84 s | 8.78 s | 848.0 MiB |
| Snapmates | 19／7 | 448,732 | 252 | 45.44 s | 29.77 s | 8.62 s | 1,559.7 MiB |

Ribbed Towers 由测试脚本生成。Snapmates 使用仓库现有的 `snapmates_nonmixed.3mf`。两个场景均确认预览、导出和退出，JUnit PASS=1、FAIL=0。Snapmates 选择 Slice all，以全盘导出命令可用确认切片就绪。G-code 文件核验覆盖当前盘，分别读到 100 和 45 个层标记。

切片耗时包含驱动打开菜单和轮询的时间。录像核对发现早期试跑的切片按钮模板曾把生成 G-code 中的帧提前判定为完成，此表仅使用修正为原生导出菜单状态后的批次。启动到模型可见包含自动化的启动等待。

完整记录包括 CPU、工作集、私有内存、I/O、页错误、句柄、GDI／USER，以及两个 Prepare／Preview 循环后的空闲资源。部分视口动作未通过截图变化判据。Windows 采样后端未返回该客机 Orca 的 GPU 引擎或显存数据，PresentMon 未生成逐帧 CSV。

- 最终批次 `ce81b9dca8cb4ea7828209a0d9448219`，回收目录 `artifacts/perf_harvest/ce81b9dca8cb4ea7828209a0d9448219`。两条原始 MP4、录屏时间索引和 JSONL 均通过哈希回收。
- 单盘 JSONL 的 SHA-256 为 `6077a3ce13f216227f268356e03cc0e645ccc3aec5db6df8b2147d464a1d7014`。
- 多盘 JSONL 的 SHA-256 为 `4abd147e7ba9e66c49afb3d26520d02002ec2ea138e730e6e7088085ab664d1c`。
- 客机已恢复到原 `software_testing`，测试任务空闲，无 Orca 残留。25 个采样与客机识别单测，以及用例注册表检查均通过。
