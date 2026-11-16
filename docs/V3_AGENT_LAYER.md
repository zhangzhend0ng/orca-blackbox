# v3 AI 层高修改与 G-code 产物闭环

状态：2026-11-16，首次无人值守 CLI 完整业务验证为 SHADOW；[运行记录](runs/v3-layer-2026-11-16.md) 保留四次失败探针及最终正例。固定能力为 `m3d_param_reslice / ai-layer-1`，复用 `agent_mcp` 执行器，不运行或包装旧 m3d/m5a 用例的 main。当前只证明固定夹具的层高修改、GUI 切片导出和正常退出，不代表稳定性、其他业务或发布验收。

任务是让模型从实际截图定位 Layer height，将 0.40 改成 0.24 mm，初层保持 0.40 mm，再通过 GUI 切片和导出，独立证明设置进入实际对象挤出层序。只保存 3mf 或只检查 G-code 配置注释均不能完成此契约；若只做到持久化，必须作为另一个明确范围的结果，不能将本任务改记通过。

## 复用主链与固定输入

沿用 `hv_go → run-agent → run_once → AgentExecutor → OwnedJob worker`，宿主继续 `CodexModel → controller → stdio MCP bridge → mailbox`。不增加 runtime 模式或平行执行框架。`agent_protocol.agent_profile` 只登记两个固定 case；原 `m1_minimal_loop / ai-tabs-1` 的工具、四字段模型动作和契约摘要保持不变。新 case 使用 `AgentLayerVerifier`，runtime 拒绝跨 case 替换检查器。

派生输入 `fixtures/agent_layer_cube.3mf` 来自已提交 mixed_filament_test.3mf：把 model_settings 中对象 extruder 6 改为 1，删除 source_file 私有路径，并去除三角面上的 paint_color 属性。仅改对象 extruder 不能消除面级多材着色，首次真实探针已暴露这一点。保留全部顶点、三角索引、component/build transform、27 mm 立方体放置、U1 0.8 mm 喷嘴、layer_height=0.4、initial_layer_print_height=0.4 等设置。project_settings 字节不变；几何 XML 的着色属性改变，物理几何语义不变。该离线派生是可审查测试输入，不是在 run 中修改目标配置。

固定 SHA-256：`ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`。摘要写进契约 boot goal；worker 启动前核对并复制到 run-owned 输入路径，GUI 加载该副本。旧带着色夹具及其 run 不能被接受为此摘要对应的执行。保留 fresh=False 的独占新 profile，不调用旧全局同名清理。启动仍遵守 hands-off 期，既有 tab 路径不改启动方式。

## 模型职责与窄工具

预期流程：初始 observe → slice → export_gcode（A）→ edit → slice → export_gcode（B）→ finish。每一步由模型根据当前截图选择下一动作；工具只执行固定权限的 GUI 原语，不代模型决定修改坐标或目标数值。

| 工具 | 新 case 的 MCP 参数 | 边界 |
|---|---|---|
| observe / click / finish | 保留原能力 | click 仍限 Prepare/Preview 页签区；finish 不是业务通过 |
| edit | observation_id, x, y, text | 截图 client 坐标命中同 PID 可见原生 Edit；仅 0.16–0.56 的短十进制数字（夹具喷嘴允许范围），GUI 写入并提交，不写配置文件 |
| slice | observation_id | 对当前应用 Slice 控件点击一次，再有界等待 GUI 可导出；不运行 CLI slicer、不盲目重击 |
| export_gcode | observation_id | GUI 导出到固定 `exports/0001.gcode`、`exports/0002.gcode`；模型不能指定路径，不覆盖既有产物 |

所有动作绑定最新观测。capture_window 使用 GetClientRect 与 PW_CLIENTONLY，edit 必须通过 client_to_screen 转屏幕坐标，不使用 window_rect 原点。目标 Edit 的 PID/父窗口/可见性必须再检查；不存在或身份变化即失败，不猜测另一个控件。收尾只处理本 PID、可识别的关闭/丢弃提示，不能因模型 finish 就报告应用已退出。

模型层仅新 case 增加 `text` 字段：edit 时为字符串，其余动作必须 null；tabs 保留原四字段 schema。mailbox 外层字段不变，edit arguments 为 `{x,y,text}`，slice/export_gcode arguments 为 `{}`；桥将 observation_id 单独附入原请求字段。响应和 observation 不增加字段，原 tab 严格解析器无需兼容宽松新格式。

