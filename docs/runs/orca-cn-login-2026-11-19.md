# Orca 中国区首页登录试点 · 2026-11-19

在 win11-test 通过 hv_go.ps1 的 INTERACTIVE suite 串行运行。每轮使用新 Orca profile 和新 WebView2 用户数据目录。hv_harvest.ps1 只回收该探针的产物。模型调用为 0。

被测为客机现有 Orca 2.4.0，构建标记为 56e82d53c8。AppConfig.cpp:1348 将 China 映射到 CN，WebSMUserLoginDialog.cpp:63 选择 id.snapmaker.cn。客机实际首页引用未加哈希的 flutter_bootstrap.js，固定 ref 中的首页引用带哈希名称的文件。入口与表单以客机实测为准。

| Run ID | 探针提交 | 阶段 | 结果 | 总耗时 |
| --- | --- | --- | --- | ---: |
| 4a4893e7128a415f9a4bfb5dee65b23d | 9f53583 | 首页控件搜索 | NON_GREEN，未定位入口 | 45.11 s |
| c0d5593b64f54d709a441552879e9fea | 863d6d5 | 首页延时及无障碍 | NON_GREEN，未定位入口 | 88.41 s |
| 0fba8d9b2ac84155ae99f1a6599551a0 | 9e1cd63 | 未登录首页画面 | NON_GREEN，画面确认左栏 Login/Register | 49.50 s |
| b2b860ac6e2e4665af424ad3a2cefa3b | 8fe55f4 | 首页入口到中国区表单 | NON_GREEN，首页 OCR 点击成功，UIA 验证中国区域名 | 22.66 s |
| 28e7517e7a514dafb1c96f4c6106eb7d | 8bef3c0 | 中国区密码表单 | NON_GREEN，手机号、密码和协议复选框已确认 | 23.80 s |
| 190129f4c0294dd6b9d93c63397e2405 | 02ff5bf | 提交密码登录 | NON_GREEN，提交后对话框关闭，首页账号判据未通过 | 35.52 s |
| 0fbaef4a554149409ac6431430e42aa5 | b950398 | 首页账号状态复验 | NON_GREEN，提交后对话框关闭，OCR 对带图标的首页标签要求整行相等 | 34.12 s |
| 21d7f3e196e64cc4802f4d6e49b73032 | 87c0461 | 放宽首页标签匹配 | NON_GREEN，手机号字段读回失败，未提交 | 28.53 s |
| 4a327c49bb494e33b2d112c5e1e3d8cb | 5a2889e | UIA 写入手机号 | NON_GREEN，读回成功，提交键仍禁用 | 28.69 s |
| 545658d78c1d46bfaa81f218e15350b4 | e13085c | 真实鼠标聚焦与键盘输入 | NON_GREEN，提交成功且登录框关闭，首页登录入口消失，账号正向判据待补 | 37.53 s |
| 6407867ffcad41dd8c99d7dd469f1eed | 72d83d8 | 首页 My Favorites 判据 | NON_GREEN，提交后首页仍未显示该可选入口 | 57.88 s |
| 9663b61facc34f0fb25b3f8f67095ec3 | fb9b0dc | 首页账号下拉复核 | NON_GREEN，已提交，登录框关闭，首页 Login/Register 消失，未识别到退出控件或资料页 | 37.67 s |

首次探针启动尝试 16373f0068914e0c877b3a7f9de8762c 使用旧检出，未执行探针。当时 Git 把成功的 bundle 校验提示写到 stderr，PowerShell 将其当作错误中止。修复后要求明确的同步回执和客机干净工作树才启动。

真实登录从 Windows 凭据库读取客机 test 用户的通用凭据，协议勾选使用本次授权。登录模式只保留阶段、布尔回执和总耗时。未登录画面采样仅用于独立表单探索。探针未连接、绑定或操作打印机。

本次计划验证一条中国区首页登录路径。完成 5 次入口及表单探查、7 次登录模式执行。5 次实际提交，其中 2 次在提交前分别停于手机号读回和表单仍禁用。登录成功正向判据通过 0/7，所有轮次均保留 NON_GREEN。最后一轮的 suite 为 Ready，Orca 和本轮拥有的子进程为 0，私有 profile 已回收，客机工作树干净。

调用时使用独立 run ID，保持当前固定版本，另行确认 guest 检出干净并与宿主一致。检查表单只传 CloudLoginProbe。需要实际提交时，同时传 CloudLoginAuthenticate，并取得本次操作所需的协议授权。

    runner/hv_go.ps1 -WindowsMcpProbe -CloudLoginProbe -ProbeRunId <32位run ID>
    runner/hv_harvest.ps1 -CloudLoginProbe -WindowsMcpRunId <同一run ID>

回收目录为 artifacts/windows_mcp_harvest/<run ID>。计时从客机进程开始到删除本轮私有目录为止，包含准备、交互、首页观测和回收。Git 同步与宿主回收在该计时外。

## 首页登录状态复核

直接检查客机 Orca 2.4.0 安装的 `resources/web/flutter_web/main.dart.js`。可执行文件 SHA-256 为 `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`，首页脚本 SHA-256 为 `5d9ef1810174e1a22d75a168e5c148fc1fa3574f80f4531a249e3e67b578383b`。首页 `HomeSideMenuWidget.aQ8` 用 `gnQ()` 选择账号区。`gnQ()` 要求状态为 `online` 或 `Online`，并要求身份字段非空。该条件为假时才渲染首页唯一的 `Login/Register`。原探针要求额外找到退出菜单、账号资料页或受条件控制的 `My Favorites`，漏判了已观察到的首页状态切换。

回看 `545658d78c1d46bfaa81f218e15350b4`、`6407867ffcad41dd8c99d7dd469f1eed`、`9663b61facc34f0fb25b3f8f67095ec3`。三轮都从可点击的 `Login/Register` 进入已核对域名的登录框，提交后该框关闭。随后同一 Orca 首页仍能同时识别 `Model Library` 和 `My Devices`，登录入口已消失。按已核实的渲染逻辑，这三轮的界面证据支持登录成功。历史回执与表中原探针判定照原样保存。

新判据在登录前后使用同一首页截图区域和 OCR 方法。提交前需同时读到登录入口及两个首页导航标签，登录框关闭后需连续两次只读到两个导航标签。只输出标签是否可见和匹配次数。设备在线、打印任务投递及实打仍需各自验收。
