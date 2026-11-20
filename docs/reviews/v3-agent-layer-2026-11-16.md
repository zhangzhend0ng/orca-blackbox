# Review: v3 AI 层高修改与 G-code 闭环（2026-11-16）

结论：APPROVE，限 `m3d_param_reslice / ai-layer-1` 固定试点。真实无人值守 CLI run `6bfe7cb6c9d54994a0106247bab08294` 首次取得完整 SHADOW，本审阅者独立重放核证 path/business pass、evidence_complete/execution_compliant true，模型动作、实际层序与自然清理证据完整。自写 session 接线由协调者独立复核。四次历史 NON_GREEN 及审阅漏查面着色/API 常量的勘误保留；此前代码批准不追认为业务通过。单次 SHADOW 不证明通用能力、跨版本稳定性或发布资格，release_eligible=false。

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

诊断 `close_windows.json` 明确标注 diagnostic_only=true/oracle_evidence=false：应用 PID 6828 的 #32770 窗口标题 `Snapmaker Orca - Save`，文本为 Yes/No/Cancel/htmlWindow 与可选 Remember my choice。旧 owner_hwnd=396874 由错误 GetWindow(...,2) 取得，实际为 Z-order NEXT，撤回其作为 owner 证据的解释。正文位于 HTML，不能靠普通窗口文本包含 save changes 来识别。

Tool Control Items 3–5 / Input Validation Items 1–4 (C) — 历史结构检查通过，但 owner API 审阅存在遗漏（见下述勘误）：关闭补丁只在已发 close_requested、精确标题且上述四项各唯一、没有其他非空文案时选择 No。错误标题、未请求关闭、缺 HTML/Cancel、重复 No、未知文本均拒绝；当时所谓 GW_OWNER 链实际错误查询 NEXT，不能保留该部分 PASS。相关 175 项 pure tests 曾通过，但 fake 忽略 command 参数，没有检出此错误。

AI Evaluation Items 1–4 (C) — PASS（格式兼容）：只读上游 `src/libslic3r/GCode.cpp` 的 gcode_label_objects 分支确实在对象实例挤出前后成对发射 `; printing object NAME id:N copy N` / `; stop printing object ...`。新增解析以 name/id/copy 精确配对，禁止嵌套、第二对象及清料塔范围重叠；有 EXCLUDE_OBJECT 指令时保持原模式。注释只定义生成器的对象范围，层高和工具仍由范围内真实运动重算，没有扩为整文件 E 统计或相信 Z 注释。

真实生成器还使用不含 E 的 G2/G3 抬头移动。兼容分支只接受数值参数 XYZ/IJK/R/P/F，清空 XYZ，后续对象正向挤出之前必须由直线指令重新建立明确坐标；不推导弧线轨迹，带 E（包括 E0）、未知/重复参数仍拒绝。59 项 layer oracle 测试通过（1.68 秒），包含缺失坐标恢复及带 E 弧线反例。以上均为有限格式兼容，没有扩大业务通过条件。

## 59b7 产物与关闭 owner 关系复核

完整 CLI run `59b7bfbd23024db98cf62ff70a0b6cdd` 仍为 NON_GREEN/cancelled：finish 返回 graceful_close_unconfirmed，runtime 自动回收 owned Job（active=0、forced_termination=true、cleanup_confirmed=true），原包缺少 agent_report.json。本审阅者独立复算 ZIP SHA `26f24bf5830da86c38f14ba758e729e923165442b238e4491e9aa7ac0b3093ad`、49 文件，并纯重放 A/B 的对象运动：68 层×0.40 → 112 层×0.24，首层均 0.40，末 Z 27.20/27.04、正 XY/E 运动 1907/2882，对象工具均 T0。6 次宿主输入图 hash、原始 CLI action/usage、action 文件和 guest 请求链一致。产物检查成立不改变原始失败裁决，详细运行记录另存 docs/runs/v3-layer-2026-11-16.md。

