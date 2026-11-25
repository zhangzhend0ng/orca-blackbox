# 飞书 #250 添加负零件

飞书记录 `reczz28aa4fiYT9f`。原行要求选中盘上对象 A，右键打开「添加负零件」二级菜单，在二级菜单选择形状或文件，观察负零件的区别颜色，并确认切片后的局部挖除。

独立入口 `m7x_250_negative_part` 使用 `agent_layer_cube.3mf`，每轮独立启动两个 profile 并复制同一单立方体夹具。目标场景通过二级菜单的 `Load...` 选中 `cutter.stl`。保存的项目用于核对唯一打印实例中存在 `normal_part` 和 `negative_part`，且主体的世界坐标范围不变。对照场景直接切未加负零件的同一夹具。

从两次实际切片导出的 G-code 提取对象范围内的正挤出线段，按保存件读出的世界坐标将线段裁至切除区和对侧保留区。通过要求切除区在基线有超过 10 mm 的正挤出，负件切片中低于 0.01 mm，对侧保留区两份文件均有超过 10 mm 正挤出，且对象层数相同。裁剪检测整段路径，可捕捉端点均在区域外但中间穿过区域的挤出。

离线对照以合成输入确认正常差集可通过，基线对自身、已切对自身、区域全丢失和交换输入均会拒绝。异色判据也验证了样本相同拒绝、加入相邻中性灰区域通过。

## Hyper-V 实跑

2026-11-25 14:56:33 +08:00 领取。全部 GUI 证据来自 `win11-test` 的 `test` 交互会话，运行 [Orca 2.4.0](a7a65272-build.json)。

| 提交 | 派发（北京时间） | 场景完成（北京时间） | 结论 | 证据 |
| --- | --- | --- | --- | --- |
| `7d9c87c1` | 15:08:52.404 | 15:10:16.150 | RED。对象 A 的右键菜单出现且列出 Add Negative Part。鼠标悬停后子菜单未得到验证，后续负件添加和切片未执行。 | [日志](7d9c87c1-case.log) · [收据](7d9c87c1-receipt.json) · [JUnit](7d9c87c1-junit.xml) · [Prepare 原始画面](7d9c87c1-prepare-before.png) |
| `df2916ab` | 15:15:10.528 | 15:17:01.065 | RED。真实键盘打开并验证了二级菜单，选择 `Load...`，文件选择器读回 `cutter.stl`。GUI 验证负件渲染与附着，目标切片完成，预览区旧导出入口未生成 G-code。 | [日志](df2916ab-case.log) · [收据](df2916ab-receipt.json) · [JUnit](df2916ab-junit.xml) · [加负件后的 Prepare 画面](df2916ab-prepare-negative.png) · [项目](df2916ab-negative-project.3mf) |
| `a7a65272` 首轮 | 15:26:25.228 | 15:29:01.723 | **GREEN**。场景墙钟 156.495 秒，负件与基线 PID 分别为 `10052`、`11920`。 | [日志](a7a65272-run1-case.log) · [收据](a7a65272-run1-receipt.json) · [JUnit](a7a65272-run1-junit.xml) · [逐区读数](a7a65272-run1-analysis.json) |
| `a7a65272` 独立复跑 | 15:29:10.214 | 15:31:47.661 | **GREEN**。场景墙钟 157.447 秒，负件与基线 PID 分别为 `6540`、`1640`。 | [日志](a7a65272-run2-case.log) · [收据](a7a65272-run2-receipt.json) · [JUnit](a7a65272-run2-junit.xml) · [逐区读数](a7a65272-run2-analysis.json) |

从领取至首次 GREEN 为 32 分 28.723 秒，首次通过前有 2 次客机实跑失败。两个通过轮次使用同一个提交，各自从新的夹具副本和 profile 执行。

## 飞书原行对照

| 飞书预期 | 两轮客机证据 |
| --- | --- |
| 弹出二级页面并添加负零件。 | 选中盘上唯一主体，通过消息右键打开其原生菜单。键盘高亮 `Add Negative Part`，按向右方向键后读取与该项关联的可见子菜单句柄，再确认高亮 `Load...`，文件选择器读回实际 STL 路径。保存件含同一个打印对象下的 `normal_part` 和 `negative_part`。主体 X/Y/Z 范围为 `[122,149] / [122.5,149.5] / [0,27]` mm，负零件为 `[141.5,153.5] / [118,130] / [-2.5,29.5]` mm。 |
| 负零件以不同颜色显示。 | 原始 Prepare 画面显示主体前右角的半透明灰件。排除白色选择框后，两轮均在主体右缘得到 278 个相连像素，灰件 BGR 中位数为 `(96,97,95)`，彩色主体为 `(48,136,178)`。 |
| 切片后该区域从主体中挖除。 | 两轮分别执行 Slice Plate 并通过 File > Export > Export G-code 导出。在切除体积内部，两轮的对象正挤出路径长度均从 `535.317` mm 降至 `0`，对侧保留区为 `613.017` → `535.317` mm，两份 G-code 均为 68 层。以同一基线代替负件导出件或把切除体积移到对侧时，离线复算均拒绝。 |

| 轮次 | 负零件场景 | 同盘切片工件 |
| --- | --- | --- |
| 首轮 | [截图前](a7a65272-run1-prepare-before.png) · [截图后](a7a65272-run1-prepare-negative.png) · [STL](a7a65272-run1-cutter.stl) · [3MF](a7a65272-run1-negative-project.3mf) | [基线](a7a65272-run1-baseline.gcode) · [负件](a7a65272-run1-negative.gcode) · [SHA-256 清单](a7a65272-run1-object_artifacts.json) |
| 复跑 | [截图前](a7a65272-run2-prepare-before.png) · [截图后](a7a65272-run2-prepare-negative.png) · [STL](a7a65272-run2-cutter.stl) · [3MF](a7a65272-run2-negative-project.3mf) | [基线](a7a65272-run2-baseline.gcode) · [负件](a7a65272-run2-negative.gcode) · [SHA-256 清单](a7a65272-run2-object_artifacts.json) |

## 复跑入口

确认 `win11-test` 空闲，在具备 Hyper-V 权限的 PowerShell 中同步待测提交。使用项目既有 v3 检出时先执行 `runner/guest_v3_bundle_sync.ps1 -Head <完整 SHA>`。

```powershell
$env:ORCA_BB_GUEST_SANDBOX = 'C:\coil\orca-blackbox-v3-r1'
& .\runner\hv_go.ps1 -Cases m7x_250_negative_part -NoSync
# 等 suite 回到 Ready 且 regress_summary.txt 写入本轮结果后收割
& .\runner\hv_harvest.ps1
```

日志给出本轮 `artifacts/feishu-object-cases/250/run-*` 的客机目录。两份 G-code、GUI 保存的负件项目和 Prepare 前后截图保存在该目录。

在仓库根目录可离线复算两轮切除和保留区读数。

```powershell
@'
import sys
from pathlib import Path

sys.path.insert(0, 'tests')
from negative_part_oracle import measure_difference, project_boxes

root = Path('docs/runs/evidence/feishu-250-251-2026-11-25/row-250-hyperv')
for run in (1, 2):
    base = f'a7a65272-run{run}-'
    boxes = project_boxes(root / (base + 'negative-project.3mf'))
    a, b = [root / (base + name) for name in ('baseline.gcode', 'negative.gcode')]
    print(measure_difference(a, b, boxes['normal_part'], boxes['negative_part']))
'@ | python -B -
```
