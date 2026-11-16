# Review: v3 AI 层高修改与 G-code 闭环（2026-11-16）

结论：APPROVE，限独立审阅范围内的代码进入受控客机试验。`m3d_param_reslice / ai-layer-1` 尚无真实 GUI 成功证据；本报告不将 fake UI 或生成的测试 G-code 记为业务通过。对外继续仅 SHADOW/NON_GREEN，release_eligible=false。

## 范围与独立性

本审阅者独立检查本批 `agent_protocol.py`、`agent_guest.py`、`agent_executor.py`、新增 `agent_business_ui.py`、`agent_layer_verify.py`、`agent_model.py`、`runner/agent_bridge.py`、`tools/v3_agent_host.py` 的增量及相关测试。原 tab verifier 保持原实现，并随兼容测试执行。

本审阅者编写 `agent_session.py`、`runtime.py` 的固定 case 接线、`test_agent_session.py` 及 `docs/V3_AGENT_LAYER.md`。这些部分本报告仅记录自检；协调者已独立逐段核对两 case 白名单、精确版本/verifier、原 tab 契约不变、fixture 摘要及 canonical root/guest-console，报告无阻塞，不以作者自检替代独立批准。已有 launcher/profile/farm_runner 用户改动不属于审阅范围，没有修改这些文件。审阅期间未调用 relay、Hyper-V 或 GUI。

## 验证记录

本审阅者执行 `python -B -m pytest unit_tests/test_agent_protocol.py unit_tests/test_agent_business_ui.py unit_tests/test_agent_executor.py unit_tests/test_agent_layer_verify.py unit_tests/test_agent_verify.py unit_tests/test_agent_model.py unit_tests/test_agent_bridge.py unit_tests/test_agent_host.py unit_tests/test_agent_session.py unit_tests/test_runtime.py unit_tests/test_v3_session.py -q`：269 passed，3.74 秒。该结果仅为无 GUI 验证。因 dev-guidelines 只读，反馈检查使用 `check_review_signals.py --dry-run`，结果 No signals detected。

独立比较原始 mixed_filament_test.3mf 与派生 agent_layer_cube.3mf：ZIP 成员列表相同，只有 `Metadata/model_settings.config` 内容不同；其余成员字节相同。派生文件 SHA-256 为 `a468c33bda6c79cd4edb3a4d134db50024f7283211452de3640cce7530993513`，匹配可信注册常量。原 tab 契约摘要保留 `4fe2d56332c5525524cceed2dccdc3a212995d742c98f828a86fcd15964c0901`，有回归断言。

## Harness: Tool Calling and Agent Control

`common/ai/tool-calling-and-agent-control.md`

Items 1–3 (C) — PASS：只增加第二个可信 case，没有平行 runtime。模型通过截图选择 edit 坐标与数值及下一工具；新 case 允许 observe/click/edit/slice/export_gcode/finish，旧 tab 仍为原三工具。模型输出不成为命令、文件路径或插件名；内部导出流程固定 run-owned 目标，目标已存在即拒绝。worker 不调用旧 m3d/m5a main。

Items 4–5 (C/A) — PASS：操作前核对应用身份、DPI/尺寸及模态可用性；edit 必须命中同 PID、同主窗的可见可用原生 Edit。输入采用 client_to_screen 转换。click 保留 tab band。新业务工具各最多 2 次，整体仍为 12 工具、8 模型、6 点击、host 600 秒、guest 900 秒。slice 最长 180 秒；bridge/client 采用 210/230 秒上限并受 host 剩余 deadline 限制，不扩整体预算。取消仍独立于模型额度，清理仍由 Job 事实确认。

Items 6–7 (C/A) — PASS：模型凭据留宿主，原 native CLI 隔离参数及子进程代理逻辑不放宽；美元成本未知。原 mailbox/response/observation 外形不变，仅新增可信副作用收据，按 run/seq/request hash/窗口/时间绑定。原始结果和文件不覆盖。运行目录与同权限进程仍是信任边界，没有 ACL 隔离声明。

## Harness: Input Validation

`common/security/input-validation.md`

Items 1–4 (N/C) — PASS：case 固定注册，未知能力拒绝；tab/new case 模型字段严格分流，非 edit 的 text 必须 null。edit 仅接受 0.16–0.56 十进制数字，允许错误但有效的 0.40 用于反例，不把成功值硬编码进执行工具。最新 observation_id、单调 seq、整数坐标及固定范围在 host/worker 边界校验，checker 再独立校验路径。