Tool Control Items 3–5 / Input Validation Items 1–4 (C) — 历史判断勘误：撤回“保存窗直接 owner 不是 main”及“wx 中间 owner 是根因”的结论；当时依据的 owner_hwnd 实际是 Z-order NEXT。Plater.cpp 的 this parent 不能补足 Win32 常量验证。IsChild 的限制方向没有扩大到共享隐藏祖先，但执行中的边来自错误命令，前次批准漏查了 API 语义，不能以纯测试通过证明正确。

GetParent/GetAncestor 及点击返回目标仅增加有界诊断（最多 32 关系节点、16 次点击记录），不参与 oracle 或扩大许可。审阅者运行 88 项 business UI/protocol/executor 测试通过（0.66 秒）；协调者报告全套 488 passed / 1 skipped、diff --check 通过。代码审阅无新增阻断，真实关闭兼容性仍须新 run 证明；不追认 59b7 为 SHADOW。

## b0 根因与 API 常量勘误

本审阅者独立核对 [微软 GetWindow 文档](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindow)：GW_HWNDNEXT=2，GW_OWNER=4。原代码四处 GetWindow(...,2) 与错误注释被作者、协调者和本审阅者共同漏检；fake 根据 hwnd 返回预设 owner 而不验证 command，复制了错误前提。该失误不是 wx owner 布局差异。

真实 run `b0d46bb81b004814a7e985f9a2d70431` 再次 NON_GREEN/cancelled、强制 Job 清理。独立计算 ZIP SHA 为 `d7f1ddce0b6b34a3041f2abe08e491071f673686bde88dd222cf83f50a7280b0`，49 文件。close_attempts=[]；正确 GetParent 与 GA_ROOTOWNER 均为 main 525700，而错误 owner_hwnd 沿 Z-order 遍历隐藏窗口。a708/59b7/b0 的原始 owner_hwnd 及 relations.owner_hwnd 全部保留但按 NEXT 解读，不重写历史 JSON；GetAncestor 的参数 2 是另一个 API 的正确 GA_ROOT，不能一并替换。

Tool Control Items 3–5 / Input Validation Items 1–4 / Review Checklist Items 1–8 (C) — 原 FAIL 已闭合：四处调用统一具名 GW_OWNER=4；测试对字面值 4 断言，并令 command=2 返回同 PID 无关窗口或恰好 main 的陷阱，最后断言调用集合仅 {4}，不再依赖同一个错误常量自证。独立审阅及 88 项专项通过（0.47 秒），协调者报告全套 488 passed / 1 skipped。修复未扩大同 PID/保存结构/有界遍历限制，可进入新试验；不追认旧 run 通过。

## 首次完整正例独立核证与剩余边界

代码 `636a080b91958c62ff938ec30011daa495987d65` 的 run `6bfe7cb6c9d54994a0106247bab08294` 已补齐先前缺失的真实业务与自然关闭证据。独立计算 ZIP SHA `d0265310fd3cf814c4cd82d7a99650024d44b602fdf3fda06943690ede70bd87`（3,923,953 bytes），48 文件与提取内容一致；契约/fixture 摘要匹配可信注册，9 条 runtime event 序号与 hash 链完整。只读完整 verifier 重放即使接收 ExecutionOutcome('failed') 诊断上下文，仍从原始证据得出 path/business pass、完整性/合规 true。

模型 6 次实际 CLI 图像调用选择 slice/export/edit(286,764,0.24)/slice/export/finish；初始 observe 后共 7 工具，无 chat decision 文件、无直接 tab 点击。输入 PNG hash、原始 stdout 的结构动作/usage、summary、action 与 guest 最新观测/请求逐条匹配，未出现模型工具执行事件。usage input=101824、output=385、reasoning=55、cached=0，model/USD unknown；host 157.214 秒、guest process 172.556 秒。

A/B 分别 68 层×0.40 和 112 层×0.24，初层均 0.40，末 Z=27.20/27.04，正 XY/E 运动 1895/2866，对象工具均 T0。process driver=9268、app=5096，exit=0、Job active=0、forced_termination=false、cancel_reason=null；完整 agent_report 与 runtime result 均 completed，cleanup_confirmed=true，最终 SHADOW/verified_pass=true。SUT 与代码来自同步/收割日志补证，manifest.metadata 为空；原包仅在本地忽略 artifacts，未声称已长期上传。

