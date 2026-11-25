# 飞书 #229 导入多实体 STEP：三个实体成了三个零件，颜色没有保留（RED）

记录 `reczz28aa4fiWpbZ`（P1）要求准备含 3 个实体、各实体不同颜色的装配体 assembly.step，通过「文件→导入」导入，观察对象列表与盘上零件数量/颜色。预期「3 个实体均被导入，对象列表可见对应零件（或拆分为多对象），颜色保留，无缺件」。

**结论：四句里三句成立，「颜色保留」不成立。** 勾上导入参数框里的 `Split compound and compsolid into multiple objects` 之后，三个立方体作为同一个对象 `assembly.step` 的三个零件进来，对象列表里一行是对象、下面三行是 `assembly-SOLID-1/2/3`，各 12 个三角面；但 STEP 里的红、绿、蓝全丢了——三个零件都在耗材 1，没有一面带涂色，盘上是三个红色方块。这个勾选框默认不勾，不勾时三个立方体并成一个 36 个三角面的零件，前两句也不成立。预期不成立，飞书状态保持空白。

| 运行 | 测试提交 | 客机 | 场景耗时 | 读数 |
| --- | --- | --- | ---: | --- |
| [对照：不碰勾选框](253195c7-run1-receipt.json) | `253195c7…` | RED | 109.913 秒 | 1 个对象 1 个零件，36 个三角面，四句全红 |
| [首轮](1387bc8c-run1-receipt.json) | `1387bc8c…` | RED（只有「颜色保留」） | 110.034 秒 | 其余三句 PASS |
| [第二轮](1387bc8c-run2-receipt.json) | `1387bc8c…` | RED（只有「颜色保留」） | 109.233 秒 | 与首轮逐项相同 |

三个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和工作目录，打开 `fixtures/agent_layer_redblue.3mf`（U1 0.8 mm，耗材 1 红、耗材 2 蓝）。[构建摘要](build.json)。fa706g3 上同一条用例、同一提交跑了一次 SHADOW（[收尾记录](fa-1387bc8c-62d7a8-done.json)，用例内 88.192 秒），四个分句与客机相同，[对象列表截图](fa-1387bc8c-62d7a8-object-list.png)也相同。

**夹具。** `fixtures/assembly.step` 由 `tools/make_assembly_step.py` 生成并逐项自检：三个 10 mm 的立方体沿 x 并排、间隔 10 mm，底面在 z = 0，三个实体 `cube_red` / `cube_green` / `cube_blue` 各带一种 `COLOUR_RGB`（纯红、纯绿、纯蓝）。每轮开始时把它的字节数和 SHA-256 记进读数。

用例里发生的事（[日志](1387bc8c-run1-case.log)、[analysis](1387bc8c-run1-analysis.json)）：

1. File→Import→`Import 3MF/STL/STEP/SVG/OBJ/AMF...`，在标题 `Choose one or more files (3mf/step/stl/svg/obj/amf):` 的文件框里选 `assembly.step`。
2. 产品弹 `Step file import parameters`（[截图](1387bc8c-run1-import-dialog-0.png)）：Linear Deflection 0.003、Angle Deflection 0.50、`Split compound and compsolid into multiple objects`（默认不勾）、Number of triangular facets: 36。
3. 勾选框。给控件发 `BM_CLICK` 就勾上了（[截图](1387bc8c-run1-import-dialog-ticked.png)），但 `BM_GETCHECK` 前后都是 0——这个框是自绘的，用例读方框里 13×13 个像素（有勾时墨量 0.99，没勾时 0）。勾前勾后三个读数不变：0.003 / 0.50 / 36。
4. OK → 等盘上有模型且没有对话框 → 另存 `imported.3mf` → 切到侧栏 Objects 页读对象列表（[截图](1387bc8c-run1-object-list.png)）。

另存工程里的读数，两轮相同：

