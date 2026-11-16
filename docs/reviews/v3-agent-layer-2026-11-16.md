# Review: v3 AI 层高修改与 G-code 闭环（2026-11-16）

结论：APPROVE，限独立审阅范围内的修复进入受控客机再试验；新增 session 取消接线由协调者独立复核。首次真实探针暴露的夹具前提缺失已在夹具与 oracle 两侧补齐；此前和本次 APPROVE 均不是业务通过。`m3d_param_reslice / ai-layer-1` 尚无接受的真实 GUI 成功证据；本报告不将 fake UI 或生成的测试 G-code 记为业务通过。对外继续仅 SHADOW/NON_GREEN，release_eligible=false。

## 范围与独立性

本审阅者独立检查本批 `agent_protocol.py`、`agent_guest.py`、`agent_executor.py`、新增 `agent_business_ui.py`、`agent_layer_verify.py`、`agent_model.py`、`runner/agent_bridge.py`、`tools/v3_agent_host.py` 的增量及相关测试。原 tab verifier 保持原实现，并随兼容测试执行。

本审阅者编写 `agent_session.py`、`runtime.py` 的固定 case 接线、`test_agent_session.py` 及 `docs/V3_AGENT_LAYER.md`。这些部分本报告仅记录自检；协调者已独立逐段核对两 case 白名单、精确版本/verifier、原 tab 契约不变、fixture 摘要及 canonical root/guest-console，报告无阻塞，不以作者自检替代独立批准。已有 launcher/profile/farm_runner 用户改动不属于审阅范围，没有修改这些文件。审阅期间未调用 relay、Hyper-V 或 GUI。

## 验证记录

本审阅者执行 `python -B -m pytest unit_tests/test_agent_protocol.py unit_tests/test_agent_business_ui.py unit_tests/test_agent_executor.py unit_tests/test_agent_layer_verify.py unit_tests/test_agent_verify.py unit_tests/test_agent_model.py unit_tests/test_agent_bridge.py unit_tests/test_agent_host.py unit_tests/test_agent_session.py unit_tests/test_runtime.py unit_tests/test_v3_session.py -q`：269 passed，3.74 秒。该结果仅为无 GUI 验证。因 dev-guidelines 只读，反馈检查使用 `check_review_signals.py --dry-run`，结果 No signals detected。

初版独立比较原始 mixed_filament_test.3mf 与派生 agent_layer_cube.3mf：ZIP 成员列表相同，只有 `Metadata/model_settings.config` 内容不同；其余成员字节相同。初版派生文件 SHA-256 为 `a468c33bda6c79cd4edb3a4d134db50024f7283211452de3640cce7530993513`，当时匹配注册常量，但未去除面着色，已被下述修订替代。原 tab 契约摘要保留 `4fe2d56332c5525524cceed2dccdc3a212995d742c98f828a86fcd15964c0901`，有回归断言。

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

## 关闭专项与真实生成器格式补充

关闭专项 run `a708ca48076b4348aa8586fb1dc491fd` 未执行基线/重切业务，不计 AI 正例。本审阅者只读核对 `artifacts/v3/guest_layer_close_a708_evidence.zip`，SHA-256 为 `8486271e259ec1015f4875af7584236b3f2f8055e4313ef01f95165de81faa91`。原始 result 为 NON_GREEN、execution/runtime=cancelled、cleanup_confirmed=true；process 为 active_processes=0、forced_termination=true、cancel_reason=cancelled。这证明新控制回调触发了有记录的强制回收，不是自然关闭通过。

诊断 `close_windows.json` 明确标注 diagnostic_only=true/oracle_evidence=false：应用 PID 6828 的 #32770 窗口 `Snapmaker Orca - Save` 由 main HWND 396874 拥有，文本为 Yes/No/Cancel/htmlWindow 与可选 Remember my choice。正文位于 HTML，不能靠普通窗口文本包含 save changes 来识别。

Tool Control Items 3–5 / Input Validation Items 1–4 (C) — PASS：关闭补丁只在已发 close_requested、精确标题且上述四项各唯一、没有其他非空文案时选择 No；仍先核对同 PID、#32770 与最多 8 层 GW_OWNER 链到当前 main。错误标题、未请求关闭、缺 HTML/Cancel、重复 No、未知文本及其他 owner 均拒绝。没有泛化为任意保存弹窗或任意 No，诊断不参与业务 pass。相关 175 项 business UI/protocol/layer/session/runtime 无 GUI 测试通过（2.36 秒）。

AI Evaluation Items 1–4 (C) — PASS（格式兼容）：只读上游 `src/libslic3r/GCode.cpp` 的 gcode_label_objects 分支确实在对象实例挤出前后成对发射 `; printing object NAME id:N copy N` / `; stop printing object ...`。新增解析以 name/id/copy 精确配对，禁止嵌套、第二对象及清料塔范围重叠；有 EXCLUDE_OBJECT 指令时保持原模式。注释只定义生成器的对象范围，层高和工具仍由范围内真实运动重算，没有扩为整文件 E 统计或相信 Z 注释。

真实生成器还使用不含 E 的 G2/G3 抬头移动。兼容分支只接受数值参数 XYZ/IJK/R/P/F，清空 XYZ，后续对象正向挤出之前必须由直线指令重新建立明确坐标；不推导弧线轨迹，带 E（包括 E0）、未知/重复参数仍拒绝。59 项 layer oracle 测试通过（1.68 秒），包含缺失坐标恢复及带 E 弧线反例。以上均为有限格式兼容，没有扩大业务通过条件。

## 59b7 产物与关闭 owner 关系复核

