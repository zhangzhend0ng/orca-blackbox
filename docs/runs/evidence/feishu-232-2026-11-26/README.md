# 飞书 #232 导入配置：三个预设都进了各自的列表，但选不中（部分覆盖）

记录 `reczz28aa4fiZjOA`（P1）要求准备一个导出的 `.ini` 配置文件（含 1 打印机 + 1 耗材 + 1 工艺），点击「文件→导入→导入配置…」选择该文件，导入后到对应预设下拉列表核对。预期「导入成功，3 个预设出现在对应列表且参数正确；同名重复时按产品既有策略提示（覆盖/重命名）」。

**结论：两句里一句成立，另一句成立一半。** 装着三份预设的 zip 能导入，再导一次时产品弹出覆盖提示。三个导入的预设都出现在各自的下拉列表里；但在侧栏选中它们的三种办法都没有生效，所以「参数正确」没有验证成。判据按飞书原文逐字判，这一行只算部分覆盖，飞书状态保持空白。

| 运行 | 测试提交 | 客机 | 场景耗时 | 读数 |
| --- | --- | --- | ---: | --- |
| [首轮收据](8d5a5533-run1-receipt.json) | `8d5a5533…` | RED（第一分句） | 125.891 秒 | 第二分句 PASS |
| [第二轮收据](8d5a5533-run2-receipt.json) | `8d5a5533…` | RED（第一分句） | 124.050 秒 | 与首轮逐项相同 |
| [对照一轮](3f55a59a-run1-receipt.json) | `3f55a59a…`（同一套兼容性写法，读列表的方式不同） | RED（第一分句） | 142.825 秒 | 三个名字都读到了；选中耗材失败 |

三个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和工作目录，打开 `fixtures/agent_layer_cube.3mf`（U1 0.8 mm）。[构建摘要](build.json)。更早的几轮留在这个目录里（`641f1a6c…`、`2c32e51c…`），是改兼容性写法之前的版本：那时耗材、工艺下拉里没有导入的名字。

**配置文件是怎么来的。** 飞书前置条件写的是 `.ini`。2.4.0 的「导入配置」文件框放行 `.ini`，随后却报 `Import result`：`There are 0 configs imported. (Only non-system and compatible configs) Hint: Make sure you have added the corresponding printer before importing the configs.`（[截图](8d5a5533-run1-ini-dialog-1.png)）。所以用例现场改用产品认的容器：从模板的三个系统预设（`Snapmaker U1 (0.8 nozzle)`、`Generic PETG @U1 0.8 nozzle`、`0.40 Standard @Snapmaker U1 (0.8 nozzle)`）把继承链合并成独立预设，改名为 `BB Test Printer` / `BB Test Filament` / `BB Test Process`；耗材、工艺两份把 `compatible_printers` 写成空列表、条件写成空串，使它们与所有打印机兼容（源码 `Preset::is_compatible_with_printer`：列表和条件都为空时为真）；三份 JSON 平铺在工作目录，另打成 zip（5,865 字节）。这一段每轮都留作读数，不参与判定。

用例里发生的事（[日志](8d5a5533-run1-case.log)、[analysis](8d5a5533-run1-analysis.json)）：

