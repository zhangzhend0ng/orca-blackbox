# v3 首个 AI 执行切片：页签往返

状态：2026-11-16，codex_chat 和无人值守 codex_cli 真实 AI/GUI 正例均为 SHADOW，无状态变化的客机反例 NON_GREEN；[运行记录](runs/v3-agent-2026-11-16.md)。上一批 m0 的 SHADOW 不作为本批证据。

固定任务为 `m1_minimal_loop`，契约版本 `ai-tabs-1`，executor=`agent_mcp`：由模型观察实际截图，选择点击，使界面完成 Prepare → Preview → Prepare。只证明页签状态切换与路径，不证明切片、渲染质量或完整产品正确性。始终不可发布。

同一主链已扩展固定业务 `m3d_param_reslice / ai-layer-1`，其 GUI 层高编辑、切片导出和实际对象层序独立检查首次完整 SHADOW；详见 [业务架构](V3_AGENT_LAYER.md) 与 [运行记录](runs/v3-layer-2026-11-16.md)。本页的 ai-tabs-1 工具、契约和验证范围保持独立，不据此扩大页签结果。

## 最小架构与复用边界

```text
宿主 v3_agent_host（受控 agent loop）
  ├─ ModelPort → Codex CLI / 当前 Codex chat agent → 严格 JSON 下一动作
  └─ 标准 MCP client → agent_bridge（stdio JSON-RPC）
                         └─ PSDirect/relay 短事务 → run-owned mailbox
客机 hv_go → run_once → AgentExecutor → Job 内 agent_guest
                         └─ 独立 agent_verify → SHADOW / NON_GREEN
```

模型、登录态与凭据留在宿主；客机只接收结构化工具动作。CLI 子进程禁用 shell、文件编辑、浏览器、apps、plugins、computer-use 或多 agent 功能，模型输出仍在宿主严格校验。这里真实使用 MCP 工具协议，但调用者是受控 host loop，不宣称 Codex 原生工具循环已接入 MCP。

两个模型来源分账：`codex_chat` 由当前聊天 agent 实际查看本 run PNG，再独占写入严格下一动作；`codex_cli` 由受限 CLI 图像推理返回动作，controller 自动调用 MCP。本轮两者已分别验证，后者不是聊天动作回放；chat 的 token/USD 为 unknown，CLI 记录实际 token 字段、美元未知。controller 校验 run/obs、预算与 deadline，模型不能预填 scripted 坐标冒充推理。

默认优先发现已安装 App 最新 native CLI，缺失再用 npm native，支持 `--codex` 显式指定。仅在 Windows 推理子进程中、环境没有显式 HTTP/HTTPS 代理时继承系统既有配置，不改全局配置，不记录代理值。本机旧 CLI 与代理路径问题及对照证据见运行记录；默认模型未取得精确 ID 时保留 null，不能虚构固定模型版本。

实际入口（先经现有管理员 relay/通道启动客机，再在宿主运行控制器）：

```powershell
# ORCA_BB_GUEST_SANDBOX 须指向已同步且干净的独立客机检出。
$run = [guid]::NewGuid().ToString('N')
& runner/hv_go.ps1 -V3 -V3Executor agent_mcp -V3RunId $run -Cases m1_minimal_loop
python -B tools/v3_agent_host.py --run-id $run --guest-root 'C:\coil\orca-blackbox-v3-r1'
& runner/hv_harvest.ps1 -V3
```

不建立常驻网络服务或命名管道。宿主标准 stdio bridge 实现 initialize、notifications/initialized、tools/list、tools/call；底层 mailbox 是本项目传输，不冒充标准 MCP transport。PSDirect/relay 只执行固定的短读写操作，单槽串行，不在 relay 内等待整个模型调用。大 PNG 按有界分块取回并验证大小/hash；不依赖有损的 PowerShell byte[] 回传。

