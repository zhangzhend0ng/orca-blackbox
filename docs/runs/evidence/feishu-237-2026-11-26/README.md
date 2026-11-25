# 飞书 #237 导出配置包：工艺预设列不出来，导出耗材名报 add file fail（RED）

记录 `reczz28aa4fiXAf5`（P1）要求存在自定义打印机/耗材/工艺预设时，点击「文件→导出→导出配置包…」，选择要导出的预设并保存，随后用「导入配置…」重新导入核对参数一致。预期「生成配置包文件（.ini/.zip），重新导入后预设参数与导出前一致」。

**结论：四轮客机实跑都没有生成配置包。** Snapmaker Orca 2.4.0 的弹窗里，`Process presets(.zip)` 一行都列不出；列得出的两个耗材名是工程内嵌的耗材预设，导出它们时应用报 `add file fail`，磁盘上留下一个 0 字节的 zip。预期不成立，原因分两层，见下。飞书状态保持空白。

| 运行 | 测试提交 | 客机 | 场景耗时 | 读到的结果 |
| --- | --- | --- | ---: | --- |
| [首轮收据](da4ecd60-run1-receipt.json) | `da4ecd60…` | RED | 82.434 秒 | 五种类型各普查一次；工艺类型没有行，没有导出 |
| [第二轮收据](ff55c9d8-run1-receipt.json) | `ff55c9d8…` | RED | 118.301 秒 | 导出 `Filament presets(.zip)` 的 `Generic PLA`：结果框 `add file fail`，落盘一个 0 字节的 `Filament presets.zip` |
| [第三轮收据](847aa160-run1-receipt.json) | `847aa160…` | RED | 121.791 秒 | 同上，并且应用日志点名了失败的文件；经 GUI 另存一个用户工艺预设没做成 |
| [第四轮收据](a09a0662-run1-receipt.json) | `a09a0662…` | RED | 121.390 秒 | 同上；再造预设仍然没做成，[整屏截图](a09a0662-run1-preset-before.png)里一个 Windows 防火墙提示压在应用上面 |

四轮都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，打开 `fixtures/feishu_std_cube.3mf`（U1 0.4 mm）。[构建摘要](build.json)

弹窗（[截图](ff55c9d8-run1-bundle-dialog.png)）的五种类型和各自列出的行，四轮相同：

| 类型 | 列出的行 | 弹窗自己的说明 |
| --- | --- | --- |
| Printer config bundle(.orca_printer) | 无 | Only display printers with changes to printer, filament, and process presets are displayed. |
| Filament bundle(.orca_filament) | Generic PLA、Snapmaker PLA Basic | Only display the filament names with changes to filament presets. |
| Printer presets(.zip) | 无 | Only printer names with user printer presets will be displayed… |
| Filament presets(.zip) | Generic PLA、Snapmaker PLA Basic | Only the filament names with user filament presets will be displayed… |
| Process presets(.zip) | 无 | Only printer names with changed process presets will be displayed… |

**第一层：仓库种子出来的预设不是这里要的「自定义预设」。** 磁盘上有 3 个工艺预设和 3 个耗材预设文件，但应用启动时的日志（[第三轮的应用日志](847aa160-run1-app-log.log)）对它们逐一报错：

```
[error] can not find parent for config …\user\default\process\0.20mm Standard @Snapmaker U1 (0.4 nozzle) - HF-TEST.json!
[error] can not find parent for config …\user\default\filament\Snapmaker PLA SnapSpeed @U1 - FLOW-TEST.json!
```

它们都没有被载入。所以工艺类型列不出行，是测试夹具的问题，不是产品的。

**第二层：产品的导出对工程内嵌的预设失败。** 弹窗列出的 `Generic PLA`、`Snapmaker PLA Basic` 是打开的工程自带的耗材预设（名字带 `(feishu_std_cube.3mf)` 后缀，磁盘上没有对应文件）。勾选导出时应用日志写：

```
[info] Generic PLA @U1 0.4 nozzle(feishu_std_cube.3mf).json Filament preset failed to add file to ZIP archive
```

随后弹 `add file fail`（[截图](ff55c9d8-run1-result-dialog.png)），磁盘上留下 0 字节的 zip。源码里对应 `ExportConfigsDialog::save_presets_to_zip`：`mz_zip_writer_add_file` 失败即返回 `ADD_FILE_FAIL`，压缩包已经创建但没有收尾（`src/slic3r/GUI/CreatePresetsDialog.cpp`）。#232 的另一轮（模板 U1 0.8 mm）导出耗材名时也是同样的签名。

**给测试同事。** 这是一条可以单独提缺陷的产品问题：打开任意带内嵌耗材预设的工程 → 文件→导出→导出配置包 → 选 `Filament presets(.zip)` → 勾一个耗材名 → 导出，会得到 `add file fail` 和一个 0 字节的 zip。另外「经应用自己另存出来的用户工艺预设能否导出、再导入后参数是否一致」这一段本轮没有走到，仍是未测：第三、四轮里经 GUI 造预设都停在找 Advanced 开关这一步。第四轮的整屏截图显示，当时桌面上压着一个 `Windows Security` 防火墙提示（`Snapmaker Control` 请求访问公共和专用网络），它盖在应用上面接走了输入。这个提示属于客机环境问题，不是产品的；它出现的确切时机没有定位。

```powershell
& runner/hv_go.ps1 -Cases m7x_237_export_configs -NoSync
```

计时：第二轮用例内约 48 秒（读弹窗 13.1、导出 35.0），第三轮约 86 秒、第四轮约 86 秒（读弹窗 13.1、尝试造预设 3.3、耗材读数 34.9、导出 34.7）。领取到首轮（提交 `da4ecd60`，02:52）约 3 小时 53 分，此后没有一轮通过。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
