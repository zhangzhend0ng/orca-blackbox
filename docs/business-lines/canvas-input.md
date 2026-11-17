# Canvas 数字输入适配（尚未启用）

2026-11-18。只新增只读采集器、纯绑定/权限判定及合成反例，不修改公共工具、模型循环、场景门禁或历史合同。真实客机 canvas 类别、PFD、Win32 采集与 Type 行为均为 **NOT VERIFIED**；`pilot_transform` 继续保持 blocked，不能仅凭本测试解封。

## 为什么需要这层

既有 transform 探索中，145.50 超过通用输入 0..99.9999；改用合法10仍因 Move ImGui字段不是原生 Edit 被拒绝。截图只显示外观，不能证明命中的 HWND 是canvas。方案不硬编码菜单/坐标，也不为模型提供新的业务动作工具。

`harness/canvas_input.py` 暴露：

```python
collect_window_evidence(run_id, app_pid, main_hwnd, loc=None) -> dict
bind_canvas(evidence, canvas_hwnd, *, approved_class, diagnostic_id) -> CanvasBinding
decide_type(scenario, text, loc, evidence, *, output_path, now_ns,
            binding=None, revoked=False) -> dict
numeric_text_allowed(scenario, text) -> bool
```

`CanvasInputRejected(ValueError)` 是权限拒绝。函数不捕获为允许，不静默改写文本。`CanvasBinding` 是冻结dataclass；只能由可信setup构造，不能从模型JSON反序列化。helper绝不输入、移动鼠标、改变焦点、启动进程或写文件。

## 只读诊断证据

collector先调用 `host_guard.in_guest()`，宿主拒绝发生在任何 Win32 API 之前。由唯一 `hv_go` 入口在 INTERACTIVE worker 调用。scope里的run/PID/main HWND由可信拥有者传入，不由模型选取。

顶层证据包含：schema_version=1、run_id、app_pid、process_created（GetProcessTimes创建FILETIME整数）、main_hwnd、session_id/active_session_id、thread_desktop/input_desktop、foreground_hwnd、GetGUIThreadInfo得到的focus_hwnd、WindowFromPoint命中target_hwnd、loc、screen、complete、captured_monotonic_ns、windows、opengl_candidates。

`loc=None`适合setup只读枚举，此时target_hwnd=0，不支持即时输入判定。带loc时必须是当前模型选择的桌面整数坐标。枚举main所有后代，同时记录foreground/focus/target；最多260条，达到上限标complete=false，不能绑定。窗口不存在/类名或矩形查询失败直接拒绝此次采集。foreign窗口仅保留身份/类名，不取标题和DC。

每条window记录hwnd/pid/thread_id/class/title/parent/root_hwnd/is_main_child/exists/visible/enabled/dpi/rect/client_rect/pixel_format。对owned窗口，使用GetDC→GetPixelFormat→DescribePixelFormat→finally ReleaseDC，只读采集索引、描述符计数、flags及完整PIXELFORMATDESCRIPTOR字段；从不SetPixelFormat或创建OpenGL上下文。

候选要求真实像素格式索引有效，Describe成功，并同时具备 `PFD_SUPPORT_OPENGL (0x20)`、`PFD_DRAW_TO_WINDOW (0x04)`。`opengl_candidates`只是诊断线索，不自动批准；PFD证明窗口支持OpenGL绘制，不证明具体ImGui数值字段已激活。绑定和每次决定会从raw row再次验证PFD，不信任候选数组标签。

root应将完整JSON写入本run的canvas_diagnostic.json，绑定诊断run ID、冻结源码/SUT及截图hash。诊断run无需MCP/模型，不修改应用，规范结果仍为NON_GREEN/diagnostic；从中独立确认真正canvas HWND及精确class后，才设计受控试验。**本文件没有填写任何猜测class名称。**

## 最小接线与权限