真实 Quality/Edit 提交、两次 GUI 切片/导出与自然关闭现有一次通过。导出按钮 enabled 仍只是等待信号，实际层序才是业务证据。真实 A 的内存 header-only/header+Z注释伪改均被独立 oracle 拒绝，但不计实际 GUI 故障挑战。跨版本重复性、其他几何/参数、固件/实印和发布晋级仍未验证；详细证据和全部失败历史保留在 docs/runs/v3-layer-2026-11-16.md。

## 首次真实探针暴露的单材前提缺失

协调者在 run `6640e019fa05428ba641dee6fdd192b1` 的实际切片预览发现多耗材、换料和清料塔，未接受该 run 为本契约通过。本审阅者随后只读解析原始及派生 3mf：`3D/Objects/立方体_1.model` 的 12 个三角面中均仍有 2 个含 `paint_color`。先前 ZIP 字节对比正确，但由“对象 extruder=1”推导“单材”不成立，预审漏查面级着色语义。

AI Evaluation Items 1–3、Requirements Gap Items 1–3 (C) — 原 FAIL 已闭合：旧 fixture 的 single-material 契约前提未经 oracle 验证。修复限定为离线去除三角面着色属性，保留物理几何和 project_settings，更新固定 SHA/契约摘要；独立 G-code 检查已要求对象范围内正向 XY/E 挤出使用唯一已知工具，A/B 工具相同，不把对象外塔/起始线算成多材对象。旧探针原始记录保留，不重写为新夹具 run。

夹具修订已独立只读核证：仅 `Metadata/model_settings.config` 与 `3D/Objects/立方体_1.model` 改变；原 2 个 paint_color 属性已删除，顶点、三角索引、component/build 属性与源文件相同，project_settings 字节相同。新 SHA-256 为 `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`，新契约摘要为 `a84be6d0070374966f50ae053a41fe8779ed483f7863fd2055ce75ce99e81114`。保留项目耗材槽和清料设置，不把 UI 列出多个可选耗材当作对象多材证据。

工具前提补丁已独立审阅：Tn 显式选择绑定后续对象正向 XY/E 挤出，未知工具拒绝、对象多工具失败，`analyze_gcode` 返回 object_tools 并核对 A/B 一致。反例覆盖对象双工具、缺失工具选择、A/B 各单工具但不同，以及对象外第二工具/结束 T999 不误计入集合。没有未取证就硬编码 T0。固定生成器范围内检验导出文件的显式工具命令，不模拟固件宏。

协调者另报告旧探针 finish 时 graceful_close_unconfirmed，worker 已退出但 owned app 仍存活；仅由 worker 读取 control_cancel 会延迟至整体超时。按授权在 session 向 runtime 传入当前 run 控制路径的 exists 回调，复用已有 OwnedJob 取消与归零确认，不新增清理框架。合法及畸形控制均触发停止，其他 run 控制不触发；协调者已独立核对固定 root/run_id 路径、回调在 worker 退出后仍有效及对应反例，无阻塞。135 项 fixture/protocol/oracle/session/runtime 无 GUI 测试通过（2.22 秒）。旧探针的外部操作者终止必须单独记录，不宣称自然退出或改写旧运行收据。

协调者最终整套纯检查：456 passed / 1 skipped（符号链接权限），diff --check 通过。首次探针 `6640e019fa05428ba641dee6fdd192b1` 最终 NON_GREEN；关闭失败后仅在核对 PID 4580、父 PID 7100、可执行名及该 run 唯一 profile 后强制停止残留应用，外部操作留在独占 operator_recovery.json。此强制收尾不能当作自然关闭。归档 SHA-256 `90b3e3ff972e9c0073f36cb76dbb772502e15338e576407b0368788fb06c658a`；旧 probe 输入 SHA 仍为 a468c33b，不能替代新夹具验证。关闭兼容性仍需有界实测，新增 close_windows.json 只用于诊断。
