# 新会话提示词：虚拟 U1 L2 已闭环 → L3（Orca 客内端到端）

以下是完整提示词，直接复制到新会话即可。

---

## 角色与目标

你是 GLM 总控，继续推进 orca-blackbox 的虚拟 U1 联机监控测试。**L2（CLI 设备面板 web UI 渲染断言）已于 2026-11-23 傍晚闭环**：`test_l2.py --ui` 17/17（cache 8 + ui 9），负对照 17/17，正向多次全绿。本轮目标：**L3——在 Orca 桌面端内跑通上传/切片/打印提交链**（少量代表例）。

## 开工三步（宿主现场不持久，每次重建）

```bash
# 1. SSH 隧道（后台常驻）
ssh -i ~/.ssh/id_ed25519_codex_mac_gateway -o BatchMode=yes -o ExitOnForwardFailure=yes \
    -o ServerAliveInterval=30 -N -L 30996:127.0.0.1:30996 coilwin@172.18.6.213
# 2. headless Chrome（独立 profile，不碰用户 Chrome；脚本幂等）
cd /c/coil/Projects/orca-virtual-u1 && tools/chrome_headless.sh          # 端口 9224
# 3. 自检
python test_l2.py --ui --negative-control   # 先证明检查能翻红（≈60s）
python test_l2.py --ui                      # 再看是否全绿（≈45s）
```

**隧道的本地端口必须是 30996，换不了。** CLI 的 WebSocket 握手做同源端口校验——同一条隧道下实测：`Origin` 端口为 `:30996` → `101`，为 `:30997` → `403 Forbidden`。换端口后页面打得开，但 WS 一连上就被关，设备卡渲染不出来（18:18 实跑预检失败）。所以**宿主上开着 Windows 版 Orca 时 L2 的 UI 断言跑不了**：它自带的 CLI（`C:\Users\snapmaker\Documents\Snapmaker_Orca241\resources\snapmaker_control_windows_x64.exe`，2026-11-23 17:43 起监听 30996）会占住这个口，先关掉它。这种情况下 `test_l2.py` 预检会直接报 `serves device None, not the virtual U1 … — wrong --base`，不会误跑到别的 CLI 上。
若 Mac 侧 broker 没起或设备未连：`python tools/deploy_fw.py`（推送固件 → 重启 broker → `action.device.connect` → 校验 cache）。

## 现场状态

**Mac mini 测试机**（coilwin@172.18.6.213，密钥 `~/.ssh/id_ed25519_codex_mac_gateway`），`~/sc_probe/`：

| 文件 | 说明 |
|---|---|
| `virtual_u1_mqtt.py` | 虚拟固件 = 仓 `c2b8046` 版，sha256 `a23b58a1…b21563`（本地与 Mac 一致） |
| `authorized_clients.json` | 已绑定客户端注册表（对应真机 `printer_data/mqtt/client.json`）。**删掉它 = 让设备忘记配对**，下次连接重新走授权 |
| `device_state.json` | 设备状态入口；测试整文件原子替换 |
| `snapmaker_control_macos_arm64` | 官方 CLI v1.10.0，sha256 `d7b813b0…38f44b`，监听 127.0.0.1:30996 |
| `web/flutter_web/` | CLI 自带设备面板 web UI（Flutter），`main.dart.js` sha256 `ce43ba92…2fbfc1`，version.json `orca 1.10.0 build 20261116160427` |