权限上限保持 12 次工具、8 次模型调用、6 次直接 tab 点击、宿主 600 秒、客机 900 秒；业务工具另限 edit/slice/export 各最多 2 次。一次 slice 最长 180 秒且仍受整体 deadline 限制。此处次数是受限工具调用次数，不把复合 GUI 原语内部每条窗口消息冒称独立模型动作。保存对话框等内部操作有固定步骤和有界等待，不允许自动扩大权限或无限重试。取消继续使用独立 control_cancel，不消耗模型额度；同一 run 的控制文件同时触发 worker 协作取消和 runtime OwnedJob 取消，即使 worker 已退出但应用仍存活，也不会仅等待 900 秒。畸形控制文件同样停止，不视为清理完成。

## 副作用证据与独立裁决

每次工具之后沿用两帧 BMP、PNG、窗口身份和 trace。新增 `operation_receipts.ndjson` 记录启动夹具、edit 控件/前后文本、slice GUI 动作、export 固定路径/hash/大小。每行固定为 `schema_version/run_id/seq/method/request_sha256/started_at_ns/finished_at_ns/window/details`；window 仅含 hwnd/pid，request 摘要采用排序键、无空格的 UTF-8 JSON。boot 为 seq=0、request_sha256=null，其余绑定原请求，动作时间须位于前一末帧与当前首帧之间。它是可信工具的副作用收据，不是业务 oracle，不将 PASS 或期望检查结论回传给模型；原 response/observation 保持不变。

`AgentLayerVerifier` 独立读取完成后的 A/B 文件、操作收据、trace 和 Job receipt，分开核对路径与业务：

- 必须有本 run 的初始夹具、基线切片导出、模型 GUI edit、再次切片导出和关闭顺序，不能以直接写配置或旧文件替代；A/B 均唯一、完整、新鲜且 hash 关联。
- G-code 配置回显分别为 layer_height 0.40 / 0.24，初层值保持 0.40；使用精确数值解析，不采用旧 startswith 判定。
- 重算实际对象的正向 XY 挤出运动 Z 层序，处理 G90/G91、M82/M83、G92 和工具状态；用对象边界区分起始线/prime tower，排除 Z-hop。只看 LAYER_CHANGE/Z/HEIGHT 注释或文件 hash 不够。
- 单材前提必须同时在实际产物成立：对象范围内正向 XY/E 挤出使用唯一已知工具，A/B 的对象工具相同。对象外的起始线、清料塔和结束工具命令不直接计入对象耗材集合；模型或配置名称中的“单材”不是证据。
- 实际对象层序必须支持 A/B 的预期层高变化；不能用 `; layer_height=0.24` 注释掩盖仍为 0.40 的运动。未支持的 G-code 语义或不完整对象范围记未知，不能默认通过。
- worker、应用及 checker 静止后才确认 cleanup；未知/skip 仍不能通过，结果不开放发布 GREEN。

首个真实正例必须由 Codex CLI 实际看图并自动选择 edit 坐标/文本及后续工具。反例至少覆盖仅改 header、只改原生控件文本未提交、无效/陈旧产物、缺少 reslice、A/B 颠倒、参数没改而正常退出。真实 GUI 与离线篡改重放分别报告，不把 fake UI 测试当业务能力证明。

首次完整正例 `6bfe7cb6c9d54994a0106247bab08294`：6 次真实图像推理、7 次工具调用，GUI 导出的实际对象层序由 68×0.40 变为 112×0.24 mm，初层均为 0.40 mm、对象工具均为 T0。独立路径/业务检查通过，process exit=0、forced_termination=false、cancel_reason=null、Job active=0。真实 A 仅伪改回显/Z 注释的内存重放被拒绝；其他故障主要由纯测试覆盖，不能计作真实 GUI 挑战。精确模型 ID 和美元费用未知，SHADOW 不进入原 GREEN 覆盖表。

## 文件分工和实现边界

guest/协议作者扩展现有 agent_guest、agent_protocol、agent_executor，并新增窄 `agent_business_ui.py`；oracle 作者新增纯读取 `agent_layer_verify.py` 及反例。session/runtime 只增加固定 case 的契约和 exact verifier 选择。现有 `tools/v3_session.py run-agent CASE` 与 hv_go 的动态批准列表已能承载新 case，不增加另一套入口。宿主按可信 case 选择工具、schema 和 prompt，复用已有模型/桥/控制循环。

已知旧 export_util 的真实点击后备会把 screen rect 再做 client_to_screen；不能照搬这段双坐标转换，也不能照搬其隐藏重试或全局副作用。复用其原生控件枚举和保存对话框思想，但本 run 的路径、所有权、deadline 与记录必须由新窄工具保证。原 m5 预设菜单仍有未解决问题，本任务使用直接字段编辑，不扩大为对旧 m5 的修复或通过声明。
