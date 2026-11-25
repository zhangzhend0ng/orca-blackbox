# Mac 线：阻塞是什么、恢复条件（2026-11-25）

任务是在 Mac 的后台测试账号里跑壁环数 2→3（`--goal walls`，候选 `ninehour1125-walls-1`，仓库在 636a733，01:35:35 起，见 `ledger.txt` 第一行）。**这一线今晚没有通过任何一次**：首次运行 NON_GREEN（run `5bb1a766`；run 号和评级只见于上级目录的 `findings-sheet.md`，宿主上没有它的收割件），随后 8 次探针（01:42–02:21）都没有走过启动这一步。Mac 口径本来也最高记 SHADOW，这个目标不对应飞书原行。

## 阻塞

- 前台账号 coil 的控制台会话自 2026-11-24 19:25:27 起锁屏：`console_sessions_0342.json`（03:42 的检查）里该会话 `CGSSessionScreenIsLocked` 为 `true`、`CGSSessionScreenLockedTime` 为 1795519527。测试账号 coilwin（uid 502）在另一个不在控制台的会话里。
- 测试会话本身可用：`probe6.log` 第 13–14 行是 `ax_trusted=True post_allowed=True session=True`，窗口服务器列出本会话 179 个窗口。
- 但这个会话里每个应用的 AX 树都读不出真正的窗口：`AXWindows`、`AXMainWindow`、`AXFocusedWindow` 返回的是一个标题为应用名、自指的 `AXApplication` 节点，不是带工程标题的标准窗口（`probe6.log` 第 74–100 行是测试 Orca；`probe_other1.log`、`probe_other2.log` 是 Finder、Safari、iTerm2、UURemote）。给 Finder、iTerm2 设 `AXEnhancedUserInterface` 返回 `-25208`（`probe_other2.log`）。
- 工作器要等到带工程标题的窗口才往下走，所以 `probe2.log`、`probe3.log`、`probe6.log` 停在 `baseline.launch`：`TimeoutError: Named project window did not open`。`probe4.log`、`probe5.log` 只看到 `supervisor` 等工作器 510 秒后报 `Mac worker timed out`，日志里没有工作器自己的报错。
- 不是应用的问题：`mac_probe6_baseline2.png`（02:15，1466589 字节，与 `probe6.log` 的 `shot=True size=1466589` 是同一张）里测试实例在渲染，工程 `baseline` 已装进标题为 `baseline` 的窗口。

## 不算证据的两处

- `probe1.log` 是探针自己的缺陷：复制过去的工作器里字符串断行（`SyntaxError: EOL while scanning string literal`），没有发出任何读取，不说明阻塞。
- `probe3.log` 里的 `EXC NameError("name 'ax' is not defined")` 也是探针读法的缺陷（受信读取里变量没定义），不是应用的返回；应用真正的返回见 `probe6.log`。

## 恢复条件

coil 的控制台会话由它的用户解锁。解锁后可以先检查（命令出自总控的会话状态文件，不在仓库里）：
`ioreg -n Root -d1 -a | plutil -extract IOConsoleUsers json -o - -`，看 coil 会话的 `CGSSessionScreenIsLocked` 是否为 `false`。
然后按运行记录「合并与回归」一节的 Mac 复跑入口重跑 walls → layer → 错层对照（`--wrong-layer-control`）。

没有做的事（据 `findings-sheet.md`；本目录的文件无法证明「没做」）：解锁、切换控制台、碰 coil 自己的 Orca 进程。

## 之后的处置（总控的说明，没有对应的文件）

- 到 08:20 的最后一次检查，控制台会话仍然锁着；本目录里最新的会话列表是 03:42 的那一份。
- 07:51 清掉了探针的暂存目录：今晚建的 9 个 `orca-bb-copy.*` 工作目录（探针日志里 `remote_evidence:` 指的就是它们，现在不在了）和 Mac 上的 `/tmp/ninehour_mac`。测试账号下没有留下测试应用的进程。
- coil 自己的 Orca（pid 69507，11-24 18:13 启动）没有被碰过。
- Mac 的 checkout 还在 `636a733`，第二次推送之后才移到最终提交。

恢复条件不变：coil 的控制台会话由它的用户解锁。

## 文件

| 文件 | 内容 |
|---|---|
| `ledger.txt` | 首次运行和 8 次探针的起始时间、HEAD、目标；探针只跑了工作器的暂存副本 |
| `probe1.log` … `probe6.log` | 6 次带应用启动的探针：报错尾部和 AX 读取结果 |
| `probe_other1.log`、`probe_other2.log` | 两次不带应用启动的探针：同一会话里其它应用的 AX 窗口 |
| `console_sessions_0342.json` | 03:42 的控制台会话列表（coil 锁屏，coilwin 不在控制台） |
| `mac_probe6_baseline2.png` | probe6 的截图，本目录唯一的一张 |

## 09:57 解锁之后的三次运行（追加于窗口结束前）

控制台会话在 09:57 的复查里已经解锁（`IOConsoleLocked = No`）。下面三次都停在比启动更晚的位置，上面的锁屏阻塞不再出现。

| 文件 | 内容 |
|---|---|
| `result_af903eb963c64ed4a777bedca5f05fe7.json`、`result_681c990797e149b381f96dc999d052c6.json` | 两次正式运行（提交 `6fc59b2`，候选标签 `ninehour1125-walls-2`、`-3`）。都是 NON_GREEN，`failure_stage` 是 `baseline.wall`；`guest.phases.baseline` 记有 PID、窗口标题 `baseline` 和读到的层高 0.4/0.4 |
| `walls_af903eb9_strength_tab.png` | 第一次失败时的整屏截图，页签行清晰可见 |
| `strength-tab-merged-line.candidate.patch` | 候选补丁：页签行被 OCR 合并时，用只含 Strength 的窄裁剪再读一次。只在草稿副本上跑过，没有合入 |
| `candidate-8f8efa35-report.json` | 候选探针的 worker 报告：基线读到壁环数 2，编辑后读到 3 并保存副本，基线切片回执在，重开后停在 `reopen.wall` |
| `ledger.txt` | Mac 上的起始时刻表，含这三次 |

失败签名：

- 两次正式运行：`RuntimeError: Strength tab label not found by OCR`。在那张截图上手工运行同一个 OCR（`swift ocr.swift <png> 360 700 460 190`，1 秒返回）得到 `376,764,132,18  Quality Strength`，两个页签是一个文本框；`go_strength` 要求某一行的小写恰好是 `strength`。
- 候选探针：`TimeoutError: Strength wall-loops OCR value mismatch in reopen`。页签在基线和编辑两个阶段都是经窄裁剪读到的（坐标 448,764，宽 59），重开阶段读壁环数值时没有在限时内读到 3，原因没有查。

没有做的事：没有改仓库里的 Mac 驱动，没有重试第三次。10:12 的状态：测试账号下没有 worker 和测试应用进程，控制台未锁。
