# Win10 真机便携性能诊断（2026-11-21）

在用户授权的新 Win10 x64 实体机上，通过 SSH 触发交互式计划任务，在已经登录的控制台会话运行单文件 OrcaPerfRunner。分辨率 1920×1080，Windows 缩放 100%。EXE 的 SHA-256 为 `fdfccb9ef76c728775b3fee1735c784b33e000494e9b59dccf75526ba391ff00`，传输后校验通过，`--check` 和 `--stage` 通过。Orca 在测试期间加载 Windows 系统 OpenGL 和 AMD 模块 `atio6axx.dll`、`amdihk64.dll`。WDDM 指标按 Orca 进程取样，测试使用系统 OpenGL。

本记录为单机诊断。三轮 GUI 运行的进程退出码均为 1，七盘流程在 Win10 上仍未通过。Hyper-V 上两组通过的结果及其不同的渲染条件见 [便携包验证记录](../../deploy/monitoring/PORTABLE_PERF.md)。

| 运行 | Ribbed Towers · 单盘六件 | Snapmates · 七盘十九件 |
| --- | --- | --- |
| `win10-679db201` | 切片、预览通过，导出菜单未打开，正常退出 | 未取得前台，正常退出 |
| `win10-retry-f1d8b732` | 隐藏启动器控制台后，切片、预览、视口操作、两轮页面切换、导出、退出通过 | 切片通过，预览校验失败，未执行导出，退出超时 |
| `win10-focus-41c7f298` | 只置顶本轮 Orca 窗口后，仍未取得前台，正常退出 | 切片通过，预览校验失败，未执行导出，退出超时 |

置顶诊断前有一次任务启动失败，未生成测试报告，也未启动 Orca。三轮原始报告已通过 SSH 回收并校验 SHA-256。本次创建的八个临时计划任务已全部注销。

## 可比较的数据

下表使用 `win10-retry-f1d8b732` 同轮数据。切片时长包含打开原生导出菜单和轮询的时间。启动时长包含自动化等待。

| 指标 | Ribbed Towers | Snapmates |
| --- | ---: | ---: |
| 启动到模型可见 | 42.64 s | 42.66 s |
| 点击切片到导出命令可用 | 7.36 s | 27.38 s |
| 发起 G-code 导出到文件稳定 | 8.16 s | 未执行 |
| G-code 层切换标记 | 100 | 未执行 |
| 应用成功提交帧数 | 617 | 80（进程被强制退出，记录部分可用） |
| GPU 最忙引擎峰值 | 50.02% | 4.86% |
| 进程专用显存峰值 | 5.23 MiB | 4.68 MiB |
| 进程共享显存峰值 | 417.45 MiB | 328.39 MiB |
| 工作集峰值 | 1,189.01 MiB | 1,767.00 MiB |

单盘旋转为 44.32 提交帧/秒，帧间隔 P95 为 88.53 ms。平移为 43.97 提交帧/秒，P95 为 86.89 ms。预览层滑条为 5.40 提交帧/秒，P95 为 268.74 ms。三项均取对应动作期间的 Preview 画布。七盘在导出菜单可用后连续两轮未通过预览着色判据，实测约 0.92% 和 0.90%，阈值为 1.0%。截图判据失败只能确认本轮自动化未建立预览证据。

普通权限的内置 PresentMon 在实际触发采集时返回 `presentmon_exit_6`，早期日志记录 ETW access denied。提权后的专用 PresentMon 会话可启动和结束，覆盖完整重跑的进程名过滤和一次单盘启动期的 PID 过滤均未输出显示帧 CSV。应用提交、WDDM 利用率和显示帧是三种独立观测。实际显示 FPS、逐帧 GPU 时长和显示延迟仍缺测。便携包中的进程采样使用 Win32 回退，线程数和系统级指标在这些数据中缺测。

## 复现与证据

1. 在已登录且桌面可见的 Windows x64 控制台，会话中直接运行 `OrcaPerfRunner.exe`。远程编排时，用 SSH 启动同一用户的交互式计划任务。使用 `--output <目录> --no-open` 可指定独立报告目录并抑制自动打开浏览器。
2. 保持系统 OpenGL 路径，使用 `run.json` 中的载荷哈希核对版本。WDDM 资源指标按 Orca PID 观察。需要显示帧时，使用专用 PresentMon 会话并检查输出 CSV 是否确实包含目标进程的显示记录。
3. 逐项核对预览、导出层标记和退出。失败场景仍保留原始进程和应用帧数据。官方回归按仓库规定经 Hyper-V 入口执行。

- [三轮状态、二进制哈希与指标汇总](evidence/portable-perf-win10-2026-11-21/run-summary.json)
- [进程采样 CSV](evidence/portable-perf-win10-2026-11-21/process-samples.csv) · [应用逐帧 CSV](evidence/portable-perf-win10-2026-11-21/submitted-frames.csv) · [动作和验证事件 CSV](evidence/portable-perf-win10-2026-11-21/measurements.csv)
- [重跑的 CPU、内存、GPU 和提交帧曲线](evidence/portable-perf-win10-2026-11-21/hardware-curves.png)

CSV 以 `run` 和 `model` 连接，同一场景的横轴是距该 Orca 进程启动的秒数 `t_rel`。`cpu_pct` 采用单逻辑核为 100% 的口径。空白字段表示该行没有观测。带桌面画面的录屏、完整 HTML 报告和未删减日志保存在本地证据包。
