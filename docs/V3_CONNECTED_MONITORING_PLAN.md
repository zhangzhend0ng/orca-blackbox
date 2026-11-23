# 联机/监控族测试方案（定稿，2026-11-23 旁线验证闭环）

由 side-thread 并行验证产出，证据链见 `docs/runs/`（snapmaker_control 实跑）与 `artifacts/sc_probe/`（CLI 留档）。主任务空闲窗执行 Phase 0。

## 已验证事实（全部 live 实证）

1. U1 = klipper+moonraker（`Snapmaker/u1-klipper`/`u1-moonraker`，GPLv3）；Orca webview 直呼 moonraker HTTP（`<host>+/server/...`）。
2. `Snapmaker/snapmaker_control`（CLI，专有许可可运行）：官方 release v1.10.0，**独立运行**（SHA256 校验通过，实跑）：伺服 web UI + `/api/health`（含 device_control 等页面路由）+ HTTP-RPC + `cmd-ws` 通知。
3. CLI 3s 空闲看门狗（无 HTTP/WS 客户端即优雅退出）；2s 心跳轮询即长活（实测）。
4. **LAN 发现独立可用**：实跑自动枚举办公室 LAN 上 18 台真实设备（U1/U1b/M0/TW3…，`notify.device.discovery_changed` 事件流）。
5. README 明示：自动发现 + **按 IP 添加** + PIN 绑定，本地网络连接为一等公民；`gateway.test.s.com` 测试云存在。

## 分层定责

| 层 | 被测物 | 场 | 用例来源 | 性质 |
|---|---|---|---|---|
| L1 | CLI↔设备行为 | mock 访问日志 | 流量录制派生（真机标定一次+mock 会话 diff），不手写 | 刻画/漂移哨兵，非门禁 |
| L2 | 监控 UI | 浏览器直开 CLI 页（已验证可行，最便宜） | 飞书状态呈现类：温度/进度/报警/设备列表 | 回归资产 |
| L3 | Orca 端到端 | 客机现有 harness | 上传/提交/打印链（浏览器模式覆盖不了，不省） | 回归资产 |

边界：L2 ≠ L3（上传/提交只在 Orca 内成立）；oracle=三方独立读数交叉（mock 状态日志×CLI 自带 log×GUI 读回），mock 不自证；L1 有循环论证陷阱，真机标定抓包是解。

## 四阶段（各有 go/no-go）

### Phase 0 实测结果（2026-11-23，Mac 侧执行，材料在 Mac `~/sc_probe/`）

