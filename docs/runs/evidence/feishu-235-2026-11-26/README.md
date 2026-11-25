# 飞书 #235 多盘导出：一个归档装两盘，不是两个文件

记录 `reczz28aa4fiZOda`（P1）要求工程含 2 个盘且均已切片时，点击「文件→导出→导出所有盘切片文件…」一次性导出。预期「每个盘各生成对应切片文件（共 2 个），均含有效 G-code」。

**结论：三句里两句成立，一句按字面不成立。** Snapmaker Orca 2.4.0 的一次性导出只落 **一个** 文件 `plates.gcode.3mf`，里面是 `Metadata/plate_1.gcode` 和 `Metadata/plate_2.gcode`，两份 G-code 都完整；磁盘上不是两个文件。两轮客机实跑（不同提交）结论逐项相同。判据按飞书原文逐字判，没有放宽；这一行只算部分覆盖，飞书状态保持空白。

| 运行 | 测试提交 | 客机 | 场景耗时 | 落盘 |
| --- | --- | --- | ---: | --- |
| [首轮收据](7179e65c-run1-receipt.json) | `7179e65c…` | RED | 104.212 秒 | `plates.gcode.3mf`，95,464 字节 |
| [第二轮收据](0d7222e7-run1-receipt.json) | `0d7222e7…` | RED | 104.407 秒 | `plates.gcode.3mf`，95,502 字节 |

两轮都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动。[构建摘要](build.json)

初态是用例现场搭的两盘工程：盘 `Keep` 上是立方体 Alpha，盘 `Remove` 上是缩放过的盒子 Bravo（由 `fixtures/feishu_std_cubesfar.3mf` 生成，[before.3mf](7179e65c-run1-before.3mf)）。动作：在 Slice 下拉里选 `Slice all` 并按一次主按钮，等 File→Export 的 `Export all plate sliced file` 行启用（5.3 秒），再走 File→Export→这一行，保存框里输入不带扩展名的 `plates`，应用落盘为 `plates.gcode.3mf`。

| 飞书预期 | 读数 | 结论 |
| --- | --- | --- |
| 每个盘各生成对应切片文件 | 归档里每盘各有一份切片数据：`plate_1.gcode` 240,928 字节、100 层，对应 `Keep` 的 Alpha；`plate_2.gcode` 158,494 字节、60 层，对应 `Remove` 的 Bravo | PASS |
| 共 2 个 | 磁盘上 1 个文件 | FAIL（按字面） |
| 均含有效 G-code | 两份都有完整的起始与结束段、层号连续、MD5 记录一致；G-code 的挤出范围都落在该盘对象上（超出量 0.0 mm） | PASS |

归档成员与预览图在 [plates.gcode.3mf](7179e65c-run1-plates.gcode.3mf)；逐项读数在 [analysis.json](7179e65c-run1-analysis.json) 的 `all_plates`。

**给测试同事定口径。** 产品把多盘切片装进一个 `.gcode.3mf`（每盘一份 G-code 和预览图），和飞书写的「共 2 个」不同。要么把预期改成「一个归档，内含每个盘的切片」，要么这是产品需要改的地方。用例作者按 tag `sm-v2.4.0` 读到的是单次保存框、单一路径、盘序号传 `PLATE_ALL_IDX`（`Plater.cpp:20379-20444`）。

```powershell
& runner/hv_go.ps1 -Cases m7x_235_export_all_plates -NoSync
```

计时：用例内每轮约 84 秒（打开两盘工程 13.7、Slice all 9.9、导出 12.3）。领取到跑通整条流程约 55 分钟，其间一次失败轮：`Slice all` 那一行的点击被弹层上面的窗口吞了，改成以弹层自身为根再点后通过。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