旧 `mcp_server.py` 不能原样开放：共享 artifacts/mcp/profile、fresh 清理、全局分辨率调整、窗口搬动、run_case 孤儿清理和草稿写入均超出本任务。复用它依赖的 winutil 截图与消息点击等原语，明确坐标语义；不开放 app_launch、run_case、screen_guard、写模板、参数修改或 gcode_assert 给模型。启动、profile、关闭和 Job 回收由可信客机执行器控制。

## 冻结工具与数据格式

MCP tools/list 仅包含以下三项；不接受额外参数：

| 工具 | arguments | 语义 |
|---|---|---|
| observe | `{}` | 采集当前同一窗口两帧，返回最新 PNG 与观测元数据 |
| click | `{observation_id, x, y}` | 仅在最新观测对应窗口的允许页签区域点击；随后采两帧并返回新观测 |
| finish | `{}` | 请求结束执行；仍保存观测并由可信执行器关闭应用，不接受 pass/期望/检查结果 |

`x/y` 统一为截图中的 client 像素，不是宿主或屏幕绝对坐标。客机验证整数、图像/窗口尺寸、观测新鲜度、窗口 PID/HWND 归属及允许区域；坐标转换由可信工具完成。截图改变、窗口失效或 observation_id 过期时拒绝，不猜测新目标。点击响应已有新图，不需要强制追加 observe。

模型输出只有严格 schema 的下一动作：工具名与对应 arguments。finish 不能改变结果；模型文本、解释或自报成功不是业务证据。初始化截图和每次工具响应可供下一次模型调用观察，独立 checker 的阈值与结论不作为可修改模型输入。

桥把外层 MCP tools/call 转换成以下 mailbox 请求；该格式已与客机实现冻结：

```json
{"schema_version":1,"run_id":"...","seq":1,"method":"click","arguments":{"x":244,"y":49},"observation_id":"..."}
```

observe/finish 的 MCP arguments 为 `{}`；桥在所有 mailbox 请求中附上最新 observation_id，仅首次 observe 为 null。click 的模型参数必须引用最新 observation_id。`run_id` 只防误归属，不是认证凭据。同权限进程及配置仍被信任，本批不声称 ACL、签名或抵御恶意进程隔离。

响应字段：`schema_version, run_id, seq, tool, is_error, error_code, observation, finished`。成功观测结构如下；工具失败无有效画面时 observation 可为 null，不能伪造截图：

```text
observation:
  id
  frames: [{path, sha256, width, height, captured_at_ns}, ...]  # 两帧
  image: {path, sha256, size_bytes}                           # 给模型的 PNG
  window: {hwnd, pid, width, height, dpi}
```

路径均是本 run 内受校验的相对引用；模型不能传路径，bridge 不能因此读取任意客机文件。PNG 传给模型前校验大小及 hash，帧和动作收据留在客机供独立验证。

请求按 seq 独占写文件；重复 seq 不重放，不能因丢响应再执行一次点击。发送前后、响应序号与 run 归属必须一致。丢响应、重复或无法判断动作是否发生时停止并保留未知，不以新的 seq 偷偷重试。每个调用都保留两帧；采图失败保存错误，不能把操作已投递当作状态已经改变。

## 生命周期、预算与停止

客机通过 hv_go 进入 run_once，使用与 Script 相同的 canonical evidence root、桌面排他锁和 Job 所有权。AgentExecutor 管理 guest worker 与应用后代；固定新 profile，不进入旧 fresh 全局清理。宿主先确认 guest ready/run_id，再启动模型循环。宿主不能直接写 result.json 或 checker 输出。

本批固定上限：最多 8 次模型调用、12 次工具调用、6 次点击；宿主整体 600 秒，客机整体 900 秒。常量由受信注册配置提供，模型不能修改。宿主在模型调用前、bridge 在发送前、客机在动作前分别检查所负责限额；取消/回收控制不应被动作额度耗尽阻断。宿主不自动重启失败的 CLI 调用，也不失联续跑。8 次是 CLI 调用上限；未验证关闭的 CLI 内部网络重试不算作已被限制的 API 请求次数。

