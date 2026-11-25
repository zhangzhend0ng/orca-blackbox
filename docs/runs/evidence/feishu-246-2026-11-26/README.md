# 飞书 #246 修复模型：被测构建的对象菜单里没有这一项（RED）

记录 `reczz28aa4fiXai8`（P1）要求对含孔洞的模型右键点「修复模型」，预期「模型被修复（孔洞补齐）、可正常切片，或给出无法修复的明确提示」。

**结论：在 win11-test 的 Snapmaker Orca 2.4.0 上，开了洞的立方体的右键菜单里没有「Fix model」这一行，既没有修复动作，也没有任何提示。预期不成立。** 原因没有定位，见下。飞书状态保持空白。

| 运行 | 测试提交 | 客机 | 场景耗时 | 读到的结果 |
| --- | --- | --- | ---: | --- |
| [首轮收据](6bdf66b3-run1-receipt.json) | `6bdf66b3…` | RED | 119.748 秒 | 当时用例在菜单里找不到这一行后继续去切片，以「切片点击未生效」中断 |
| [第二轮收据](a2aafd3d-run1-receipt.json) | `a2aafd3d…` | RED | 107.667 秒 | 用例改成读清菜单就直接下结论：`the object menu has no "Fix model" row … 27 rows read; no repair was attempted and the model was not sliced` |

两轮都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动。[构建摘要](build.json)

用例先经 File→Import 导入一份少了第 5 个三角面的 20 mm 立方体 [cube_holed.stl](a2aafd3d-run1-cube_holed.stl)，另存为 [before.3mf](a2aafd3d-run1-before.3mf)：读回 11 个三角面、8 个顶点、3 条开放边，未闭合。然后在对象上右键，把菜单的全部行读下来，并留了桌面截图 [context-menu.png](a2aafd3d-run1-context-menu.png)。

对着开洞立方体读到的 27 行：`Clone`、`Simplify Model`、`Mesh boolean`（灰）、`Center`（灰）、`Drop`（灰）、`Split`（灰）、`Mirror`、`Delete`、`Add Part`、`Add Negative Part`、`Add Modifier`、`Add Support Blocker`、`Add Support Enforcer`、`Height Range Modifier`、`Printable`、`Edit Process Settings`、`Edit in Parameter Table`、`Reload from disk`、`Replace with STL`、`Export as one STL...`、`Convert from Inches`、`Convert from Meters`、`Change Filament`（另 3 行分隔线）。和完好的立方体读到的菜单相同。

**原因没有定位，有一个候选。** 用例作者按 tag `sm-v2.4.0` 读到：这一行由 `GUI_Factories.cpp:882` 的 `append_menu_item_fix_through_netfabb` 追加，条件是 `is_windows10()`；而 `Utils/FixModelByWin10.cpp:195` 的 `is_windows10()` 读的是注册表 `ProductName` 是否以 `Windows 10` 开头。这台客机是 Windows 11（内部版本 26200），注册表里的 `ProductName` 却是 `Windows 10 Pro`，按这段源码条件应当成立、这一行应当出现（至多是置灰）。它没有出现。候选原因是编译开关：`FixModelByWin10.hpp:15-27` 只在定义了 `HAS_WIN10SDK` 时才编译真函数，否则是恒返回假的桩；`CMakeLists.txt:319-324` 只在 Windows SDK 里有 `winrt/windows.graphics.printing3d.h` 时才定义它。若被测构建是后一种配置，注册表写什么都不会有这一行。构建日志本轮没有查，所以仍是候选。

给测试同事：这一行在当前 Windows 11 测试机上无法执行，需要确认它在哪种系统或构建上存在，或改用别的修复入口。

```powershell
& runner/hv_go.ps1 -Cases m7x_246_repair_model -NoSync
```

计时：第二轮用例内 79 秒（空盘准备 11.7、导入并读网格 10.2、另存 8.4、读菜单 1.3）。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
