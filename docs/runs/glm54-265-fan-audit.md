# #265 悬垂风扇与普通面进给离线复核

2026-11-24，以同一欧特克 FDM 夹具的已收割 Snapmaker Orca 2.4.0 G-code 比对。Quality 和 Strength 两个 Script 导出均为 SHADOW。两者目标槽已保存悬垂风扇 80%、阈值 10% 和翘边减速开启，但两个产物均无 80% 主风扇指令。普通面的 167 段进给变化均为顶面提速，历史翘边减速单变量对照复现了这 167 段。

## 主风扇从第二层起为 100%

| 证据 | 基线 | Quality / Strength 各自 |
|---|---:|---:|
| 主风扇 `M106 S0` / `M106 S255` 指令数（含机器宏中的重复写入） | 4 / 486 | 4 / 1,039 |
| 辅助风扇 `P2` 的 PWM 与次数 | S0 × 5、S178 × 1 | S0 × 5、S178 × 1 |
| 任一风扇通道的 PWM 204 指令数 | 0 | 0 |
| `Overhang wall` / `Bridge` / `Internal Bridge` 挤出段数，全部处于主风扇 S255 | 452 / 963 / 3,150 | 452 / 963 / 3,150 |
| `Bottom surface` / `Top surface` 挤出段数 | 1,216（S0）/ 2,350（S255） | 1,216（S0）/ 2,350（S255） |

正式比较的 `overhang_80pct_matches=0` 指基线与目标中几何匹配的 1,415 段悬垂墙和外桥里，有效主风扇 PWM 落在 203–205 且相对基线发生变化的段数为零。独立读数从整份文件跟踪模态风扇和进给，补查全部角色（含正式判据未列入的 3,150 段内桥）、显式风扇指令、弧移和重复几何键。两份正式配对的五个目标角色均无漏配或重复几何键，三个导出的首层均无悬垂墙或桥接挤出。多出的 S255 指令没有改变相关路径的模态状态。

发布标签 `sm-v2.4.0`（`b1831e5dcb464172de33783142425aafda834fbc`）给出一致的解释。普通冷却的槽 1 最小风扇和最大风扇均为 100%，`reduce_fan_stop_start_freq=1` 以最小值起算，首层关闭，之后没有爬升。源码只在 `overhang_fan_speed > fan_speed_new` 时受理悬垂风扇覆盖，设定 80 无法覆盖普通 100。内桥设置为 `-1`，回退到同一覆盖条件。该 Klipper 输出用 `unsigned(255.5 * percent / 100)` 产生 S 值，80 对应 204。参见上游 `src/libslic3r/GCode/CoolingBuffer.cpp:735–797,846` 和 `src/libslic3r/GCodeWriter.cpp:897–928`。

`GCode.cpp:7852,8076–8089` 的 10% 分支检查局部支撑重叠不高于 0.9，外桥和已标记悬垂墙按角色直接满足判定。最终导出不带每段重叠率，且本夹具的覆盖条件始终为假，无法量到跨过 10% 的边界。源码解释针对同发布标签，与产物的指令和配置一致，未对运行二进制做源码等价证明。

## 167 段是顶面提速

| 层（从 1 起） | Z（mm） | 段数 | 模态 F 变化（mm/min，基线 → 目标） |
|---:|---:|---:|---:|
| 97 | 19.45 | 6 | 6593 → 9493.002 |
| 110 | 22.05 | 62 | 9252 → 9701.105 |
| 120 | 24.05 | 24 | 8438 → 9621.777 |
| 124 | 24.85 | 5 | 9615 → 9684.635 |
| 140 | 28.05 | 21 | 5842 → 5869 |
| 141 | 28.25 | 13 | 6198 → 6240 |
| 143 | 28.65 | 7 | 6195 → 6281 |
| 144 | 28.85 | 10 | 5595 → 5735 |
| 146 | 29.25 | 8 | 5090 → 5386 |
| 150 | 30.05 | 11 | 4489 → 4744 |

例如第 97 层从 `(116.584,136.371)` 到 `(115.710,135.496)` 的顶面挤出为 `G1 X115.71 Y135.496 E.039`，基线第 183363 行、Quality 第 184171 行、Strength 第 184170 行。其各自上一行明确设置不同 F，主风扇均为 S255。全部 3,566 段配对普通面的主风扇状态不变；1,216 段底面进给不变。墙线有 2,521 段减速（2,069 外墙、452 悬垂墙）。

