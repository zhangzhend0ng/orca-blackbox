# 飞书右键菜单用例的客机验收

本轮自 software_testing 的 5d8d9de 开始，主工作树、三个既有附加工作树和用户文件均保留。飞书六条候选的前置条件、步骤、预期和最终回读在原对照表的对应行。[飞书原文对照](../feishu-writeback-plan-2026-11-23.md)

开始时没有宿主历史派活进程。win11-test 的 suite 为 Ready，无 Orca、Python 作业，交互分辨率 1920×1080。fa706g3 的 glm_line 为 Ready，实跑复用原有交互任务身份。Windows 两台均为 Snapmaker Orca 2.4.0，产品二进制 SHA-256 为 5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf，Snapmaker 预设逐文件核对 738 项。工程预设为 U1 0.4 mm、PLA、0.20 mm Standard。Mac 采用 coilwin 的独立后台 Aqua 会话，产品为 2.4.2，前台仍由 coil 使用。Mac 的两次 #241 分别停在命名窗口识别和原生右键菜单识别，两次均确认清理。[Mac 收据一](evidence/feishu-241-2026-11-25/mac-f8d32e3c-result.json) · [Mac 收据二](evidence/feishu-241-2026-11-25/mac-46fb318f-result.json)

| 飞书 | 传给 hv_go.ps1 的单例名 | 候选证据 |
| --- | --- | --- |
| #240 | m7x_240_arrange | [两轮工程和逐对交集](evidence/feishu-240-2026-11-25/README.md) |
| #241 | m7x_241_orient | [两轮逐件角度和贴盘面积](evidence/feishu-241-2026-11-25/README.md) |
| #242 | m7x_242_delete_plate | [保留对象和未分配盘归属](evidence/feishu-242-2026-11-25/README.md) |
| #245 | m7x_245_clone_fill | [克隆、填充与饱和证明](evidence/feishu-245-2026-11-25/README.md) |
| #247 | m7x_247_split_shells | [拆分和逐件着色](evidence/feishu-247-2026-11-25/README.md) |
| #252 | m7x_252_export_stl_viewer | [STL、F3D 渲染及坏输入对照](evidence/feishu-252-2026-11-25/README.md) |

## 复跑

用提权 PowerShell，从仓库根目录调用 runner/hv_go.ps1 -Cases <单例名>。本轮的客机工作树为 C:/coil/orca-blackbox-v3-r1，可用 ORCA_BB_GUEST_SANDBOX 指向该目录。客机必须同步同一受测提交。使用已验证的 Git bundle 同步时，可按现有 runner 规则使用 -NoSync。每轮等待 suite 返回 Ready，再调用 runner/hv_harvest.ps1。用例日志会打印 feishu-object-cases/<编号>/run-* 工件目录。analysis.json 记录逐步判定，同目录保留工程、截图和当前用例的其他工件。对已收割的原始证据，从仓库根目录用 python tools/replay_case_evidence.py <收据路径> 校验文件摘要并独立重算。

## 计时和模型

| 飞书 | 首个完整客机会话从调度至收割（秒） | 正式两轮脚本内耗时（秒） |
| --- | ---: | ---: |
| #240 | 101.014 | 75.546 / 74.297 |
| #241 | 103.383 | 78.266 / 78.485 |
| #242 | 97.293 | 70.766 / 71.281 |
| #245 | 126.485 | 99.359 / 99.406 |
| #247 | 130.834 | 105.704 / 105.406 |
| #252 | 92.221 | 67.375 / 67.453 |

各收据单独保留调度起点、用例日志完成和收割时刻。用例过程没有人工桌面输入。两次正式验收沿用同夹具，换初态返工与人工历史计时均为未测。

fa706g3 的只读判据审阅由实际模型 new-provider/glm-5.4 在 41.55 秒返回完成标记。Mac 显式选定 Snapmaker 的同一模型，82.86 秒到期无完成标记。改试已登记的 deepseek-v4-flash，12.38 秒返回 HTTP 401。模型参与文字审阅，平台脚本和原始工件回放采用同一组业务判据。

优先复用逐实例 3MF 世界坐标网格、盘成员和打印边界检查。它能定位对象误删、移盘、几何变动、碰撞和壳体丢失。上轮 #239、#243、#248 的六份旧收据本轮重新离线通过，这三行飞书状态均为已自动化。

完整的 unit_tests 运行通过 1790 项、跳过 3 项，另有 4 个子测试通过。后续变更后再次运行四个相关测试文件，29 项通过。

## 继续跟踪

- #254 的飞书状态为待实现。已有一次客机完整通过，262.972 秒。复跑出现切片完成按钮已亮、目标 G-code 仅留临时文件的结果。[原始工件和候选时间](evidence/win11-254-2026-11-25/README.md)
- #262 的飞书状态为待实现。fa706g3 和 Mac 的 SHADOW 已验证顶底挤出、路径和对象流量系数。累计正挤出分别增加 0.22835% 和 0.2809%，「对象整体流量不变」仍需明确是否指累计正挤出。[fa706g3 实跑](evidence/feishu-262-fa-2026-11-25/README.md) · [Mac 实跑](evidence/mac-262-2026-11-25/README.md)
