# 飞书 #238 未切片时切片导出条目置灰

记录 `reczz28aa4fiXhYu`（P1）要求盘上有模型但未切片时观察「文件→导出」里切片类条目的状态，执行切片后再次观察。预期「切片导出类条目置灰；切片完成后恢复可用」。

Snapmaker Orca 2.4.0，U1 0.4 mm、Generic PLA、0.20 mm Standard（`fixtures/feishu_std_cube.3mf`）。[构建摘要](build.json)

| 候选提交 | 会话 | 客机 | 场景耗时 | 离线复核 |
| --- | --- | --- | ---: | --- |
| `c378dee0…` | [首轮收据](c378dee0-run1-receipt.json) | GREEN | 149.725 秒 | 通过（51 项） |
| `c378dee0…` | [第二轮收据](c378dee0-run2-receipt.json) | GREEN | 147.204 秒 | 通过（51 项） |

两个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和同一夹具。每个会话打开未切片的标准立方体工程，读一次 File→Export 子菜单，点一次 `Slice plate`，等 File→Export 的 `Export G-code` 行启用后再读一次。

| 飞书预期 | 读数 |
| --- | --- |
| 切片导出类条目置灰 | 切片前读到的 7 行里，`Export plate sliced file... Ctrl+G`、`Export all plate sliced file...`、`Export G-code...` 三行禁用；另外 4 行（`Export all objects as one STL...`、`Export all objects as STLs...`、`Export Generic 3MF...`、`Export Preset Bundle...`）启用 |
| 切片完成后恢复可用 | 点 Slice 后 8.6 秒 `Export G-code` 行启用；再读一次，三行都启用，另外 4 行仍启用，行名与行序和第一次相同 |

行状态读的是原生菜单项的标志位（`harness/topbar_util.py` 的 `menu_items`）。逐项读数在 [analysis.json](c378dee0-run1-analysis.json)。

**头两轮没有像素证据。** 客机上 Export 子菜单没有在屏幕上展开（记录里 `menu_picture.image` 为空，原因写作 `the Export submenu did not open on screen`），那两轮的菜单状态只存在于 analysis.json 和 case.log。离线复核能把两者绑在一起，但不能重新观察界面。原因和后来的变化见文末。

离线复核用 `tools/replay_case_evidence.py`：先核对清单里的字节数与 SHA-256，再重判并做 24 个反例，每个收据启动一个独立进程，各约 7 秒。读数分三层：三次读到的行与启用状态；主线判据 `export_rows_expectation_gaps` 的重算结果与记录对照；与收据哈希绑定的 case.log——日志里两行 `[export] File > Export read: [...]` 必须和记录的两次菜单逐行一致，`'Export G-code' enabled 8.6s` 必须等于记录的秒数。反例包括切片前任一行启用、切片后任一行仍置灰、行缺失或重复、两次行序不同、改了 gaps、阶段顺序颠倒、换成别的工程、切片前工程已含 G-code、护栏未关、清单不符、日志里的菜单行被改。

```powershell
& runner/hv_go.ps1 -Cases m7x_238_export_disabled -NoSync
python tools/replay_case_evidence.py docs/runs/evidence/feishu-238-2026-11-26/c378dee0-run1-receipt.json docs/runs/evidence/feishu-238-2026-11-26/c378dee0-run2-receipt.json
```

计时：用例内每轮约 78 秒（打开工程 9.2、读菜单 27.2、切片 13.2、再读菜单 28.2），宿主派发到收割 127 秒。领取到首次客机通过（提交 `11858f1`，02:23:27）约 3 小时 24 分，其间 1 轮失败：Export 子菜单没有在屏幕上展开，用例当时因此中断；之后改成读原生菜单并把「没拍到」记为事实。随后的正式双会话没有失败轮。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。

实体机 fa706g3 的一次 SHADOW：`c378dee`（96.4 秒）RED。它读到的两次菜单与客机相同（切片前三行禁用，切片 8.1 秒后三行启用），但收尾时 File 菜单的窗口没有关上，用例按 RED 结束（[日志](fa-c378dee0-06ad1c58064e-case.log)）。只计 SHADOW。

**2026-11-26 07:03 起客机上也出现了，用例已改，并在改后的提交上重新验收。** 收尾的金丝雀里这一条连红三次（`1387bc8c…`，119.325 / 120.297 / 118.624 秒，三次读数都已读齐）：两次菜单读的是对的，第二次读完之后 File 菜单关不上。原因分两层。客机上此前子菜单从来没有为真实光标展开过，所以 `WM_CANCELMODE` 就够；06:21 关掉客机上那个铺满整屏的 `Windows Security` 遮罩之后，真实悬停第一次生效，子菜单在屏幕上展开（上面说的「没有像素证据」从此不成立），而为真实光标展开的菜单不理会 `WM_CANCELMODE`，要真实 Esc 键才关——第二次读菜单时真实 Esc 键没有关掉它，和 fa 上一样的签名。`dismiss_menus` 现在在真实 Esc 键之后，把 Esc 投递给每个还开着的菜单窗口（`39d9222…`）。改后的两个新会话都通过，日志里都有 `Escape posted to the menu windows closed them`：

| 会话 | 候选提交 | 客机 | 场景耗时 | 离线复核 |
| --- | --- | --- | ---: | --- |
| [第三轮收据](39d92227-run1-receipt.json) | `39d92227…` | GREEN | 111.291 秒 | 通过（51 项） |
| [第四轮收据](39d92227-run2-receipt.json) | `39d92227…` | GREEN | 111.873 秒 | 通过（51 项） |

这两轮每轮约 19 秒就读完两次菜单（头两轮各约 55 秒），并且留下了菜单的截图：[切片前](39d92227-run1-menu-before.png)、[切片后](39d92227-run1-menu-after.png)。回放工具原来只认「没有截图」那种日志行，为这两轮放开了带截图名的那一种（`5031a0a…`），头两轮的收据回放仍然通过。
