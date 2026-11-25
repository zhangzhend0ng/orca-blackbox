# 飞书 #234 导出当前盘切片文件

记录 `reczz28aa4fiZOgT`（P0）要求当前盘已切片时，点击「文件→导出→导出当前盘切片文件…」（或 Ctrl+G）选路径保存，检查扩展名与文件内容。预期「生成 .gcode.3mf 文件，内含 G-code 与预览信息，文件大小随切片复杂度合理增大」。

Snapmaker Orca 2.4.0，U1 0.4 mm、Generic PLA、0.20 mm Standard（`fixtures/feishu_std_cube.3mf`、`fixtures/feishu_std_sphere.3mf`）。[构建摘要](build.json)

| 候选提交 | 会话 | 客机 | 场景耗时 | 离线复核 |
| --- | --- | --- | ---: | --- |
| `48e3aa7d…` | [首轮收据](48e3aa7d-run1-receipt.json) | GREEN | 190.995 秒 | 通过（97 项） |
| `48e3aa7d…` | [第二轮收据](48e3aa7d-run2-receipt.json) | GREEN | 191.465 秒 | 通过（97 项） |

两个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动。每个会话依次导出两份：先导出标准立方体（简单），再导出标准球体（复杂），用两者比文件大小。

| 飞书预期 | 读数 |
| --- | --- |
| 生成 .gcode.3mf 文件 | 保存框标题 `Save Sliced file as:`，输入不带扩展名的 `plate`、`sphere`，应用落盘为 [plate.gcode.3mf](48e3aa7d-run1-plate.gcode.3mf)、[sphere.gcode.3mf](48e3aa7d-run1-sphere.gcode.3mf) |
| 内含 G-code 与预览信息 | 归档里有 `Metadata/plate_1.gcode` 和它的 MD5 记录 `Metadata/plate_1.gcode.md5`，预览图 `Metadata/plate_1.png`、`plate_1_small.png`、`plate_no_light_1.png`、`top_1.png`、`pick_1.png`，另有 `project_settings.config`、`slice_info.config` 等配置 |
| 文件大小随切片复杂度合理增大 | 立方体 64,546 字节（G-code 353,856 字节、135 层、6,122 段挤出）；球体 238,801 字节（G-code 755,965 字节、100 层、20,394 段挤出），归档约为立方体的 3.7 倍 |

第二轮：立方体 64,532 字节（G-code 350,616），球体 238,816 字节（G-code 757,765）。逐项读数在 [analysis.json](48e3aa7d-run1-analysis.json)。

两个会话切球体时都弹出了 `Memory Usage Warning`（01:37:22、01:40:42），用例以对话框自身为根窗口点 `Yes, Continue` 后切片继续（[截图](48e3aa7d-run1-memory-guard-0.png)）。切片完成的信号是 File→Export 的 `Export G-code` 行启用，不是按钮的完成态。

离线复核用 `tools/replay_case_evidence.py`：先核对清单里的字节数与 SHA-256，再只从归档文件重判，并做 17 个反例，每个收据启动一个独立进程，各约 14.5 秒。正读数里，归档的配置要等于切片时另存的工程、`slice_info` 要和 G-code 的层数与对象一致、挤出范围要落在对象上（超出量 0.0 mm）。反例包括归档名下放纯 G-code、没有 G-code、没有预览图、空白预览、留下旧校验、删一层并改写校验、把打印整体移出对象等。

```powershell
& runner/hv_go.ps1 -Cases m7x_234_export_plate_slice -NoSync
python tools/replay_case_evidence.py docs/runs/evidence/feishu-234-2026-11-26/48e3aa7d-run1-receipt.json docs/runs/evidence/feishu-234-2026-11-26/48e3aa7d-run2-receipt.json
```

计时：用例内每轮约 71 秒（打开工程 9.2、切片 13.2、导出 12.4；球体 9.0、15.2、12.0），宿主派发到收割 172 秒。领取到首次客机通过（提交 `81dbcf14`，00:55:28）约 2 小时 56 分，首次实跑即通过，没有失败轮。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。

实体机 fa706g3 的一次 SHADOW：`48e3aa7`（160.4 秒），三个分句都通过；立方体 64,745 字节、球体 221,705 字节，没有弹出内存护栏。前两次 SHADOW 因为显示器休眠而是 RED，唤醒显示后重跑通过，只计 SHADOW。
