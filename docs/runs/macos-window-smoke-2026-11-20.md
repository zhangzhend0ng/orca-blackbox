# macOS 首次窗口试验

2026-11-20，macOS 26.6.2 arm64，Snapmaker Orca 2.4.1。结果为 **NON_GREEN**。测试账号在已有的后台 Aqua 登录会话启动了 Orca，桌面探针定位到该进程的窗口。辅助功能和截屏权限预检均未通过，画布、另存为和切片待验证。

| 阶段 | 实测结果 |
| --- | --- |
| SSH 预检 | 识别到产品包和测试用户的登录会话。JXA 未导出所调用的截屏预检函数，随后改用系统框架的 C 接口。 |
| 首次 Aqua 探针 | 读取会话用户 ID 时使用了错误的字典键，探针在启动产品前中止。 |
| 修正后复试 | 临时 LaunchAgent 在测试用户的 Aqua 会话取得匹配的 UID、已登录状态和后台状态。以独立 datadir 和仓库的 `fixtures/agent_layer_cube.3mf` 启动 Orca，通过 CoreGraphics 按本次 PID 枚举到一个标记为 onscreen 的 1200 × 800 窗口。该标记属于测试会话。 |
| 观察边界 | `AXIsProcessTrusted()` 与 `CGPreflightScreenCaptureAccess()` 对探针均返回 false。未请求系统弹窗授权，未注入输入。传入夹具的 SHA-256 与仓库一致，实际模型画面和载入结果尚无图像证据。 |
| 收尾 | 探针对本次 Orca 发送 SIGTERM 并等到退出。稍后复核测试账号下已无该安装包的可执行进程，临时 LaunchAgent 已卸载，控制台仍属于原日常账号。 |

证据回收到宿主 `artifacts/mac_smoke/20261120-5hd8onwi/`，含两次 Aqua 探针日志及复试的 Orca 启动日志。复试探针日志的远端与回收件 SHA-256 均为 `bef0e77975280d60b8b8dc1ff1caba3a57d13751b044855445eeb3309fc8c8f4`。

下一次用相同测试账号核实执行程序的授权，采集 Orca 窗口的实际模型帧并检查原生保存面板。后台会话的捕获和输入能力仍需分别实测。
