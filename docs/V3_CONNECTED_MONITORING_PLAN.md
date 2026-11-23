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

**⚠️ 心跳待修**：连接 60s 后 CLI 报 `heartbeat lost`——需调整 `<sn>/status` 推送频率/格式。

**⚠️ mDNS 组播风暴事故**（2026-11-23）：旧版广播器因无退避+宽泛匹配在生产网发送 23k pps（77Mbps），致同事 PC CPU0 DPC 77%。已完全重写（`mdns_safe.py`）：30s 间隔、10/min 硬上限、精确匹配、预检、21 项离线单测全过后才部署。修复后 2 包/分钟。

## Phase 1 实测进展（2026-11-23 深夜，Mac 侧，九小时计划第 1.5h）

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