完整 CLI run `59b7bfbd23024db98cf62ff70a0b6cdd` 仍为 NON_GREEN/cancelled：finish 返回 graceful_close_unconfirmed，runtime 自动回收 owned Job（active=0、forced_termination=true、cleanup_confirmed=true），原包缺少 agent_report.json。本审阅者独立复算 ZIP SHA `26f24bf5830da86c38f14ba758e729e923165442b238e4491e9aa7ac0b3093ad`、49 文件，并纯重放 A/B 的对象运动：68 层×0.40 → 112 层×0.24，首层均 0.40，末 Z 27.20/27.04、正 XY/E 运动 1907/2882，对象工具均 T0。6 次宿主输入图 hash、原始 CLI action/usage、action 文件和 guest 请求链一致。产物检查成立不改变原始失败裁决，详细运行记录另存 docs/runs/v3-layer-2026-11-16.md。

Tool Control Items 3–5 / Input Validation Items 1–4 (C) — PASS（修复进入再试验）：保存窗的直接 owner 不是 main，本次新增规则只接受 GW_OWNER 有界链中同 PID 且 `IsChild(bound_main, owner)` 成立的真实主窗后代。只读开发检出 Plater.cpp 的 close_with_confirm 使用 this/Plater 作为对话框 parent，与该关系相符。仍要求 own #32770、精确保存结构、close_requested；同 PID 旁支、共享隐藏 root-owner、外部 PID、循环链均拒绝，不以共享祖先作为授权。

GetParent/GetAncestor 及点击返回目标仅增加有界诊断（最多 32 关系节点、16 次点击记录），不参与 oracle 或扩大许可。审阅者运行 88 项 business UI/protocol/executor 测试通过（0.66 秒）；协调者报告全套 488 passed / 1 skipped、diff --check 通过。代码审阅无新增阻断，真实关闭兼容性仍须新 run 证明；不追认 59b7 为 SHADOW。

## 尚待真实验证

实际 Quality/Edit 定位、wx 字段提交、Slice/Export 控件状态、保存对话框及关闭提示尚未通过本批客机运行。导出按钮 enabled 只是工具等待条件，最终 G-code oracle 才决定层高是否生效。首个真实 run 必须记录 CLI 图像输入/结构动作与 guest 请求 hash 关联，以及 Job 空、无强制终止/取消和确认 cleanup；后续负例须与正例、离线篡改重放分别标注。

## 首次真实探针暴露的单材前提缺失

协调者在 run `6640e019fa05428ba641dee6fdd192b1` 的实际切片预览发现多耗材、换料和清料塔，未接受该 run 为本契约通过。本审阅者随后只读解析原始及派生 3mf：`3D/Objects/立方体_1.model` 的 12 个三角面中均仍有 2 个含 `paint_color`。先前 ZIP 字节对比正确，但由“对象 extruder=1”推导“单材”不成立，预审漏查面级着色语义。

AI Evaluation Items 1–3、Requirements Gap Items 1–3 (C) — 原 FAIL 已闭合：旧 fixture 的 single-material 契约前提未经 oracle 验证。修复限定为离线去除三角面着色属性，保留物理几何和 project_settings，更新固定 SHA/契约摘要；独立 G-code 检查已要求对象范围内正向 XY/E 挤出使用唯一已知工具，A/B 工具相同，不把对象外塔/起始线算成多材对象。旧探针原始记录保留，不重写为新夹具 run。

夹具修订已独立只读核证：仅 `Metadata/model_settings.config` 与 `3D/Objects/立方体_1.model` 改变；原 2 个 paint_color 属性已删除，顶点、三角索引、component/build 属性与源文件相同，project_settings 字节相同。新 SHA-256 为 `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`，新契约摘要为 `a84be6d0070374966f50ae053a41fe8779ed483f7863fd2055ce75ce99e81114`。保留项目耗材槽和清料设置，不把 UI 列出多个可选耗材当作对象多材证据。

工具前提补丁已独立审阅：Tn 显式选择绑定后续对象正向 XY/E 挤出，未知工具拒绝、对象多工具失败，`analyze_gcode` 返回 object_tools 并核对 A/B 一致。反例覆盖对象双工具、缺失工具选择、A/B 各单工具但不同，以及对象外第二工具/结束 T999 不误计入集合。没有未取证就硬编码 T0。固定生成器范围内检验导出文件的显式工具命令，不模拟固件宏。

协调者另报告旧探针 finish 时 graceful_close_unconfirmed，worker 已退出但 owned app 仍存活；仅由 worker 读取 control_cancel 会延迟至整体超时。按授权在 session 向 runtime 传入当前 run 控制路径的 exists 回调，复用已有 OwnedJob 取消与归零确认，不新增清理框架。合法及畸形控制均触发停止，其他 run 控制不触发；协调者已独立核对固定 root/run_id 路径、回调在 worker 退出后仍有效及对应反例，无阻塞。135 项 fixture/protocol/oracle/session/runtime 无 GUI 测试通过（2.22 秒）。旧探针的外部操作者终止必须单独记录，不宣称自然退出或改写旧运行收据。

协调者最终整套纯检查：456 passed / 1 skipped（符号链接权限），diff --check 通过。首次探针 `6640e019fa05428ba641dee6fdd192b1` 最终 NON_GREEN；关闭失败后仅在核对 PID 4580、父 PID 7100、可执行名及该 run 唯一 profile 后强制停止残留应用，外部操作留在独占 operator_recovery.json。此强制收尾不能当作自然关闭。归档 SHA-256 `90b3e3ff972e9c0073f36cb76dbb772502e15338e576407b0368788fb06c658a`；旧 probe 输入 SHA 仍为 a468c33b，不能替代新夹具验证。关闭兼容性仍需有界实测，新增 close_windows.json 只用于诊断。
