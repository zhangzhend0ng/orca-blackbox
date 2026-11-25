# 飞书 #232 导入配置：三个预设导入了，下拉里只核对到打印机（部分覆盖）

记录 `reczz28aa4fiZjOA`（P1）要求准备一个导出的 `.ini` 配置文件（含 1 打印机 + 1 耗材 + 1 工艺），点击「文件→导入→导入配置…」选择该文件，导入后到对应预设下拉列表核对。预期「导入成功，3 个预设出现在对应列表且参数正确；同名重复时按产品既有策略提示（覆盖/重命名）」。

**结论：两句里一句成立。** 装着三份预设的 zip 能导入，同名重复时产品弹出覆盖提示；但三个预设只在打印机下拉里列出来，耗材和工艺下拉里没有，侧栏也切不到导入的打印机，参数正确性没有验证成。判据按飞书原文逐字判，这一行只算部分覆盖，飞书状态保持空白。

| 运行 | 测试提交 | 客机 | 场景耗时 | 读数 |
| --- | --- | --- | ---: | --- |
| [首轮收据](641f1a6c-run1-receipt.json) | `641f1a6c…` | RED（第一分句） | 115.313 秒 | 第二分句 PASS |
| [第二轮收据](641f1a6c-run2-receipt.json) | `641f1a6c…` | RED（第一分句） | 111.061 秒 | 与首轮逐项相同 |

两个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和工作目录，打开 `fixtures/agent_layer_cube.3mf`（U1 0.8 mm）。[构建摘要](build.json)

**配置文件是怎么来的。** 飞书前置条件写的是 `.ini`。2.4.0 的「导入配置」文件框放行 `.ini`，随后却报 `Import result`：`There are 0 configs imported. (Only non-system and compatible configs) Hint: Make sure you have added the corresponding printer before importing the configs.`（[截图](641f1a6c-run1-ini-dialog-1.png)）。源码里 `PresetBundle::import_presets` 只收单个预设的 JSON 或 zip 类容器里的成员。所以用例现场改用产品认的容器：从模板的三个系统预设（`Snapmaker U1 (0.8 nozzle)`、`Generic PETG @U1 0.8 nozzle`、`0.40 Standard @Snapmaker U1 (0.8 nozzle)`）把继承链合并成独立预设，改名为 `BB Test Printer` / `BB Test Filament` / `BB Test Process`，三份 JSON 平铺在工作目录，另打成 `bb_three.zip`（5,865 字节）。这一段每轮都留作读数，不参与判定。

用例里发生的事（[日志](641f1a6c-run1-case.log)、[analysis](641f1a6c-run1-analysis.json)）：

1. File→Import→`Import Configs...` 打开标题 `Select profile to load:` 的文件框，类型下拉是 `Config files (*.json;*.zip;*.orca_printer;*.orca_filament)`，没有 `.ini`。
2. 第一次导入 zip：`There are 3 configs imported. (Only non-system and compatible configs)`。配置目录多出三份文件：`filament/BB Test Filament`、`machine/BB Test Printer`、`process/BB Test Process`。
3. 读预设下拉。打印机弹层（[截图](641f1a6c-run1-machine-list.png)）是：`------ Project-inside presets ------`、`------ User presets ------`、`BB Test Printer`、`------ Select/Remove printers (system presets) ------`、`------ Create printer ------`——名字在。此时选中的仍是工程自带的打印机，耗材和工艺弹层里没有 `BB Test Filament`、`BB Test Process`；工艺弹层只有 `------ System presets ------` 和 `~ Default Setting`（[截图](641f1a6c-run1-selection-failed.png)）。
4. 用例要把打印机切到 `BB Test Printer` 再比有效值：先发消息点击那一行，再真实点击，预设行上的文字都没变（`ValueError: the printer preset could not be switched to BB Test Printer`）。这一步连续三轮没切过去，按纪律停下，不再重跑。
5. 第二次导入同一个 zip：连弹三个 `Overwrite config`——`A config exists with the same name: BB Test Printer. Do you want to overwrite it?`（另有 Filament、Process 两个），按钮 `Yes` / `No` / `Yes to All` / `No to All`（[截图](641f1a6c-run1-zip2-dialog-1.png)）。逐个答 Yes，最后 `There are 3 configs imported`。

| 飞书预期 | 读数 | 结论 |
| --- | --- | --- |
| 导入成功，3 个预设出现在对应列表且参数正确 | 导入成功（3 个）；打印机下拉列出；耗材、工艺下拉没有列出；参数没有比 | FAIL（按字面） |
| 同名重复时按产品既有策略提示（覆盖/重命名） | 三个 `Overwrite config` 提示，Yes / No / Yes to All / No to All | PASS |

**参数读到了什么（离线，不参与判定）。** 第五轮（提交 `fc163e85`，样本在 [dev-fc163e85](dev-fc163e85/)）把导入后的三份预设文件和导出的 JSON 逐键比过：规范化之后没有一处值不同——差异只有写法：工艺里 23 个速度/加速度键从 `"30"` 变成 `["30"]`，打印机起始/结束 G-code 里两个字符的 `\n` 变成真换行。只在导出件里有的键：耗材 52 个、工艺 8 个、打印机 4 个（如 `type`、`instantiation`、`bed_model`、`counter_coef_1`），这个构建的有效配置里没有它们。导入之后多出来的键：耗材 44 个、工艺 205 个、打印机 56 个。

**给测试同事。** 三件事请定口径：前置条件里的 `.ini` 在 2.4.0 上导不进任何预设，要不要改成 zip 或 `.orca_printer`；「出现在对应列表」是否要求在当前打印机下的耗材、工艺下拉里也能看到（导入的打印机预设是没有父预设的根预设，可能和工程自带的耗材、工艺不兼容）；导入之后当前工艺预设变成了 `Default Setting`（导入前是工程自带的 0.40 mm 标准），这是产品侧行为，是否合预期。

```powershell
& runner/hv_go.ps1 -Cases m7x_232_import_configs -NoSync
```

计时：用例内 ini 观察 8.8 秒、第一次导入 9.7 秒、读下拉并尝试切换 10.1 秒、第二次导入 10.6 秒，宿主派发到收割 123 秒。领取到第一次看到「3 个导入」（提交 `fc163e85`，03:07）约 4 小时 08 分，其间多轮失败，原因是：按类型导出预设时产品报 `add file fail`（后来改成离线生成配置文件）、造用户打印机预设时找不到按钮、文件框多出一个空下拉框被误判、两个漏导入的名字。此后为「在侧栏选中导入的预设」又跑了几轮，都没有切过去。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
