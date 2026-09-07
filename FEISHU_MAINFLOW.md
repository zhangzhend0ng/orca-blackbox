# Feishu 测试用例（主流程）→ vision-gui case mapping

Traceability matrix for the Feishu wiki bitable **测试用例**
(wiki node `Thm9wiVFBi3p14kpksjcVs0HnEd`, base `WbIjb4vM0aZX7BsJxI9cWBWAnad`,
table `tblLR8zYgwBuggDI`「数据表」, view `vewBht96jW`「总测试用例」; snapshot
parsed 2026-09-08, 305 records). The table's 一级分类 splits into
APP测试 (85) / 服务端测试 (36) / 消息推送 (32) / 软件更新 (40) /
**ORCA测试 (111)** — only the ORCA测试 records are in scope for this
black-box Orca suite; the rest target the mobile app, the cloud backend and
the push infrastructure and are listed here as OUT-OF-SCOPE without per-
record work.

Status legend: **COVERED** (automated, m7 case), **PARTIAL** (core intent
automated, sub-steps out of black-box reach — noted), **MANUAL** (needs a
physical device / update server / backend state — not automatable here),
**SKIP** (feature absent from the current build, or the record is empty).

Execution rig: the guest VM (`win11-test`, dev exe 08-24) via the
push_verify / guest_run relay loop; see `runner/README.md`.

## Stale-expectation notes (table vs current build)

| Record | Table says | Current build (source-verified) |
|---|---|---|
| #7 | 完成首次启动引导设置 | seeded profile pins `firstguide.finish=true` — the wizard is deterministically skipped; the case asserts the READY page instead |
| #10 | 执行 Orca 热重启 | no hot-restart feature exists in this build (MainFrame/menu grep 09-08) |
| #14 | 切片后检查 G-Code 起始位置 | m6a asserts the same intent through the exported 3mf build-item transform (exact matrix), not the gcode |
| #16 | 验证模型还原功能 | the Scale window's Reset button is used when OCR finds it, otherwise typing 100 (equivalent restore); noted per run |
| #22 | 耗材合并操作 | the black-box surface is the mixing entry's Options > Merge with (m4d, 表1 #46 semantics) |
| #24 | 擦除塔材料切换后 G-Code 正确 | wipe-tower gcode semantics need a device/printer context; the automated surface is the Flush Options toggle flip |
| 模板 #79 | 拆分为对象/零件 | split gates follow `plater()->can_split()`; the case records the gate state honestly when the fixture has no second volume |
| 模板 #84/#109 | 耗材合并 / 耗材全局改变 | merge semantics are m4d-mapped; the global filament popup is enumerated as evidence, remap rows degrade to SKIP |

## GUI业务 (#7–#24)

