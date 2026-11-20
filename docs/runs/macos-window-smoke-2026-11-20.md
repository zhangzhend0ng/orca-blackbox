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

## 同日测试账号前台复验

在同一测试账号的前台 Aqua 会话做了三种启动对照。LaunchAgent 通过系统 `/usr/bin/python3` 入口运行时，AX 和录屏预检均返回 false。通过 Launch Services 启动 Xcode 内的签名 `Python.app`，以及 LaunchAgent 直接运行该包内的可执行文件，两种方式均得到 AX true、录屏 false。

| 检查 | 结果 |
| --- | --- |
| 立方体与另存为 | 探针用独立 profile 启动产品，从本次 PID 的 AX 树读到主窗标题 `agent_layer_cube`。执行 File 菜单的 `Save Project as...` 后，在对话框中识别到可编辑控件、Save 和 Cancel。Cancel 的 AX 动作返回成功。未写入另存文件。 |
| 系统设置 | 从测试账号的设置面板读到 `Python_Toggle` 的值为 1。该条目位于允许录制屏幕和音频的分组，在仅系统音频分组之前。仅凭条目显示名无法确定其授权记录对应的程序身份。 |
| 单窗捕获 | 按本次 Orca 的 PID 和窗口 ID 调用系统截图工具，退出码 1，未生成图片。另一次独立启动由同一测试 Python 进程直接调用 ScreenCaptureKit，获取可分享内容时返回 `com.apple.ScreenCaptureKit.SCStreamErrorDomain` 的 `-3801`。 |

窗口标题和原生保存面板已有前台实测证据。模型像素、后台截图和切片仍待验证，整项保留 NON_GREEN。结束后复查测试账号下 Orca 主程序为 0。宿主已逐份校验并回收七份原始日志，位置为 `artifacts/mac_smoke/20261120-foreground/`。

### 录屏权限的实际归属

在测试账号的前台会话运行 Xcode 内置 Python，并以管理员账号限时读取 15 秒的 TCC 日志。测试进程发出五次 ScreenCaptureKit 查询，对应十条预检与正式判定。十次均以 `com.apple.python3` 为访问进程、`com.apple.replayd` 为请求方、`com.apple.dt.Xcode` 为授权对象，结果为 `Denied (System Set)`。同一账号的录屏设置中，Python 开关为 1、Xcode 开关为 0。针对这条启动路径，需要由用户决定是否向 Xcode 授予录屏权限。采样摘要及逐条判定保存在 `artifacts/mac_smoke/20261120-foreground/tcc-decisions.json`。
