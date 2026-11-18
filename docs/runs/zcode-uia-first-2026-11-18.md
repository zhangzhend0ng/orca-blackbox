# UIA 优先路线验证 2026-11-18

## 原生 Save As 第一闸

源 `472e0bdd7d5d20c49cc66f58637a8f24c1ae948c`，run `cc73dbd6ca30a22843068dc0abf78608`。通过 `hv_go.ps1` 在 `win11-test` 用 ZCode Snapmaker `glm-5.3-flash` 验证预打开的 Save As。模型入口仅开放 Snapshot、Type、Click、Wait、ControlStatus，坐标与截图均不在合同内。

seq1 用 UIA 属性找到 `File name:`（EditControl、AutomationId=1001）和 `Save`（ButtonControl、AutomationId=1）。seq2 用 ValuePattern 写入精确分配的路径并读回相同值。seq3 InvokePattern 调用成功返回。seq4 前台切换到同一 PID 的另一个 HWND，旧观察分支只接受原对话框或主窗，拒绝了该状态。未回收到 3MF/G-code，正式 NON_GREEN，清理确认。新增 Invoke 后的 owned 窗口文本与对话框存活观察，用 UIA 继续分诊。

源 `9cadd7a`，run `dc685b49004cce9f1348d0ec70c497e0`。结构化 Snapshot 读出新增 owned 模态为 `Confirm Save As`，文字为 `fixture.3mf already exists. Do you want to replace it?`。纯 ValuePattern 写入读回了新路径，但未让 Windows 文件对话框按新值提交。覆盖按钮未被授权，保留 NON_GREEN，清理确认。随后通过 UIA 定向聚焦同一文件名 Edit，修改并恢复末字符以发出原生编辑通知，逐键守卫并再次读回精确路径，然后才允许 Invoke Save。

源 `7139740`，run `d0dbcd4d8ef7c6005f3f55c4b53826b1`。UIA SetFocus 后的焦点报告不等于已定位的文件名 Edit。Type 在发送全局键前报 `native_uia_filename_focus_changed`，没有 Invoke，正式 NON_GREEN，清理确认。随后改为每条原生编辑消息直接发给重新核对过的同一 UIA Edit HWND，并读回中间值与最终值。

源 `fcffb0f2fd15ea2508c4ac197aeac27a8f7d82a4`，run `d7299035e33b80969e0064a8d9b3e4fc`，Save As 第一闸通过，正式 SHADOW。6 次工具调用依序为 UIA Snapshot、文件名 ValuePattern 写入和读回、Save 按钮 InvokePattern、Wait、UIA Snapshot 确认关闭、ControlStatus。模型截图 0、坐标输入 0。原生编辑通知以 UIA 锁定的 Edit HWND 为接收方，通知后再次读回完整路径。独立重开所保存的 3MF，所有 fixture 设置及形状保持，切出 68 层，末层 Z=27.2 mm。清理确认。

- 3MF SHA256 `89743a1f8213a3dd1ba2298b8bcb15ca34926c470f6dc339daae447fb997da2e`
- G-code SHA256 `33b96a7c766fc3f960aba7a2699c32c3cdb1b908bf8f4e591a11bec0f0a10899`

## wx 与 ImGui 开发锚点

源 `fcffb0f`。层高 run `2d1838fd41fca5e5c3871bc371605f93` 完成 UIA 查询和侧栏裁图，ZCode 在 Click 派发前拒绝字符串型 `loc`。平移 run `c2776a6c2400d0b03086d7bb6b5263b1` 完成 UIA 查询和两张裁图，ZCode 在 Click 派发前拒绝空参数。两次均收取了 Snapshot/Screenshot 的可信收据，无 Click 到达桌面。两次的正式结果均为 NON_GREEN，清理确认。为 Click/Type 补上顶层的结构化字段声明，同时在 Snapshot 给出 Edit 的 UIA 边界，使自绘标签可与属性目标关联。