历史 `4b8da518` 是实测单变量对照。其完整导出配置相对基线只改变 `slowdown_for_curled_perimeters=0→1` 及对应的 `different_settings_to_system` 记录，阈值和速度仍为 50% / 100%。它复现相同的墙线减速计数，167 段顶面的几何键及各段变化前后 F 均与正式配对一致。源码中翘边减速标志进入墙线品质估计，冷却缓冲随后依据整层动作耗时和最短层时（本夹具槽 1 为 8 秒）重算可调挤出的 F。墙线变慢会减少为同层顶面追加减速的需要，与十层只出现提速的方向一致。产物足以用单变量对照将顶面变化归到开关，内部原始层耗时和冷却计算的逐层分支未采样。参见上游 `GCode.cpp:7702,7722`、`CoolingBuffer.cpp:327,650–705,908`。

## 复算与机器记录

| 样本 | Run ID | G-code SHA-256 |
|---|---|---|
| 同夹具基线 | `0cccce4a3b3f40798bcab64c8a815680` | `4e1b6d62ef07f56878b598edb20df27e862a24b133a4e38f45ea66c73f375ec4` |
| Quality | `62854736359b4fc1a44747cfe8437064` | `ef2c0e8a616e79edfb0ef94da42ee13034dcfbd8841ea08b16eb73bcec21935c` |
| Strength | `6ffe565d35bf42b7809c4ed403649599` | `7071692fabe0182ffc366f893f2d3bd14a9a2b23fad90ac531eed069d34f2323` |
| 翘边减速对照 | `4b8da518325c4ce98057c3b30010aa86` | `ed858d9fe5009581fc95c1eb728c0867ea2cb741b6603ccf88f19ee68ed87ea1` |

在仓库根目录运行。历史收割件目前位于 `.worktrees/glm`，正式运行位于根仓的收割目录。

```powershell
$old = '.worktrees/glm/artifacts/windows_mcp_harvest'
$runs = 'artifacts/windows_mcp_harvest'
$base = "$old/0cccce4a3b3f40798bcab64c8a815680/exports/0001.gcode"
$quality = "$runs/62854736359b4fc1a44747cfe8437064/exports/0001.gcode"
$strength = "$runs/6ffe565d35bf42b7809c4ed403649599/exports/0001.gcode"
$curlOnly = "$old/4b8da518325c4ce98057c3b30010aa86/exports/0001.gcode"
python -B tools/audit_265_fan.py $base $quality $strength $curlOnly
function ExportConfig($file) {
    $inConfig = $false
    foreach ($line in [IO.File]::ReadLines((Resolve-Path $file).Path)) {
        if ($line -eq '; CONFIG_BLOCK_END') { break }
        if ($inConfig -and $line -match '^; [a-z0-9_]+ = ') { $line }
        if ($line -eq '; CONFIG_BLOCK_START') { $inConfig = $true }
    }
}
Compare-Object (ExportConfig $base) (ExportConfig $curlOnly)
```

实体 Win10 `DESKTOP-FA706G3` 在 21:15 左右经固定主机指纹的专用 SSH 通路执行离线读数，Python 进程记录 1.987 秒。输入限制为前三行测试 G-code 和读数脚本。执行目录为 `C:\coil\orca-blackbox-glm\artifacts\glm54-265-fan-audit`，使用该测试仓已有 `.venv\Scripts\python.exe`，参数依次为 `-B audit_265_fan.py baseline.gcode quality.gcode strength.gcode`。宿主保存的回执 `artifacts/glm54-265-fan-audit-fa706g3.json` SHA-256 为 `1f3f115a62409655a0ee35bac3f2cc1e75a3fa804e381bb584b7e4014a2e7bed`。回执的 `baseline`、`variants`、`pairs` 与宿主离线复算逐字段一致。翘边减速对照在宿主另行计算。本次验收证据是既有导出件的离线复核，GUI 和打印机均未运行。

本次 agent 墙钟约 6 分钟，含 SSH 自动审批、读数与文档整理。实体机的 1.987 秒为读数程序耗时，SSH 和传输未单独计时。