| 零件 | 三角面 | 包围盒 x（mm） | 包围盒体积 | 耗材 | 没有涂色的面 |
| --- | ---: | --- | ---: | ---: | ---: |
| assembly-SOLID-1 | 12 | 110.5–120.5 | 1000 mm³ | 1 | 12 |
| assembly-SOLID-2 | 12 | 130.5–140.5 | 1000 mm³ | 1 | 12 |
| assembly-SOLID-3 | 12 | 150.5–160.5 | 1000 mm³ | 1 | 12 |

三个零件 y、z 范围相同，间隔 10 mm，都在 z = 0 上。三角形的属性只有 `v1`、`v2`、`v3`，没有涂色；三个零件的 extruder 都是 1，工程里耗材 1 是红色 `#FF0000`。应用自己的信息栏写：Object name: assembly.step，Size: 50 x 10 x 10 mm，Volume: 3000 mm³，Triangles: 36。

| 飞书预期 | 读数 | 结论 |
| --- | --- | --- |
| 3 个实体均被导入 | 三个零件，各 12 个三角面、1000 mm³，并排 | PASS |
| 对象列表可见对应零件（或拆分为多对象） | 对象列表：`assembly.step` 一行，其下 `assembly-SOLID-1/2/3` 三行 | PASS |
| 颜色保留 | 三个零件都在耗材 1（红），没有一面带涂色 | FAIL |
| 无缺件 | 三个零件各 12 个三角面，共 36 | PASS |

**离线重算。** `tools/replay_case_evidence.py` 对这一条没有回放入口。另存的工程和读词的位置都在收割件里，用 `tests/step_import_oracle.py` 的 `step_import_readings` 对两轮分别重算，四句都与记录逐字相同；对照那一轮四句也都是 FAIL（它的记录还是改判据之前的文字，所以说明文字不逐字相同）。

**前四轮差在哪**（收割件在总控的宿主目录，不在仓库里）。对照轮（05:36）没有碰勾选框。第二次（`21fa17bd…` 05:55）点了一下，`BM_GETCHECK` 读到 0，用例按「没勾上」停下。第三次（`24eef7a6…` 06:13）依次试了 `BM_CLICK`、置前后的真实点击、`BM_SETCHECK` + `BN_CLICKED`，读数都是 0 → 0，其中真实点击那一步没有做成——另有一个窗口盖住了勾选框。第四次（`55e44162…` 06:28）改读像素，才知道 `BM_CLICK` 第一回就勾上了，四个分句第一次全部读到；「对象列表」一句却判了 FAIL：名字就在列表上，判据借用的 #227 帮手会把同一行的邻词拼起来，行首图标被 OCR 读成的 `y` 加上 `assembly.step` 被算成名字出现了两次。`1387bc8c…` 改成只认整词，并把读词用的截图和每个词的位置留下。

**命令行对照（不参与判定）。** 产品的命令行在客机上把 STL 转储崩掉（`0xC0000005`），对 STEP 直接拒绝：`Input file must have .stl, .obj, .amf(.xml) extension`（[日志](8d5a5533-stepcli-case.log)）。装配体的读数只能从 GUI 另存的工程里取。

**给测试同事。** 三件事请定口径：前置条件「各实体不同颜色」在 2.4.0 上保不住，STEP 的颜色不进工程，值得单独提给产品；测试步骤没有说要不要勾「拆分为多对象」，默认不勾时三个实体并成一个零件，飞书原文里「或拆分为多对象」指的是哪一种需要写明；勾选框的状态只能从画面读。

```powershell
& runner/hv_go.ps1 -Cases m7x_229_import_step -NoSync
```

计时：领取的准确时刻没有留档，按未测计；夹具的第一次提交在 04:58，第一次读全四个分句在 06:28（约 1 小时 30 分），之后改判据两处、13 分钟后在最终提交上过了两轮。用例内：空盘 12.0、导入框 12.4、观察载入 6.4、另存并读列表 11.7 秒。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
