# Mac mini 实测：控制台整夜锁屏，只跑成三条命令行对照

**结论：Mac mini（Snapmaker Orca 2.4.2）这一夜没有跑成任何 GUI 动作。** 日常账号 `coil` 在 2026-11-25 23:33:40 锁了控制台，专用账号 `coilwin` 的后台 Aqua 会话读不到窗口，到 03:30 复查仍是锁屏。GUI 的 SHADOW（#236、#227）因此没有派发。平台线改跑了三条命令行对照，都判通过；它们不是 GUI 动作，只计 SHADOW。

预检见 [preflight-4-report.json](preflight-4-report.json)：辅助功能已授权，应用 `/Applications/Snapmaker Orca.app`，版本 2.4.2，可执行文件 SHA-256 `8e66373f2cdd53fad29c7b123f0c8a25f45c37c6132c161f6e7d6d6a89abbd75`；`gui_cases_runnable` 为 false，原因是 `console_locked` 为 `Yes`。

| 对照 | 命令行做了什么 | 判定 |
| --- | --- | --- |
| #227 | `cube_20mm.stl` → `--export-3mf`，profile 里选中模板预设 | [判据](cli-stl227-3-judge-stl227.json)：恰好 1 个对象 1 个实例、12 个三角面与源 STL 一致、三轴 20 mm、在盘上、`source_file` 指向本轮的 STL，全部 PASS |
| #236 | 标准立方体 → `--slice 1 --export-3mf`，得到 [plate.gcode.3mf](cli-gcode236-1-plate.gcode.3mf) | [判据](cli-gcode236-1-judge-gcode236.json)：135 层、层号连续、Z 单调不减、起止段齐全；与客机 2.4.0 的一份导出件相比，层标记、层数、层号、Z 范围、挤出段数、起止段相同，只有生成时间和配置行数不同（596 对 572） |
| #233 | 球体 → `--export-stl`；立方体加那份球体 STL → `--export-stl`（每对象一个文件） | [判据](cli-stl233-3-judge-stl233.json)：两个导出的 STL 与盘上两个对象的三角面一致（[立方体](cli-stl233-3-cube.stl)、[球体](cli-stl233-3-sphere.stl)）；「导出为单个 STL」在命令行下不可评，命令行是每个对象写一个文件 |

每条对照的命令、退出码和耗时在各自的 `*-report.json`（每步 2.1–2.2 秒）。命令行入口是 `runner/macos/cli_cases.py`；给 GUI 准备好的 `runner/macos/file_io.py` 写完了，但整夜没有得到能跑的桌面。

两个导出 STL 的原名含中文，入库时改了名：`cli-stl233-3-cube.stl` 原名 `out__stl__obj_1_立方体.stl`，`cli-stl233-3-sphere.stl` 原名 `out__stl__obj_2_obj_1_球体.stl`。
