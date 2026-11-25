# 飞书 #251 从磁盘重新加载：重载成立，缺源时弹的是文件选择框

记录 `reczz28aa4fiXrq7`（P1）要求对象由外部 STL 导入、磁盘上同名文件已修改（20mm→30mm）时，选中对象右键点「从磁盘重新加载」并观察几何。预期「对象按磁盘最新文件重新加载，尺寸变为 30mm；文件被删则明确报错」。

**结论：两句里一句成立。** 同一路径换成 30 mm 后重载，对象变成 30 mm；源文件被删之后再重载，Snapmaker Orca 2.4.0 弹的是标题 `Please select a file:` 的文件选择框，没有任何报错。判据按飞书原文逐字判，这一行只算部分覆盖，飞书状态保持空白。

| 运行 | 测试提交 | 客机 | 场景耗时 | 读数 |
| --- | --- | --- | ---: | --- |
| [首轮收据](ff55c9d8-run1-receipt.json) | `ff55c9d8…` | RED（第二分句） | 129.327 秒 | 第一分句 PASS |
| [第二轮收据](ff55c9d8-run2-receipt.json) | `ff55c9d8…` | RED（第二分句） | 130.246 秒 | 第一分句 PASS |

两个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和工作目录。[构建摘要](build.json)

用例里发生的事（[日志](ff55c9d8-run1-case.log)、[analysis](ff55c9d8-run1-analysis.json)）：

1. 新工程里经 File→Import 导入用例现场写的 20 mm 二进制 STL `reload_cube.stl`（684 字节，[文件框截图](ff55c9d8-run1-chooser.png)），另存为 [before-reload.3mf](ff55c9d8-run1-before-reload.3mf)：1 个对象、12 个三角面，顶点集合与 20 mm STL 相同，三轴 20.0 mm，`source_file` 是它的完整路径。
2. 把同一路径覆盖成 30 mm，在对象上右键点 `Reload from disk`，另存为 [after-reload.3mf](ff55c9d8-run1-after-reload.3mf)：顶点集合与 30 mm STL 相同，三轴 30.0 mm，`source_file` 不变，对象中心没有移动。
3. 删掉这个 STL，再点 `Reload from disk`：应用弹出文件选择框（[截图](ff55c9d8-run1-missing-dialog.png)），文件名框预填 `reload_cube`，类型 `Supported files (*.3mf, *.stl, …)`，按钮 `Open` / `Cancel`，没有任何消息框。取消后另存为 [after-missing.3mf](ff55c9d8-run1-after-missing.3mf)：仍是 30 mm。

| 飞书预期 | 读数 | 结论 |
| --- | --- | --- |
| 对象按磁盘最新文件重新加载，尺寸变为 30mm | 20.0 → 30.0 mm，三角面与磁盘上那份 30 mm STL 一致 | PASS |
| 文件被删则明确报错 | 文件选择框 `Please select a file:`，不点名任何文件，没有消息框 | FAIL（按字面） |

**给测试同事定口径。** 产品在源文件缺失时的做法是让用户另选一个文件，取消则保持原模型。它不报错，但也说不上静默失败。要么把预期改成「文件被删则提示重新选择文件或明确报错」，要么这是产品需要补提示的地方。源码里对应 `Plater::priv::reload_from_disk` 的缺源分支。

一个与判定无关的读数：重载后工程元数据里的 `source_offset_x/y/z` 仍是 10（20 mm 立方体的半边长），30 mm 立方体应为 15；摆放位置本身是对的。

本轮早些时候的现状探针（提交 `7dc0906`，模型作为启动参数载入）读到同样的行为，留下的样本在[探针目录](../feishu-251-probe-2026-11-26/win11-test/)，供 `unit_tests/test_reload_oracle.py` 使用。上一轮同一条用例的记录见[#250、#251 首次自动化尝试](../../feishu-250-251-followup-2026-11-25.md)。

```powershell
& runner/hv_go.ps1 -Cases m7x_251_reload_from_disk -NoSync
```

计时：用例内每轮约 59 秒（空盘准备 11.7、文件框 12.4、另存三次各 9.2、两次右键重载 1.6 与 4.8），宿主派发到收割 108–110 秒。领取到首次走完全流程（提交 `fc163e85`，03:05:35）约 4 小时 06 分，其间一次失败轮：导入后立刻另存，撞上还没关的 Loading 框；改成等盘上出现模型且没有对话框之后通过。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
