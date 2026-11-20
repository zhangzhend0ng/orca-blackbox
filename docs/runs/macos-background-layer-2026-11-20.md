# macOS 后台层高对照试验

2026-11-20，macOS 26.6.2 arm64，Snapmaker Orca 2.4.1。日常账号使用前台时，测试账号在自己的后台 Aqua 会话完成了编辑、普通保存、新进程重开和 GUI 切片。原始工程切出 68 层，改动后切出 112 层。两次预览读数均与各自的 G-code 模型挤出轨迹一致。本轮计 **SHADOW**。后台原生导出面板未能写出文件。

## 工程与切片

1. 将仓库的 `fixtures/agent_layer_cube.3mf` 复制到测试目录。通过辅助功能读取 Prepare 页的两个层高字段，确认均为 0.40 mm。只把常规层高设为 0.24 mm，确认输入并移出焦点后读回两个字段。
2. 通过 File → Save Project 保存到工作副本。编辑进程退出后将已保存文件复制为只读工程，并记录 SHA-256。宿主用 `harness.project_3mf.inspect_project` 对照原夹具，确认两个层高均符合预期，网格的 8 个顶点和 12 个三角形保持一致。
3. 用新进程和新配置目录重开只读工程，再次读到 0.24 和 0.40 mm。在 1200 × 800 的已捕获窗口定位 Slice plate，将点击绑定到本次 Orca 进程和窗口。完成后 Export G-code 菜单从禁用变为可用，Preview 页显示 112 层。
4. 另启新进程和配置目录，打开原始夹具的逐字节副本，同样从 Prepare 页点击 Slice plate。Preview 页显示 68 层。两次切片均使用 Snapmaker U1 的 0.8 mm 喷嘴配置。

| 独立检查 | 原始夹具 | 编辑后重开 |
| --- | ---: | ---: |
| 常规层高（mm） | 0.40 | 0.24 |
| 首层实际模型挤出 Z（mm） | 0.40 | 0.40 |
| 实际模型挤出层数 | 68 | 112 |
| 末层实际模型挤出 Z（mm） | 27.20 | 27.04 |
| 有正挤出的 XY 移动段数 | 1,907 | 2,882 |

每次都在进程退出前，用该进程的打开文件列表识别当前盘的临时 G-code，并核对文件所属用户及路径中的 PID。宿主用相同的 `harness.agent_layer_verify.analyze_gcode` 核对首层、相邻模型挤出层的 Z 增量和末层高度。用原始层高 0.40 mm 检查编辑后的产物时，检查器按预期拒绝。

## 原生文件面板

| 动作 | 实际结果 |
| --- | --- |
| File → Save Project | 工作副本实际落盘。退出后冻结，独立进程成功重开，切片完成后再次校验冻结文件摘要。 |
| File → Save Project as… | 在临时目录和测试用户的专用目录中均可打开面板并读回新名称。Save 按钮禁用，未生成另存文件。 |
| File → Export G-code… | 完成切片后可打开面板，能够进入新建的测试子目录并读回目标名称。确认名称后 Save 仍禁用，取消后检查目标目录为空。 |

两个 G-code 均来自 Orca 在 GUI 切片时写出的临时盘文件。后台保存面板禁用的原因仍待定位。若要检验会话前后台状态的影响，可让同一测试账号短暂使用前台，以相同程序、工作目录和夹具复测原生文件面板。

## 证据与收尾

本机证据位于 `artifacts/mac_layer/fKtKvC5a/`。其中 `comparison.json` 包含工程检查、两次 G-code 检查及 SHA-256。`baseline-preview.png` 和 `after-slice-button.png` 分别是原始与修改后的预览。`save_existing.log`、`reopen_slice.log`、`export_confirm_close.log` 和 `baseline_slice.log` 记录了保存、重开、导出阻塞和进程收尾。

回收时再次校验文件摘要。最后复核测试账号的 Orca 主进程为零，本轮 19 个临时 LaunchAgent 均已卸载，前台仍属于日常账号。Linux 本轮没有可用测试机。

## 原生保存面板对照

同日保持日常账号在前台，在测试账号的后台 Aqua 会话运行独立编译的 AppKit 小程序。五次原生保存面板试验均复现 Save 禁用。程序在显示面板前已指定本次测试目录和合法的新文件名，观察初始按钮状态时无需自动化输入文件名。