- ✅ CLI 独立运行于 Mac arm64（v1.10.0 SHA256 校验通过；2s 心跳防 3s 空闲自杀）。
- ✅ **RPC 词汇全集（20 方法）**从 CLI 自带 main.dart.js 提取：`action.device.{connect,disconnect,remove,unbind}`、`query.device.{current,list,discovery}`、notify×12（含 discovery_changed/list_changed/link_state/authorization_changed）。
- ✅ **mDNS 蓝图完整**（dns-sd 实测真机）：服务类型 **`_snapmaker._tcp`**，TXT=`version|machine_type=Snapmaker U1|device_name|sn|link_mode=lan|userid(空!)|ip|region`，SRV 端口真机为 1884。
- ✅ **虚拟 U1 已被真实 CLI 发现**：自写纯 stdlib mDNS 广播器（`mdns_advertise.py`）+ moonraker mock（`mock_u1.py`:7125，全请求落日志）→ CLI 重启后 `onDeviceInfoUpdate sn=8110099900000001MOCK1 name=U1-MOCK` 入列（与 42 条真机记录并列）。
- ✅ 通道确认：`/ws`（101 升级，与 C++ GatewayService 配置一致）+ HTTP 面 `/api/{health,cache/all,account,store,region,config}`；`/api/cache/all` 给出单设备实时监控状态 schema（connection/identity/info/objects/job）。
- ✅ 登录问题实质已答：真机 TXT `userid=` 为空（LAN 设备不绑云账号）。
- ✅ **connect 全链贯通（后续补验）**：有头 Edge（宿主、临时 scratch profile、CDP 驱动）→ Flutter a11y 激活（占位符需 synthetic `.click()`，坐标点击打不中）→ My Devices → Add Device → 附近列表**首位即 U1-MOCK（Lan Mode）**→ 点 Connect → CLI 真实发起 `lan connect host=172.18.6.213 port=7125`，ws 回 `action.device.connect code=-32001`，UI 呈现标准错误弹窗。截图 `artifacts/sc_probe/connect_attempt.png`。
- 🔑 **决定性协议事实：设备通道是 MQTT**（`MqttConnectionException: Connection closed while connecting`）——真机 SRV 端口 1884 = MQTT；moonraker HTTP（/server/*）用于文件面。**Phase 1 修正：虚拟 U1 的设备侧 = MQTT broker + moonraker HTTP**；话题/报文规格源= u1-moonraker 的 mqtt 组件源码（上游 moonraker 有 `[mqtt]` 组件）或真机一次抓包。
- 附获：connect 请求参数 schema（`{"sn","ip"}`——CLI 内部组装）、ws 错误码模型（-32001+完整 exception 链）、UI 错误弹窗文案（"The device communication failed…"——L2 负例断言素材）。

原计划其余阶段不变。

## Phase 1 最终状态（2026-11-23，**连接成功**，详见独立工程 `C:\coil\Projects\orca-virtual-u1\`）

完整协议规格+虚拟 U1 工程 → `C:\coil\Projects\orca-virtual-u1\README.md`（git 仓库 `cb52749`）

**✅ 配对连接全通**（2026-11-23 10:40）：CLI 返回 `connected=true`，U1-MOCK 出现在设备列表（online, Snapmaker U1, v1.4.1）。根因=大通知（4KB 含 PEM 证书）不被 dart_mqtt 处理；迷你通知（仅 state/clientid/sn）通过后 CLI 直接 connected。

**✅ 心跳已修**（2026-11-23 12:05）：状态推送改为 moonraker 真实格式（JSON-RPC `notify_status_update`，pretty 分隔符，QoS1 retained）+ `printer.*` RPC 应答。2 分钟无心跳丢失，`device_connected=true` 稳定。

**✅ 监控状态回放全通**（2026-11-23 12:10）：

| 状态变化 | CLI 读回（/api/cache/all） | 延迟 |
|---|---|---|
| idle → printing(15%, 210°C) | print_state=printing, filename=test_cube.gcode, progress=15.0, extruder=210.5 | <4s |
| printing → error(42%, "Foreign Object Detected") | print_state=error, message=Possible Foreign Object Detected..., progress=42.0 | <4s |
| error → complete(100%) | print_state=complete, progress=100.0 | <4s |

改 `device_state.json` 一个文件 → 2s 内 CLI 全链感知。温度/进度/文件名/层号/故障消息 全部可编程注入。

**⚠️ mDNS 组播风暴事故**（2026-11-23）：旧版广播器因无退避+宽泛匹配在生产网发送 23k pps（77Mbps），致同事 PC CPU0 DPC 77%。已完全重写（`mdns_safe.py`）：30s 间隔、10/min 硬上限、精确匹配、预检、21 项离线单测全过后才部署。修复后 2 包/分钟。

## Phase 1.5 进展（2026-11-23 下午，SHADOW）

- ✅ **虚拟固件 API 通道补齐**（orca-virtual-u1 b1b063a）：`<sn>/request → <sn>/response`（u1-moonraker spec/mqtt.py 权威格式，api_qos=1）。补齐前 CLI 对 `printer.objects.list/subscribe` 全部 -32006 超时、web UI 设备页数据永远不就绪；补齐后 CLI cache 出现独立 `extruder` 对象（temperature/target/power/can_extrude）。
- ✅ **`test_l2.py` 7/7 PASS**（温度/进度/文件名/故障/层号/离线/在线）：cache 级断言（= web UI 数据层消费的精确状态）；场景 7 含 broker 重启 → 自动重配对 → node-WS `action.device.connect`（**port=7125 必须显式**，CLI 存储端口陈旧为 53526）全链自动恢复。
- ⚠️（**当日晚已闭环，见本节末「L2 UI 渲染断言闭环」。以下为原始记录，其中“点击死”“glass pane 未初始化”两条结论已被纠正。**）**L2 UI 渲染层（canvas 文本）断言未达**：CLI web UI（Flutter CanvasKit）在本自动化环境**悬停可用、点击死**（CDP Input / agent-browser / OS SendInput / 语义节点点击全灭；Chrome+Edge 双浏览器对照；无 JS 异常、RPC 全应答）。另有三定律：页面 hidden（遮挡/副屏）→ 冻结渲染+忽略输入+语义树衰减，需 `Page.setWebLifecycleState('active')` + `setFocusEmulationEnabled(true)` 或启动标志 `--disable-backgrounding-occluded-windows --disable-features=CalculateNativeWinOcclusion`；语义树靠 `flt-semantics-placeholder` 点击（懒创建、reload 后重做）；断言备用通道 = Windows OCR（`ocr_words.ps1` 带词坐标）。工具已沉淀在 orca-virtual-u1 `tools/`（ocr_words.ps1 / ui_sem.sh / ws_watch.js / exc_watch.js）。破局路线见 orca-virtual-u1 `NEXT_SESSION_PROMPT.md`（用户手点一次导航 / Mac 侧开浏览器 / 接受数据链结论直进 L3）。

### L2 UI 渲染断言闭环（2026-11-23 傍晚，SHADOW，宿主 dev 调试口径）

- ✅ **`test_l2.py --ui` 17/17**（cache 8 + ui 9）：设备面板 web UI 的**实际渲染**被断言——温度（`210 / 215 °C`、`60 / 0 °C`）、进度（`35%`）、文件名、层（`34/68 layer`）、暂停（`Paused`）、故障（异常弹窗）、离线（离线弹窗 + 数据变占位）、在线（CLI **自行重连** 3–15s 后数据恢复）与恢复后的实时翻转（`80%`）。页面只开一次，之后全是实时更新断言。
- ✅ **负对照 17/17**：每个 UI 检查先等正确预期成立，再要求同一页面状态下被篡改的预期失败。正向连续 4 次 17/17（备选入口页面）；改用桌面端权威页面后再正向 17/17、负对照 17/17；cache-only 8/8。
- **四钉收据**：SUT = CLI 自带设备面板 web UI `main.dart.js` sha256 `ce43ba92…2fbfc1`（`orca 1.10.0 build 20261116160427`）；CLI = `snapmaker_control_macos_arm64` sha256 `d7b813b0…38f44b`；mock 脚本 = `virtual_u1_mqtt.py` sha256 `a23b58a1…b21563`（本地=Mac）；剧本 = orca-virtual-u1 `7972d34`（`c2b8046` 首版 + `b505ca0` 文档 + `7972d34` 权威页面入口）。页面 = CLI `/api/health` 的 `server_url.device_control`。
- **断言通道**：语义树文本（精确，门禁）+ 进度条填充比例（截图像素解码，门禁：0.35 / 0.80）+ Windows OCR（旁证，非门禁——大号百分数读不出）。
- **纠正上一轮四条**：① Control 按钮无需点击——监控页 URL 直达，权威来源是 CLI `/api/health` 的 `server_url.device_control`（`/web/flutter_web/device_control`，上游 `GatewayService::web_url` 读的就是这张表，Orca 桌面设备页加载的即此页）；该按钮的处理链是面向桌面宿主的 `refreshControl` 命令，浏览器里本就是空操作。② “glass pane 0×0 未初始化”是误判——渲染层在 shadow root 内，属该版引擎常态。③ “点击死”只属于有头遮挡实例；headless=new 下真实鼠标点击、悬停、语义点击均可用。④ “CLI 不自愈 / 授权被移除弹窗”是模拟器忘记配对的假象，补注册表后 CLI 自行重连。
- **根因不是 UI 缺陷而是虚拟固件保真缺口**（6 项已修，均有消费证据）：`machine_state_manager` 应报 `{main_state, action_code}`；`info.total_layer`（单数）；`file_position` + `server.files.metadata`；异常通道（`server.exception.query` + `notify_exception_*`）；已绑定客户端注册表；状态文件撕裂读不再重置。清单与 ground truth 见 orca-virtual-u1 `NEXT_SESSION_PROMPT.md`。
- **边界**：宿主直跑（Mac 夹具 + 宿主 headless Chrome），**非信管 VM 运行，不计 GREEN，不写飞书**。未进门禁的假设：`complete`/`error` 的机器状态稳态（真机未抓）、异常弹窗未走本地化标题、缩略图与文件列表接口为空、控制 RPC 未实现。被测物是 CLI 自带面板，**不是 Orca 桌面端**。
- **首里程碑对照**：L2 状态呈现 3 条 → 已 5 条（温度/进度/文件名/层号/暂停）+ 报警负例 1 条（故障弹窗），均 SHADOW；**L3 上传回执仍 0/1**，是下一步。L3 前置：客机到 Mac `172.18.6.213:7125` 的可达性未验；客机桌面被 glm 批队列占用期间不得启动。
- **落点**：源仓 orca-virtual-u1 无 remote（本地至 `6105779`）；其受跟踪文件（不含真机抓包 `spec/pairing_capture.pcapng`）以快照保存在**本仓 `runner/virtual_u1/`**，两边不自动同步。入库时行尾归一为 LF：收据里固件 sha256 `a23b58a1…` 是 Windows 工作树 CRLF 字节口径（即部署到 Mac 的那份），LF 归一化后为 `b5dad467…`。本工作流在本仓的改动走独立分支 `connected-monitoring/l2-ui-20261123`（快照也先在这里），并入批分支要等队列空闲；**不在批队列运行期间**往 `codex/glm-flash-expansion-20261121-0217` 提交（该分支上每条 run 的 `launch.ps1` 硬编码宿主 HEAD，批中提交会让后续 run 快败）。



- ✅ **手写纯 stdlib MQTT v5 broker**（`C:\coil\Projects\orca-virtual-u1\virtual_u1_mqtt.py`→Mac `~/sc_probe/`）：CONNECT/CONNACK（v3/v5 属性字节）、SUBSCRIBE/SUBACK（v5 varint 属性跳越）、PUBLISH QoS0/1（v5 属性+retain）、PUBACK、PING/ pong，全部对 dart_mqtt v5 客户端实测可达。
- ✅ **CLI 的 MQTT RPC 全貌捕获**：CLI 连上即 SUBSCRIBE 四话题（`12345678/config/response`、`<sn>/status`、`<sn>/notification`、`12345678/config/notification`），随即向 `12345678/config/request` PUBLISH `{"jsonrpc":"2.0","id":<snowflake>,"method":"server.client_manager.confirm_lan_status","params":{"clientid":"SnapmakerOrca-<uuid>"}}`（载荷带 `\x02\x00` 二字节内框前缀）。
- ✅ **配对协议三源交叉**（HelixScreen 文档 + n3o Rust 实现 + 我们的 broker 实测）：confirm_lan_status→(unauthorized/authorizing/success)→request_lan_auth→**notify_lan_auth 携 mTLS 材料**（ca/cert/key/sn/port）→客户端以 mTLS 重连 8883。openssl 铸证代码已实现（`mint_client_cert`）。
- ⏳ **唯一卡点（字节级）**：我们的 config/response 应答帧被 CLI 在 5ms 内断连。已排除：state 值（unauthorized/success）、QoS（0/1）、retain（off/on）、v5 属性（len0/payload-format-indicator）。剩余疑点：dart_mqtt v5 会话保持/CONNACK 属性要求、或应答需特定前缀。**一次对真机的 10 秒授权抓包即可定案**（被动订阅 `+/config/#`——真机 1884 端口实测 TCP 可达但需 mTLS 凭据，无法裸听）。
- 环境：Mac 栈常驻（CLI+keepalive+MQTT broker+mDNS 广播+mock HTTP）；宿主 Edge headful+CDP 走 SSH 隧道驱动 UI（前台激活是语义树可用的必要条件）。
- **Phase 1 最小 mock（~半天）**：实现被抓到的端点+mDNS（服务类型从真机观测取）。首闭环用例=上传→设备回执（解 0/7 断点，1 条 L3 SHADOW）。
- **Phase 2 状态机+故障注入（1-2 天）**：秒级回放打印全生命周期；故障档案（热床异物 0002 0532/升温超时/中途断连——真机不可做的负例）。铺 L2。
- **Phase 3 标定+贯通**：一次真机抓包（授权+空闲机）→ mock 差分验证；少量 L3 代表贯通。

## 纪律条目

1. run 收据四钉：SUT SHA + CLI SHA + mock 脚本 SHA + 状态剧本 ID。
2. 失败三归一（mock log/CLI log/GUI 断言），层间不背锅。
3. L1 diff=哨兵；L2/L3=回归。
4. 虚拟 U1=纯 fixture：只实现被调用端点，随版本钉死，不独立演进，不是被测物。
5. 云端远程路径留 blocked（测试云可达性另验，不阻塞本族）。
6. 真机两轻车道：标定抓包一次 + 纯发现被动观测（零连接零风险）。

## 验收定义与首里程碑

每条 L2/L3 用例：固定剧本（状态档案）→ 独立断言 → 清理复位 → 一键重跑 → SHADOW 登记。
首里程碑：L3 上传回执 1 条 + L2 状态呈现 3 条 + 报警负例 1 条，全带四钉收据。
