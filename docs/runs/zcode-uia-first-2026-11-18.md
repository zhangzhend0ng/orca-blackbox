# UIA 优先路线验证 2026-11-18

## 原生 Save As 第一闸

源 `472e0bdd7d5d20c49cc66f58637a8f24c1ae948c`，run `cc73dbd6ca30a22843068dc0abf78608`。通过 `hv_go.ps1` 在 `win11-test` 用 ZCode Snapmaker `glm-5.3-flash` 验证预打开的 Save As。模型入口仅开放 Snapshot、Type、Click、Wait、ControlStatus，坐标与截图均不在合同内。

seq1 用 UIA 属性找到 `File name:`（EditControl、AutomationId=1001）和 `Save`（ButtonControl、AutomationId=1）。seq2 用 ValuePattern 写入精确分配的路径并读回相同值。seq3 InvokePattern 调用成功返回。seq4 前台切换到同一 PID 的另一个 HWND，旧观察分支只接受原对话框或主窗，拒绝了该状态。未回收到 3MF/G-code，正式 NON_GREEN，清理确认。新增 Invoke 后的 owned 窗口文本与对话框存活观察，用 UIA 继续分诊。
