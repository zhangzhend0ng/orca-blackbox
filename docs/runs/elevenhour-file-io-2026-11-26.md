# 飞书文件导入导出十三行的客机验收

本轮自 software_testing 的 `e4128c3` 开始，T0 = 2026-11-25 22:59:24（+0800），截止 2026-11-26 09:59:24，09:29 起只收尾。主工作树、三个共有附加工作树和用户文件均保留。开始时 win11-test 的 suite 为 Ready、无 Orca 与 Python 作业、交互分辨率 1920×1080；fa706g3 的 glm_line 为 Ready。两台 Windows 均为 Snapmaker Orca 2.4.0，产品二进制 SHA-256 为 `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`，fa 的 Snapmaker 预设逐文件核对 738 项相同。Mac mini 是 2.4.2，日常账号的控制台自 23:33:40 锁屏，整夜没有跑成 GUI。

飞书选定的前置条件、步骤和预期均逐字取自飞书表；对照见[原对照表的对应行](../feishu-writeback-plan-2026-11-23.md)。

| 飞书 | 传给 hv_go.ps1 的单例名 | 结论（候选证据） |
| --- | --- | --- |
| #227 | m7x_227_import_stl | [二进制 STL 导入、平移与旋转，正式双 GREEN](evidence/feishu-227-2026-11-26/README.md) |
| #233 | m7x_233_export_merged_stl | [两个对象合并导出为一个 STL，F3D 可打开](evidence/feishu-233-2026-11-26/README.md) |
| #234 | m7x_234_export_plate_slice | [当前盘切片文件，大小随复杂度增大](evidence/feishu-234-2026-11-26/README.md) |
| #236 | m7x_236_export_gcode | [导出纯 G-code](evidence/feishu-236-2026-11-26/README.md) |
| #238 | m7x_238_export_disabled | [未切片时切片导出行置灰](evidence/feishu-238-2026-11-26/README.md) |
| #230 | m7x_230_import_project | [工程 3MF 经 Import 只载几何，预期不成立](evidence/feishu-230-2026-11-26/README.md) |
| #231 | m7x_231_import_zip | [归档里的模型载不进来，预期不成立](evidence/feishu-231-2026-11-26/README.md) |
| #246 | m7x_246_repair_model | [对象菜单里没有 Fix model，预期不成立](evidence/feishu-246-2026-11-26/README.md) |
| #235 | m7x_235_export_all_plates | [一个归档装两盘，部分覆盖](evidence/feishu-235-2026-11-26/README.md) |
| #251 | m7x_251_reload_from_disk | 进行中 |
| #232 | m7x_232_import_configs | 进行中 |
| #237 | m7x_237_export_configs | 进行中 |
| #228 | m7x_228_import_colored_obj | 进行中 |

前五行已写回飞书并逐条回读，进入默认回归；默认回归现为 98 条。#230、#231、#246、#235 的飞书状态保持空白。菜单与对话框的普查证据见[文件菜单普查](evidence/elevenhour-filemenu-2026-11-25/README.md)，#262 的离线定论见[表面流量平衡](evidence/elevenhour-262-balance-2026-11-26/README.md)。

## 复跑

用提权 PowerShell 调 `runner/hv_go.ps1 -Cases <单例名>`。客机工作目录为 `C:/coil/orca-blackbox-v3-r1`，须先把提交推送到 origin（或按既有 Git bundle 规则同步后加 `-NoSync`）。每轮是一个新的 Orca 进程和新的配置目录，结束后调 `runner/hv_harvest.ps1`。本轮总控另有一个宿主脚本把「派发 → 等待 → 收割 → 逐文件核对 → 留收据」串起来（不在仓库内，`C:\coil\vm_setup\elevenhour_1125\obj_run.ps1`）。

离线复核每个收据：

```powershell
python tools/replay_case_evidence.py <证据目录>\<提交8位>-run1-receipt.json <证据目录>\<提交8位>-run2-receipt.json
```

## 计时和模型

| 飞书 | 候选提交 | 正式两轮脚本内耗时（秒） | 离线复核（每会话） | 领取到首次客机通过 |
| --- | --- | ---: | ---: | --- |
| #236 | `48e3aa7d…`（另有 `81dbcf14…` 两会话） | 111.888 / 111.389 | 38 项 | 约 1 小时 10 分（00:09，首次实跑即通过） |
| #233 | `6bdf66b3…` | 121.875 / 122.475 | 43 项 | 约 1 小时 40 分（00:41，一次失败轮） |
| #234 | `48e3aa7d…` | 190.995 / 191.465 | 97 项 | 约 1 小时 53 分（00:55，首次实跑即通过） |
| #227 | `11858f17…` | 134.174 / 134.569 | 56 项 | 约 3 小时 09 分（02:10，七次失败轮） |
| #238 | `c378dee0…` | 149.725 / 147.204 | 51 项 | 约 3 小时 21 分（02:23，一次失败轮） |

各收据单独保留调度起点、用户日志完成和收割时刻。用例过程中没有人工桌面输入。换初态的返工耗时与人工历史耗时均为未测。

总控与六类子 agent（用例 ×4、判据、平台）的实际模型均为 `new-provider/glm-5.4`；没有用到备选模型。

实体机 fa706g3 的 SHADOW 只作旁证：#227、#233、#234、#236 各有 GREEN（#234 前两次因显示器休眠为 RED），#231 三次都是 RED 且与客机同签名，#238 一次 RED（两次菜单读数与客机相同，收尾时 File 菜单窗口没关上）。Mac mini 整夜锁屏，只有三条命令行对照，见[Mac 线记录](evidence/elevenhour-mac-2026-11-26/README.md)。

本轮最值得下一批复用的判据：从另存工程读顶点集合与逐实例位姿（不依赖截图）；File→Export 的 `Export G-code` 行启用作为切片完成信号；原生菜单标志位读行状态并与收据哈希绑定的日志对读；归档内成员（G-code、MD5、预览图、配置）与另存工程交叉核对；每个反例都能让旧判据翻红。驾驶事实与踩过的坑见 PITFALLS §22。

## 继续跟踪

- #254 的切片完成信号是假信号一节已在 PITFALLS §22.2 记录；用例本身按新信号改造后进行中。
- #229（多实体 STEP）和 #298（下载任务中再次打印）本轮未领取。