1. File→Import→`Import Configs...` 打开标题 `Select profile to load:` 的文件框，类型下拉是 `Config files (*.json;*.zip;*.orca_printer;*.orca_filament)`，没有 `.ini`。
2. 第一次导入 zip：`There are 3 configs imported. (Only non-system and compatible configs)`。配置目录多出三份文件：`filament/BB Test Filament`、`machine/BB Test Printer`、`process/BB Test Process`。
3. 读预设下拉。打印机弹层（[截图](8d5a5533-run1-machine-list.png)）是：`------ Project-inside presets ------`、`------ User presets ------`、`BB Test Printer`、`------ Select/Remove printers (system presets) ------`、`------ Create printer ------`。耗材弹层（[截图](8d5a5533-run1-filament-list.png)）第 13 行起依次是工程内嵌预设、`------ User presets ------`、第 116 行 `BB Test Filament`、`------ System presets ------`、系统预设。工艺弹层在对照那一轮读到：`------ User presets ------`、`BB Test Process`、`------ System presets ------`、`~ Default Setting`；最终两轮因为先停在下一步，没有读工艺弹层。
4. 选中导入的预设。先切打印机的两轮（消息点击、真实点击）都没切过去；改成不切打印机之后，选中 `BB Test Filament` 这一行试了三种办法——消息点击（先发鼠标移动）、真实鼠标点击、方向键两次再 Enter——预设行上的文字三次都还是 `Generic PETG @U1 0.8 nozzle(agent_layer_cube.3mf)`（[截图](8d5a5533-run1-selection-failed.png)）。这一步前后六轮没有一次选中，按纪律停下。
5. 第二次导入同一个 zip：连弹三个 `Overwrite config`——`A config exists with the same name: BB Test Printer. Do you want to overwrite it?`（另有 Filament、Process 两个），按钮 `Yes` / `No` / `Yes to All` / `No to All`（[截图](8d5a5533-run1-zip2-dialog-1.png)）。逐个答 Yes，最后 `There are 3 configs imported`。

| 飞书预期 | 读数 | 结论 |
| --- | --- | --- |
| 导入成功，3 个预设出现在对应列表且参数正确 | 导入成功（3 个）；打印机、耗材列出（两轮），工艺列出（对照一轮）；选不中；参数没有比 | FAIL（按字面） |
| 同名重复时按产品既有策略提示（覆盖/重命名） | 三个 `Overwrite config` 提示，Yes / No / Yes to All / No to All | PASS |

**参数读到了什么（离线，不参与判定）。** 导入后的三份预设文件和导出的 JSON 逐键比过：规范化之后没有一处值不同——差异只有写法：工艺里 23 个速度/加速度键从 `"30"` 变成 `["30"]`，打印机起始/结束 G-code 里两个字符的 `\n` 变成真换行。只在导出件里有的键：耗材 52 个、工艺 8 个、打印机 4 个（如 `type`、`instantiation`、`bed_model`、`counter_coef_1`），这个构建的有效配置里没有它们。

**离线复核做不了。** `tools/replay_case_evidence.py` 对这一条要求收割件里有另存的 `after-import.3mf`；最终几轮都停在选中预设之前，没有另存，回放直接拒绝（`the harvest lacks ['after-import.3mf']`）。只有更早一轮走到了另存的 `2c32e51c` 会话被回放过：25 项里 20 项为真，为假的 5 项正是分句一记录的失败。这个目录里更早几轮的收据缺三份 profile 快照，也不能完整重算；原件在总控的宿主目录。

**给测试同事。** 三件事请定口径：前置条件里的 `.ini` 在 2.4.0 上导不进任何预设，要不要改成 zip 或 `.orca_printer`；「参数正确」是否接受「导入后的预设文件与导出件一致」这种比法；导入的预设为什么在列表里却选不中——是产品的限制（导入的根预设不可选，或选中时需要先确认什么），还是测试驱动的问题，本轮没有分清。

```powershell
& runner/hv_go.ps1 -Cases m7x_232_import_configs -NoSync
```

计时：用例内 ini 观察 8.9 秒、第一次导入 10.4 秒、读下拉并尝试选中 17.4 秒、第二次导入 10.5 秒。领取到第一次看到「3 个导入」（提交 `fc163e85`，03:07）约 4 小时 08 分，其间多轮失败，原因是：按类型导出预设时产品报 `add file fail`（后来改成离线生成配置文件）、造用户打印机预设时找不到按钮、文件框多出一个空下拉框被误判、两个漏导入的名字。此后为「在侧栏选中导入的预设」又跑了六轮，没有一次选中。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
