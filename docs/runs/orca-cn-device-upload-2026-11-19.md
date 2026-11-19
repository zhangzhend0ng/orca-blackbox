# Orca 中国区设备上传试点 · 2026-11-19

验收点为 Orca 登录、中国区账号下设备可达、上传 G-code、设备端可确认收到该文件。所有 GUI 通过 win11-test 的 hv_go.ps1 串行执行。探针只保留白名单状态字段和计数。

固定构建源码中，PrintHostDialogs.cpp:154–159 的 Upload 按钮选取 None，Plater.cpp:21627–21631 将其路由至 WebPreprintDialog 的发送模式。WebPreprintDialog.cpp:24 设定独立发送页。设备文件回执按本次上传文件名核对。设备状态或发送模式无法确认时停止在相应阶段。

已有准备文件为试点 run 425c967c274a45968d7e31c6cfef17dc 的 Snapmaker U1 G-code，163024 字节，SHA-256 4df5005244ade297912e67fc48bd30929675b20e6a8fbb35d99d0b233bd85d08。目标机型可用后才能选用它。

| Run ID | 探针提交 | 耗时 | 实测结果 |
| --- | --- | ---: | --- |
| b015cd24bcb14886ac024dd909a95f40 | 0c9eec4 | 56.62 s | SHADOW，登录后到达 My Devices，读取到页面标题和添加设备，未识别到可选在线设备。 |
| e73546577edb42b7b094ffdbf1edb380 | 7aa1ec8 | 65.84 s | SHADOW，登录及设备页通过，触发添加设备，发现页初版特征未匹配。 |
| 8f4fcc2160df47d6a3085af3e1db3bf1 | cc0b8cc | 53.70 s | SHADOW，设备页出现 U1 卡片，附近发现仍处于搜索，未读到附近设备型号。 |
| 20c3805e6aa8445f831d45901791d2b8 | 3f95be3 | 46.94 s | SHADOW，识别 U1 卡片，整页 OCR 未能定位卡片的 Device Control。 |
| f2b7ae6b72344fd2a0ffba8f4f5ecf9a | 14cbb3b | 67.51 s | SHADOW，定位并点击卡片的 Device Control，未观察到已连接的正向状态。 |
| 99014845d4d44910a6bce7e593ed28f4 | a00b66c | 56.03 s | SHADOW，进入 U1 控制视图，读取到温度区和 Files。 |
| 8aeaa8723fef4d309f78c1b6493a661d | 6665f07 | 49.88 s | SHADOW，确认设备面板可见，首次文件页定位仅查主窗口，未打开文件页。 |
| 7fb39c37e03b49bcac86d17d7c35ae0b | df7c757 | 50.16 s | NON_GREEN，首次上传模式到达 U1 控制面板，打开工程的前置步骤失败，未发送。 |
| 818d208e765444c59a4274c8d44c2951 | 922b19b | 67.03 s | NON_GREEN，原生 File 菜单打开工程，通过工程加载判据，停在切片阶段，未发送。 |
| 86292e9d76ed4727955eec418b95e3c7 | 7581345 | 56.75 s | NON_GREEN，切片出口已启用，首次导出驱动未保存 G-code，未发送。 |
| e0d0fcc294c34ff0899df8393badd2ed | 3306b39 | 67.72 s | NON_GREEN，独立保存了本轮 U1 G-code，原生 Upload 进入 WebView path=5 的只上传页，并读回同名文件。设备与发送控件未确认，未发送。 |
| 1b816c0b91e94ef8bbc01a7312937f25 | 7bb284e | 73.08 s | NON_GREEN，确认选择打印机标题，首次将标题识别成下拉按钮，未选中设备。 |
| 456df4d7d50e4589a4d22f07777203f7 | 6fadf68 | 74.39 s | NON_GREEN，打开打印机下拉并检测到一条条目，未识别到 U1 选项，未发送。 |
| b959ee83ffc24b5980a0ef90242910f1 | 76f2cc9 | 76.33 s | NON_GREEN，验证此次文件名和只上传页，打开打印机下拉后唯一识别的条目是 Add Device，未触发发送。 |

表中 SHADOW 表示账号登录和设备页探查通过。端到端上传单独验收，须有设备接收回执。

