# 飞书 #232 导入配置：三个预设进了各自的列表，选中后有效参数与导出件一致

记录 `reczz28aa4fiZjOA`（P1）要求准备一个导出的 `.ini` 配置文件（含 1 打印机 + 1 耗材 + 1 工艺），点击「文件→导入→导入配置…」选择该文件，导入后到对应预设下拉列表核对。预期「导入成功，3 个预设出现在对应列表且参数正确；同名重复时按产品既有策略提示（覆盖/重命名）」。

**结论：两句都成立，前提是配置文件用 zip 而不是 `.ini`。** 装着三份预设的 zip 导入后，三个预设都出现在各自的下拉列表里，在侧栏逐个选中之后另存的工程里，导出件带的参数没有一个与有效配置不同；再导一次时产品弹出三个覆盖提示。飞书的前置条件写的是 `.ini`，2.4.0 的「导入配置」对它报 0 个，所以这一行按「前置条件需改口径」交付。

| 运行 | 测试提交 | 客机 | 场景耗时 | 离线复核 |
| --- | --- | --- | ---: | --- |
| [首轮收据](1b2d99dd-run1-receipt.json) | `1b2d99dd…` | GREEN | 123.560 秒 | 通过（25 项） |
| [第二轮收据](1b2d99dd-run2-receipt.json) | `1b2d99dd…` | GREEN | 123.837 秒 | 通过（25 项） |

两个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和工作目录，打开 `fixtures/agent_layer_cube.3mf`（U1 0.8 mm）。[构建摘要](build.json)。进入默认回归（提交 `c5ec2ec…`）之后在同一提交上又跑了一次，收据见[金丝雀回归](../elevenhour-canary-2026-11-26/README.md)。更早的会话留在这个目录里（`2c32e51c…`、`641f1a6c…` ×2、`3f55a59a…`、`8d5a5533…` ×2），都是选不中预设的版本。

**配置文件是怎么来的。** 飞书前置条件写的是 `.ini`。2.4.0 的「导入配置」文件框放行 `.ini`，随后报 `Import result`：`There are 0 configs imported. (Only non-system and compatible configs) Hint: Make sure you have added the corresponding printer before importing the configs.`（[截图](1b2d99dd-run1-ini-dialog-1.png)）。所以用例现场改用产品认的容器：从模板的三个系统预设把继承链合并成独立预设，改名为 `BB Test Printer` / `BB Test Filament` / `BB Test Process`；耗材、工艺两份把 `compatible_printers` 写成空列表、条件写成空串，使它们与所有打印机兼容。三份 JSON 平铺在工作目录，另打成 zip。这一段每轮都留作读数，不参与判定。

用例里发生的事（[日志](1b2d99dd-run1-case.log)、[analysis](1b2d99dd-run1-analysis.json)），两轮相同：

1. File→Import→`Import Configs...`：`.ini` 报 0 个；zip 报 `There are 3 configs imported. (Only non-system and compatible configs)`，配置目录多出 `filament/BB Test Filament`、`machine/BB Test Printer`、`process/BB Test Process`。
2. 三个下拉列表都列出了导入的预设：打印机列表 `------ User presets ------` 下是 `BB Test Printer`，耗材列表 `------ User presets ------` 下是 `BB Test Filament`，工艺列表 `------ User presets ------` 下是 `~ BB Test Process`（换到导入的打印机之后它已经是当前预设）。
3. 逐个选中。打印机行、第一耗材行各点一次（消息点击）就换成导入的预设；工艺行此时已写着 `BB Test Process`，再点一次确认。没有弹出别的对话框。
4. 另存 `after-import.3mf`：`printer_settings_id` 是 `BB Test Printer`，`print_settings_id` 是 `BB Test Process`，`filament_settings_id` 的第一项是 `BB Test Filament`。
5. 第二次导入同一个 zip：连弹三个 `Overwrite config`——`A config exists with the same name: BB Test Printer. Do you want to overwrite it?`（另有 Filament、Process 两个），按钮 `Yes` / `No` / `Yes to All` / `No to All`。逐个答 Yes，最后 `There are 3 configs imported`。

| 飞书预期 | 读数 | 结论 |
| --- | --- | --- |
| 导入成功，3 个预设出现在对应列表且参数正确 | 导入 3 个；三个列表都列出；三个都被选中；导出件带的参数与有效配置逐键比过，耗材 62 键、打印机 79 键、工艺 113 键，没有一处不同；三份落盘的预设文件与导出件也没有一处不同 | PASS |
| 同名重复时按产品既有策略提示（覆盖/重命名） | 三个 `Overwrite config` 提示，Yes / No / Yes to All / No to All | PASS |

只在导出件里有、这个构建的有效配置和预设文件不带的键（耗材 50 个、打印机 2 个、工艺 6 个，如 `bed_model`、`description`）不参与比较，清单在 analysis 的 `inert_keys` 和离线复核的 `not_carried` 里。

**离线复核。** `tools/replay_case_evidence.py` 用另一个读取器把上面几句重算一遍：三份预设文件、三次配置目录快照、另存的工程、配置 zip（现场从仓库的系统预设重建一份，逐键相同）、应用弹过的对话框、三个下拉列表的读数、与收据哈希绑定的 case.log，共 25 项，两轮都通过。

```powershell
& runner/hv_go.ps1 -Cases m7x_232_import_configs -NoSync
python tools/replay_case_evidence.py docs/runs/evidence/feishu-232-2026-11-26/1b2d99dd-run1-receipt.json docs/runs/evidence/feishu-232-2026-11-26/1b2d99dd-run2-receipt.json
```

**为什么前面二十次会话都选不中。** 这不是产品的限制。客机交互桌面上有一层铺满整屏的置顶窗口（`Windows Security` 防火墙提示的遮罩），用例点下拉列表里的行时按屏幕点找目标窗口，找到的是那层遮罩；真实鼠标点击也被它挡住。06:21 关掉它之后，07:53 的会话里耗材行第一次一点就中，随后的截图上工艺行也写着 `BB Test Process`。此后改了用例的三处：工艺行按控件读，而不是按旧文字再找一次（`17be49c`）；下拉列表里带键盘焦点框的那一行默认的 OCR 读不到，一页只剩分隔行时把图反相再读一遍（`17be49c`）；换到导入的打印机这一步是用例最初的写法，因为当时点不中才被拿掉，现在恢复（`3c0c606`、`1b2d99d`）。早先写在记录里的「打印机预设在侧栏选不中」和「导入的预设在列表里却选不中」都作废。

**给测试同事。** 前置条件里的 `.ini` 在 2.4.0 上导不进任何预设，请改成 zip（或 `.orca_printer` 等单个预设文件）。

计时：用例内 ini 观察 8.7、第一次导入 9.8、读列表并选中 17.2、第二次导入 10.7 秒。领取到首次客机通过（提交 `17be49c`，08:04，那一版还没有换打印机）约 9 小时 05 分，带打印机切换的版本在 08:14 通过（`1b2d99d`）；其间先有 15 次会话失败（最后六次停在选不中，之前是导出、文件框和漏导入的名字），关掉遮罩之后又有一次停在两处读数错误上，恢复换打印机之后两次停在读控件的错误上。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例在默认回归里。
