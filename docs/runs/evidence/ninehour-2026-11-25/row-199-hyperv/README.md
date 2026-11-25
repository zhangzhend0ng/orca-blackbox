# 飞书 #199 新建项目与默认名称

飞书记录 `reczz28PBdmFqQ1k`。在 `win11-test` 的 `test` 交互桌面载入 `mixed_filament_test.3mf` 并导入 `Prusa.stl`。随后打开 File 菜单，触发 New Project，确认应用提示有未保存的项目改动，选择 No 后核对提示关闭、场景为空和项目标题恢复 `Untitled`。飞书状态已为「已自动化」。

## 客机运行

| 提交 | 派发 → 场景完成（北京时间） | 判定 | 原始证据 |
| --- | --- | --- | --- |
| `53e58c34` | 13:25:47.995 → 13:27:27.299 | RED。项目有初始场景与名称，真实右键未弹出 Add Primitive 菜单。 | [日志](53e58c34-case.log) · [回执](53e58c34-receipt.json) · [JUnit](53e58c34-junit.xml) |
| `0aee5bbf` | 13:29:52.200 → 13:31:38.452 | RED。STL 导入后两个着色连通区域增大并相连，连通区域数量判据未增加。 | [日志](0aee5bbf-case.log) · [回执](0aee5bbf-receipt.json) · [JUnit](0aee5bbf-junit.xml) |
| `f6f47018` | 13:35:31.582 → 13:37:21.851 | RED。导入后画布面积增加，File → New Project 弹出了正确的未保存提示；真实点击 No 未关闭提示。 | [日志](f6f47018-case.log) · [回执](f6f47018-receipt.json) · [JUnit](f6f47018-junit.xml) |
| `b5deb4ff` | 13:40:22.878 → 13:42:04.200 | RED。No 关闭提示，画布为空，Win32 标题为 `Untitled - Snapmaker Orca`，自绘顶栏实读 `*Untitled`，当时的标题判据未接受星号。 | [日志](b5deb4ff-case.log) · [回执](b5deb4ff-receipt.json) · [JUnit](b5deb4ff-junit.xml) |
| `00235a01` | 13:43:38.347 → 13:45:05.654 | **GREEN**。提示关闭，画布着色 `0.121%`，两个标题位置的项目名称均为 `Untitled`。 | [日志](00235a01-case.log) · [回执](00235a01-receipt.json) · [JUnit](00235a01-junit.xml) |
| `00235a01` 独立复跑 | 13:45:10.691 → 13:46:37.676 | **GREEN**。新 Orca 进程重复得到未保存提示、空板 `0.121%` 与默认项目名。 | [日志](00235a01-rerun-case.log) · [回执](00235a01-rerun-receipt.json) · [JUnit](00235a01-rerun-junit.xml) |

领取时间为 13:15:09，至首次 GREEN 为 29 分 56.654 秒。此前保留四次 RED。首次 GREEN 的场景墙钟为 87.307 秒，第二次为 86.986 秒。

| 飞书预期 | 客机实测 |
| --- | --- |
| 有未保存改动时弹出是否保存当前项目 | `mixed_filament_test.3mf` 导入 `Prusa.stl` 后画布着色由 `0.796%` 增至 `1.577%`。打开 File 菜单并触发 New Project 后，读到 `The current project has unsaved changes. Would you like to save before continuing?`。 |
| 确认后清空场景，进入空白新项目 | 点击该提示的 No 控件后原提示关闭，画布着色降至 `0.121%`，低于本夹具空板门槛 `0.400%`，程序仍存活。 |
| 标题栏显示默认项目名 | Win32 窗口标题从 `mixed_filament_test - Snapmaker Orca` 变为 `Untitled - Snapmaker Orca`；自绘顶栏从 `mixed_filament_test` 变为 `*Untitled`。应用在自绘标题中用前导 `*` 标记未保存状态，名称比较跳过这一标记，日志保留完整显示文本。 |

## 复跑入口

在具备 Hyper-V 权限的宿主 PowerShell 中，对已确认空闲的客机，先用 `runner/guest_v3_bundle_sync.ps1 -Head <完整提交>` 同步指定代码，再派发单例。客机回到 `Ready` 且本轮摘要生成后收割。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m7x_199_new_project_title -NoSync
& .\runner\hv_harvest.ps1
```
