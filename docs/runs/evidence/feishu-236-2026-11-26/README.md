# 飞书 #236 导出纯 G-code

记录 `reczz28aa4fiali6`（P0）要求当前盘已切片后，点击「文件→导出→导出 G-code…」导出，检查扩展名与文件头尾。预期「生成 .gcode 文件，含起始/结束 G-code，无空文件，层命令连续」。

Snapmaker Orca 2.4.0，U1 0.4 mm、Generic PLA、0.20 mm Standard（`fixtures/feishu_std_cube.3mf`）。[构建摘要](build.json)

| 候选提交 | 会话 | 客机 | 场景耗时 | 离线复核 |
| --- | --- | --- | ---: | --- |
| `48e3aa7d…`（现行） | [首轮收据](48e3aa7d-run1-receipt.json) | GREEN | 111.888 秒 | 通过（38 项） |
| `48e3aa7d…` | [第二轮收据](48e3aa7d-run2-receipt.json) | GREEN | 111.389 秒 | 通过（38 项） |
| `81dbcf14…`（上一版） | [首轮收据](81dbcf14-run1-receipt.json) | GREEN | 110.605 秒 | 通过（38 项） |
| `81dbcf14…` | [第二轮收据](81dbcf14-run2-receipt.json) | GREEN | 110.628 秒 | 通过（38 项） |

四个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和同一夹具。两个候选提交之间，这条用例多了一项 GUI 内判据：G-code 的挤出范围要落在另存工程的对象包围盒内（超出不超过 1.0 mm）。所以在新提交上重新跑了两个会话，两次的超出量都是 0.0 mm；旧提交的两个会话保留作对照。

| 飞书预期 | 读数 |
| --- | --- |
| 生成 .gcode 文件 | 保存框里输入不带扩展名的 `plate`，应用落盘为 `plate.gcode`，类型下拉为 `G-code files (*.gcode)` |
| 含起始/结束 G-code | 起始：`PRINT_START`、`M140 S65`、`M104 T0 S140`、`G28 X Y` 等；结束：`PRINT_END`、`M106 S0`、`M73 P100 R0`。U1 的结束段不直接关加热，那在打印机的 `PRINT_END` 宏里 |
| 无空文件 | 每份 13,558 行、135 层；353,856 字节（`81dbcf14` 的首轮多 1,620 字节，来自一行更长的对象 id 注释） |
| 层命令连续 | 135 个 `;LAYER_CHANGE`；`CURRENT_LAYER` 从 1 连续到 135；头部 `; total layer number: 135`、尾部 `; total layers count = 135`、`TOTAL_LAYER=135` 三处一致；Z 从 0.25 到 27.05 mm 单调不减 |

四份导出件的 10,256 行运动指令逐行相同，只有生成时间和对象 id 三行注释不同。切片以 File→Export 的 `Export G-code` 行启用为完成信号（点 Slice 后 8.5 / 8.6 秒），不用按钮的完成态模板：客机内存紧张时那个模板会在切片仍被「Memory Usage Warning」暂停时照样匹配，见[菜单普查记录](../elevenhour-filemenu-2026-11-25/README.md)。四个会话都没有出现该对话框。逐项读数在 [analysis.json](48e3aa7d-run1-analysis.json) 里。

离线复核用 `tools/replay_case_evidence.py`：先核对清单里的字节数与 SHA-256，再只从归档文件重判，并做 13 个反例，每个收据启动一个独立进程，各约 1.5 秒。反例包括空文件、只有文件头、删一层并改写全部声明层数、去掉结束段、整份 G-code 平移 3 mm、扩展名不是 .gcode、换成别的工程、清单不符、把 analysis 改成 PASS。

```powershell
& runner/hv_go.ps1 -Cases m7x_236_export_gcode -NoSync
python tools/replay_case_evidence.py docs/runs/evidence/feishu-236-2026-11-26/48e3aa7d-run1-receipt.json docs/runs/evidence/feishu-236-2026-11-26/48e3aa7d-run2-receipt.json
```

计时：用例内每轮约 91 秒（打开工程 13.7、切片 13.1、导出 15.0、读文件 0.1），宿主派发到收割 116–117 秒。领取到首次客机通过（提交 `07ac1bf`，00:10:59）约 55 分钟，首次实跑即通过，没有失败轮；加上挤出范围判据后在新提交上重跑两个会话，也没有失败轮。其间作者读了 315 份已有导出件来归纳判据，并采用了总控的菜单普查和导出探针事实。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。

实体机 fa706g3 的两次 SHADOW：`07ac1bf`（88.05 秒）、`81dbcf1`（88.07 秒），四个分句都通过，运动指令与客机相同，只计 SHADOW。
