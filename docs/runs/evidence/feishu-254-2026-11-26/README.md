# 飞书 #254 层高组合：临时 G-code 的原因已定位，改完成信号后两段切片都完整

记录 `reczz28b6mRB1GVG`（P0）要求固定 U1 0.4 mm、PLA、0.20 mm 标准工艺，添加标准球，先按默认参数做基准切片，再应用 `layer_height = 0.20`、`initial_layer_print_height = 0.25` 重新切片，对照基准检查配置、预览和 G-code。预期「组合参数写入正确，切片成功并产出 G-code；首层 Z = 0.25 mm，第 2 层起按 0.20 mm 递增；层数、总高度和后续层 Z 步进与默认基准一致」。

**结论：上一轮「切片按钮已亮、盘目标 G-code 只留临时文件」的原因是运行期内存护栏暂停了切片，而按钮的完成态是假信号。** 用例改成等 File→Export 的 `Export G-code` 行启用、并应答护栏之后，在占着 1500 MB 内存的客机上，基准和目标两段切片都完整结束，两份 G-code 的可执行行逐行相同。用例自己的总判仍是 FAIL，红在预览截图的时机上，与 G-code 无关。这一轮只是探针：不进默认回归，飞书状态保持原样。

| 运行 | 测试提交 | 客机 | 场景耗时 | 结果 |
| --- | --- | --- | ---: | --- |
| [收据](847aa160-run1-receipt.json) | `847aa160…` | RED（总判） | 279.978 秒 | 基准切片 PASS，目标切片 PASS |

在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，切片期间另有进程占着 1500 MB 内存。[构建摘要](build.json)

| 读数 | 基准 | 目标 |
| --- | --- | --- |
| 点 Slice 后 `Export G-code` 行启用 | 5.0 秒 | 7.4 秒 |
| `Memory Usage Warning` | 没有 | 03:49:03 弹出，以对话框为根点 `Yes, Continue` 后继续（[截图](847aa160-run1-memory-guard-0.png)） |
| 层数 | 100 | 100 |
| 首层 Z、末层 Z、层间步进 | 0.25、20.05、0.2 mm | 相同 |
| 可执行行 | [baseline.gcode](847aa160-run1-baseline.gcode)，23,933 行 | [target.gcode](847aa160-run1-target.gcode)，与基准逐行相同 |
| 配置块 | 570 个键 | 只有 `filament_ids` 不同（身份键，不是打印参数） |

预期里的三句在 G-code 上都成立：配置块里 `layer_height = 0.2`、`initial_layer_print_height = 0.25`；两份 G-code 都完整（各有起止段和 100 个 `;LAYER_CHANGE`）；首层 Z = 0.25，之后每层 +0.2，层数与总高度和基准一致。

**总判为什么还是红。** 用例的第 4 步要对照预览，它比的是两张截图里彩色路径的重叠：`colored_preview_overlap` 只有 67.7%。两张截图（[基准](847aa160-run1-baseline-preview.png)、[目标](847aa160-run1-target-preview.png)）的取景相同，差别在目标的球体还是半透明、右下角压着一条 `Slice complete` 提示——截图早于预览渲染完成。这是用例的截图时机问题。下一轮要么等画面连续两次相同再截，要么改比切片工程里的 `Metadata/plate_1.png`。

上一轮的记录见 [#254 客机计时](../multi-244-254-2026-11-25/README.md)和[#254 临时文件](../win11-254-2026-11-25/README.md)。

```powershell
& runner/hv_go.ps1 -Cases m7x_254_sphere_layer_pair -NoSync
```

计时：用例内基准段 77.1 秒、目标段 82.3 秒，宿主派发到收割约 290 秒。用例过程中没有人工桌面输入。