源 `ee84a61ee886e57bbe44cd34698bc70189c7ee59`，层高 run `bfd5c93af9571ba3ddc53f7099d7e407`。正式 SHADOW，清理确认。10 次调用含 2 张 wx 侧栏裁图、1 次原生 Edit 属性写入读回、0 次坐标输入。Save As 仍全程走属性。冻结 3MF 层高 0.24、首层 0.40，立方体保持，新 profile 重开后导出 112 层。

- 3MF SHA256 `1df22525520f1ede4d6d34a8a5e3627b7d2bd6c36479574ba25a300157319d0c`
- G-code SHA256 `0dcc5d1bdd63ff8936c7a8add5c2b6c83ea1ec7f951ee71634c0d1993c3b1227`

同源画布 run `ab480a1a3efe230b861c82240d0a1c3a`。结构化工具参数已传过 ZCode，Click 在 guest 被 `native_uia_save_dialog_required` 拒绝且未派发。根因是局部视觉 Click 经过裁图与控件检查后，误调了父类 Save As 门禁。改为复用普通 owned-window 门禁，再走已绑定的画布能力。该次保留 NON_GREEN，清理确认。

源 `6c5cfa8`，画布 run `cee7a86c1fb6e16e02178e50f989d73d`。成功派发 seq6 的画布选择。seq7 最近裁图的 X 范围 `[426,1100)`，seq8 试点 X=1477，守卫在输入前停住。NON_GREEN，清理确认。明确模型可以一次观察整个已登记画布区域以保留场景和工具的空间关系，点击必须落在最新裁图内，仍无全桌面视觉通道。

源 `6b3bfbae8b599a7f3e8ad37b1083e05016bb9603`，画布 run `52a21e14b5e0456bf5e965cb98970cf4`。16 次工具调用，画布裁图 4 张，3 次像素 Click，1 次受限画布数值 Type，Save As 全程为属性操作。正式 SHADOW，清理确认。冻结 3MF 证明全局 X+10 mm，其余设置、Y/Z 与形状保持。独立重开导出 68 层，实际物体挤出范围 X=132.41–158.59、Y=122.91–149.09 mm。PFD 与 ImGui 内部编辑器焦点仍未独立证明。

- 3MF SHA256 `be355d81ea9f388fe5d26525fdd0e1b988e241cd3ed64c62cc0c3ad30d775061`
- G-code SHA256 `00fad745db327c6a43db64514731ffccbe50e1be3cc185dce1a4585fa1887209`

## UIA 优先泛化预登记

三道开发闸通过后冻结。`tools/zcode_matrix.py --suite uia_generalization` 根据三份通过收据复核轨迹与清理，在首槽前写入源 SHA、模型 bundle、fixture、SUT、合同摘要和全部 run ID。各槽仅运行一次。用另一个批次记录[历史视觉坐标轮](zcode-generalization-2026-11-18.md)。

| 槽位 | 目标与初态 |
|---|---|
| `uia_general_wall` | 开发锚点。Quality，Wall loops=3 |
| `uia_general_slot2` | 开发锚点。Quality，给立方体分配逻辑材料槽 2 |
| `uia_general_bottom_strength` | 新目标。Strength，Bottom shell layers=6 |
| `uia_general_bottom_quality` | 同一新目标，Quality |
| `uia_general_y_quality` | 新目标。Quality，全局 Y+8 mm，保留 X/Z |
| `uia_general_y_others` | 同一新目标，Others |
| `uia_general_combo` | 新组合。Quality，Wall loops=3 和逻辑材料槽 2 |
| `uia_general_combo_dialog` | 同一组合，附加预打开的 owned Save As 对话框，需先用 Cancel 属性恢复 |

底层目标检查 3MF、G-code 配置与真实 Bottom surface 挤出。Y 平移检查世界三角面、保留项与重切物体挤出范围。组合同时核验配置、分配和 T1 物体挤出。仅用合成正反例预检新目标。沿用 [V3 规划](../V3_PLAN.md) 的八槽分母、投入阈值及停止条件。
