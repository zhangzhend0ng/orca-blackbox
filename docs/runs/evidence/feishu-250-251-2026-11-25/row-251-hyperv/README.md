# 飞书 #251 从磁盘重新加载

飞书记录 `reczz28aa4fiXrq7` 的原状态为空白。用例在每轮的独立目录生成 20 mm 和 30 mm 两份立方体 STL，并以同一个可替换的 `reload_cube.stl` 路径作为 Orca 的导入源。

| 飞书预期 | 判据 |
| --- | --- |
| 模型按磁盘最新文件重新加载，尺寸变为 30 mm | 读取导入后 GUI 保存的 `.3mf`，确认单模型、单实例、来源路径和三轴 20 mm。以 30 mm 文件覆写同一源路径，从画布上的对象右键菜单执行 `Reload from disk`。GUI 再保存后读回三轴 30 mm 和同一来源路径。 |
| 文件被删除后明确报错 | 确认隔离源文件删除后再次执行同一右键命令，读取实际对话框标题、文字和文件名。替换文件选择框作为产品实际行为记录。关闭提示后独立读取一次保存产物，检查此前 30 mm 模型是否保留。 |

离线验证两份生成 STL 均包含 12 个三角面、684 字节，三轴端点分别为 `0–20 mm`、`0–30 mm`。用于判定的 3MF 读取器从仓内已知夹具读回三轴 `27 mm` 和其源文件字段。

## Hyper-V 实跑

领取时间为 2026-11-25 14:56:54.877 +08:00。场景运行经过 `runner/hv_go.ps1`，在 `win11-test` 的 `test` 交互会话执行 Orca 2.4.0，执行文件 SHA-256 为 `5C48644D7DA18B50636CEEEE4EF9FD2EAF6D4E8AC05BD88752F40E3717FC47BF`。日志、JUnit 与多份原始模型和工程随轮次保留。

| 提交 | 派发及完成时间（+08:00） | 结果 | 证据 |
| --- | --- | --- | --- |
| `df2916ab` | 15:13:25.454 → 15:14:57.209，91.76 秒 | RED。初始 3MF 读到三轴各 20 mm 和实际导入源路径。同一路径已替换为 30 mm STL，画布定位选中右下区域，未打开对象菜单。 | [日志](df2916ab-case251.log) · [收据](df2916ab-receipt.json) · [JUnit](df2916ab-junit.xml) · [工件清单](df2916ab-object_artifacts.json) |
| `1149a497` | 15:23:02.017 → 15:24:51.958，109.94 秒 | **RED，重载尺寸通过**。两个阶段均读到可用的对象 `Reload from disk` 菜单。覆写同一路径后，保存工件从 `20×20×20 mm` 变为 `30×30×30 mm`。删除源后打开 `Please select a file:`，文件名框预填 `reload_cube`，原预期的明确报错未出现。取消选择框后再次保存，三轴仍为 30 mm。 | [日志](1149a497-case251.log) · [收据](1149a497-receipt.json) · [JUnit](1149a497-junit.xml) · [工件清单](1149a497-object_artifacts.json) |
| `a7a65272` 独立复跑 | 15:34:20.882 → 15:35:58.759，97.88 秒 | **RED，重载尺寸通过**。新进程和隔离目录复现 `20×20×20 mm` → `30×30×30 mm`。删除同一源文件后再次打开预填 `reload_cube` 的 `Please select a file:` 选择框。取消后保存的工程保持 `30×30×30 mm`。 | [日志](a7a65272-case251.log) · [收据](a7a65272-receipt.json) · [JUnit](a7a65272-junit.xml) · [工件清单](a7a65272-object_artifacts.json) |

从领取到首次完成两条分支的现场观察用时 27 分 57.08 秒。当前完整 GREEN 次数为 0，飞书自动化状态保留原样。共享交互层在客机桌面命中到画布之外时使用针对 Orca `wxGLCanvas` 的 Win32 右键消息，读取实际打开的原生对象菜单后派发其中唯一、可用的 `Reload from disk` 项。对话框截图保留了原生文件选择器的内容，窗口标题另由 Win32 读回。[20 mm STL](1149a497-source-20mm.stl) · [30 mm STL](1149a497-source-30mm.stl) · [初始工程](1149a497-before-reload.3mf) · [重载工程](1149a497-after-reload.3mf) · [取消后工程](1149a497-after-missing.3mf) · [缺源选择器](1149a497-missing-dialog.png)

复跑使用相同的 #251 场景脚本。20、30、30 mm 三阶段的 3MF 尺寸、各阶段单模型实例及同一源路径均经独立复算。复跑继续要求缺源时明确报错，因此整项保留 RED。[复跑初始工程](a7a65272-before-reload.3mf) · [复跑重载工程](a7a65272-after-reload.3mf) · [复跑取消后工程](a7a65272-after-missing.3mf) · [复跑缺源选择器](a7a65272-missing-dialog.png)

## 复跑入口

`cases.py` 将 #251 登记为已知限制，默认回归套件排除该项。使用 `hv_go.ps1 -Cases m7x_251_reload_from_disk` 可显式执行完整原步骤，并保留缺源报警断言的真实判定。

将已确认空闲的 `win11-test` 同步至待测提交。在有 Hyper-V 权限的 PowerShell 中运行以下命令。项目既有 v3 检出路径通过 `runner/guest_v3_bundle_sync.ps1 -Head <提交完整 SHA>` 同步。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m7x_251_reload_from_disk -NoSync
# 等待 suite 回到 Ready 且 regress_summary.txt 输出本轮结果
& .\runner\hv_harvest.ps1
```

每轮工作目录由日志打印，位于客机 `artifacts/feishu-object-cases/251/run-*/`。该目录可保留两份原始 STL、三个阶段生成的 3MF 和缺源时对话框截图。