Codex 使用已有 ChatGPT 登录，不把 OAuth 凭据复制到客机，不提取私有应用凭据。每次调用记录 CLI/模型版本、输入观测 hash、输出动作、耗时及实际返回的 token usage；中断后缺 usage 记 unknown，不能计为零。订阅调用无法得到可靠的逐 run 美元账单或强制美元额度，美元成本标为 unavailable，不把零美元或契约 max_cost_usd 字段冒充已执行费用门禁。本批可强制的是次数、动作与时间；USD 硬上限仍不支持。

模型调用超时、无有效结构输出、额度耗尽、工具错误或用户取消时，宿主停止模型，并独占写入本 run 的 `control_cancel.json`（schema_version=1、run_id、reason=host_stopped）。这是宿主控制面，不是模型工具，不消耗动作额度。guest 在等待请求及动作/采图边界检查，收到有效或畸形取消记录均停止并尝试关闭；已进入的 OS 调用仍靠客机 deadline 和 Job 回收兜底。finish 仅用于正常意图结束；故障退出不能伪装成 finish 成功。取消投递不代表已清理，只有 Job 归零才确认退出；检查器/worker 未静止则保留隔离锁，只杀本 run 所有进程。

## 独立判定与真实验收

agent_verify 从客机原始帧与可信 trace 重算状态，不接受模型/bridge 的成功标签。沿用 anchors.py 中 Prepare/Preview 的互斥颜色探针与现有 m1 稳定性方法：初态 Prepare、Preview 和最终 Prepare 各需连续两帧支持。限定语言、DPI、窗口布局，条件不满足记未知。动作顺序、obs 引用、run/seq、窗口身份与产物关联必须对应；最终一张 Prepare 截图不能证明中间曾到 Preview。

结果保留初态、每次操作两帧、给模型的 PNG、请求/响应、宿主模型事件摘要及客机 Job 退出收据。path/business 只表达本页签任务；错误操作及无变化不得从轨迹中删除。结果使用 SHADOW 或 NON_GREEN，release_eligible=false；不得混入旧 GREEN/飞书覆盖写回。

验收必须包含真实宿主图像推理驱动真实客机页签切换，不能以 scripted action replay 或 fake model 当作 AI 接入完成。本轮已取得真实 CLI 图片、结构输出和 token 元数据；实际取消/失联与权限隔离仍未用本轮正例证明，保留专项反例与验证缺口。登录状态本身不证明推理可调用。

反例至少验证：立即 finish 不能通过；过期观测、越界点击、重复 seq 被拒绝；中间 Preview 帧缺失/篡改不能通过；丢响应不会重复点击；模型/宿主中止后 guest deadline 与 Job 清理有效。纯单元测试、MCP 协议测试和真实 GUI 证据分别报告。

## 文件分工

| 文件 | 职责 |
|---|---|
| harness/agent_protocol.py | 固定 capability、mailbox schema、限额与路径/序号验证；不含模型和 GUI 实现 |
| harness/agent_guest.py | guest-only 交互 worker，run-owned GUI 会话、三工具、双帧采集、原始 trace |
| harness/agent_executor.py | run_once 端口、Job 后代生命周期、ready/取消/退出事实 |
| harness/agent_verify.py | 独立帧与路径检查、证据完整性及 scope 受限的 CheckResult |
| harness/agent_session.py | 固定 m1/ai-tabs-1 注册与 guest 调用组合，不加载任意插件 |
| runner/agent_bridge.py | 标准 stdio MCP 外层；固定 PSDirect/relay mailbox 读写、分块取图和摘要验证 |
| tools/v3_agent_host.py、harness/agent_model.py | 宿主受控 agent loop 与可替换 ModelPort；CLI/聊天决策读取、schema 校验、预算、模型事件与退出处理 |

本稿按 harness-driven-review、工具调用控制、AI 评估与风险验证要求冻结边界。实施和真实运行结论另见本批审阅报告，不从接口存在推断能力已经验证。
