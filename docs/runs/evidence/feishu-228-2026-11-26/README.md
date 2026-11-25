# 飞书 #228 导入带 .mtl 材质的 OBJ：两种颜色只留下一种（RED）

记录 `reczz28aa4fiXZMM`（P1）要求准备 `model.obj` + `model.mtl` + 贴图（面片含红、蓝两种材质分区），通过文件对话框选中 `model.obj`，导入后观察配色，切片看颜色分区分料。预期「模型导入成功，两种颜色按面片正确显示；切片后按颜色生成对应耗材/换料」。

**结论：预期不成立。** 两种夹具形态在 Snapmaker Orca 2.4.0 上都没有保住两种颜色：材质只写 Kd 颜色时，产品弹 `Obj file Import color` 让用户映射耗材，点 OK 之后整件却只有一种颜色；材质引用贴图且 OBJ 带 UV 时，产品按纯几何导入，一个颜色也不上。飞书状态保持空白。

| 运行 | 测试提交 | 判定件形态 | 客机 | 场景耗时 | 读数 |
| --- | --- | --- | --- | ---: | --- |
| [首轮收据](2c32e51c-run1-receipt.json) | `2c32e51c…` | 引用贴图 + UV | RED | 273.838 秒 | 24 个面全部未着色，单色；对照件（只有 Kd）弹出了颜色框，用例当时没点掉 |
| [第二轮收据](9b3291cc-run1-receipt.json) | `9b3291cc…` | 只有 Kd | RED | 185.015 秒 | 红组与蓝组都按耗材 2 打印，单色 |
| [第三轮收据](a09a0662-run1-receipt.json) | `a09a0662…` | 只有 Kd | RED | 185.974 秒 | 与第二轮逐项相同；对照件的 G-code 也读到了 |

三轮都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和工作目录。模板是 `fixtures/agent_layer_redblue.3mf`（U1 0.8 mm，前两个耗材为红色和蓝色，由 `tools/make_agent_layer_redblue.py` 从 `agent_layer_cube.3mf` 生成）。[构建摘要](build.json)

**夹具。** 判定件 `model.obj` + `model.mtl`（522 与 89 字节，用例现场写；三个文件的字节数和 SHA-256 记在 analysis 里）：边长 20 mm 的立方体分成左右两个各 10×20×20 的盒体，左半 `usemtl red`（Kd 1 0 0），右半 `usemtl blue`（Kd 0 0 1），共 24 个面；`texture.png`（79 字节）放在同一目录，MTL 不引用它，OBJ 不带 `vt`。飞书前置条件只要求贴图文件存在，没有写 MTL 必须引用贴图。对照件 `model_tex.obj` + `model_tex.mtl` 是另一种读法：`map_Kd texture.png`，面带 UV。

**判定件上发生的事**（[日志](a09a0662-run1-case.log)、[analysis](a09a0662-run1-analysis.json)）：

1. File→Import 的 `Import 3MF/STL/STEP/SVG/OBJ/AMF...` 行交给它 `model.obj`，产品弹出 `Obj file Import color`（[截图](a09a0662-run1-import-dialog-0.png)）：`Specify number of colors: 2 (2 Recommended)`，两行映射 `R:1 G:2 B:255` → 耗材 2、`R:255 G:1 B:0` → 耗材 1，按钮 `OK` / `Cancel`。用例点了 OK，对话框关闭。
2. 另存的 [imported.3mf](a09a0662-run1-imported.3mf)：1 个对象、1 个部件，对象的 `extruder` 是 2；蓝组的 12 个面带 `paint_color="8"`（耗材 2），红组的 12 个面没有涂色。没有涂色的面跟着对象的耗材号，于是红组也是耗材 2。盘上看出来就是一整件蓝色（[截图](a09a0662-run1-imported.png)）。
3. 切片后导出的 [plate.gcode](a09a0662-run1-plate.gcode)：只有工具 1（第 2 个耗材）挤出，1,377 段挤出，0 次换工具；耗材用量 `0.00, 1655.94, 0.00, 0.00, 0.00` mm。

**对照件上发生的事**：没有任何对话框，24 个面全部未着色，对象的 `extruder` 是 1，切片后只有工具 0 挤出。

| 飞书预期 | 判定件读数 | 结论 |
| --- | --- | --- |
| 模型导入成功，两种颜色按面片正确显示 | 红组的有效耗材 2，蓝组 2，相同 | FAIL |
| 切片后按颜色生成对应耗材/换料 | 只有一个耗材挤出，0 次换工具 | FAIL |

**给测试同事。** 两条可以单独提的产品问题。其一：OBJ 颜色导入时，映射到耗材 1 的那组面没有写进面涂色，而对象的耗材号被设成了 2，结果整件按耗材 2 打印——对话框里明明显示红→1、蓝→2。其二：MTL 引用贴图且 OBJ 带 UV 时不上色、也不提示。另外请明确前置条件里 MTL 是否引用贴图：两种读法在 2.4.0 上都保不住两种颜色。

```powershell
& runner/hv_go.ps1 -Cases m7x_228_import_colored_obj -NoSync
```

计时：判定这一段用例内约 64 秒（空盘准备 11.6、文件框 12.4、等导入 3.3、另存 9.2、切片 13.1、导出 15.0），对照一段约 51 秒，宿主派发到收割约 191 秒。领取到首次走完全流程（提交 `9b3291cc`，03:53:03）约 4 小时 54 分，其间两轮失败：第一轮选错了模板（空盘准备要求 U1 0.8 mm 模板）；第二轮对照件的颜色框没有被点掉。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
