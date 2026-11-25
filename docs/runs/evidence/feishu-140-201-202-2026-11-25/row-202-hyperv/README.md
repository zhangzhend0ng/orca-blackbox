# 飞书 #202 项目另存为

飞书记录 `reczz28PBdmFsziK`。单独复跑时，把 `mixed_filament_test.3mf` 复制为隔离目录下的 `source/test_project.3mf`，在 Orca 打开该项目。每次运行使用独立源副本、目标目录和 Orca profile。

| 飞书预期 | 判据 |
| --- | --- |
| 在新路径生成新的 `.3mf` 文件 | 经 `File > Save Project as` 打开原生文件对话框，输入并读回 `target/test_project_v2.3mf` 的绝对路径。确认窗口关闭、新文件 ZIP 校验通过、模型对象和构建实例数保持一致。打印机字段对比只归一化 Orca 附加的当前源或目标工程文件名后缀。 |
| 原项目文件保持不变 | 比对已打开项目的源文件在另存为前、另存为后和普通保存后的 SHA-256，同时留存可独立验证的源 3MF。 |
| 另存后当前项目指向新文件，后续保存写入新文件 | 读取活动项目名 `test_project_v2`。导入 `Prusa.stl` 后先确认新文件 SHA-256 保持原样，再从 `File` 选择普通 `Save Project`。验证新文件 SHA-256 改变、新增 Prusa 模型和一个构建实例，源文件 SHA-256 保持不变。 |

## Hyper-V 实跑

领取时间为 2026-11-25 14:03:56.082 +08:00。运行经过 `runner/hv_go.ps1`，在 `win11-test` 的 `test` 交互会话中执行 Orca 2.4.0，执行文件 SHA-256 为 `5C48644D7DA18B50636CEEEE4EF9FD2EAF6D4E8AC05BD88752F40E3717FC47BF`。`runner/hv_harvest.ps1` 取回 JUnit，客机日志和 3MF 采用 SHA-256 验证。

| 提交 | 派发及完成时间（+08:00） | 结果 | 证据 |
| --- | --- | --- | --- |
| `a9d10eec` | 14:10:02.927 → 14:11:20.442，77.52 秒 | RED。原生另存对话框和新项目名读回通过，目标 `.3mf` 已生成，源 SHA-256 保持不变。首次判据拒绝了 Orca 附加在打印机预设 ID 上的 `(test_project.3mf)` 来源后缀，普通保存阶段未执行。 | [日志](a9d10eec-case202.log) · [收据](a9d10eec-receipt.json) · [JUnit](a9d10eec-junit.xml) · [工程工件清单](a9d10eec-project_artifacts.json) |
| `89410a03` | 14:14:56.680 → 14:16:36.389，99.71 秒 | **GREEN**。原生对话框读回目标绝对路径，保存后活动标题为 `test_project_v2`。源文件三次 SHA-256 相同。导入后的普通 `Save Project` 把目标工程从 1 个构建实例写为 2 个，新增 `Prusa.stl`。 | [日志](89410a03-case202.log) · [收据](89410a03-receipt.json) · [JUnit](89410a03-junit.xml) · [工程工件清单](89410a03-project_artifacts.json) |
| `89410a03` 首次复跑 | 14:16:41.859 → 14:18:17.975，96.12 秒 | RED。新进程打开隔离源工程，原名、模型、源 SHA-256 均已读到。File 菜单在本轮未能打开，另存对话框未出现。 | [日志](89410a03-rerun-case202.log) · [收据](89410a03-rerun-receipt.json) · [JUnit](89410a03-rerun-junit.xml) · [工程工件清单](89410a03-rerun-project_artifacts.json) |
| `7a7a584f` | 14:21:08.896 → 14:22:50.974，102.08 秒 | **GREEN**。源文件 SHA-256 保持不变，目标新名和另存快照读回。普通保存后的目标工程新增 Prusa.stl 和一个构建实例。 | [日志](7a7a584f-case202.log) · [收据](7a7a584f-receipt.json) · [JUnit](7a7a584f-junit.xml) · [工程工件清单](7a7a584f-project_artifacts.json) |
| `7a7a584f` 独立复跑 | 14:23:01.477 → 14:24:43.468，101.99 秒 | **GREEN**。独立进程和隔离目录复现新路径、源文件保持、活动标题和普通保存的目标工程改动。 | [日志](7a7a584f-rerun-case202.log) · [收据](7a7a584f-rerun-receipt.json) · [JUnit](7a7a584f-rerun-junit.xml) · [工程工件清单](7a7a584f-rerun-project_artifacts.json) |

从领取到首次完整 GREEN 用时 12 分 40.31 秒，期间有 1 次 RED。首次 GREEN 的现场哈希为源工程 `ea00678017a7b6d7d65a4280b8f80c2d441493fd15998a924c66998ac946ccf0`，刚另存为时的目标 `91490f599bdca6a4e072381e880c721b5033192e065ea1d5751911d5351eee89`，普通保存后的目标 `c533ab3f429f748d74317dee0747aeb777e133702dac7dbaf55106a92cd1a25f`。

最终双 GREEN 共用 `7a7a584f`，场景代码与 `89410a03` 相同。两轮 3MF 的 SHA-256 均与各自客机清单一致。独立读取可见每轮源文件和另存快照各有 1 个立方体构建实例，普通保存后的目标各有原立方体及 `Prusa.stl` 共 2 个实例。累计 2 次 RED 均保留。[最终首轮源](7a7a584f-source-test_project.3mf) · [另存快照](7a7a584f-after-save-as.3mf) · [普通保存目标](7a7a584f-target-test_project_v2.3mf) · [复跑源](7a7a584f-rerun-source-test_project.3mf) · [复跑另存快照](7a7a584f-rerun-after-save-as.3mf) · [复跑普通保存目标](7a7a584f-rerun-target-test_project_v2.3mf)

## 复跑入口

将已确认空闲的 `win11-test` 同步至待测代码提交。在宿主有 Hyper-V 权限的 PowerShell 中运行以下命令。项目既有 v3 检出路径通过 `runner/guest_v3_bundle_sync.ps1 -Head <提交完整 SHA>` 同步。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m7x_202_save_as_project -NoSync
# 等待 suite 回到 Ready 且 regress_summary.txt 输出本轮结果
& .\runner\hv_harvest.ps1
```

日志打印该轮工程所在的绝对目录。客机的 `artifacts/feishu-project-cases/202/<运行目录>/` 中保留 `source/test_project.3mf`、另存为时的目标快照 `after-save-as.3mf` 以及普通保存完成后的 `target/test_project_v2.3mf`。