| # | 用例 | Status | Case | Assertions |
|---|---|---|---|---|
| 7 | 首次启动进入准备页面 | COVERED | m7a | Prepare tab template active + canvas paints + slice idle (wizard step = seed invariant, stale note) |
| 8 | 正常关闭无残留进程 | COVERED | m7a | WM_CLOSE → tasklist sweep clean for 10s |
| 9 | 新建项目清空模型 | COVERED | m7b | dirty via Add-Primitive → File > New Project → save prompt → Don't save → empty-bed floor |
| 10 | 热重启后状态恢复 | SKIP | — | feature absent from the 08-24 build |
| 11 | 导入本地 STL 并显示 | COVERED | m7c | File > Import > STL dialog → Prusa.stl arrives (0.25% + blob) |
| 12 | 导入不合法文件提示错误 | COVERED | m7d | garbage STL → error #32770 → app alive + plate unchanged |
| 13 | 单模型切片生成 G-Code | COVERED | m2/m3a | slice done rendering + empty-scene rejection (existing suite) |
| 14 | 坐标输入精确移动 | COVERED | m6a | Position X=60 → 3mf build-item transform exact (stale note) |
| 15 | 旋转 Z 45° | COVERED | m7e | Rotation Z field commits 45 → matrix cos/sin ≈ 0.7071 |
| 16 | 等比缩放 120% + 还原 | COVERED | m7f | Scale commits 120 → matrix column norms ≈1.2 → restore (Reset/typed) → reads 100 |
| 17 | 多模型重叠后整理分离 | COVERED | m7g | cube overlaps fixture → Arrange slot → ≥2 blobs separated >120px (per-plate/global split not reachable — PARTIAL sub-step) |
| 18 | 右键删除模型 | COVERED | m7h | object menu Delete row → empty-bed floor + slice rejection |
| 19 | 右键创建新模型 | COVERED | m7i | bed menu > Add Primitive > Cube → model appears + slice accepted |
| 20 | 多区域涂色 | PARTIAL | m4e+m4i | painting gizmo + painted slice verified (existing); per-region gcode color audit beyond black-box reach |
| 21 | 切换对象耗材 | COVERED | m7j | Change Filament submenu → exported 3mf extruder attrs differ from fixture baseline |
| 22 | 多耗材配置合并 | COVERED | m4d | mixing entry Options > Merge with (existing; stale note) |
| 23 | 切换打印机预设参数差异 | COVERED | m3e | preset combo switch → gcode `; layer_height` follows (existing) |
| 24 | 擦除塔材料切换 | PARTIAL | m7k | Flush Options toggle flips (menu state evidence); gcode wipe-tower semantics manual |

## 联机业务 (#25–#38) — MANUAL

全部需要真实设备（云联/局域网发现、绑定、PIN 码、打印控制、监控摄像头、
打印头/热床/LED/风扇控制）：#25–#38。本仓为纯黑盒 GUI 套件，无设备桩，
设备栈联测走白盒 `ORCA_GUI_TEST_MODE=network` 通道（BLACKBOX_CASES.md）。

## 软件更新（ORCA 部分 #65–#67）— MANUAL

启动检测更新 / 手动检查更新 / Flutter 更新重启：需要可控的更新服务端
（版本号、下载产物），黑盒环境无法在不触网的情况下构造「有新版本」状态。

## 主流程-用例 (#58–#70) — PARTIAL（GUI 链已自动化 + 设备步骤人工）

| # | 用例 | Status | 自动化部分 |
|---|---|---|---|
| 58 | 安装后新建项目并完成打印 | PARTIAL | m7t73 (new/create/delete) + m7t74 (transform/slice)；PIN 码绑定/打印控制人工 |
| 59 | 多模型布局与本地文件直接打印 | PARTIAL | m7t75 (overlap/arrange/delete/slice)；上传打印/绑定人工 |
| 60 | 多材料涂色打印 | PARTIAL | m4e+m4i (涂色/切片)；云设备绑定/监控人工 |
| 61 | 用户登录绑定设备后打印 | PARTIAL | GUI 链 = m7t82 变体；登录/云设备人工 |
| 62 | 打印参数差异验证 | COVERED | m3e（预设切换 → gcode 差异） |
| 63 | 模型快速调整与局域网打印 | PARTIAL | m7t74（调整/切片）；局域网绑定人工 |
| 64 | 多模型合并耗材后打印 | PARTIAL | m7g（重合/整理）；耗材合并=m4d；打印人工 |
| 65 | 打印参数差异验证与云打印 | PARTIAL | m3e；云打印人工（注意：表中 ID 与软件更新 #65 重复） |
| 66 | 涂色多材料打印并上传本地任务 | PARTIAL | m4e+m4i；上传/绑定人工 |
| 67 | 模型布局优化与多设备切换打印 | PARTIAL | m7t75；多设备人工 |
| 68 | 用户登录预打印参数修改本地打印 | PARTIAL | m3e（预设）+ m4d（合并）；登录/打印人工 |
| 69 | 设备绑定异常与恢复打印 | MANUAL | 全链设备操作 |
| 70 | 设备局域网 IP 连接设备控制 | MANUAL | 全链设备操作 |

