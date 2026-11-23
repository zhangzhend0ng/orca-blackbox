# Mac 搜索过滤物化探针（任务 A4）：三选一结论 = 过滤不生效

标签 `mac-author`，2026-11-23。宿主 GLM 总控派发，假说：参数页搜索框过滤
outline 树后结果集小，硬虚拟化的树会把匹配行全部物化，绕开"滚动全灭"死局。
**结论：过滤不生效**——"wall" 可靠进入真 wx 搜索框（逐字符 keycode + 点击聚焦
确认），但树行集纹丝不动，匹配结果进自绘下拉 popup（AX 仅 1 个空元素），
Return / Down+Return 提交通道同样不产生任何物化；全窗口扫描 wall_loops 为 0。

## 三轮运行（同一 LaunchAgent 通道，探针 `runner/macos/panel_probe13.py`）

| 轮 | 收获名 | 目的 | 关键产出 |
| --- | --- | --- | --- |
| v1 | `search_a4` | 任务书字面路径：outline 页找 preset 搜索框 | outline 页 AX 树中 **无** "Search in preset" 入口（无该 help 的按钮/字段）；发现树顶 (387,718) 有真 wx 过滤框，placeholder **"Search plate, object and part."**（w=381 AXTextField） |
| v2 | `search_a4_v2` | 树过滤框 keycode/unicode 两法 + preset 框跨视图存活 | keycode 逐字符 "wall" **完整落框**（AXFocused=true 确认）；unicode 整串法因 popup 抢焦点未落；preset 框在 flat 页可展开 (401,728) 但**切回 outline 即消失**（`preset_field_outline: null`） |
| v3 | `search_a4_v3` | 提交通道补测 + 全窗口物化扫描 + flat 页 preset 框严谨重测 | 见下表；`materialized_wall_rows: 0`，Phase C（焦点/写探针）按条件未触发 |

v3 主证据（`v3_dumps/`，文件名与状态一一对应）：

| 状态 | 树行数 | wall 行 | popup | 全窗口元素 / wall |
| --- | --- | --- | --- | --- |
| outline_baseline | 17 | 0 | 无 | — |
| tree_keycode（键入 "wall" 后） | 17（add 5 / remove 5=指针串抖动，role/x/y 集合不变） | 0 | AXUnknown (361,742) **412×452**，1 元素 | 76 / 0 |
| tree_return（Return 提交后） | 17 | 0 | 同上 | 76 / 0 |
| tree_down_return（Down+Return 后） | 17 | 0 | 同上 | 76 / 0 |

- 落框证据：键入后 `field_value: "wall"`；Return 后 `app_focused` =
  该搜索框自身（role=AXTextField, placeholder="Search plate, object and part.",
  value="wall", spot=[387,718]）——输入确实进了 wx，焦点确实在框上。
- flat 页 preset 框重测（v3 Phase B）：本轮点击聚焦失败（app_focused=AXWindow，
  值 ""，如实记录）；扁平列表 45→45 无变化。叠加 A2 panel4 证据（值曾落
  "wall" 仍不过滤），preset 框两条路都不过滤。
- 清框通道：popup 打开后 Escape / Cmd+A+Backspace 均清不掉（焦点被 popup
  接管，v2 `tree_clears` 两法后值仍 "wall"）。

## 对 A2 旧结论的修正与确认

1. **修正**：A2「真键入只落首字符」是探针粗糙所致——逐字符 keycode
   （120ms 间隔，keyDown/keyUp 成对）+ CGEvent 点击聚焦后，"wall" 四字符
   完整落框。输入通道本身无罪。
2. **确认**：过滤语义不存在于 AX 可见层。搜索框驱动的结果是自绘下拉
   （412×452，AXUnknown 窗口仅 1 个空元素），既不过滤 AXOutline 也不过滤
   扁平列表；这与 A2 对 preset 框「结果在自绘 popup」的归因一致，现在对
   树自己的过滤框也成立，且补测了 Return / Down+Return 提交通道均为无效。
3. **推论**：「搜索过滤 → 物化匹配行」在 Mac 2.4.1 上不可达；wall_loops
   物化缺口回归 A2 的 blocked 归因（outline 硬虚拟化 + 自绘渲染），上游
   若把搜索结果或参数树完整暴露为 AX，缺口才消失。

## 纪律与预算

- 只读保持：三轮均无 AXValue 写入、无保存、无项目脏化（Phase C 条件分支
  未触发，"3" 写探针未执行）；datadir 一次性播种后丢弃。
- 通道：一次性 LaunchAgent（gui/502 后台 Aqua 会话，签名 Python.app），
  驱动 `tools/mac_panel_probe.py panel_probe13.py <harvest>`；未触碰前台
  coil（console 501）；无新 TCC 依赖，无权限弹窗。
- GUI 预算：三轮合计约 8 分钟（红线 ≤15 分钟）；各轮 `orca_left: []`。

## 溯源

- 原始收割（本机，git 惯例不入库）：`artifacts/mac_probes/2026-11-22/search_a4{,_v2,_v3}/`。
- 本目录：v1/v2 `result.json`（关键 note 全量）+ `v3_dumps/`（result、
  各状态 outline census、全窗口 dump、popup dump、flat 前后 census、
  worker.log、search_probe.json 汇编）。
- 复跑：`.venv/bin/python -B tools/mac_panel_probe.py panel_probe13.py <name>`。