| 对照条件 | 实测结果 |
| --- | --- |
| 同一目录，分别配置不限类型、G-code 和 3MF | 三个独立进程中，文件名和目录均正确，文件名框有焦点，Save 均禁用，Cancel 均可用。 |
| 同一进程依次直接写文件、显示普通确认框、显示保存面板 | AppKit 程序在新建的专用子目录中成功创建并读回文件。普通确认按钮可用，辅助功能点击后程序收到了确认返回值。随后在该子目录打开系统保存面板，Save 禁用。 |
| 通过 Launch Services 正常启动同一个不限类型程序 | 在测试账号自己的桌面中，程序处于最前，保存面板为主窗口。约 11 秒内四次读取均为 Save 禁用、Cancel 可用。Save 的辅助功能帮助及描述均为空。 |

目前能定位到后台测试会话中的系统文件面板。独立程序已复现，因此复现不依赖 Orca、切片结果或特定扩展名。测试目录写入和普通辅助功能确认均通过。macOS 使用独立进程显示保存面板，程序在测试桌面最前与测试账号占用物理控制台是两个条件。[Apple NSSavePanel 文档](https://developer.apple.com/documentation/appkit/nssavepanel)

测试账号没有读取系统统一日志的权限，面板也没有给出禁用理由。本轮保持了用户指定的前台账号，尚无相同程序在测试账号前台的对照，不能由此断定 macOS 对所有后台会话实施相同限制。

原始日志已回收到同一证据目录，分别为 `native_panel_controls.log`、`native_input_pair.log`、`native_launch_services.log` 和 `native_session_diag.log`。同目录保留 `panel_comparison.m`、`panel_input_pair.m` 和 `native_control_driver.py` 供核对实验条件。

## 后台另存工程的两条路径

在 Mac 版的“文件 → 项目另存为…”（⌘⇧S）中，实测菜单项可用，系统面板能显示新的工程名。后台账号的 Save 按钮在输入新名字前后均禁用，取消后目标文件不存在。证据见 `standalone_native_as.log`。本次只在后台复测了这条菜单路径。

对于已有的 3MF，可在开始编辑前，以新名字复制原件，打开副本编辑，展开“文件”并选择“保存项目”。本轮副本名为 `layer-024-copy.3mf`。首次探针直接读取未展开菜单的保存项，读到禁用后中止。复试激活测试账号中的 Orca 窗口并展开“文件”菜单，保存项可用，保存后标题的未保存标记清除。

另一进程使用新配置重开同名副本，读到常规层高 0.24 mm、首层 0.40 mm。原件 SHA-256 与仓库夹具一致，修改前后保持不变。回收件 SHA-256 为 `a73d4238df01f01e1c039014035043f5385d9d95b89a3396fd78d485770be3fc`，独立工程检查确认网格几何一致。副本和日志 `standalone_copy_flow.log`、`standalone_copy_menu.log` 均保存在本轮证据目录。该操作适用于编辑前已经有磁盘原件的场景。

## 可复跑的仓库入口

从 Windows 仓库运行以下命令。将 `TEST_USER@MAC_HOST` 替换为实际 SSH 目标，也可使用已有 SSH 配置中的别名。独立密钥和主机指纹文件分别用 `--identity` 和 `--known-hosts` 指定。测试账号需已登录为后台桌面用户，所用的 Xcode 签名 Python 应已获辅助功能授权。安装包路径为 `/Applications/Snapmaker Orca.app`。

```powershell
.\.venv\Scripts\python.exe -B runner/macos_project_copy.py TEST_USER@MAC_HOST
```

每轮均从仓库传入固定夹具，在独立目录中新建 `layer-024-copy.3mf`，经 GUI 将常规层高从 0.40 改为 0.24 mm，首层保留 0.40 mm。保存、退出并冻结文件后再以新配置重开。宿主检查原件摘要、两次进程身份、重开字段、回收文件摘要以及网格。结果写入 `artifacts/mac_project_copy/<run_id>/result.json`，并保留 3MF。结果为 SHADOW 时退出码为 0，失败时记录 NON_GREEN 并返回非零。原生另存为与 GUI G-code 导出在此用例中分别记为 `NOT_TESTED`。

| 实机运行 ID | 编辑 → 重开 PID | 原件摘要前后一致 | 回收副本验证 |
| --- | --- | --- | --- |
| `b6ca5a53d7f244f19ffadc0329519214` | 196 → 240 | 是 | 0.24 / 0.40 mm，网格一致 |
| `87a39c6b95fc41bea9bf7f1c59bbc0bf` | 460 → 505 | 是 | 0.24 / 0.40 mm，网格一致 |

第二轮还在卸载后查询了本轮 LaunchAgent，确认注册项已移除，并复查本次 Orca 进程均已退出。