1. trusted setup采集证据，明确选择已批准class对应的本run owned canvas HWND。`bind_canvas`验证GL、主窗后代、完整owned父链、可见/启用、DPI96、session/desktop等，并保存创建时间、固定main矩形、父链及class/thread。
2. 输入前保留原始Type schema/options检查、预算、取消/撤销及串行锁。只有注册的pilot_transform可请求 `0 < 数值 < 1000`、最多4位小数；不接受负号、科学计数、前导零、Unicode数字、换行、任意字符串。其他场景的数值范围不扩大，非Edit输入仍拒绝。旧分支可完全保持不变。
3. 在同一输入调度进程即时重新采集loc证据，再调用纯decide_type，传该进程单调时钟now_ns；证据年龄上限1秒，未来时间同样拒绝。loc必须与采集的hit test一致并处于当前target rect。
4. canvas输入必须target==focus==绑定HWND、foreground==绑定main。run/PID/进程创建时间/主窗/desktop/session/class/thread/完整父链/main rect不得变化，PFD必须仍满足条件；任何撤销、foreign窗口、几何/DPI、锁屏桌面或身份异常都拒绝。
5. **canvas自身rect/client_rect允许合法变化**，例如AI收起侧栏；每次检查当前rect有效且包含在固定main rect内，位置用当前hit test与当前rect。不能把初始canvas宽度写死。主窗resize/DPI变化则仍拒绝，本轮不自适应重绑定。
6. 完整保存路径仅可投向owned原生Edit，前台须为owned `#32770` Save file as/Save file as:，Edit的root须是该对话框。正常模态框禁用main不应导致此路径被误拒绝。禁止把路径发给已绑定canvas。

返回值只有 `{route: native_edit|canvas_numeric, target_hwnd, diagnostic_id?}`；root仍调用原版Windows-MCP Type并记录完整raw evidence与决定，不复制Agent规划。数值白名单不能代替选中正确业务字段：操作后仍需截图和独立保存/重开/3MF/G-code oracle。

## 未解决的边界与停止条件

- OS focus==canvas不证明ImGui内部具体数字编辑器的焦点。原版Type的clear/点击/回车对实际字段是否正确仍需客机受控验证；不能据PFD批准任意画布键盘用途。
- 证据采集与原版输入之间有TOCTOU，collector不是原子OS事务。同权限恶意进程可以干扰或伪造文件；本helper不提供ACL隔离、独占桌面或生产安全沙箱。
- HWND绑定仅限本run。进程创建时间防止跨进程PID重用；同一进程销毁并以相同句柄/类/父链重建的窗口仍无法仅靠这些快照完全识别。
- 多个候选、缺focus/PFD、未知class、窗口重建、采集失败均停止，不猜候选、不自动放宽；布局变化仅允许已绑定canvas在固定main内部变化。
- root未做客机只读诊断前不得解封；实际输入前需确认冻结版本、取消收尾与原业务权限回归。诊断失败不得启动模型试错代替识别。

## 验证与 Harness 自检

命令 `python -B -m pytest unit_tests/test_canvas_input.py -q`：**56 passed in 0.16s**，仅合成窗口证据与guest gate模拟。没有调用宿主Win32桌面、客机、模型或relay；这不是GUI通过。

覆盖：明确binding正例、侧栏收起合法布局、数值边界、旧场景权限不扩大、无binding、进程重用、错run/类/父链/thread、主窗改变、DPI/屏幕异常、焦点/前台/foreign窗口、PFD缺失、撤销/陈旧证据、hit test不一致、锁屏、模态SaveAs及路径投canvas拒绝、guest gate先于Win32调用。

- (N) input-validation：信任边界输入均检查类型/范围；完整路径不扩大；不执行输入文本。PFD与身份从可信raw数据核对，不依据模型断言。
- (C) tool-calling：只读collector与纯authority；未新增planner/业务按钮路线；输入序列化与取消仍归公共层。原工具schema、timeout、预算必须继续存在。
- (C) risk-verification：权限扩展为高风险；只批准纯helper开发，明确Win32/GUI NOT VERIFIED；交付独立取消/越界/布局反例。
- (C) AI evaluation：合法替代路径（布局改变）与恶意/越界反例分开；历史失败保留，不能把纯单测加入业务成功分母。
- (C) error-handling：失败明确拒绝，DC始终释放；不重试输入或吞错误为成功。
