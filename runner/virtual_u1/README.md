# Virtual U1 — Snapmaker Orca 联机监控测试夹具

纯 stdlib 实现的虚拟 Snapmaker U1 打印机，用于测试 Orca 的设备发现/配对/监控链路。协议规格源自开源固件（u1-klipper/u1-moonraker）+ 社区逆向（n3o/HelixScreen）+ 一次授权真机抓包（2026-11-23）。

> **保存位置**：本仓没有 remote。2026-11-23 晚起，除真机抓包 `spec/pairing_capture.pcapng` 外的全部受跟踪文件以快照形式并入 orca-blackbox 的 `runner/virtual_u1/`；两边不自动同步，改了这里要重新导出快照。接手先读 `NEXT_SESSION_PROMPT.md`。

## 组件

| 文件 | 角色 |
|---|---|
| `virtual_u1_mqtt.py` | MQTT v5 broker + moonraker 状态模拟器 + 配对协议（confirm_lan_status → request_lan_auth → notify_lan_auth approve + mTLS 证书铸造） |
| `mdns_advertise.py`（在 Mac `~/sc_probe/`） | `_snapmaker._tcp` mDNS 广播（TXT: machine_type/sn/link_mode=lan/ip/port） |
| `mock_u1.py`（在 Mac `~/sc_probe/`） | moonraker HTTP API mock（/server/info 等） |
| `ws_pair.py` | WCP JSON-RPC 客户端（直连 CLI 的 /ws 通道，浏览器头+permessage-deflate） |
| `real_listen.py` | 真机被动监听器（MQTT 订阅真机 1884 端口采集协议） |
| `test_l2.py` | L2 监控场景回归：cache 断言 + `--ui` 设备面板渲染断言（`--negative-control` 验证检查能翻红） |
| `tools/cdpclient.py` `tools/uiprobe.py` `tools/pngpix.py` | 设备面板读取层：CDP 客户端 / 语义树与模态框解析 / 截图像素 |
| `tools/deploy_fw.py` `tools/chrome_headless.sh` | 推固件到 Mac 并重连 / 起自动化用 headless Chrome |

## 设备面板 UI 断言与固件保真（2026-11-23 傍晚）

`python test_l2.py --ui` 断言 CLI 自带设备面板 web UI 的**实际渲染**：17/17（cache 8 + ui 9），`--negative-control` 17/17。完整战报、ground truth 与未验证假设见 `NEXT_SESSION_PROMPT.md`。

**页面通道**
- 入口走 URL：以 CLI `/api/health` 公布的 `server_url.device_control` 为准（`/web/flutter_web/device_control?…`，Orca 桌面读的就是这张表，上游 `GatewayService::web_url`）。设备卡上的 Control 按钮在浏览器里是面向桌面宿主的空操作，不必点。
- `--headless=new` Chrome（`tools/chrome_headless.sh`，端口 9224）；点一次 `flt-semantics-placeholder` 后语义树成型。渲染层在 `flt-glass-pane` 的 shadow root 里。
- 温度按钮文本（`<当前>\n/\n<目标>\n°C`，整数）与 Printing Task 卡片的 aria-label 就是页面渲染的文字；进度条填充比例从截图像素测得（门禁）。Windows OCR 只作旁证——大号蓝色百分数它读不出。
- 模态框有三种（异常 / 离线 / 授权被移除），按 OK / Got it 按钮检测，不按文案。

**固件必须给对的字段**——缺了它们页面看似“不刷新”，实为保真缺口：

| 设备侧 | 页面的消费方式 |
|---|---|
| `machine_state_manager {main_state, action_code}`（整数） | 卡片状态；只在 `main_state == 1` 时渲染打印视图 |
| `print_stats.info.total_layer`（单数）+ `current_layer` | `cur/total layer` |
| `virtual_sdcard.file_position` + `server.files.metadata` 的 `gcode_start_byte/gcode_end_byte/estimated_time` | 百分比与剩余时间由此计算，不是读 `display_status.progress` |
| `server.exception.query` + `notify_exception_status` / `notify_exception_notification`（`<sn>/notification`） | 故障弹窗 `Exception / Error Code: <level id index code> / <message>` |
| 已绑定客户端注册表 `authorized_clients.json` | 已配对客户端的 `confirm_lan_status` 回 `{state: "success", access_code, sn, …}`，CLI 才会静默重连 |

## 已验证的协议事实（真机抓包 2026-11-23，230 帧 pcapng）

### mDNS 发现
- 服务类型：`_snapmaker._tcp.local.`
- TXT 记录：`version | machine_type=Snapmaker U1 | device_name | sn | link_mode=lan | userid=(空) | ip | region`
- SRV 端口：1884（MQTT）真机 / 7125（mock 用）

### MQTT 配对通道（端口 = SRV 通告端口）
1. CLI 连接 MQTT v5 → SUBSCRIBE 四话题：
   - `12345678/config/response` QoS1
   - `<sn>/status` QoS1
   - `<sn>/notification` QoS1
   - `12345678/config/notification` QoS1
2. CLI PUBLISH → `12345678/config/request`：
   ```json
   {"jsonrpc":"2.0","id":<snowflake>,"method":"server.client_manager.confirm_lan_status",
    "params":{"clientid":"SnapmakerOrca-<uuid>","app_id":""}}
   ```
3. 设备响应 → `config/response`（QoS1, 无 id 前缀，`: ` 分隔）：
   ```json
   {"jsonrpc": "2.0", "result": {"state": "unauthorized", "clientid": "...", "app_id": "", "message": "client is unauthorized"}, "id": <echo>, "cli_time": -1, "dev_time": <unix秒>}
   ```