## 主流程-模板 (#72–#111)

| # | 模板 | Status | Case | 备注 |
|---|---|---|---|---|
| 72 | 模型导入 | COVERED | m7t72 | arrive → Delete All → close |
| 73 | 新建项目 | COVERED | m7t73 | new → create cube → delete → close |
| 74 | 单模型切片调整 | COVERED | m7t74 | move 60 / rotate 45 / scale 120 (OCR) → slice done |
| 75 | 多模型布局切片 | COVERED | m7t75 | overlap → arrange → delete one → slice + gcode export |
| 76 | 打印参数切换与验证 | COVERED | m3e | （已有覆盖） |
| 77 | 基础模型分割 | COVERED | m7t77 | Cut gizmo Perform → 2 parts → move/arrange → slice |
| 78 | 自动朝向选择底面 | COVERED | m7t78 | auto orient (view diff) → Flatten face click → slice |
| 79 | 拆分对象/零件 | PARTIAL | m7t79 | split slots driven；can_split 门控状态如实记录 |
| 80 | 可变层高绘制支撑 | COVERED | m7t80 | VLH + Support Painting 激活 + 涂抹 → slice |
| 81 | 布尔剪贴模型整理 | PARTIAL | m7t81 | Add Part 第二体积 → MeshBoolean 激活（操作 UI 证据级）→ arrange → slice |
| 82 | 剪贴耗材切换 | COVERED | m7t82 | cut → Change Filament → slice |
| 83 | 新建项目导入模型 | COVERED | m7t83 | new → Import STL → arrive → slice |
| 84 | 打印机预设更改耗材合并 | PARTIAL | m7t84 | 打印机 combo 切换 + 导入 + 切片；耗材合并 = m4d 映射 |
| 85 | 涂色多材料 | COVERED | m4e+m4i | （已有覆盖） |
| 86 | 自动朝向布尔剪贴整理 | COVERED | m7t86 | orient + Add Part + MeshBoolean + arrange + slice |
| 87 | 选择底面可变层高绘制支撑 | COVERED | m7t87 | flatten + VLH + support paint + slice |
| 88 | 多模型导入拆分缩放耗材切换 | COVERED | m7t88 | 2×import + split probes + scale 120 + filament + slice |
| 89 | 模型创建旋转涂色切片 | COVERED | m7t89 | Add Primitive Cube → rotate 45 → Color painting dab → slice |
| 90–108 | 设备类模板（F-01…F-26） | MANUAL | — | 需云联/局域网设备（发现/绑定/PIN/连接/打印控制/打印头/热床/外设/监控/切换/断网重连/登录） |
| 109 | 打印机预设全局更改耗材 | PARTIAL | m7t109 | 打印机切换 + 耗材弹窗枚举（证据级）+ 导入 + 切片 |
| 110 | 预打印界面更改预设 | MANUAL | — | F-37 预打印耗材 + F-24 本地上传打印 = 设备链 |
| 111 | 局域网 IP 连接 | MANUAL | — | 设备链 |

## 模型站 (#201–#220) — OUT-OF-SCOPE / MANUAL

需要模型站后端可控状态（500 注入、磁盘满、404、空列表、超长文件名）与
Flutter 侧 UI：#201–#220。其中 #209 卡片高亮 / #212 弹窗层级属 Flutter
WebView UI 语义，不属于本仓 wx 黑盒范围。

## 记录质量备注

- 表中 ID 列有跨节重复（主流程-用例 #65/66/67 与 软件更新 #65/66/67 同号），
  引用时以「一级分类+二级分类+标题」消歧。
- 表尾存在 3 条空记录（模型站/联机业务/GUI业务各一），无内容可映射。
- 自动化状态回写：本映射落库后，将 COVERED 记录的 自动化状态 字段更新为
  「已覆盖」（其余保持 未覆盖）。