Items 5–7 (C) — PASS：证据采用已有有界、分块、取消可感知的读取，核验路径、链接/文件身份、freshness、长度与 hash。操作收据严格字段，固定 fixture 与 A/B 导出 hash 关联。PNG 不作为业务 oracle；BMP 用于完整非空截图证据，业务结论来自 G-code 运动。

## Harness: AI Evaluation and Regression Strategy

`common/ai/ai-evaluation-and-regression-strategy.md`

Items 1–3 (C/A) — PASS：独立 verifier 重算 trace/收据/进程与 A/B 文件，不使用模型完成声明、rc0 或 execution 上下文直接得出业务 pass。路径必须包含 slice/export/edit/slice/export 和 finish；业务同时验证精确配置回显、初层 0.40、实际对象正向 XY/E 挤出 Z 层序及 27 mm 范围。层序从运动计算，不相信 Z/HEIGHT 注释或文件变化。

Item 4 (C) — PASS：反例覆盖仅改 header/注释、旧文件、错误初层、仅塔/纯 E、无对象挤出、不完整块、乱序对象层、错误夹具/hash/request/time、缺少 edit、跨窗口范围及不支持坐标语义。完整路径但错误业务产物保留 path=pass/business=fail；未知语义不算通过。后台只读 verifier 取消后必须确认线程静止。

Items 5–7 (C/A) — 边界明确：该 oracle 验证固定 U1 输入的对象层高变化，不证明任意 G-code、全几何切片正确、固件执行或实物打印。模型真实来源与图像/动作链需由实际宿主记录补证；fake 测试不能替代真实看图决策。

## Harness: Risk and Verification / Requirements Gap

`common/planning/risk-and-verification-plan.md` Items 1–5 (C/A)，`common/planning/requirements-gap-analysis.md` Items 1–6 (C/A)。

PASS（试验准备范围）：复用原主链，业务产物、路径证据、模型动作和清理事实各有责任模块。真实试验必须取得两次 GUI 导出及目标实际层序；若只保存项目或只改变控件文本，不能降格修改本契约为通过。未知弹窗、编辑未提交、切片未完成或清理失败须如实失败；不以旧 m5 缺陷被修复作前提或结论。

## Harness: Review Checklist / Pytest Patterns

`common/code-review/review-checklist.md` Items 1–8 (C/A)，`python/testing/pytest-patterns.md` Items 1–5 (C/A)。

PASS：测试隔离 fake Win32/模型/传输，不启动应用；关键反例断言具体失败原因。GUI 输入一处一次、导出固定新文件、不采用旧导出隐藏重击后备。较长的 verifier 保留显式证据顺序，作为有理由的 (C) 偏离，不为此引入新解析或执行框架。

## 发现与闭合

- (C) G20 在对象外被忽略，逻辑坐标可被错当 mm；G92 XYZ 重设原点可伪造实际 Z。已全局拒绝不支持单位/坐标模式及 G92 XYZ，仅允许 G92 E；外部 G28/G2/G3 清空位置，之后须重新建立明确对象坐标。相应反例已通过。
- (C) 独立路径检查原先只限制 click 到窗口内，弱于执行协议 tab band。已增加固定 x/y 范围和反例。
- (C) pause 在 guard 耗时跨过截止时可能负 sleep。已 clamp 到零并增加时钟推进反例。
- (C) 新 slice 的 180 秒等待超过旧 bridge/client 上限。已按工具扩展有界等待，仍受整体 host deadline 限制。
- (C) 编辑数值最初过宽。已收敛为固定夹具允许的 0.16–0.56 范围，并覆盖端点及越界值；模型仍自行选择目标值。

## 尚待真实验证

实际 Quality/Edit 定位、wx 字段提交、Slice/Export 控件状态、保存对话框及关闭提示尚未通过本批客机运行。导出按钮 enabled 只是工具等待条件，最终 G-code oracle 才决定层高是否生效。首个真实 run 必须记录 CLI 图像输入/结构动作与 guest 请求 hash 关联，以及 Job 空、无强制终止/取消和确认 cleanup；后续负例须与正例、离线篡改重放分别标注。