**宿主**：`C:\coil\Projects\orca-virtual-u1\`（master，本地提交；**该仓没有配置 remote，推不出去**）。隧道与 headless Chrome **不常驻**（上轮收尾时已停，避免给同机的批队列添负载），按上面三步重建。

**持久化（2026-11-23 晚起）**：本仓的全部受跟踪文件以**快照**形式并入 orca-blackbox 的 `runner/virtual_u1/`（先在分支 `connected-monitoring/l2-ui-20261123`，并入其批分支要等队列空闲），随 orca-blackbox 的远端保存。两点要知道：
- 快照**不含** `spec/pairing_capture.pcapng`（真机授权抓包；会推到外部远端的东西由用户决定要不要入库）。
- 两边没有自动同步：改了本仓，要重新导出一份快照覆盖过去（见 `runner/virtual_u1/` 下的同一份文档）。orca-blackbox 开着 autocrlf，入库后行尾归一为 LF——收据里的固件 sha256 `a23b58a1…` 是 CRLF 字节口径，LF 归一化后是 `b5dad467…`。

## 本轮结论（2026-11-23 傍晚）— 纠正上一轮的四条

1. **Control 按钮不需要点，也不该点。** 设备监控页走 URL 直达。**权威来源是 CLI 的 `/api/health`**（`server_url.device_control` = `/web/flutter_web/device_control?locale=en-US&dark_model=1`）——上游 `GatewayService::web_url` 就是读这张页面表，Orca 桌面的设备页加载的就是它；`test_l2.py` 运行时取这个 URL。备选入口 `/web/flutter_web/index?tab=device_control&mode=1&id=<sn>`（顶栏式外壳）仅作回退。Control 按钮的处理链是 `refreshControl` 命令（日志串 "manual refresh control"），面向 Orca 桌面宿主——在独立浏览器里**本来就是空操作**：语义点击、真实 CDP 鼠标点击都无页内副作用（对照：同环境真实点击 Home 正常）。此为按包内证据的推断，桌面端内行为留给 L3 验证。
2. **“glass pane 布局从未初始化（0×0/static）”是误判。** 该版 Flutter 引擎把渲染层放在 `flt-glass-pane` 的 shadow root 里（`flt-scene-host › flt-scene › flt-canvas-container › canvas`）；宿主元素自身 `static/inline 0×0` 是常态，`document.querySelectorAll('canvas')` 查不到是因为没穿透 shadow DOM。不存在“app 侧 view 初始化缺陷”。
3. **“点击死”只属于有头遮挡实例**（帧泵停）。`--headless=new` 下真实 CDP 鼠标点击、悬停、语义节点点击全部可用；语义树在点一次 `flt-semantics-placeholder` 后即成型。
4. **页面不反映设备状态不是 UI 缺陷，是虚拟固件保真缺口。** 页面对 WS 推送的消化一直是通的（温度早就实时变）；Printing Task 面板不动是因为固件没给对字段（见下）。
5. **“broker 重启后 CLI 不自愈”与“设备授权已被移除”弹窗都是模拟器忘记配对的假象。** 真机把已绑定客户端持久化，已配对的 slicer 静默重连。补上注册表后，CLI 的重连监督器自行恢复（观测：broker 恢复后 3/4/5/9/15s），全程无 `action.device.connect`、无 authorization 事件。
6. **OCR 不能给大号蓝色百分数当门禁**（"35%" 四次都读成 "0 0"）；温度区、层、剩余时间、异常码可读。进度的像素门禁改用**进度条填充比例**（解码截图像素，35% → 0.350，80% → 0.800）。OCR 只作非门禁旁证。
7. **模态框检测要按按钮不按文案。** 页面有三种模态框（异常 / 离线 / 授权被移除），只认其中两种时 `"dialog": None` 会在第三种存在时判绿（假绿）。现按“含 OK / Got it 按钮的最小 group”检测。
8. **负对照抓出了 3 个我自己的测试 bug**（标签判定写反、恢复后的翻转误置为 idle、非 UI 模式误触未导入模块）。先跑 `--negative-control` 这条纪律留着。
9. **我在批队列运行期间往它的分支上提交过一次**（16:50 `9cae843`，推送了）。16:52:13 用“另存分支 + `reset --keep`”把本地 HEAD 还原到 `aa8e3b7`；暴露窗口内没有新 run 启动，收割逻辑也不读 HEAD。远端上的这个提交后来已被批会话合并（`40ecf8c`），本地与远端现都在 `024733e`，**无遗留**。红线见下节。
   - 同一队列当时的结局（非我造成，但我无法证明零影响，如实记）：`uia_param_first_speeds`（16:45:28 启动）撞 620s 看门狗被杀（其宿主进程 16:53:27 仍存活，晚于我的两次 git 操作 → 不是被我杀的）；随后 `arc_resolution`、`ooze_prevention` 共 4 条启动全部 `Guest desktop busy`（16:57:11–16:59:47），队列 17:00 前退出。这是队列脚本自注的既有故障模式（“wedge ~40%”）。**后续**：该 run 已于 17:08:04 被收割，17:23 起队列启动恢复正常。
10. **CLI 的 WebSocket 握手做同源端口校验**（见“开工三步”下的说明）：隧道的本地端口只能用 30996；宿主上另一个 Orca 的 CLI 占着它时，L2 的 UI 断言在这台宿主上跑不了。启动脚本 `tools/chrome_headless.sh` 曾因后台 Chrome 继承 stdout 而让接管道的调用方永久挂起，已修（输出重定向到 /dev/null）。

## 协作红线（2026-11-23 傍晚踩过，见第 9 条）

`.worktrees\glm`（分支 `codex/glm-flash-expansion-20261121-0217`）是 **glm 批队列的工作树**：队列脚本 `C:\coil\vm_setup\glm_queue*.sh` → `tools/native_save_demo.py` → `hv_go.ps1 -NoSync` 就从这里跑，每条 run 的 `launch.ps1` 把**当时的宿主 HEAD** 硬编码进前置检查。在这条分支上提交一次，队列后续每条 run 都会快败（`demo_guest_sync_or_runtime_required`）。

- 动 orca-blackbox 的任何 git 写操作前，先看有没有 `native_save_demo.py` / `glm_queue*.sh` 进程，以及 `artifacts/native_save_demo/*/launch.stages` 的最新时间。有队列在跑 = 零提交、不切分支、不碰客机、不发 relay 探针（relay 单槽，demo 每 ~8s 轮询）。
- 本工作流在 orca-blackbox 侧的改动走**自己的分支**（现为 `connected-monitoring/l2-ui-20261123`）和独立 worktree `C:\Users\snapmaker\.zcode\worktrees\ab9e\orca-blackbox`（用户已指定）。虚拟 U1 整仓快照也在这个分支的 `runner/virtual_u1/` 下。
- **未并入批分支的一笔**：该分支上的 `060b343`（SHADOW 登记：四钉指向最终剧本 `7972d34`、页面入口改为 `/api/health` 给出的 URL）还没进批分支，批分支上是旧版登记（`9cae843`）。并入要等队列空闲，由批会话合并；不要为了并入它去动 `.worktrees/glm`。
- L3 需要客机桌面：队列没排空之前不要启动。

## 虚拟固件保真缺口清单

**已修（每项都有 UI 包/spec 里的消费证据）：**

| 字段 / 接口 | 修前 | 修后 | 消费证据 |
|---|---|---|---|
| `machine_state_manager` | `{state: "printing"}`（自造） | `{main_state, action_code}` 整数 | UI 包 `parseInt(main_state/action_code)`，缺失即保留旧值 → 卡片恒 idle |
| `print_stats.info.total_layer` | `total_layers`（复数，猜测） | `total_layer` | UI 包 `info["current_layer"]/info["total_layer"]` |
| 进度 / 剩余时间 | 只有 `display_status.progress` | `virtual_sdcard.file_position` + `server.files.metadata {gcode_start_byte, gcode_end_byte, estimated_time}` | UI 包：`(pos−start)×100/(end−start)`；metadata 为空 → 0% / N/A |
| 故障呈现 | `server.exception.query` 恒回空 | 按 `fault` 回 `{id,index,code,level,message,timestamp}`；变化时推 `notify_exception_status` / `notify_exception_notification` | UI 包解析器 + 页面 WS 抓包；CLI 会把 `<sn>/notification` 原样转发 |
| 配对持久化 | 每次重启都 unauthorized | `authorized_clients.json`；已绑定客户端的 `confirm_lan_status` 回 `{state:"success", access_code, sn, clientid, app_id, …}` | CLI 报错逐项反推：`authorized` → "unexpected state"；缺 `access_code`/`sn` → 空主题过滤器 |
| 状态文件撕裂读 | 读到半截 JSON 就重置为默认值 | 回落到上一次读到的完整快照，不写文件 | 竞态分析 |

状态码口径：main_state 0=Idle、**1=Working**、7=Error、14=Offline；action_code 0、129=Paused、130=Resuming、137=异常暂停、138=异常取消、139=取消、140=完成（spec `snapmakercloud.py` AC_PRINT_*）。**卡片只在 `main_state == 1` 时渲染打印视图**，所以 paused/error/complete 默认都保持 main_state=1。

**未实现 / 属假设（未进门禁，别当事实用）：**

- `complete` 的机器状态 `(1,140)` 是事件时快照的假设，真机完成后稳态**未抓过**；该输入下 UI 显示 `working + 100% + N/A`，没有“完成”徽标。
- `error` 默认 `(1,138)`：卡片仍显示 working、**卡片上无报错文字**，故障只靠异常弹窗呈现；`(7,x)` 则是 idle 式卡片 + `Error` 徽标。真机热床异物实际走哪条未知（en.json 文案暗示是“暂停等确认”，即 137）。
- 异常弹窗标题是通用的 `Exception` + 设备 message，没走 `error_<level><id><index><code>_title` 的本地化查找（可能需要别的字段）。
- `server.files.thumbnails_base64` 回 `{}` → 一直显示默认封面；`server.files.list_page` 回 `{}`。
- 暂停/恢复/停止按钮会触发 CLI 的控制 RPC，固件未实现（未知方法回 `{}`）。
- mTLS 8883 未实现：首次配对靠迷你 `notify_lan_auth` 让 CLI 以明文继续（README 既有结论）。
- “CLI 重启后不自动连设备”是补注册表**之前**的观察，未复验。
- mDNS 不参与（IP 直连，零组播风险）。

## 页面渲染 ground truth（headless=new，en-US，viewport 1584×905）

| 设备状态 | Printing Task 卡片 | 其他 |
|---|---|---|
| idle | `idle` 徽标 + 设备名，灰态占位 | — |
| printing | `working` · 文件名 · `N%` · `cur/total layer` · `Time remaining：Xm` | 进度条按比例填充；暂停/停止键 |
| paused | 同上 + 独立文案 `Paused` | 暂停键变恢复键 ▶ |
| error (1,138) | `working` 视图，无报错文字 | 弹 `Exception / Error Code: 0002 1330 0000 0001 / <message> / Got It`，关掉后无常驻标识 |
| offline | 无卡片数据、温度变占位图 | 弹 “The device is currently processing the offline state…” + `Check Network` + `OK`；设备回来后**自动关闭** |

显示规则：温度取整（210.5 → `210`，22.1 → `22`）；`display_status.progress` 按**整数百分数**解析（量纲保持 35.0 不变）；剩余时间 = `toInt(estimated_time × (1−pct/100))` 再向下取整到分钟（3600s@35% → 2340s → 显示 `38m`，浮点截断所致）。

## 已固化的工具（本仓 `tools/`）

| 工具 | 用途 |
|---|---|
| `cdpclient.py` | stdlib CDP 客户端：`navigate`（自动点占位符启用语义树）/ `semantics` / `screenshot(clip, scale)` / `click` |
| `uiprobe.py` | 页面读取层：`task_card` / `temperatures` / `texts` / `modal` / `ocr_words` / `bar_fill` |
| `pngpix.py` | 最小 PNG 解码（像素断言用） |
| `deploy_fw.py` | 推固件到 Mac + 重启 broker + 重连 + 校验 |
| `chrome_headless.sh` | 起自动化用 headless Chrome（9224） |
| `cdp.js` | 交互式 CDP 小工具：`nav / sem / semclick / semid / xy / move / shot / info`，`--watch` 旁路 WS 帧/导航/异常（不 reload） |
| `ocr_words.ps1` | Windows OCR，输出 `词@x,y,w*h` |
| `click_watch.js` / `ws_watch.js` / `exc_watch.js` | 上轮观察工具；**`ws_watch.js` 会 Page.reload，勿在断言中途跑** |

## 本轮任务：L3（Orca 客内端到端）

- Hyper-V 客机 `win11-test`，入口 `runner/hv_go.ps1`（orca-blackbox 仓纪律：宿主直跑需 `ORCA_BB_ALLOW_HOST=1`）。L2 全程是宿主 dev 调试口径（Mac 夹具 + 宿主 headless Chrome），**不是信管 VM 运行，不计 GREEN**。
- 用 Orca 的 Prepare 页 + 设备页完成上传/切片/打印提交链（少量代表例）。首条 = 上传回执（解 0/7 断点）。
- 虚拟 U1 对 Orca 来说就是 LAN 设备（`172.18.6.213:7125`，SN `8110099900000001MOCK1`）。客机到 Mac 的网络可达性未验，先探。
- L3 很可能需要固件补控制面 RPC（打印启动、文件上传 `server.files.upload`/`post`）；按“只实现被调用端点”的纪律，从 WS/MQTT 抓包里取真实调用再补。
- 顺手可做：用 Orca 宿主内嵌的同一页验证 Control 按钮（桌面宿主下）的行为。

## 收尾纪律

- 测试结果全部记 SHADOW，不进发布 GREEN；报绿前先有负对照红。
- 上游 `C:\coil\Projects\SnapmakerOrca` 源码只读。
- orca-blackbox 侧：`hv_harvest.ps1` → commit+push → `tools/feishu_writeback.py`（仅 GREEN/已覆盖）。orca-virtual-u1 仓无 remote，只能本地提交。

## 关键路径备忘

- 虚拟 U1 仓：`C:\coil\Projects\orca-virtual-u1\`（master `c2b8046`）
- 监控计划与 SHADOW 登记：orca-blackbox `docs/V3_CONNECTED_MONITORING_PLAN.md`
- 本轮截图证据：`artifacts/l2_ui/<时间戳>/`（gitignored；`*-negative` 为负对照）
- 静态分析素材：web UI 包与 en.json 的离线副本在 `%TEMP%\orca-webui\`，辅助脚本在 `%TEMP%\orca-webui-tools\`（均可删，按需重新 curl）

---

## 提示词结束
