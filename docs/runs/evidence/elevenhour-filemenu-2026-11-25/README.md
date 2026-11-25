# File 菜单普查与切片导出探针（win11-test，2026‑11‑25 夜）

在 Hyper-V 客机 `win11-test` 的 `test` 交互会话里对 Snapmaker Orca 2.4.0 做了三次只读菜单普查、三次切片导出探针，每次是独立 Orca 进程和新配置目录。产品二进制 SHA‑256 `5c48644d…fc47bf`（[构建摘要](build.json)）。普查和探针都是诊断记录，不是用例判定，也不对应飞书行；它们是 #227、#230–#238 的写法依据。

## File → Import / Export 的真实行

| 子菜单 | 行（en_US 原文） | 切片前 | 对话框 |
| --- | --- | --- | --- |
| Import | `Import 3MF/STL/STEP/SVG/OBJ/AMF...`（Ctrl+I） | 可用 | 标题 `Choose one or more files (3mf/step/stl/svg/obj/amf):`；类型下拉只有一条 `Supported files (*.3mf, *.stl, *.oltp, *.stp, *.step, *.svg, *.amf, *.obj)`（[截图](a0efc09-census2-import-stl-dialog.png)） |
| Import | `Import Zip Archive...` | 可用 | 标题 `Choose ZIP file:`，类型 `ZIP files (*.zip)`；选文件后弹自绘的 `Archive preview`（见下） |
| Import | `Import Configs...` | 可用 | 标题 `Select profile to load:`，类型 `Config files (*.json;*.zip;*.orca_printer;*.orca_filament)` |
| Export | `Export all objects as one STL...` | 可用 | 标题 `Export STL file:`，类型 `STL files (*.stl)`，默认名 `feishu_std_cube`（不带扩展名） |
| Export | `Export all objects as STLs...` | 可用 | 文件夹选择框 `Choose a directory` |
| Export | `Export Generic 3MF...` | 可用 | 标题 `Save file as`，类型 `3MF files (*.3mf)` |
| Export | `Export plate sliced file...`（Ctrl+G） | **置灰** | 切片后可用：标题 `Save Sliced file as:`，类型 `Gcode 3MF files (*.gcode.3mf)`，默认名 `立方体_PLA_21m22s.gcode`（[截图](3270a35-census1-sliced-file-dialog.png)） |
| Export | `Export all plate sliced file...` | **置灰** | 切片后可用，对话框同上 |
| Export | `Export G-code...` | **置灰** | 切片后可用：标题 `Save G-code file as:`，类型 `G-code files (*.gcode)`，默认名 `立方体_PLA_21m22s` |
| Export | `Export Preset Bundle...` | 可用 | 自绘对话框（五种导出类型单选 + OK/Cancel）；IDCANCEL 关不掉，WM_CLOSE 能关 |

类型下拉的文本不是子窗口文本，要用 CB_GETCOUNT / CB_GETLBTEXT 读类名 `ComboBox` 的子控件。原生文件框用 `WM_COMMAND` IDCANCEL 关闭，应用存活。三次普查：[第一次](3270a35-census1-analysis.json) · [第二次](a0efc09-census2-analysis.json) · [第三次](a4ce4a2-census3-analysis.json)。

`Archive preview`（#231「导入 ZIP 压缩包」要过的一步）：顶层窗口类 `#32770`、标题 `Archive preview`；里面是 `wxDataView` 列表（表头 `filename` 带复选框，三行 `cube_10mm.stl` / `cube_20mm.stl` / `cube_30mm.stl` 只能从截图读），按钮 `All`、`None`、`Open`、`Cancel` 都是 `wxWindowNR`（[截图](a4ce4a2-census3-archive-preview.png)）。用 WM_CLOSE 关闭后没有导入任何对象、无残留窗口。

## 导出落盘的文件

在文件名框先输入本轮工作目录并确认（对话框留在打开状态并进入该目录），再输入不带扩展名的名字（[探针 1](b958af2-probe1-analysis.json)）：

| 菜单项 | 输入的名字 | 落盘文件 | 字节 | 内容 |
| --- | --- | --- | ---: | --- |
| `Export G-code...` | `plate-gcode` | `plate-gcode.gcode` | 353,856 | 纯文本 G-code，135 层 |
| `Export plate sliced file...` | `plate-sliced` | `plate-sliced.gcode.3mf` | 64,548 | ZIP：`Metadata/plate_1.gcode`（353,856 字节）、五张预览图、`plate_1.gcode.md5`、`slice_info.config`、各配置 |

样本：[plate-gcode.gcode](b958af2-probe1-plate-gcode.gcode) · [plate-sliced.gcode.3mf](b958af2-probe1-plate-sliced.gcode.3mf)。U1（klipper 口味）的 G-code 里层标记是 `;LAYER_CHANGE` + `;Z:` + `;HEIGHT:`，每层有一条 `SET_PRINT_STATS_INFO TOTAL_LAYER=135 CURRENT_LAYER=n`（n 从 1 连续到 135）；头部有 `; total layer number: 135`，尾部有 `PRINT_END`、`; total layers count = 135` 和 `; CONFIG_BLOCK_START … END`。没有 `;LAYER_COUNT:` / `;LAYER:n`。

## 运行时内存护栏

客机只有 4.6 GB 动态内存（空闲约 1.9 GB）。被测构建带运行时内存护栏（上游 `src/libslic3r/PrintBase.hpp` 的 `check_memory_guard`，引入于 2026‑08‑05 的 a3a2ffb397）：切片中可用物理内存低于 512 MB 并持续两次采样，就在切片线程里弹模态框 `Memory Usage Warning`，按钮 `Yes, Continue` / `No, Stop`（[截图](f5572f6-hog1-memory-guard.png)）。

| 运行 | 触发方式 | 结果 |
| --- | --- | --- |
| [普查 2](a0efc09-census2-analysis.json) | 无（自然发生） | 点 Slice 后对话框挂着；`m2_slice_chain.wait_slicing_done` 返回 True、score≈1.0，但三个切片导出行一直置灰 |
| [探针 2](f5572f6-hog1-analysis.json)（RED） | 1500 MB 辅助进程占住内存 | 点 Slice 后 3.7 秒弹出；`msg_click_screen(cx, cy)`（不带根窗口）点了 10 次都没关掉，150 秒内导出行未启用 |
| [探针 3](e3ce6f8-hog2-analysis.json)（通过） | 同上 | 点 Slice 后 3.7 秒弹出；`msg_click_screen(cx, cy, dlg_hwnd)`（以对话框为根窗口）一次关掉；第 11.3 秒导出行启用，两份导出件落盘，应用存活 |

由此得到两条约束，已通知各用例作者：切片完成的信号是「File → Export 的对应行已启用」，不是按钮模板（置灰的按钮在切片期间就一直匹配完成态模板）；护栏对话框出现时记为环境观察，按文本定位 `Yes, Continue` 并以对话框为根窗口点击，确认关闭，连续两次关不掉就停。#254「完成按钮已亮、只留下 `.gcode.tmp`」与这条机制一致，是否就是它的原因另由判据侧的探针确认。

## 复现

从仓库根目录，用提权 PowerShell（或经 relay 以子进程方式调用 `obj_run.ps1`）：

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases diag_file_menu_census -NoSync          # 菜单与对话框
& .\runner\hv_go.ps1 -Cases diag_slice_export_probe -NoSync         # 切片 + 两种导出
```

工作目录由日志打印，位于客机 `artifacts/feishu-object-cases/census/run-*` 与 `.../sliceprobe/run-*`。每次 95–245 秒。人工介入：无。
