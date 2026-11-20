# Orca 视口逐帧采集（2026-11-20）

Hyper-V 客机 `win11-test` 的两组负载沿用 [大模型主流程示例](heavy-project-showcase-2026-11-20.md)。使用独立 Orca 构建和每场景独立的测试配置。每条记录含视口开始渲染、调用 `SwapBuffers()` 前和调用返回后的 QPC 时间戳，并通过驱动的 QPC 同步点与录屏和资源采样对齐。

## 构建与回收

- 前三次试跑的测试驱动为 `glm` 的 `add7fe175f5645071746c240846b4259b6da7f38`。
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

- `670579e5a0914fc281eeca950969b689` 在应用级阻止规则建立后加载了两个模型。录像显示旧防火墙通知仍覆盖客机桌面，干扰切片模式和导出菜单操作。单盘有 57 条原生记录，进程强制退出，原生文件未正常收尾。多盘有 20 条原生记录，进程正常退出。两个采样器的丢记录计数均为 0，JUnit RED。两条录像、录屏索引、原生文件和进程 JSONL 均通过哈希回收。

## 完成批次

重启空闲的测试客机以清除旧弹窗。在 `glm` 的 `c7e7f64a040c5aa8046fce45b3ad8144e975d546` 运行批次 `cf8cd163113e46c9bd1a9a09de4a0fd9`。导出就绪检查通过 File 菜单的原生句柄读取对应的 Export 子菜单。JUnit PASS=1、FAIL=0，回收了两个场景各自的 JSONL、原生帧文件、录像和录像时间索引。

| 场景 | 成功提交帧 | 旋转窗口提交 FPS | 旋转帧间隔 P95 | 切片点击至可导出 | 导出至文件稳定 | 当前盘 G-code 层标记 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Ribbed Towers（六件单盘） | 187 | 5.48（18 帧） | 211.19 ms | 7.97 s | 8.33 s | 100 |
| Snapmates（十九件七盘） | 290 | 30.65（99 帧） | 93.83 ms | 28.09 s | 8.19 s | 45 |

两组应用均正常退出，无交换失败、无采样器丢记录，各完成两轮 Prepare／Preview 切换。单盘另外采集到平移和切层窗口。两组缩放、七盘平移及切层未通过当前用例的视口变化验证。旋转等动作使用各自的输入数和项目视图，这组数据用于演示时间对齐与采集口径。

提交帧和耗时来自 Orca 自身的三点 QPC 采集。软件渲染客机的 PresentMon 返回 `presentmon_csv_missing`，屏幕实际显示 FPS 和物理 GPU 指标缺测。

- 单盘 `.render.bin` SHA-256 为 `0b87f457e72c386b7479a972f14b1fba69308b92f961f9f2ccfbd3b6b0674d4a`。
- 七盘 `.render.bin` SHA-256 为 `ed53dd0046ed45178072747283e4d18df5d1cafbdf19b6cd108e5c094f7b43b7`。
- 性能采样、原生帧解析、客机识别和中继时钟单测 28 个通过、2 个跳过。PowerShell 启动及回收脚本语法检查通过。此性能用例不对应飞书矩阵条目。
- 测试结束后，客机检出恢复为 `software_testing` 的 `534cfee91c5e8d81b56043b7281e0050531f30bc`，任务为空闲，无 Orca 进程。
