# m2 性能采集实跑（2026-11-20）

在 Hyper-V `win11-test` 使用 `glm` 的 `26cf3870d518e8cb245b8366d554808473bb24de`，运行固定夹具 `mixed_filament_test.3mf`。客机分辨率为 1920×1080，使用软件 GL。按 [监控说明](../../deploy/monitoring/README.md) 开启 `-Perf -PerfViewport -PerfCycles 2`，指定 PresentMon CLI 2.3.1。

- 批次 `3e4016db41134c7e90b1008305542330`。功能 JUnit 为 PASS=1、FAIL=0。性能 JSONL 完整终止，155 个 Orca 主进程样本，采集间隔约 500 ms。
- 回收目录为 `artifacts/perf_harvest/3e4016db41134c7e90b1008305542330`。原始文件为 `m2_slice_chain__deb99beb2e6142b8a536dc323014a0f8.jsonl`，SHA-256 为 `4102039b7903a88fe76f4599b9083145a4edb5f983d8e92775fc1c095f5a5a08`。回收后生成同名 `.summary.json`。
- 宿主性能单测 20/20，`hv_go.ps1`、`hv_harvest.ps1` 通过 PowerShell 语法检查。回收后客机恢复到 `software_testing` 的 `534cfee91c5e8d81b56043b7281e0050531f30bc`，任务空闲，无 Orca 残留进程。

| 动作 | 实测 |
| --- | ---: |
| 启动到稳定主窗口 | 7.531 s |
| 启动到模型可见 | 45.921 s |
| 切片点击到按钮变化 / 完成态 | 468 / 671 ms |
| 切换 Preview 到刀路可见 | 1.344 s |
| 缩放 / 旋转 / 平移 / 切层到检测到画面变化 | 141 / 406 / 407 / 93 ms |
| 发起 G-code 导出到弹出保存对话框 / 文件稳定 | 7.828 / 8.688 s |
| 确认保存到文件稳定 | 547 ms |
| 请求关闭到进程退出 | 812 ms，退出码 0 |

启动到模型包含驱动的安全等待。页签耗时包含 1 秒稳定确认。视口耗时受截图节奏影响，旋转、平移包含初次拖动的输入时间。单次采样用于检验指标和回收链路。

本次观测到工作集峰值 651.801 MiB，私有内存峰值 425.863 MiB，进程句柄／GDI／USER 峰值为 1595／1191／1898。首尾有效样本间的进程 I/O 增量为读 136,852,537 字节、写 44,637,474 字节，CPU 累计增加 27.875 秒，页错误计数增加 1,026,238。

| 同一 PID 的空闲窗口 | 私有内存中位数 | 句柄 | GDI | USER |
| --- | ---: | ---: | ---: | ---: |
| 初始 Preview | 410.703 MiB | 1126 | 1069 | 1775 |
| 第 1 轮切回 Preview | 386.469 MiB | 1124 | 1069 | 1775 |
| 第 2 轮切回 Preview | 411.688 MiB | 1130 | 1071 | 1776 |

两轮 Prepare／Preview 切换均观察到刀路，每个空闲窗口有 5 个样本。第 2 轮相对初始私有内存增加 0.985 MiB、句柄增加 4 个。泄漏判定需要更长的重复运行。

PresentMon 启动 ETW 会话返回 `access denied`（退出码 6），因此逐帧数据缺失。WDDM 未返回 Orca PID 的 GPU 引擎或显存样本。真实 GPU 基线仍待采集。[PresentMon CLI 说明](https://github.com/GameTechDev/PresentMon/blob/v2.3.1/README-ConsoleApplication.md)

先前通过新建工程或整板清空构造循环的诊断未能连续验证清空。批次 `da9bda8ae512430a89485661408678bc` 还记录到关闭请求后 10.110 秒触发强制结束。当前循环固定为同一项目的 Prepare／Preview 切换。
