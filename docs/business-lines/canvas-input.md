# Canvas 数字输入适配（尚未启用）

2026-11-18。只新增只读采集器、纯绑定/权限判定及合成反例，不修改公共工具、模型循环、场景门禁或历史合同。客机只读probe bb64f8a261f74ed4b78fe2a8aed577aa已观察到唯一可见wxGLCanvas/GLCanvas；外部PFD均为0（unknown），实际内部字段的Type语义仍为 **NOT VERIFIED**；`pilot_transform` 继续保持 blocked，不能仅凭本测试解封。

## 为什么需要这层

既有 transform 探索中，145.50 超过通用输入 0..99.9999；改用合法10仍因 Move ImGui字段不是原生 Edit 被拒绝。截图只显示外观，不能证明命中的 HWND 是canvas。方案不硬编码菜单/坐标，也不为模型提供新的业务动作工具。

`harness/canvas_input.py` 暴露：

```python
collect_window_evidence(run_id, app_pid, main_hwnd, loc=None) -> dict
bind_canvas(evidence, canvas_hwnd, *, approved_class, diagnostic_id, approval=None) -> CanvasBinding
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

root应将完整JSON写入本run的canvas_diagnostic.json，绑定诊断run ID、冻结源码/SUT及截图hash。诊断run无需MCP/模型，不修改应用，规范结果仍为NON_GREEN/diagnostic；从中独立确认真正canvas HWND及精确class后，才设计受控试验。**现有class来自该真实只读诊断，不是猜测；不能据此声称已证明GL driver或ImGui字段可输入。**

## 最小接线与权限

1. trusted setup采集证据，明确选择已批准class对应的本run owned canvas HWND。`bind_canvas`验证GL、主窗后代、完整owned父链、可见/启用、DPI96、session/desktop等，并保存创建时间、固定main矩形、父链及class/thread。
2. 输入前保留原始Type schema/options检查、预算、取消/撤销及串行锁。只有注册的pilot_transform可请求 `0 < 数值 < 1000`、最多4位小数；不接受负号、科学计数、前导零、Unicode数字、换行、任意字符串。其他场景的数值范围不扩大，非Edit输入仍拒绝。旧分支可完全保持不变。
3. 在同一输入调度进程即时重新采集loc证据，再调用纯decide_type，传该进程单调时钟now_ns；证据年龄上限1秒，未来时间同样拒绝。loc必须与采集的hit test一致并处于当前target rect。
4. canvas输入必须target==focus==绑定HWND、foreground==绑定main。run/PID/进程创建时间/主窗/desktop/session/class/thread/完整父链/main rect不得变化，默认PFD模式仍须每次满足PFD条件；显式observed模式须每次满足已审批class/title与固定provenance。任何撤销、foreign窗口、几何/DPI、锁屏桌面或身份异常都拒绝。
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


## 显式诊断批准模式（本次追加，未接输入）

`harness/canvas_approval.py` 注册唯一 `observed-wxglcanvas-v1`，mode=`observed_wxglcanvas`、version=1、class=`wxGLCanvas`、title=`GLCanvas`，绑定诊断run bb64f8a261f74ed4b78fe2a8aed577aa与其原始JSON SHA256 `ea1bea303abc1f675f2f8018fa9d1e241e4a65c224beec81fb5e20660746bd40`，以及冻结SUT SHA256 `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`。这只批准控件身份，不批准实际GL硬件能力、内部字段或业务通过。

trusted setup先独立验证实际SUT/诊断字节摘要，再调用 `resolve_approval(profile_id, diagnostic_sha256=..., sut_sha256=...)`；模型schema不得暴露profile、摘要、binding写入或mode选择。profile常量不是签名或秘密，不能把模型自报一致当作来源验证。

默认 `approval=None` 的bind仍要求PFD。仅显式传入已注册的CanvasApproval，且class/title和diagnostic_id精确匹配旧诊断run ID，才允许PFD未知的观察模式。绑定当前run实际owned HWND而不是复用旧run句柄；多个可见同类同标题候选直接拒绝。当前run/PID创建时间、完整父链、main矩形、focus、session/desktop、hit-test及短期新鲜度仍保留。父链每层现在都检查visible/enabled/DPI/有效矩形，修复了中间父容器disabled仍可获准的纯规则缺口。SaveAs原生Edit模态例外不受影响。

`binding_to_json(binding)` 导出；`load_canvas_binding(raw, run_id=..., app_pid=..., process_created=..., main_hwnd=..., approval=...)`严格检查16KB上限、exact fields、duplicate keys、NaN/Infinity、bool冒充int、不可变父链与可信scope；observed记录还必须提供独立的可信approval。它是严格校验，不是文件访问控制或同权限攻击防护。加载记录不能自行改变模式或将未知PFD转为“已验证OpenGL”。

## 原版Type源码语义及受控能力诊断

核对本地原wheel `windows_mcp-0.8.9-py3-none-any.whl`（SHA256 `e90e5b02b3e545991f203ce93cefb436a326861657968591653fa254105dc85d`）；已存展开快照与wheel内容经换行归一化后相同。以下行号均指wheel中的 `windows_mcp/desktop/service.py`：

- 875先`uia.Click`。877–888的caret start/end会发Home/End，若UIA判断多行则Ctrl+Home/End。
- 891–894的clear先等待0.5秒并查询FocusedControl；1033–1076中，已知非文本控件会返回“did not clear”警告，但主Type仍继续输入；FocusedControl未知None时反而发送Home、Shift+End、Backspace。没有Ctrl+A。不能把clear=True解读为已确认清空。
- 903–906短文本逐字SendKeys。canvas数字最长16字，因此不走20字及以上的剪贴板粘贴分支；保存路径仍只可进入原生SaveAs Edit。
- 909–912的press_enter会发送Enter。1078–1114的值不符/焦点移动/无法读回只是返回文本警告，不自动抛ToolError，原生工具completed不代表值正确。

首个受控能力诊断应独立于业务晋级：使用fresh fixture，由正常视觉操作者或AI从当前截图选择字段/loc，脚本不写菜单和坐标路线。未激活态应由授权层拒绝并记录original dispatch=false，不为“验证拒绝”向空canvas发数字；激活态需保留现场截图、可得到的UIA ValuePattern和读值证据。先验证最窄组合clear=False/caret=idle/press_enter=False，并证明旧值已选中且是替换而非追加；再单独确认Enter/Tab提交。clear、caret start/end与press_enter需要分别验证和组合验证，不能一次全部放开。异常状态、字段未证实或参数警告即停止，保留NON_GREEN。

最终仍须正常保存、停输、自然退出、冻结原文件、独立profile重开，检查+10X的3MF及实际G-code XY范围。Focus==canvas、像素格式、class/title或“Typed ...”答复均不能代替该证明。此追加不接dispatch、不解除transform的PILOT_BLOCKS。

本轮纯测试：`python -B -m pytest unit_tests/test_canvas_input.py unit_tests/test_canvas_approval.py -q`，95 passed（0.20s），只用合成证据；未执行GUI、VM、relay、模型或Git写操作。


## 隔离canvas_trial接线（能力试验，非transform解封）

root决定新增独立canvas_trial合同进行首个受控能力试验，普通pilot_transform继续blocked。此试验允许在内部字段状态尚未被独立证明的情况下，用fresh fixture、已有Click与原版Type研究最窄数字输入组合；成功Click和Focus==canvas均不作为字段已激活证明。上文“未激活态应拒绝”的建议是后续字段级授权目标，当前identity helper本身没有实现ImGui内部字段识别，不能冒称已完成该negative能力验收。

- `scoped_tool_schemas(..., scenario='base')`、`validate_input(..., scenario='base')`只有canvas_trial扩大到正数<1000，其他场景保留旧范围。trial schema按精确保存路径分支保留原生Edit选项；所有数值Type限定clear=False、caret_position=idle、press_enter=False。原版Type自身仍会Click，可能使先前选择折叠；试验就是要观察这项风险，而不是预先宣称覆盖写入成功。
- root成功执行原版Click后调用`guard.record_click(loc)`。canvas Type需要30秒内、同loc、同bound HWND的单次令牌；消费一次。令牌仅证明操作顺序，不证明激活态。完整保存路径继续要求原生SaveAs Edit，不会发往canvas。
- worker仅在canvas_trial读取已入仓`contracts/evidence/canvas-diagnostic-bb64.json`真实字节并核对固定诊断hash，以及已验证的当前SUTsha；绑定唯一可见exact class/title后，scope记录canvas_binding_json、canvas_approval_profile、canvas_diagnostic_sha256、canvas_sut_sha256和actor/contract_sha256。
- `canvas_setup.json`保存binding及原始census，PFD与internal_numeric_field_verified均明确false。输入guard仅在canvas_trial Type重新collect、load绑定和调用纯权限判定；raw证据单独保存在guard.last_canvas_evidence，由root控制器归档，native_trace只写compact摘要和外部证据引用，避免突破256KB限额。
- 试验必须保留MCP调用、截图、未派发拒绝与任何警告，最终仍走保存/停输/冻结/重开/3MF与G-code oracle。失败保留NON_GREEN，不因有canvas绑定或收到Typed答复而解封。

受影响纯回归：`python -B -m pytest unit_tests/test_canvas_trial_policy.py unit_tests/test_canvas_input.py unit_tests/test_canvas_approval.py unit_tests/test_native_save.py unit_tests/test_native_wait_compat.py -q`，160 passed（0.52s）。覆盖trial专属范围、条件schema与保存路径、最窄options、recent-click过期/错loc/错HWND/无令牌、一次消费、focus/撤销、原始证据分离及实际入仓诊断hash。未运行GUI、relay、模型，也未提交或推送。
