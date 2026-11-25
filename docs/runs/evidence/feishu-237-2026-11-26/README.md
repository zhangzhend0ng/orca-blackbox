# 飞书 #237 导出配置包：应用自己另存的工艺预设也列不出来，导出耗材名报 add file fail（RED）

记录 `reczz28aa4fiXAf5`（P1）要求存在自定义打印机/耗材/工艺预设时，点击「文件→导出→导出配置包…」，选择要导出的预设并保存，随后用「导入配置…」重新导入核对参数一致。预期「生成配置包文件（.ini/.zip），重新导入后预设参数与导出前一致」。

**结论：十三次客机会话都没有生成配置包。** 最后三次把前置条件做到了位：用例经应用自己的 `Save preset` 框另存了一个用户工艺预设 `BB Export Test`（层高 0.2 改成 0.3，文件落盘，侧栏预设行变成它）。之后再打开 `Export Preset Bundle`，`Process presets(.zip)` 仍然一行都列不出；能列出的两个耗材名是工程内嵌的耗材预设，导出它们时应用报 `add file fail`，磁盘上留下 0 字节的 zip。预期不成立，原因分两层，见下。「重新导入后参数一致」没有走到。飞书状态保持空白。

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

十三次都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，每次是新的 Orca 进程、配置目录和工作目录，打开 `fixtures/feishu_std_cube.3mf`（U1 0.4 mm）。[构建摘要](build.json)。第六至十一次的收割件在总控的宿主目录（不在仓库内）。

弹窗（[截图](1387bc8c-run1-bundle-dialog.png)）的五种类型和各自列出的行，各次相同，另存预设之前和之后也相同：

| 类型 | 列出的行 | 弹窗自己的说明 |
| --- | --- | --- |
| Printer config bundle(.orca_printer) | 无 | Only display printers with changes to printer, filament, and process presets are displayed. |
| Filament bundle(.orca_filament) | Generic PLA、Snapmaker PLA Basic | Only display the filament names with changes to filament presets. |
| Printer presets(.zip) | 无 | Only printer names with user printer presets will be displayed… |
| Filament presets(.zip) | Generic PLA、Snapmaker PLA Basic | Only the filament names with user filament presets will be displayed… |
| Process presets(.zip) | 无 | Only printer names with changed process presets will be displayed… |

**先排除夹具的问题。** 磁盘上有 3 个工艺预设和 3 个耗材预设文件，但应用启动时的日志（[第三轮的应用日志](847aa160-run1-app-log.log)）对它们逐一报错：

```
[error] can not find parent for config …\user\default\process\0.20mm Standard @Snapmaker U1 (0.4 nozzle) - HF-TEST.json!
[error] can not find parent for config …\user\default\filament\Snapmaker PLA SnapSpeed @U1 - FLOW-TEST.json!
```

它们都没有被载入，所以头十次里「工艺类型列不出行」还怪不到产品头上。第六次起用例自己造前置条件，第十一次才走通：把 Orca 置前，点开侧栏的 Advanced 开关（[截图](1387bc8c-run1-preset-before.png)，读数从关 `[0, 0]` 变成开 `[0.798, 0.426]`），在 Quality 页把层高从 0.2 改成 0.3，点侧栏的保存按钮，在 `Save Process as` 框里选 `User Preset`、输入 `BB Export Test`、OK。读数（[analysis](1387bc8c-run1-analysis.json)）：`export-profile/user/default/process/BB Export Test.json` 落盘，侧栏预设行从 `* 0.20mm Standard @Snapmaker U1 (0.4 nozzle)(feishu_std_cube.3mf)` 变成 `BB Export Test`。

**产品的问题一：有用户工艺预设，工艺类型还是列不出。** 上面三步之后重新普查，`Process presets(.zip)` 仍然是空的，三次相同。源码里这个弹窗对每个可见的非默认打印机只收与它兼容的用户耗材/工艺预设（`ExportConfigsDialog::data_init()`，`src/slic3r/GUI/CreatePresetsDialog.cpp`）；这个工程的打印机是工程内嵌的预设，是不是因此被跳过，本轮没有读到底。

**产品的问题二：导出工程内嵌的耗材预设失败。** 弹窗列出的 `Generic PLA`、`Snapmaker PLA Basic` 是打开的工程自带的耗材预设（名字带 `(feishu_std_cube.3mf)` 后缀，磁盘上没有对应文件）。勾选导出时应用日志写：

```
[info] Generic PLA @U1 0.4 nozzle(feishu_std_cube.3mf).json Filament preset failed to add file to ZIP archive
```

随后弹 `add file fail`（[截图](1387bc8c-run1-result-dialog.png)），磁盘上留下 0 字节的 zip。源码里对应 `ExportConfigsDialog::save_presets_to_zip`：`mz_zip_writer_add_file` 失败即返回 `ADD_FILE_FAIL`，压缩包已经创建但没有收尾。#232 的另一轮（模板 U1 0.8 mm）导出耗材名时也是同样的签名。

**给测试同事。** 两件都可以单独提给产品：打开任意带内嵌耗材预设的工程 → 文件→导出→导出配置包 → 选 `Filament presets(.zip)` → 勾一个耗材名 → 导出，会得到 `add file fail` 和一个 0 字节的 zip；在同一个工程里另存一个用户工艺预设之后，`Process presets(.zip)` 仍然列不出它。「重新导入后参数一致」本轮因此没有测到，按未测计。另：前置条件没有说自定义预设放在哪里（用户目录还是工程内嵌），请定口径。

**用例自己的两处问题，已改。** fa706g3 上的一次 SHADOW（提交 `f9e99228…`，[整屏截图](fa-f9e99228-50e7b699a849-preset-before.png)）说明普查之后「Export Preset Bundle」对话框还开着，用例是在这个模态对话框开着的时候去点侧栏的；现在先关掉它再去造预设（第六轮起 `closed: true`）。关掉之后同一步仍然失败：两台机器上做这一步时前台窗口都是跑套件的终端，真实点击没有先把 Orca 置前，开关没有翻转（fa 的收割件在 `artifacts/fa-obj-237-21fa17bd-6d23cf11e740`，SHADOW）；现在先置前并读回落点处的窗口，开关按左右两半的颜色读（按「旋钮在右」读在这个布局上读反了）。第四、五轮截图里的 `Windows Security` 防火墙提示是真的：类名 `Shell_SystemDialog`，带一层铺满整屏的置顶遮罩，真实鼠标点击全被它吃掉；客机上的直派脚本现在在派发期间每 1.5 秒关它一次。谁触发它没有定位，见 PITFALLS §22.1。

```powershell
& runner/hv_go.ps1 -Cases m7x_237_export_configs -NoSync
```

计时：最后三次用例内约 132 秒（读弹窗 13.1、造预设 35.8、再读弹窗 13.2、耗材读数 34.9、导出 34.7）。领取到首轮（提交 `da4ecd60`，02:52）约 3 小时 53 分，此后十三次会话没有一次通过；另存预设这一步第一次做成是 06:29。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
