# 飞书 #237 导出配置包：换成真正的用户预设后打印机和耗材都能导出，工艺类型要有一台已安装的系统打印机（未做完）

记录 `reczz28aa4fiXAf5`（P1）要求存在自定义打印机/耗材/工艺预设时，点击「文件→导出→导出配置包…」，选择要导出的预设并保存，随后用「导入配置…」重新导入核对参数一致。预期「生成配置包文件（.ini/.zip），重新导入后预设参数与导出前一致」。

**结论：这一行本轮不能判「不成立」，是前置条件没有做全。** 前十三次客机会话里，配置目录只有仓库种子出来的预设（应用没有载入）和应用自己另存的一个工艺预设，当前打印机是工程内嵌的。这种初态下弹窗的工艺类型一行都列不出，耗材类型只列得出工程内嵌的耗材名，导出它们报 `add file fail`。收尾前的探针（`diag_bundle_user_printer`，提交 `fe33d9c8…`，09:00，[analysis](probe-fe33d9c8-analysis.json)、[日志](probe-fe33d9c8-case.log)）换成 #232 导入的三个用户预设，把打印机切到 `BB Test Printer`，读数就变了。飞书状态保持空白。

探针用 U1 0.8 mm 的模板（`agent_layer_cube.3mf`），切换前后各读一次弹窗（[切换后的截图](probe-fe33d9c8-user-bundle-dialog.png)）：

| 类型 | 切换前列出（当前是工程内嵌的打印机） | 切换到 BB Test Printer 之后 | 导出 |
| --- | --- | --- | --- |
| Printer config bundle(.orca_printer) | 无 | BB Test Printer | 没有试 |
| Filament bundle(.orca_filament) | Generic PETG、Snapmaker PLA Silk（工程内嵌） | 另有 BB Test Filament | 没有试 |
| Printer presets(.zip) | 无 | BB Test Printer | `Export successful`，落盘 `Printer presets.zip` 3,538 字节（[截图](probe-fe33d9c8-result-dialog.png)） |
| Filament presets(.zip) | 同上 | 另有 BB Test Filament | 只勾 BB Test Filament：`Export successful`，落盘 `Filament presets.zip` 1,434 字节 |
| Process presets(.zip) | 无 | 无 | 没有可导出的行 |

**弹窗按什么列**（`CreatePresetsDialog.cpp`，`sync/softfever-20261010`）：

- `ExportConfigsDialog::data_init()` 遍历预设集里的打印机，跳过不可见的、默认的和**工程内嵌的**；对剩下的每台打印机，收与它兼容的用户耗材预设和用户工艺预设。
- `Printer presets(.zip)` 列其中的非系统打印机，也就是用户自己的打印机。
- 两种耗材类型按耗材名列出可覆盖的耗材预设，工程内嵌的也算。
- `Process presets(.zip)` 只列**系统打印机**（而且必须是它自己的基础预设，即已安装的那一台）里至少有一个用户工艺预设的；用户打印机不在这个列表里。

测试用的新配置目录里没有安装任何系统打印机（打印机弹层把它们放在 `------ Select/Remove printers (system presets) ------` 之下，不在已启用的列表里），当前打印机又是工程内嵌的，所以工艺类型每一次都是空的。这是前置条件没有做全，不是产品的缺陷。

**仍然成立的产品问题。** 弹窗把工程内嵌的耗材名列出来（十三次会话里的 `Generic PLA`、`Snapmaker PLA Basic`，探针里的 `Generic PETG`、`Snapmaker PLA Silk`），勾选导出时应用日志写 `… Filament preset failed to add file to ZIP archive`，随后弹 `add file fail`（[截图](1387bc8c-run1-result-dialog.png)），磁盘上留下 0 字节的 zip。源码里对应 `ExportConfigsDialog::save_presets_to_zip`：`mz_zip_writer_add_file` 失败即返回 `ADD_FILE_FAIL`，压缩包已经创建但没有收尾。值得单独提给产品：弹窗不该列出它导不出的名字。

