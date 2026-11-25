# 飞书 #201 保存已命名项目并重新打开

飞书记录 `reczz28PBdmFs4ue`。原用例要求对已命名并保存过的项目中的对象做一次修改，通过「文件 → 保存项目」写回，再重开确认修改保留。此记录已标为「已自动化」。

独立用例 `m7x_201_save_project_reopen` 将单实例夹具复制到本轮独有的 `test_project.3mf`。用例在 Orca 的 Prepare 画布取得焦点，选中已有立方体，再用右箭头快捷键沿世界 X 轴移动 10 mm。文件菜单的判据精确匹配 `Save Project` 并确认同名路径的文件被重写。退出旧进程后以新的 profile 和 PID 加载同一路径。观测包括 GUI 中的立方体位置、同一路径的保存前后 SHA-256、保存前后的实例变换和网格三角面。

## Hyper-V 实跑

2026-11-25 14:03:45 +08:00 领取。在 `win11-test` 的 `test` 交互会话执行，操作步骤通过 Orca 的界面和窗口输入完成。

| 提交 | 派发 | 场景完成 | 结论 | 证据 |
| --- | --- | --- | --- | --- |
| `a9d10eec` | 14:11:25.098 | 14:13:42.602 | RED。夹具及项目名确认成功，鼠标悬停工具提示无法定位 Rotate，旧脚本在编辑前置阶段结束。 | [日志](a9d10eec-case.log) · [收据](a9d10eec-receipt.json) · [JUnit](a9d10eec-junit.xml) |
| `7a7a584f` | 14:19:35.861 | 14:21:02.480 | RED。Edit > Select All 命令已发送，右箭头后立方体的视口质心仍为 `(1172, 514)`。 | [日志](7a7a584f-case.log) · [收据](7a7a584f-receipt.json) · [JUnit](7a7a584f-junit.xml) |
| `20cdfdcd` | 14:28:23.450 | 14:29:46.489 | RED。确认 Prepare 画布获得焦点，消息式点击和菜单选择后的局部像素差为 0.0%，旧脚本在发送右箭头前退出。 | [日志](20cdfdcd-case.log) · [收据](20cdfdcd-receipt.json) · [JUnit](20cdfdcd-junit.xml) |
| `054dd881` | 14:35:10.507 | 14:36:36.665 | RED。真实按键将立方体质心从 `(1172, 514)` 移至 `(1195, 514)`，普通保存已写回原路径。停在编辑进程退出和保存件校验的边界，未开始独立重开。 | [日志](054dd881-case.log) · [收据](054dd881-receipt.json) · [JUnit](054dd881-junit.xml) · [工程收据](054dd881-project_artifacts.json) · [保存前](054dd881-before-save.3mf) · [保存后](054dd881-after-save.3mf) |
| `1216dc9e` 首轮 | 14:38:12.048 | 14:40:29.185 | **GREEN**，137.137 秒。普通保存及独立重开均通过。 | [日志](1216dc9e-run1-case.log) · [收据](1216dc9e-run1-receipt.json) · [JUnit](1216dc9e-run1-junit.xml) · [工程收据](1216dc9e-run1-project_artifacts.json) · [保存前](1216dc9e-run1-before-save.3mf) · [保存后](1216dc9e-run1-after-save.3mf) · [重开输入](1216dc9e-run1-reopen-input.3mf) |
| `1216dc9e` 独立复跑 | 14:40:35.971 | 14:42:53.327 | **GREEN**，137.356 秒。新一轮编辑、普通保存及独立重开复现首轮读数。 | [日志](1216dc9e-run2-case.log) · [收据](1216dc9e-run2-receipt.json) · [JUnit](1216dc9e-run2-junit.xml) · [工程收据](1216dc9e-run2-project_artifacts.json) · [保存前](1216dc9e-run2-before-save.3mf) · [保存后](1216dc9e-run2-after-save.3mf) · [重开输入](1216dc9e-run2-reopen-input.3mf) |

领取至首次 GREEN 约 36 分 44 秒。首次 GREEN 前有 4 次客机实跑失败，另有一次派发在检查到已有客机驱动进程后中止，随后确认空闲并派发。

`054dd881` 的两份原始 3MF 经独立读取，实例平移从 `(135.5, 136, 13.5)` 变为 `(145.5, 136, 13.5)` mm，线性分量一致，12 个世界坐标三角面整体沿 X 轴移动 10 mm。本地网格的 8 个顶点和 12 个三角面的规范化 SHA-256 均为 `421388b40950c14473924005e226b9aa85e177479ed73d5d772d1517fc91267d`。

## 飞书原行逐项对照

| 飞书预期 | 客机读数 |
| --- | --- |
| 项目保存成功，无报错。 | 经过精确的顶栏 File > Save Project，已命名 `test_project.3mf` 原地写入有效 3MF，Orca 仍响应，保存期间未出现错误弹窗。文件 SHA-256 与保存前不同。保存后的 X 从 `135.5` 变为 `145.5` mm，Y、Z、线性变换和本地网格保持。 |
| 重新打开项目后，修改被保留。 | 独立启动前再次校验同一绝对路径的 SHA-256，和保存后哈希相同。首轮编辑 PID `6944` 退出后由 PID `8788` 重开，复跑从 PID `10876` 到 PID `4340`。两轮均使用新 profile 从同一路径加载，标题读为 `test_project`，立方体质心从编辑前的 `(1172, 514)` 变为 `(1195, 514)`，与移动后画布一致。 |

两轮编辑进程的清理退出码均为 `1`。独立重开前已确认旧 PID 离开且项目字节保持。该退出观测适用于 #201 重开的隔离条件。#140 的关闭行为由其独立用例判定。

## 复跑入口

确认 `win11-test` 空闲，在具备 Hyper-V 权限的 PowerShell 中同步待测提交。使用既有 v3 检出时先执行 `runner/guest_v3_bundle_sync.ps1 -Head <完整 SHA>`。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m7x_201_save_project_reopen -NoSync
# 等 suite 回到 Ready 且 regress_summary.txt 写入本轮结果后收割
& .\runner\hv_harvest.ps1
```

日志给出本轮 `artifacts/feishu-project-cases/201/run-*` 的确切客机目录和保存后的项目哈希。工程证据为该目录的 `before-save.3mf`、`after-save.3mf` 与 `reopen-input.3mf`。
