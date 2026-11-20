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

### 授权 Xcode 后的实测

在原测试账号前台重新启动 Python 和 Orca，辅助功能及录屏预检均为 true。ScreenCaptureKit 按本次 Orca 进程与主窗口 ID 成功捕获 1200 × 800 的图像。首轮图像显示配置包更新对话框遮挡盘面，保存在 `artifacts/mac_smoke/20261120-03HooSYK/`。

第二轮在新建的测试 datadir 中沿用 `runner/boot_probe.py` 的本地更新源配置。回收截图中，Prepare 页的 U1 盘面中央可见金黄色立方体，标题为 `agent_layer_cube`。同一实例随后通过 File 菜单打开原生另存为面板，识别到可编辑控件和 Save、Cancel 按钮，执行 Cancel 后退出。复核测试账号下 Orca 主程序为 0。截图和探针日志逐份校验 SHA-256，保存在 `artifacts/mac_smoke/20261120-XX0PZk6h/`。

本轮作为前台截图和对话框能力的 SHADOW 证据。实际写入工程、独立重开切片和切换用户后的后台捕获仍待验证。

### 切换用户后的后台实测

日常账号回到前台，测试账号保持登录。每轮均在测试账号的后台 Aqua 会话冷启动一个独立的 Orca 实例，使用新的 datadir，并将同一份立方体 3MF 改为本轮唯一文件名。捕获前核对会话身份，仅以本轮 Orca PID 和窗口 ID 或唯一标题选择 ScreenCaptureKit 单窗目标。三轮都保留了结果。

| 运行 | 启动与观察 | 结果 |
| --- | --- | --- |
| `nk0oVww5` | 直接启动 Orca 可执行文件，两次查询可捕获窗口。 | 未找到目标窗口，无图。 |
| `Fsng4ESY` | 通过 Launch Services 启动，等待 84.8 秒，AX 与 CoreGraphics 均未找到模型窗口。主线程采样位于 `wxGetCpuArchitectureName → fgets → read`。 | 两次 ScreenCaptureKit 查询均无目标窗口，无图。采样只说明当时的等待位置。 |
| `MV0zNh36` | 测试会话内先运行系统架构查询，返回 `arm64`。通过 Launch Services 启动 Orca，4.3 秒后 AX 和 CoreGraphics 确认本轮唯一标题。 | 捕获两张相隔约五秒的 1200 × 800 静态图。截图标题与本轮 fixture 名匹配，U1 盘面中央可见金黄色立方体。两张图 SHA-256 均为 `4aa060ca1f99528ee431fcea110fb88fa2080ac8465bf9a46884ce485c2bf4bd`。 |

三轮的本地证据目录分别为 `artifacts/mac_smoke/20261120-bg-nk0oVww5/`、`artifacts/mac_smoke/20261120-bg-Fsng4ESY/` 和 `artifacts/mac_smoke/20261120-bg-MV0zNh36/`，已核对回收件摘要。成功轮在捕获前后均确认测试会话不在控制台，收尾时该账号的 Orca 主程序数量为零。已取得一次后台冷启动、加载模型并静态截图的 SHADOW 证据。三轮条件有差异，尚未确定启动延迟的根因，也未验证后台输入、动态刷新或业务切片。