**没有测到的。** 在一台已安装的系统打印机下导出工艺预设包；把导出的 zip 用「导入配置」重新导入并比较参数（飞书第 3 步）。下一批的做法已经清楚：先在「Select/Remove printers」里安装一台系统打印机，导入或另存用户打印机、耗材、工艺预设各一个，三种类型各导出一次，再导入并逐键比较。探针在「另存工艺预设」一步停过一次（工艺行已经是用户预设时没有保存按钮），不影响上面的读数。

**前十三次会话**（都用 U1 0.4 mm 的 `feishu_std_cube.3mf`）：

| 运行 | 测试提交 | 客机 | 场景耗时 | 读到的结果 |
| --- | --- | --- | ---: | --- |
| [首轮收据](da4ecd60-run1-receipt.json) | `da4ecd60…` | RED | 82.434 秒 | 五种类型各普查一次；工艺类型没有行，没有导出 |
| [第二轮收据](ff55c9d8-run1-receipt.json) | `ff55c9d8…` | RED | 118.301 秒 | 导出 `Filament presets(.zip)` 的 `Generic PLA`：结果框 `add file fail`，落盘一个 0 字节的 `Filament presets.zip` |
| [第三轮收据](847aa160-run1-receipt.json) | `847aa160…` | RED | 121.791 秒 | 同上，应用日志点名了失败的文件；经 GUI 另存一个用户工艺预设没做成 |
| [第四轮收据](a09a0662-run1-receipt.json) | `a09a0662…` | RED | 121.390 秒 | 同上；[整屏截图](a09a0662-run1-preset-before.png)里一个 `Windows Security` 防火墙提示压在应用上面 |
| [第五轮收据](66d8233e-run1-receipt.json) | `66d8233e…` | RED | 121.047 秒 | 同上；给被测程序加了防火墙规则之后，[整屏截图](66d8233e-run1-preset-before.png)里那个提示还在 |
| 第六至十次 | `253195c7…`、`aeacaf37…`、`21fa17bd…` ×2、`24eef7a6…` | RED | 119.727–124.284 秒 | 普查后先关掉对话框；造预设停在侧栏的 Advanced 开关 |
| 第十一次 | `55e44162…`（与下面两次同一套用例代码） | RED | 175.624 秒 | 另存了用户工艺预设 `BB Export Test`；工艺类型仍无行；耗材导出 `add file fail` |
| [第十二次收据](1387bc8c-run1-receipt.json) | `1387bc8c…` | RED | 176.526 秒 | 与第十一次逐项相同 |
| [第十三次收据](1387bc8c-run2-receipt.json) | `1387bc8c…` | RED | 174.645 秒 | 与第十二次逐项相同 |

十三次都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，每次是新的 Orca 进程、配置目录和工作目录。[构建摘要](build.json)。第六至十一次的收割件在总控的宿主目录（不在仓库内）。

这十三次里用例做了什么：经应用自己另存用户工艺预设（Advanced 开关、层高 0.2 改 0.3、`Save Process as` 框选 `User Preset`，文件 `user/default/process/BB Export Test.json` 落盘，[截图](1387bc8c-run1-preset-before.png)、[analysis](1387bc8c-run1-analysis.json)）；应用启动日志对种子预设逐一报 `can not find parent for config`，所以它们没有被载入；两处用例问题已改——普查之后先把模态对话框关掉再去碰侧栏，真实点击之前先把 Orca 置前并按颜色读 Advanced 开关。

**给测试同事。** 两件请定：前置条件「存在自定义打印机/耗材/工艺预设」没有说放在哪里，请写明「用户目录里的用户预设，当前打印机是一台已安装的系统打印机」；工程内嵌的耗材名在「导出配置包」里列得出、导不出，可以单独提给产品。

```powershell
& runner/hv_go.ps1 -Cases m7x_237_export_configs -NoSync
& runner/hv_go.ps1 -Cases diag_bundle_user_printer -NoSync   # 探针
```

计时：最后三次用例内约 132 秒（读弹窗 13.1、造预设 35.8、再读弹窗 13.2、耗材读数 34.9、导出 34.7）；探针用例内约 132 秒。领取到首轮（提交 `da4ecd60`，02:52）约 3 小时 53 分，此后没有一次通过。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
