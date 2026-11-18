# UIA 优先路线验证 2026-11-18

## 原生 Save As 第一闸

源 `472e0bdd7d5d20c49cc66f58637a8f24c1ae948c`，run `cc73dbd6ca30a22843068dc0abf78608`。通过 `hv_go.ps1` 在 `win11-test` 用 ZCode Snapmaker `glm-5.3-flash` 验证预打开的 Save As。模型入口仅开放 Snapshot、Type、Click、Wait、ControlStatus，坐标与截图均不在合同内。

seq1 用 UIA 属性找到 `File name:`（EditControl、AutomationId=1001）和 `Save`（ButtonControl、AutomationId=1）。seq2 用 ValuePattern 写入精确分配的路径并读回相同值。seq3 InvokePattern 调用成功返回。seq4 前台切换到同一 PID 的另一个 HWND，旧观察分支只接受原对话框或主窗，拒绝了该状态。未回收到 3MF/G-code，正式 NON_GREEN，清理确认。新增 Invoke 后的 owned 窗口文本与对话框存活观察，用 UIA 继续分诊。

源 `9cadd7a`，run `dc685b49004cce9f1348d0ec70c497e0`。结构化 Snapshot 读出新增 owned 模态为 `Confirm Save As`，文字为 `fixture.3mf already exists. Do you want to replace it?`。纯 ValuePattern 写入读回了新路径，但未让 Windows 文件对话框按新值提交。覆盖按钮未被授权，保留 NON_GREEN，清理确认。随后通过 UIA 定向聚焦同一文件名 Edit，修改并恢复末字符以发出原生编辑通知，逐键守卫并再次读回精确路径，然后才允许 Invoke Save。
