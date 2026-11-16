# v3 保存、重开与切片整链契约

2026-11-17 接口冻结；一个完整业务 case，不把链上多个断言计成多个用例。
case=`m3g_export_3mf`，version=`ai-project-1`，executor=`agent_mcp`，公开仍为 SHADOW/NON_GREEN。
复用 run_once、同一 worker/OwnedJob、guest-console 锁、ModelPort、MCP/mailbox；旧 case 契约和 DTO 不变。
fixture 沿用 agent_layer_cube.3mf，SHA `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`。
常规最短顺序：observe → edit .24 → save_project → reopen_project → slice → export_gcode → finish（7 tools / 6 decisions）。
允许预算内额外 observe/tab click；业务操作顺序仍 exact edit/save/reopen/slice/export，不能硬编码 reopen=seq4。
契约 steps：boot/edit/save/reopen/slice/export/close；无重复 baseline 切片。
预算沿用 guest 900 秒、host 600 秒、12 tools、8 model calls、6 tab clicks、零动作重试；重开不重置预算。
模型 ID/USD 未返回即 unknown，max_cost_usd=0 不代表实现美元计量。

## 工具与固定路径

新 case 工具：observe/click/edit/save_project/reopen_project/slice/export_gcode/finish。
save_project/reopen_project/slice/export_gcode/finish 的 arguments={}；模型不可指定路径、程序或 profile。
click 仍限 tab 区域；edit 沿现有 native Edit 数值约束，目标 .24 由任务与 oracle 判定。
save_project、reopen_project、edit、slice、export_gcode 各最多一次，额外 observe 只受整体预算约束。
worker 验证安全前提/操作预算，业务顺序由独立 verifier 判定；不能提前禁掉合法但业务错误的负例动作。
保存路径 `projects/0001.3mf`，重开 profile=`profile_reopen`，最终 G-code=`exports/0001.gcode`，均相对当前 artifacts。
保存/导出目标须不存在；不删除、覆盖或静默重试。新 profile 不存在才 seed fresh=False。
reopen_project 是窄原子操作：确认旧 owned app 自然 exit=0 → 新 profile 启动保存的同 hash 文件 → 新窗口双帧。
worker 始终存活，同一 Job 保留；中途只确认旧 app 已退出，最终才要求 Job active=0。

## 收据与身份边界

沿用 operation_receipts.ndjson 外层：schema_version/run_id/seq/method/request_sha256/started_at_ns/finished_at_ns/window/details。
所有字段 exact；window={hwnd,pid} 为操作结束后的身份。保存、编辑、切片、导出在当前身份内。
save_project details={dialog_hwnd,edit_hwnd,path,sha256,size_bytes}，path 固定 projects/0001.3mf。
reopen_project details={path,sha256,size_bytes,datadir,old_pid,old_hwnd,old_exit_code,old_closed_at_ns,new_pid,new_hwnd,new_started_at_ns,driver_pid}。
datadir 固定 profile_reopen；path/hash/size 与保存收据和最终文件相同；old_exit_code 精确整数 0。
old_closed_at_ns 为旧 Popen handle 确认退出后；new_started_at_ns 为新 launcher 调用前；close≤start≤receipt.finished。
仅 reopen_project 成功边界允许 PID/HWND 切换，row.window 和响应双帧属于新实例；其他动作不得变身份。
PID/HWND 可被系统重用，不以数字必须不同代替真实旧 handle 退出与新 launch 证据。
ready.json 保留初始身份，agent_report.json 为最终身份，driver_pid 不变；不得覆盖历史收据。
响应 envelope/observation schema 沿用 v1，seq/observation_id 全程递增，旧观测不重放。

## 独立判定

AgentProjectVerifier 独立只读、可取消；runtime 只接受注册契约 digest 与 exact verifier type。
path：完整 edit/save/reopen/slice/export 顺序、两阶段窗口归属、收据时序、同文件 hash、自然收尾与 Job 清空。
business：3mf layer_height=.24、initial_layer_print_height=.4，几何/组件/build 物理语义保持固定 cube。
不得仅比较主 XML hash 或顶点数；拒绝意外 object/part 层高覆盖、可变层高配置及 paint。
重开后不再 edit；最终 G-code 复用实际对象正 XY/E 层序 oracle，.24/初层 .4、112 层、末 Z27.04、单对象工具。
3mf 持久化不单独证明切片生效；新 profile、文件绑定与重开后的 G-code 联合证明。
模型 finish、rc0、截图文本或多个 assert 都不单独算完成；失败保留原裁决和证据。

## 整组验收与分工

同一自动串行批次：首个 CLI 正例 → 三个固定负例 → 恢复 CLI 正例，共五个独立 run/new profile。
两个完整 CLI 正例构成本批整链复跑检查，不另为 primitive 跑五轮，不声称统计可靠率。
save_before_edit：save/edit/reopen/slice/export/finish，实际保存旧 .4，重开后 .4，应拒绝。
missing_reopen：edit/save/observe/slice/export/finish，即使最终 G-code .24，也缺跨进程持久化路径，应拒绝。
missing_slice：edit/save/reopen/observe/export/finish，新 profile 未切片，预期 export_not_ready。
上述均另有初始 observe；固定 fault probe 非 AI，不能计入两个 CLI 正例分母，也不改变业务契约。
同一正例的保存、重开、参数和切片断言共享链路证据，但只计一个 case/run。
具体来源/槽位在运行前冻结；独立核对实际旧 3mf/G-code、缺 reopen 或缺 slice，未命中不得计检错成功。
架构师：protocol/session/runtime、本文件及接线测试；core：ProjectUI/guest/lifecycle及其测试。
独立检查器作者：project verifier/3mf与Gcode oracle及反例；协调者：host/bridge/model/整批串行执行。
所有真实 VM/relay/GUI 操作只由协调者执行；架构师实现范围交协调者复核，架构师独立审其余实现。