4. CLI 发 `request_lan_auth`（params 加 `app_id:"app-<snowflake>"`）
5. 设备响应 `authorizing`
6. 设备推 `notify_lan_auth` → `config/notification`（QoS1）：
   ```json
   {"jsonrpc": "2.0", "method": "notify_lan_auth", "params": [{"state": "approve", "clientid": "...", "sn": "...", "ca": "<PEM>", "cert": "<PEM>", "key": "<PEM>", "port": 8883, "app_id": "..."}]}
   ```
7. CLI 以收到的 mTLS 证书重连 8883 端口 → 配对完成

### 关键字节级陷阱（全部踩过）
- MQTT v5 所有出向帧（CONNACK/SUBACK/PUBACK/PUBLISH）需带属性字节
- JSON 必须用 `", "` / `": "` 分隔（pretty 风格）
- `id` 在 `result` 之后，且必须回显请求 id
- `cli_time: -1` 和 `dev_time: <unix秒>` 必须存在
- PUBLISH 固定头 flags 字节的 QoS 位在低半字节（不在变头）
- QoS1 请求必须收到 PUBACK，否则 60 秒超时断连
- notify_lan_auth 应 QoS1 且在 authorizing 响应后 ≥2s 发送（模拟人类点屏延迟）

## 配对状态机到达记录

> 历史记录（2026-11-23 上午）。下表“待修”一行与下文“心跳（待修）”一节均已过时：配对与心跳后来都通了（orca-blackbox 提交 d92abe6；本轮长时间保持连接、cache 新鲜度 1–2s 可复核）。

| 步骤 | CLI 日志 | 达到次数 |
|---|---|---|
| 发现 | `onDeviceInfoUpdate sn=...MOCK1` | ✓ |
| MQTT 连接 | `mqtt Connected (sessionPresent=false)` | ✓ |
| confirm_lan_status | `CONFIG-REQ confirm_lan_status` | ✓ 多轮 |
| unauthorized 响应被接受 | CLI 主动发 request_lan_auth | ✓ 多轮 |
| authorizing 响应被接受 | `info/lan_auth/lan authorizing (等待设备端确认)` + `notify.device.authorization_changed` | ✓ 多轮 |
| notify_lan_auth approve 消化 | → `approval timeout`（通知未被处理） | **待修** |

## 部署位置（Mac mini coilwin@172.18.6.213）

```
~/sc_probe/
  virtual_u1_mqtt.py    # MQTT broker (port 7125)
  mdns_advertise.py     # mDNS 广播器
  mock_u1.py            # HTTP moonraker mock
  ws_pair.py            # WCP JSON-RPC 客户端
  real_listen.py        # 真机被动监听
  certs/                # openssl 铸造的 CA + 客户端证书
  snapmaker_control_macos_arm64  # 官方 CLI v1.10.0
  web/flutter_web/      # CLI 的 web UI
```

## 配对连接结果（2026-11-23 10:40）

**虚拟 U1 已成功连接**：
```json
{"jsonrpc":"2.0","id":1795401637292,"result":{"success":true,"sn":"8110099900000001MOCK1","connected":true,"type":"LAN"}}
```
CLI 推送链：`notify.device.authorization_changed(authorizing)` → `notify.device.authorization_changed(ready)` → `notify.device.connected(link_state=connected, responsive=true)` → `notify.device.current_changed` → `notify.device.list_changed(U1-MOCK, online, machineType=Snapmaker U1, version=1.4.1)`

**根因**：大通知（~4KB 含 PEM 证书）不被 dart_mqtt 处理；迷你通知（仅 state=approve+clientid+sn）通过后 CLI 直接进入 connected（未做 mTLS 证书重连，以明文模式继续）。

## 心跳（待修）

连接 60 秒后 CLI 报 `heartbeat lost → device not responding`。需调整 `<sn>/status` 推送频率/格式以匹配 CLI 期望的心跳信号。

## mDNS 组播风暴事故与修复（2026-11-23）

**事故**：旧版 `mdns_advertise.py` 在生产网络上因无退避循环发送 mDNS 组播（23,000 包/秒，77Mbps），导致同事 PC CPU 0 被 DPC 占满 70-91%，网络交换机受影响。

**根因**：主循环每次迭代无条件 announce + 匹配条件过于宽泛（`_snapmaker` 子串匹配所有真机流量）→ 反馈循环。

**修复**（`mdns_safe.py`，完全重写）：
1. 宣告间隔 ≥30 秒（`ANNOUNCE_INTERVAL=30`）
2. 只应答精确匹配（实例名或服务类型等值比较，拒绝子串匹配）
3. 组播速率硬上限 10 包/分钟（超限自停）
4. 21 项离线单测全过后才部署（`test_mdns_safe.py`）
5. 启动前预检现有 mDNS 流量密度（>50pps 中止）
6. 每日预算 2000 包（超限自停）
7. 响应冷却 ≥2 秒
8. DNS 头部 ANCOUNT 修正（4 条答案记录在正确字段）

**修复后实测**：2 包/分钟（vs 事故版 23,000 包/秒，降幅 99.999%）

## 文件清单

| 文件 | 用途 |
|---|---|
| `virtual_u1_mqtt.py` | MQTT v5 broker + moonraker 状态模拟 + 配对协议 |
| `mdns_safe.py` | 安全 mDNS 广播器（限速+精确匹配+预检+自停） |
| `test_mdns_safe.py` | mDNS 广播器 21 项离线单测 |
| `ws_pair.py` | WCP JSON-RPC 客户端（浏览器头+permessage-deflate） |
| `real_listen.py` | 真机被动监听器（授权采集用） |
| `spec/` | 协议规格源码（u1-moonraker 组件 + 社区逆向文档） |
