# Orca 中国区新工程打印录像 · 2026-11-19

本文记录曾经执行的实机打印试点。当前软件主流程在 G-code 传输完成时验收，见[新建工程的软件验收](orca-cn-device-upload-2026-11-19.md#新建工程的软件验收)。

验收从 Orca 首页登录开始，在空工程中添加内置立方体、切片，核对设备及材料映射并提交打印。收到提交回执后，继续在设备控制页核对同名任务和首层是否开始。目标为用户指定的两台设备中已确认空闲的一台。录像保留登录画面及密码框自带的掩码，使用 1920×1080 客机整屏、10 fps 和正常播放速度。

GUI 全程由 `runner/hv_go.ps1` 在 `win11-test` 串行驱动。安装包为 Snapmaker Orca 2.4.0，exe SHA-256 `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`。上游只读对照源码 `56e82d53c8`，实跑隔离 profile 使用仓库随附的 Snapmaker 预设 `02.02.55.02`。对照源码的预设版本为 `02.03.03.03`。

`src/libslic3r/AppConfig.cpp:593` 解析已启用机型及喷嘴配置，`src/libslic3r/PresetBundle.cpp:1952` 读取初始机器预设。原生 `Upload and Print` 经 `src/slic3r/GUI/WebPreprintDialog.cpp` 进入 `path=4` 的打印页，画面标题为 Print Preprocessing。固定构建该页的实际提交按钮为 Send。记录同时核对页面路由及目标名称，提交动作只发生一次。

| Run ID | 探针提交 | 客机总耗时 | 录像 | 结果 |
| --- | --- | ---: | ---: | --- |
| `332796f3c8f2458c97e3c045885df7b8` | `e202985` | 62.91 s | 32.6 s | NON_GREEN。启动后出现 Setup Wizard，挡住 Orca 首页登录，未提交。 |
| `9a3698509ea74a95a082dd8fba36857e` | `d1e0050` | 87.67 s | 62.8 s | NON_GREEN。登录、打开 U1 设备页并新建工程添加立方体。U1 有一笔 67% 的既有任务，新工程的机器预设为空，未切片和提交。 |
| `3db10519398e4378a0ea2d22537d7d83` | `629ad8a` | 101.38 s | 79.5 s | NON_GREEN。画面显示客户端测试空闲，脚本漏读状态标签。仓库预设在 `resources` 下，旧路径查找仍让新工程机器栏为空。未提交。 |
| `cf546eca8fec47e0920a9d31192cdcaa` | `f2bec1f` | 89.28 s | 62.4 s | NON_GREEN。读到客户端测试空闲，以 U1 0.4 mm 预设切片并进入打印页。选中设备及文件名读回成功，定位器漏读 Send，未提交。 |
| `f1ba54cf47974131953c121d247b4638` | `8ff85f2` | 73.69 s | 51.8 s | NON_GREEN。生成的 G-code 仍带回归专用 FLOW-TEST 材料预设，提交前检查拦截。 |
| `a76bf141a116448781a1ba0cffa8849a` | `0d3ee9a` | 154.77 s | 132.4 s | NON_GREEN。客户端测试接收并执行同名任务，升温后停在热床异物检测，0/135 层。提交 1 次，未消除报警或重发。 |

在最后一轮的原始录像中复核到 `Upload completed`、客户端测试任务区的 `orcabba76bf141a1.gcode`、`working`、喷嘴读数 `140/140 °C` 和 `Bed detecting`。随后出现 `Possible Foreign Object Detected on Print Bed`，错误码 `0002 0532 0000 0001`。机器预设为 Snapmaker U1 0.4 mm，工艺为 U1 0.20 Standard。G-code 声明材料类型 PLA，耗材预设名称为 `Default Filament`。G-code 为 347392 字节，SHA-256 `5d009dc888989a07cafd1cb90c980ecf7df198a49081c9015c640bb183d1dc3d`。

最后一轮共生成 1324 帧，前台命令行覆盖和登录遮挡均为 0 帧。该次录制仍沿用登录后的侧栏账户区域覆盖，覆盖会延续到工程和设备页。后续代码移除了这层覆盖，并单独判断热床报警和首层进度。本轮实际打印停在首层前，成片 `orca-new-project-to-bed-check.mp4`、原录像及回执保存在 `artifacts/windows_mcp_harvest/a76bf141a116448781a1ba0cffa8849a/`。复核探针未在设备上关闭检测或重启任务。

执行入口为 `runner/hv_go.ps1 -WindowsMcpProbe -CloudLoginProbe -CloudLoginAuthenticate -CloudDeviceProbe -CloudUploadGcode -CloudUploadLiveVideo -CloudPrintNewProject -ProbeRunId <run ID>`。回收入口为 `runner/hv_harvest.ps1 -CloudLoginProbe -WindowsMcpRunId <同一 run ID>`。每次回收均按 SHA-256 核对原始录像和生成的 G-code。该录像开发实跑按 SHADOW 或 NON_GREEN 独立登记。