同步 14cbb3b 后，宿主 relay 在写完同步正文与完成标记之间退出。用已注册的 watchdog 恢复，核对客机 HEAD 和空闲状态后继续执行。未重启虚拟机。

本轮生成的文件可在 artifacts/windows_mcp_harvest/e0d0fcc294c34ff0899df8393badd2ed/orcabbe0d0fcc294.gcode 核对，文件为 160584 字节，SHA-256 为 83545f842f0471b9d108d03452920e605fd8d2d0eeacc0d0cf599648a2f04cc1。

最终验收统计为一条端到端上传路径，设备探查执行 7 次，上传模式执行 7 次，发送提交 0 次，设备接收通过 0 次。账号主页的 U1 卡片及其控制视图可进入。附近发现阶段未读到设备型号，只上传页的打印机下拉仅出现 Add Device，缺少可选上传目标。最后一轮生成的 G-code 为 orcabbb959ee83ff.gcode，161371 字节，SHA-256 为 044c2723d3f316d54951f4f58c77ceabc67d7b1375ff5bc933a085feb364f779，回收目录为 artifacts/windows_mcp_harvest/b959ee83ffc24b5980a0ef90242910f1。未触发打印。

runner 入口为 hv_go.ps1 -WindowsMcpProbe -CloudLoginProbe -CloudLoginAuthenticate -CloudDeviceProbe -CloudUploadGcode -ProbeRunId <32 位 run ID>，随后使用 hv_harvest.ps1 -CloudLoginProbe -WindowsMcpRunId <同一 run ID>。HARVEST 对生成的 G-code 核对当前 run 的文件名、大小和摘要。总耗时包含客机准备、操作和私有目录回收。

## 指定设备后的复核

用户确认账号下有 U1 和客户端测试。run 734d7b4010bb49e8b509ac21ee6f35e2（a4bb43a，84.88 s）的下拉局部图显示两台设备均可见，U1 带勾选标记。历史回执中的 Add Device 是整窗 OCR 的唯一匹配项，局部实拍确认它另有两个设备选项。直接在已选设备名称的窄区域用行识别，可在该证据中读回 U1。该 run 未发送。

局部证据位于 artifacts/windows_mcp_harvest/734d7b4010bb49e8b509ac21ee6f35e2/upload-picker.png。

run c7dffafc16f5459cbaff562ef60ea6b9（6229bb0，66.58 s）在发送页局部读回了 U1。整窗 OCR 同样漏读了白字蓝底的 Send。底部局部图 upload-footer.png 显示 Send 已启用，本轮仍未发送。下一轮将底部按钮区域单行识别及蓝色启用态作为点击前置判据。

run 8a0ed84002694455ad9edce215044837（adb8226，60.34 s）为 SHADOW。同一客机运行完成中国区登录、打开 U1 设备面板、加载工程并切片、导出 G-code、进入独立只上传页、核对 U1 已选及本轮文件名，点击启用的 Send 后读到 Upload completed。固定安装包把该提示放在发送页的 taskComplete 流程中。只上传流程未触发打印，设备文件列表没有另跑一次核对。

本次文件为 orcabb8a0ed84002.gcode，共 163547 字节，SHA-256 为 82838177710b811c28ac35065b0d399035267ec9841d94bec77ed03477e77408。客机回执及经摘要复核的 G-code 在 artifacts/windows_mcp_harvest/8a0ed84002694455ad9edce215044837/。指定设备后共执行 3 次，实际发送 1 次，按 Orca 上传完成判据通过 1 次。

## 补录回放

成功轮仅保存 G-code 与回执。补录 run a4b8ceeadf0a437e9ef46ef6d098fd67（ced3561）从确认登录后开始。录像只采集 Orca 自己的窗口，回放完成设备页、工程装载、切片并进入 U1 的只上传页。验证 Send 已启用后停留并退出，未再次提交。首次补录 55926e405fa943db8d2203f75fe85261 卡在设备文件页入口判据，保留为 NON_GREEN。

成片在 artifacts/windows_mcp_harvest/a4b8ceeadf0a437e9ef46ef6d098fd67/orca-u1-upload-review.mp4，H.264，32.36 秒，包含加速实况和单独标注的原成功轮回执。片尾的原始回执来自 8a0ed84002694455ad9edce215044837。
