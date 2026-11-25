# orca-blackbox — Snapmaker Orca 黑盒视觉 GUI 测试套件

当前GUI AI路线与下一阶段统一见[**v3主方案**](docs/V3_PLAN.md)：先修永久撤销/有限恢复与画布能力，再冻结未见任务泛化评估；历史运行结果不重标，发布闸不变。

对 `snapmaker-orca.exe` 做**外部黑盒**驱动：截图 → 模板匹配定位 → 消息级输入注入 →
截图断言。全程不接触 app 内部 API（与上游仓库 `tests/wx_gui/` 的进程内白盒路线互补）。

> **出处**：本仓内容源自 Snapmaker_Orca monorepo 的
> `sandboxes/vision_gui/`（分支 `sandbox/vision-gui-blackbox`，经
> `git filter-repo --subdirectory-filter` 保留全部 38 个提交拆出，2026-09-02）。
> 被测对象 = 上游构建产物；本仓对上游源码零依赖（fixture 与预设资源已 vendored）。

## 跑批纪律与收尾（新会话必读）

本条是唯一权威条文；`PITFALLS_0901.md` 是证据库，`runner/README.md` 是执行细节。违背历史基线：09-02 / 09-08 / 09-16 / 09-17 四个会话，用户先后 7 次训斥"去虚拟机上跑"——所以纪律从会话口头挪到了这里，并由 `harness/host_guard.py` 机械强制。

1. **执行位置**：批量回归 / 用例 / 探针默认在 Hyper-V 客机 `win11-test` 跑（唯一入口 `runner/hv_go.ps1`）。宿主直跑仅限 dev 调试 / 用户明令，且必须 `ORCA_BB_ALLOW_HOST=1` 显式放行（launcher 强制拦截，否则 exit 2）；宿主跑出的结果**不是回归证据**。
2. **跑批前**：`hv_go.ps1` 会自动打印 PITFALLS §15 checklist，照做即可。
3. **提交**：阶段性成果及时 commit+push（客机 09-03 起 git clone 跟踪 origin，未推送的改动到不了客机）；状态如实——红可以提交，**禁止把未验证写成 GREEN**。
4. **收尾三步**：`runner/hv_harvest.ps1` 拉结果 → commit+push → `tools/feishu_writeback.py`（仅 GREEN/已覆盖项，宿主 lark-cli，**禁止把扫码/授权 URL 甩给用户**）。
5. **边界**：上游源码 `C:\coil\Projects\SnapmakerOrca` 只读，禁止修改；任务范围外的事不做。
6. **第二条实体线（物理机 fa706g3，2026-11-23 起）**：用途是在客机之外并行跑参数族用例，不是回归证据来源的变更。约束：(a) 必须用与客机**同一份 2.4.0 构建**和**同一版 Snapmaker 预设**（fa706g3 上的资源与客机相差 325 个预设文件——`C:\coil\vm_setup\fa_line\manifest_diff.py` 比较客机预设清单与 fa 侧目录；第一次跑就因 `change_filament_gcode` 不同被判「改了无关设置」）；(b) 放行开关是 `ORCA_BB_ALLOW_TESTBOX=1`（`host_guard.allow_testbox`，与 dev 用的 `ORCA_BB_ALLOW_HOST` 分开），每个 run 写 `execution_host.json`，结果只能计 SHADOW；(c) GUI 只能经**计划任务**进交互会话（`glm_line`），SSH 会话里直跑 GUI 会崩；(d) 它执行的 HEAD 在其 GUI 批运行期间不得改变——同步只在批与批之间做。宿主入口脚本不在仓库内（`C:\coil\vm_setup\fa_line\`），细节见[运行记录](docs/runs/glm-flash-expansion-2026-11-21.md)。参数族闭环数一律用 `python tools/param_closure_list.py --ids` 现算。
7. **停队列与换版本**（2026-11-24 起）：只停最外层任务不够——宿主侧的循环脚本和派活进程（客机 `glm_queue*.sh` / `native_save_demo.py`，fa `fa_queue*.sh` / `fa_run.py`）会变成孤儿继续派下一条，要按命令行找到 PID 一起结束；在跑的那一条让它在机器上自己跑完，结果作废、不收割。给某条线换 HEAD 之前先确认它空闲：fa 用 `((Get-ScheduledTask glm_line).State -eq 'Ready') -and -not (Get-Process snapmaker-orca -ErrorAction SilentlyContinue)` 让远端返回 True/False（不要在 Git Bash 里 grep 中文状态文本）；客机在 `native_save_demo` / `glm_queue` 进程数为 0 之后才 `guest_v3_bundle_sync.ps1`。11-24 在 fa 运行中切过一次 HEAD，那一条 run 作废。
8. **改引擎之后的三件事**（2026-11-24 起，三件都吃过亏）：(a) 除 `tools/test_param_engine_sim.py` 外跑 `python -B -m pytest -q unit_tests`（约 4.5 分钟）——有两条单测红了一夜没人发现；(b) 共享路径（对话框、下拉、复选框、文本框）改完后，在最终合并的引擎上把参数族**全部**重跑，不能只跑「改过的路径」；(c) pilot 的返回值就是 business 检查的 detail，上限 4096 字符，而验证器把非证据类异常一律写成 `native_evidence_unavailable`——见到这个签名先在产生该 run 的提交上跑 `python tools/verify_one_real.py <run>` 看真实异常。用例的值逐字取自飞书步骤（含单位），判据不得迁就引擎打了什么：#270 / #271 曾被写成百分数，见 PITFALLS §21。
9. **引擎冻结后只回归一次**（2026-11-24 起）：共享路径（对话框、下拉、复选框、文本框、`run_ops`）还在改的时候不做全族回归——那一夜 02:05 的 39 条全过在两小时后作废（那 144 机器分钟等于白花），之后在最终引擎上又全部跑了一遍。合并前只跑 6–8 条「金丝雀」（每类共享路径各一条）；全族回归留给最终合并的引擎，客机与 fa 分跑。
10. **新夹具、新操作先跑一个，读懂再放量**（2026-11-24 起）：新夹具先只在一条线上跑它的 `uia_param_*_save_only` 基线，用 `python tools/run_info.py <run>` 读结论、`python tools/diff_saved.py <仓根> <run>` 看保存前后差了什么；是 NON_GREEN 就先修，不在第二条线上开队列。给某条用例补一个操作也一样，先单跑那一条（#272 的桥速度写错框就是这么来的）。
11. **「导出件里为什么没有 X」先读、后跑**（2026-11-24 起）：(a) 先用 `tools/gcode_facts.py` / `tools/feishu_expect_facts.py` 读已经收割的导出件；(b) 再查源码（宿主 2.4.1 `C:\coil\Projects\SnapmakerOrca\src`；fa706g3 上有 2.3.5），可以直接派给靶机 agent 做静态定位；(c) 每个假设只跑一个实验，带环境变量的实验先在日志里确认开关真的生效。#296 的行号靠跑试了约 7 个 run，读源码 20 分钟就有答案。

宿主侧现成命令（不在仓库内，`C:\coil\vm_setup\`）：`stop_queues.ps1` 先不带参数列出宿主侧的循环与派活进程、带 `-Stop` 才结束；`sync_all.py` 一条命令走完「空闲检查 → dev 快进到主线 → 推送 → 客机 → fa」，任一步发现那条线不空闲就停在那里。合并前的离线检查用仓内的 `python tools/pre_merge.py`（引擎套件、单测、操作表校验、红证）。某条线空着而主线被卡住时，按 `backlog.txt` 跑还没覆盖的副本或第二样本——这部分单独记账，不计入闭环数。

11 月 24 日 GLM 扩样的接收依据见[31 个 Script 场景同版本复跑](docs/runs/glm-flash-expansion-2026-11-21.md)、[飞书 44 行逐项对照](docs/runs/evidence/feishu-expect-vs-gcode-2026-11-24/own-models-verdicts.md)和[89 个旧用例的迁移初稿](docs/runs/p0-3-signoff-draft-2026-11-22.md)。飞书参数行可用以下命令在仓库根目录复核：

- `python tools/replay_case_evidence.py <收据路径>` 离线重判 #201 保存、#244 添加模型、#249 添加部件和 #250 负零件的归档文件，同时核对反例。见[离线试跑](docs/runs/offline-oracle-replay-2026-11-25.md)、[#249 客机计时](docs/runs/evidence/feishu-249-2026-11-25/README.md)和[#244 客机与 #254 实体机证据](docs/runs/evidence/multi-244-254-2026-11-25/README.md)。
- `python tools/feishu_vs_table.py . --json` 按行列出步骤里出现而用例表缺少的键。
- `python tools/feishu_rows_compare.py . --check-expectations` 比较指定模型的最近一次基线和用例导出件。当前核对 #258 的挤出圆弧、#262 的顶底面单位长度挤出量、#273 的非首层最高频空驶进给及 #277 的支撑主体和界面挤出。缺少收割件或判定失败时返回非零。通过仅计对应的可观测项。

v3 运行骨架入口见 [架构设计](docs/V3_RUNTIME_ARCHITECTURE.md) 和 [使用与边界](docs/V3_FOUNDATION.md)。当前 `python tools/v3_session.py smoke` 仅验证无 GUI 的 synthetic 完整调用链，不能作为产品回归通过证据。

原生 Codex + Windows-MCP 的编辑保存业务 demo 见 [冻结路线与验收](docs/V3_NATIVE_SAVE_DEMO.md)，宿主入口 `python -B tools/native_save_demo.py`。AI 自主保存后，由停止输入后的可信阶段独立重开、切片导出，统一复用 run_once；已完成一次真实客机 SHADOW，首轮收尾失败保留，见 [两轮运行记录](docs/runs/native-save-2026-11-17.md)，不能计发布 GREEN。

Mac 后台工程编辑用例从原始立方体切片开始，以新名字编辑并保存副本，再用独立进程重开切片。入口为 [macos_project_copy.py](runner/macos_project_copy.py)。Windows 和 Mac 的候选运行用[构建报告工具](tools/gui_build_report.py)汇总。[跨平台回归安排](docs/V3_PLAN.md#9-跨平台-gui-回归安排) · [本轮命令和实机证据](docs/runs/gui-layer-candidate-2026-11-20.md)。walls 目标（壁环数 2→3）已在该入口取得首次 SHADOW（**Mac 口径**：macOS / Orca 2.4.1，仅计 SHADOW，不计入 Windows 参数族）：屏录+OCR 通道解锁自绘 Strength 页签与行寻址；判据是差分判据 `verify_walls_differential`（Windows 轨道判据会拒绝 2.4.1 保存期的配置迁移噪声），该判据经 52 项负对照验证——基线自身、只改别的键、壁环数 3 并夹带无关改动、壁环数 4 全部被拒，宿主在 Mac 上独立重跑复现（run 306d3efe）。保留项：界面读回是「读到期望值才落账」的闸门而非测量；GUI 导出 G-code 未测；[运行记录](docs/runs/mac-author-walls-2026-11-23.md) · [负对照证据](docs/runs/evidence/mac-walls-a6-negative-controls-2026-11-23/README.md)

当前 **ZCode / Snapmaker glm-5.4** 路线入口为 `python -B tools/native_save_demo.py --actor zcode`，使用现有 Snapmaker 供应商配置。[接口与边界](docs/V3_ZCODE_ACTOR.md) 原生保存路线的客机编辑、保存、新 profile 重开及 112 层 G-code 证据来自 **glm-5.3-flash**，随原始收据保留。[历史运行记录](docs/runs/zcode-snapmaker-2026-11-17.md) 路线结果只在 SHADOW 范围内验收。 GLM‑5.4 与 Script 在 #265、#276 两种初态上的实测结果见[维护对照记录](docs/runs/glm54-maintenance-265-276.md)。

#265 风扇、#276 流量的独立复算，以及 `win11-test` 上 GLM‑5.4 的后续编辑实测，见[三机复核记录](docs/runs/glm54-multimachine-2026-11-24.md)。 2026‑11‑25 九小时三机跑批的结论、逐项对照、各动作耗时、判据反例、复跑入口和证据包见[九小时运行记录](docs/runs/glm54-nine-hour-run-2026-11-25.md)。

九小时跑批后的三机复验新增一条飞书原用例完整实证。[#47 色盘取消](docs/runs/evidence/ninehour-2026-11-25/row-47-hyperv/README.md)提供独立的客机复跑入口与逐步读数。[#264 实体机验收](docs/runs/evidence/ninehour-2026-11-25/row-264-fdm-followup.md)记录错误 G-code 的负对照和仍未满足的预期。[Mac 壁环重开](docs/runs/evidence/ninehour-2026-11-25/mac/repair-README.md)记录三个独立进程的壁环读值。

飞书 #46、#48、#199 的[逐条验收与复跑计时](docs/runs/feishu-46-48-199-followup-2026-11-25.md)包含各行的独立客机入口、原始证据和首次调通耗时。

飞书 #140、#201、#202 的[进程退出与工程保存验证](docs/runs/feishu-140-201-202-followup-2026-11-25.md)记录正常退出后的进程检查、保存文件的校验和独立复跑结果。

首次自动化的两个对象右键流程见[负零件切片与外部 STL 重载实跑](docs/runs/feishu-250-251-followup-2026-11-25.md)，包含 #250 的局部挤出路径对照和 #251 的缺源响应。

飞书文件导入导出行（#227–#238、#246、#251、#254）的[十一小时客机验收](docs/runs/elevenhour-file-io-2026-11-26.md)：五条进入默认回归并已写回（#227、#233、#234、#236、#238），其余逐行给出「预期不成立」「部分覆盖」或探针结论，含复跑入口、计时、实体机 fa706g3 的旁证和 Mac 的命令行对照。这一段踩过的坑在 PITFALLS §22。

三业务线并行探索入口见[业务pilot](docs/V3_BUSINESS_PILOTS.md)（下文的「87 条」是 11-17 时点的登记册数；11-21 冻结为 89 条登记，见[台账](docs/V3_MIGRATION_LEDGER.md)）

首个真实 Script 的接入与验证方式见 [m0 Script adapter](docs/V3_SCRIPT_ADAPTER.md)，客机入口为 `runner/hv_go.ps1 -V3 -Cases m0_boot_check`；结果单独记 SHADOW，不进入发布 GREEN。

首个真实 AI 页签闭环见 [AI adapter](docs/V3_AGENT_ADAPTER.md) 与 [正反例运行记录](docs/runs/v3-agent-2026-11-16.md)：codex_chat 和无人值守 codex_cli 看图，经受限 stdio MCP 操作客机，独立检查通过；无变化反例被拒绝。页签能力仅为 SHADOW。

首个 AI 业务闭环见 [层高架构](docs/V3_AGENT_LAYER.md) 与 [首次运行记录](docs/runs/v3-layer-2026-11-16.md)：无人值守 AI 看图编辑 0.40→0.24 mm，经 GUI 切片导出 A/B，独立检查实际对象层序 68→112 层、初层保持 0.40 mm，并确认正常退出与 Job 清空。后续冻结版本的 5 次新 profile AI 运行均为 SHADOW；改错参数、漏重切、导出目标冲突三个固定故障探针均被相关检查拒绝，详见 [评估记录](docs/runs/v3-layer-evaluation-2026-11-16.md)。历史失败保留，不代表 87 条回归、跨版本可靠性或发布验收完成。

第二项业务已实现“参数编辑 → 保存 3mf → 关闭并以新 profile 重开 → GUI 重切导出”的整链，复用同一运行骨架；[接口与边界](docs/V3_PROJECT_CONTRACT.md)。前两批保存标题问题已定位；第三批首槽 GUI 整链自然完成，但保存配置的预设名称被业务 oracle 拒绝，原结果仍为 NON_GREEN，各批四个未执行槽位保留，第四批待验，见 [本批记录](docs/runs/v3-project-2026-11-17.md)；不把代码实现或纯测试通过写成 GUI 通过，结果仍限定 SHADOW/NON_GREEN。

- 范式参照：[MaaAssistantArknights](https://github.com/MaaAssistantArknights/MaaAssistantArknights) /
  [ok-wuthering-waves](https://github.com/ok-oldking/ok-wuthering-waves)
- 引擎选型：**MaaFramework (pip MaaFw) 优先**，其 Win32 控制器消息注入若无法路由到
  wx 子控件，则用 Python 自定义 action（`WindowFromPoint`+`SendMessage`，见
  `harness/winutil.py`）补洞；纯自研兜底。

## 目录

```
harness/            驱动核心（纯 ctypes，零第三方依赖即可跑 m0）
  winutil.py        眼睛+手：EnumWindows/PID 定位、PrintWindow(FULLCONTENT) 截图、
                    WindowFromPoint+SendMessage 点击（远控免疫）、WM_CHAR 键入
  env_check.py      环境预检（GameViewer 等远控层、DPI）— 移植自 wx_gui 的 C++ 门禁
  profile.py        沙盒 datadir 种子（数据源 = 仓内 vendored resources/，非用户 %APPDATA%）
  launcher.py       黑盒启动（显式剥除 ORCA_GUI_TEST_MODE！）
  perf_monitor.py   进程指标采样（ORCA_BB_PERF=1，随 launcher 按实例生成 JSONL；
                    Windows 支持 ctypes 降级，tools/perf_report.py 出报告；
                    看板配置见 deploy/monitoring/README.md）
m0_boot_check.py    里程碑0：启动→定位→截图→关闭 冒烟
m1/m2/m3*/m4*/m5*   用例（m1 层驱动验证 → m2 切片链 → m3 业务路径 →
                    m4 混色全链路 → m5 工艺参数主流程；35 例套件 = m3j..m5h，「全绿」是历史口径、本会话未复算）
diag_*.py           与用例同名的诊断脚本（不猜坐标/标签，先 diag 实证）
fixtures/           vendored 3mf/stl 测试夹具（原 monorepo tests/data/test_3mf 子集）
resources/          vendored 预设子集（profiles/{Snapmaker,BBL} + printers，~9MB；
                    datadir 种子数据源，与上游 resources/ 的该子集同源）
runner/             宿主↔客机跑批基础设施快照（hv_go / relay / 探针，见 runner/README.md）
resource/image/     模板图（提交入库，测试资产）
mcp_server.py       MCP stdio server：harness 暴露为 AI 工具（坑编码为服务端不变量）
ui_runner.py        薄 UI 封装（CustomTkinter）：选模型→跑 m1/m2/批量→流式日志
                    + live view 截图面板 + App exe 可替换（透传 --exe）
BLACKBOX_CASES.md   用例登记册（35 例判定标准/证据链）
PITFALLS_0901.md    实测坑册（§1–§17，全部有日志/帧证据）
FEISHU_MAPPING.md   飞书证据表映射
artifacts/          运行产物（gitignored）
```

## 运行

```bash
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt
.venv/Scripts/python m0_boot_check.py --grab     # 启动+截图（模板裁剪素材）
.venv/Scripts/python m1_minimal_loop.py          # M1：tab 切换闭环（纯自研层）
.venv/Scripts/python m1b_maa.py                  # M1b：MaaFw pipeline + 注入对比
.venv/Scripts/python m2_slice_chain.py           # M2：切片业务链（默认 fresh profile）
.venv/Scripts/python ui_runner.py                # 薄 UI 封装（CustomTkinter）
.venv/Scripts/python inspect_window.py           # 子控件枚举 + 截图（开发辅助）
```

App 定位链：`ORCA_VISION_APP_EXE` 环境变量 → `<repo>/orca/snapmaker-orca.exe` →
dev build 兜底路径（`harness/launcher.py`）。宿主机直跑用例要求本机有可显示会话
（消息注入 + PrintWindow 路线）；无人值守全量回归走 `runner/hv_go.ps1`（Hyper-V
客机 + INTERACTIVE 计划任务）。

## 实测结论（2026-08-25，本机 GameViewer 运行中）

| 实验 | 结果 | 证据 |
|---|---|---|
| m0 黑盒引导 | ✅ | seed→launch→定位→截图→关闭，全链路绿 |
| (a) 自绘 tab 消息点击 | ✅ | teal(0,150,136) 选中色像素 + 模板状态翻转 |
| (b) 原生 Edit WM_CHAR | ✅ | `'0.4'` → `'0.160.4'`（WM_GETTEXT 读回） |
| (c) GL 截图黑屏 | ✅ 无黑屏 | PrintWindow(PW_RENDERFULLCONTENT)，viewport std≈76 |
| M1 闭环（纯自研） | ✅ GREEN | click→verify→back 全通，含回弹重试 |
| M1b A：MaaFw 内置 Click | ❌ FAIL | 识别 3/3 全中，但 SendMessage→顶层 HWND 不路由到 wx 子控件，tab 从未切换 |
| M1b B：自定义 action | ✅ PASS | WindowFromPoint→子 HWND 一次成功且稳定 |
| M2 模型自动加载 | ✅ | CLI 位置参数 + fresh datadir；**启动期必须 hands-off**（早期前台/移动干预会静默杀死 input_files 自动加载）；到达检测 = viewport 彩色占比 ≥1%（空床实测 ~0.15%，模型 ~2.1%，双轮稳定确认） |
| M2 点击 Slice→切片完成 | ✅ | 完成信号 = 按钮带绿勾的 done 态模板（`slice_button_done.png`，≥0.85） |
| M2 Preview 工具路径 | ✅ | 彩色占比 ≥1% 且 ≥2× 切片前基线（混色模型 4.88% vs 1.90%；默认 Prusa.stl 2.22% vs 0.69% 亦绿） |

### ~~M2 切片冻结~~ 已撤回：真实的因果链（2026-08-26 复盘）

早期 Prusa 跑出的"切片冻结在 30%、app 侧问题"结论**是误诊**，两个叠加的驱动层 bug：

1. **launcher 启动期前台抢占杀死 CLI 模型自动加载**（排查中途引入的回归）：启动早期
   `SetForegroundWindow`/移动窗口会与 post_init 首个 idle 的 input_files 加载竞态——
   hands-off 启动（sleep 12s 不碰窗口）模型 100% 加载，有干预则静默不加载。
   模型没加载 → 点 Slice 无效果或仅按钮按压态变化 → "进度条 30% 冻结"实为无米之炊。
2. **完成检测模板错误**：切片完成后按钮渲染"Slice plate + 绿勾"，与点击前 idle 模板的
   归一化相关只有 0.666 —— 把已完成误判为"仍在切片"。

修正后（hands-off 启动 + done 模板）`混色级联删除测试.3mf`（Snapmaker U1 0.8 + 0.40
Standard 嵌入预设）端到端 GREEN。

### 切片"慢"是假象 — 实际 ~3 秒（2026-08-28 复盘）

用户反馈"切片怎么这么慢，正常 GUI 不应该"。调查结论：**切片从来不慢**，
"10 分钟"是三个叠加的测量假象：

| 假象 | 机制 | 证据 |
|---|---|---|
| "冻结在 30%"（Prusa 跑） | 模型没加载 → 切片从未开始，1500s 是**等待超时** | 无 gcode、无切片进程 |
| "10 分钟还在 42%"（3mf 跑） | **~20s 就切完了**（绿勾完成态），但旧 idle 模板对完成态只给 0.666 → 完成检测永不触发 → 空转满 1500s | done 模板对 wait2/wait10/wait150 全部 **1.0** 匹配，画面自 20s 起就是静止完成态 |
| 视觉模型"读出"5%→10%→42% 进度 | 对**静止完成态**画面的百分比幻觉 | 多轮截图字节级相同 |

修复后复测：`3.1s / 3.1s / 3.1s / 3.1s`（含 8 核 CPU hog 干扰下仍 3.1s）。
硬件 8C16T Ryzen 9700X、进程亲和性 0xFFFF（全 16 核）、TBB 全并发、模型为
单立方体——均无瓶颈。正常 GUI 不慢，本沙盒也不慢；机器空闲负载仅 ~4%。

保留有效的教训：
- `window_mainframe` 位置恢复键必须 drop（否则窗口落在虚拟屏）
- 早期窗口干预有害；后期按需干预（仅当窗口真的在虚拟屏时）才安全
- 视觉模型对低分辨率截图的"进度百分比/图标"读数可靠性有限，关键判定用模板/像素级确定性证据
- 完成信号必须用**完成态专用模板**（绿勾徽标），不能用"回到 idle"推断

### 引擎选型结论（M1b 决定性实验）

**MaaFramework 可用但注入层必须走 Python 自定义 action**：
- 可复用：pipeline 编排、模板识别循环、重试/超时、截图（`set_screenshot_use_raw_size(True)` 关闭默认 720p 降采样）
- 不可用：Win32 内置 Click——设计目标是游戏"单一大窗口"，对 wx 复合子窗口 UI 无效
- `harness/winutil.py` 的 `msg_click_screen`（WindowFromPoint+SendMessageTimeout）即是补洞层，纯自研路线也直接复用它

### 批量回归结论（2026-08-28，9 个模型）

| 模型 | 嵌入预设 | 结果 | 说明 |
|---|---|---|---|
| 混色级联删除测试.3mf | Snapmaker U1 (0.8) | ✅ GREEN | 标准样例 |
| 立方体.3mf | Snapmaker U1 (0.4) | ✅ GREEN | |
| 四料混色.3mf | Snapmaker U1 (0.4) | ✅ GREEN | 修复 WebView2 后 5/5 稳定（修复前 2/5 flaky） |
| Prusa.stl（m2 默认） | — | ✅ GREEN | 色度检测走"切片成功兜底"升级 |
| 混色.gcode.3mf | Snapmaker U1 (0.4) | ⏸ 已知限制 | 含 gcode → `only_gcode_mode` 源码门禁用 Slice 按钮（渲染 0.666）；正确测试路径是跳过切片直接验 Preview |
| lithophane.3mf | Bambu P1S | ⏸ 预期 | **混色耗材兼容门**：Color Mixing 引用缺失耗材 → Slice 禁用（切打印机无效，见坑 #10）；补 printers/ seed 后预设可加载但混色门仍挡 |
| Pikachu X1C | Bambu X1 Carbon | ⏸ 预期 | 同上 |
| A1mini+R3dPETG罗隐 | Bambu A1 mini | ⏸ 预期 | 同上 |

三类脆弱点与处理：
1. **WebView2 透明层吞点击**（间歇 flaky ~40%）→ winutil 穿透修复（坑 #9）
2. **非 U1 预设 → Slice 按钮 disabled**：gcode 项目（only_gcode_mode）与混色耗材不兼容
   （has_incompatible_mixed_filament_in_use）两条源码门都禁用按钮；打印机预设缺失时
   app 自动替换为默认（combo 显示 U1），所以"切打印机"不是解法——切耗材槽才是；
   已补 `printers/` seed（见下）消除预设缺失路径
3. **含 gcode 的 3mf**：按钮禁用（源码门）→ 正确测试 = 跳过切片直接验 Preview

附带发现与修复：
- 2.3.6 预设布局：`system/Snapmaker/{machine,filament,process}` + 独立的
  `printers/`（vendor 预设，BL-P001 等）；**seed 原先只拷 system** → Bambu 项目预设
  缺失 + 启动报 `[Orca Updater] staging validation failed (printers)`（待办 #5）。
  已修：seed 一并拷贝 `printers/`（2026-08-28）→ staging 错误消失
- 预设切换节点探索结论（未实现）：Printer combo 可黑盒切换（screen(625,279)，
  GetWindowText 可读、popup 行自绘需试错点击）；但 Bambu 混色项目被混色兼容门挡住，
  需切换耗材槽（UI 深度操作）——成本高，留作后续

### 已知坑（踩过并已规避）

1. **复用 datadir 后 CLI 位置参数不再自动加载模型** —— 首次运行后 app 写回的状态会阻断
   input_files 自动加载；M2 默认每次 fresh profile
2. **启动 tab 选择有竞态**：最终 select_tab 在 GL init 后的 CallAfter 里，且页面切换可能被
   `EVT_GLVIEWTOOLBAR_3D` 弹回 Prepare → 驱动必须 wait_for + 稳定性确认 + 重试，禁止定时假设
3. **模板必须从"稳态"截图切**：启动 ~3s 内是主题应用前的瞬态（白底），稳态是深色主题
4. **MaaFw 默认把截图降采样到 720p**：模板是原生分辨率切的，必须开 raw size
5. **"切片很慢"是测量假象**（已撤回，见上方 08-28 复盘）：实际 ~3s；完成检测超时
   给足 1500s 仅作安全阀，模型未加载时 m2 会把上限压到 60s 快速失败
6. **模板状态区分用颜色不用模板分**：tab 选中=teal(0,150,136)/未选=(59,68,70)（源自
   Notebook.cpp ButtonsListCtrl），TM_CCOEFF_NORMED 对纯背景变化不敏感（0.926 仍误判）
7. **沙盒卫生待办**：种子的用户 conf 无明显 token，但 app 启动后有云端订阅回调（WCP 日志）；
   对外交发沙盒 profile 前需核实数据面
8. **模型到达检测不能用"差分 vs 参考帧"**：模型在 hands-off 启动期内已渲染完（t=12s
   首帧即含模型），任何晚于启动的参考帧都包含模型 → 差分永不触发（m2 曾因此恒
   UNVERIFIED）。改用绝对阈值：空床彩色占比 ~0.15% vs 带模型 ~2.1%，≥1% + 双轮稳定即判定；
   低饱和模型（默认 Prusa.stl 实测仅 ~0.7%）会漏检，由"切片成功兜底升级"覆盖
9. **WCP WebView2 全屏透明层吞点击（间歇 flaky 根因）**：首页 WebView2 的渲染窗口
   （`Chrome_RenderWidgetHostHWND`，WS_EX_TRANSPARENT，全屏 1920x1040）间歇性出现在
   z-order 顶部——不绘制任何内容（截图无痕）但参与命中测试（WS_EX_TRANSPARENT 只影响
   绘制顺序），WindowFromPoint 命中它 → 注入点击被吞，m2 曾 ~40% flaky "click didn't
   take"（tab/按钮都中招）。修复：`msg_click_screen` 传 `root_hwnd`（主窗口）后改用
   `ChildWindowFromPointEx(CWP_SKIPINVISIBLE|SKIPDISABLED|SKIPTRANSPARENT)` 在 app
   窗口树内递归定位最深含点窗口——WebView2 是独立顶层窗口，天然不在树内
10. **非 U1 预设的模型 → Slice 按钮 WS_DISABLED**：预设缺失（本机无 Bambu 预设）时
    Slice 按钮 disabled，且 **WindowFromPoint 会跳过禁用窗口**返回主窗口 → 点击无效是
    app 预期行为（真实工作流：先切 Snapmaker U1 再切片）；m2 的"预设切换"节点待实现
    ——但注意源码门链（MainFrame.cpp get_enable_slice_status）：gcode 项目
    （only_gcode_mode）与**混色耗材不兼容**（has_incompatible_mixed_filament_in_use，
    项目级 Color Mixing 引用缺失耗材）都禁用按钮——**切打印机到 U1 无效**（缺失时 app
    已自动替换），正确路径是切**耗材槽**到兼容预设
11. **强杀 app 会损坏 Sentry 共享 crashpad DB → 后续启动全崩**：`session.close()` 超时
    后强杀（或外部 timeout 杀进程）会让 Sentry 的 crashpad 数据库
    （`%LOCALAPPDATA%\Snapmaker_Orca\`，**跨 datadir 共享**）处于半写状态，之后所有
    启动在 sentry_start_session 段抛未捕获 C++ 异常（0xE06D7363，静默崩溃）。恢复：
    改名/删除该目录后正常启动一次（Sentry 重建 DB）。**教训：永远用
    `session.close()` 优雅退出，不要在诊断脚本里用 timeout/kill 杀 app**
12. **窗口隐身化（2026-08-28，2026-08-30 部分回退）**：m1/m2 在 hands-off 结束后调用
    `demote_window()`（原 `background_tool_window()`）——`HWND_BOTTOM`（z-order 底部）
    + `WS_EX_NOACTIVATE`（禁止后续激活），让被测 app 不打扰用户桌面。**任务栏图标保留**
    （2026-08-30 用户要求回退 TOOLWINDOW：图标全隐后跑没跑、卡没卡完全不可知，图标是
    运行指示器；NOACTIVATE 仍保证点任务栏图标不会把窗口弹到顶层）。渲染/命中测试不受
    影响（截图/注入全兼容，已回归验证）。这是"嵌入到 UI 壳"的零侵入替代——SetParent
    嵌入会破坏 wx 窗口树语义并违反 hands-off 教条，**不要做**
13. **启动即弹到最顶层（2026-08-30 修复，两阶段）**：`SW_SHOWNOACTIVATE` 对 wx **无效**——
    wxMSW `Show()` 调 `ShowWindow(SW_SHOW)`，无视 STARTUPINFO wShowWindow（那只对
    `SW_SHOWDEFAULT` 生效），所以主窗口启动即**带焦点弹到用户桌面最顶层**，且因
    hands-off 要裸奔 ~12s 才被 `background_tool_window()` 压底。修复（不违反坑 #3）：
    ① `demote_window()` 补 `WS_EX_NOACTIVATE` + launch() 启动 `demote_watchdog(12s)`；
    ② **前台竞态补丁**：z 序降级和 NOACTIVATE 都不能剥夺已到手的 foreground，且
    watchdog 首拍与 app 首帧 Show 是赛跑（同代码两次实测 0 次 vs 139 次前台占用）——
    因此 watchdog 记住启动前的前台窗口，检测到 app 占前台就 `force_set_foreground()`
    **物归原主**（focus 恢复，是坑 #3"前台抢占"的逆操作）。实测模式恒定：app 只抢
    1 次 → 恢复 1 次 → NOACTIVATE 顶住后续，auto-load 不受影响。回归探针
    `diag_early_stealth.py`（判定按前台占用时长，<1s 的瞬态算 PASS）连跑 3 轮全绿。
    版本检查更新窗无配置开关可关（check_new_version_sf 直发 HTTP），由 watchdog 压底兜底。

## 关键设计事实（源码核对过，改动 app 时需复查）

| 事实 | 出处 | 对策 |
|---|---|---|
| `ORCA_GUI_TEST_MODE=1` **隐藏主窗口** | GUI_App.cpp:3046 跳过 `mainframe->Show(true)` | launcher 显式剥除该变量；隔离改用 `--datadir` |
| conf 是 **JSON + 尾行 MD5**（非 INI） | AppConfig.cpp `USE_JSON_CONFIG` | profile.py 按 nlohmann 格式写 + 复刻 MD5 行 |
| wizard 触发：无 conf / 仅默认打印机 / privacy 空 | GUI_App::config_wizard_startup | 种子 conf + 拷贝 system 预设 + privacy=true + firstguide.finish=true |
| 主窗口**无标题**（自绘 topbar） | MainFrame.cpp:237 | 按 PID+可见+尺寸最大枚举定位 |
| 位置参数自动加载 3mf | GUI_App::post_init → load_files | launcher 的 `model` 参数 |
| GL 画布 BitBlt 黑屏 | — | PrintWindow(PW_RENDERFULLCONTENT) |
| 启动版本检查可能弹更新窗 | check_new_version_sf（网络） | pipeline 预留"关意外弹窗"节点 |

## 环境危害矩阵（源自 wx_gui 调查，ADVERSARIAL_LOOP_JOURNAL.md）

| 环境 | 截图 | 消息注入(SendMessage) | OS级注入(SendInput) |
|---|---|---|---|
| 干净交互会话 | ✅ | ✅ | ✅ |
| GameViewer/ToDesk 等远控层运行中 | ✅ | ✅（LL hook 看不见 sent 消息） | ⚠️ 实测可用但受限（2026-08-29：SendInput 2/2 投递，不再被吞；但 WebView2 透明宿主吞掉 app 窗口区的真实点击——真实输入只用于 z-top 的模态菜单行，见 BLACKBOX_CASES.md） |
| zh-CN 拼音 IME | ✅ | ✅（WM_CHAR 直携字面字符） | ⚠️ 需 US layout 绕过 |
| 非交互桌面（CreateDesktop） | — | — | ❌ wx 启动挂起，已放弃 |

结论：**消息注入 + PrintWindow 截图**是本机（远控层常驻）唯一全绿通道，
MaaFramework 控制器配置也按此选择。

## 沙盒种子数据源（2026-08-28 起）

seed 的一切都来自**仓内 vendored `resources/`**（exe 旁 `resources/` 兜底），**不再拷贝用户
`%APPDATA%\Snapmaker_Orca`**——沙盒因此可复现、可交发（不泄漏用户状态）：

| datadir 项 | 来源 | 说明 |
|---|---|---|
| `system/` | `resources/profiles/{Snapmaker,BBL}` + vendor json | 打包安装形态（vendor/{machine,filament,process}），与 app 的 Orca Updater 安装结果一致；白名单 2 个 vendor（58 个全拷 = 80MB 太慢） |
| `printers/` | `resources/printers/` | BL-P001（Bambu Lab）等；缺失会触发 "staging validation failed (printers)" 且第三方项目预设丢失 |
| `Snapmaker_Orca.conf` | 手写最小模板 | 仅挡 wizard 所需键（privacy/firstguide）+ 沙盒确定性键（language/splash/page/backup）；无 recent/geometry/登录/设备标识 |

附带发现：**BBL（Bambu Lab）预设 app 会从 exe 旁 resources 直接加载**（seed 不拷也
可用，实测 lithophane 加载出 P1S 的床型/耗材/工艺）；但 BBL vendor 的 Prepare 面板
布局与 Snapmaker 不同（Printer 区非 390x26 combo），预设切换节点需按 vendor 适配。
沙盒卫生（待办 #4）随本改动大部分完成——seed 不再接触用户数据；剩余项：app 运行期
WCP 云端订阅回调（datadir/web 与 %LOCALAPPDATA% Sentry/WebView2 数据，见坑 #11）。

## 打包为自包含 exe（2026-08-28）

```bat
build_ui.bat        rem 在本仓根目录运行
```

产物：`dist\vision_gui_runner\vision_gui_runner.exe`（onedir，~183MB，含
customtkinter/Pillow/opencv/numpy；已排除 mss 与 MaaFw——沙盒代码不用 mss，
MaaFw 仅 m1b 定案实验需要）。打包布局：

- 驱动脚本 + `harness/` + `resource/`（模板）以数据形式随 exe 分发
  （PyInstaller 6.x 放 `_internal/`）；打包版内部用 `run` 子命令分发
  （`<exe> run m2_slice_chain.py --model x`）
- **被测 app 不在包内**（snapmaker-orca.exe 只是 720K loader，主体是
  Snapmaker_Orca.dll + resources ~200MB）：放到 `dist\vision_gui_runner\orca\`
  或用环境变量 `ORCA_VISION_APP_EXE` 指定
- 查找链：`ORCA_VISION_APP_EXE` → `<runner>/orca/` → dev build 兜底
  （launcher.default_exe / profile.default_resources_dir 同构）

边界（诚实声明）：模板绑定当前机器 DPI（换缩放需重采模板）；PyInstaller
产物有杀软误报风险；打包版 UI 与驱动行为与开发版一致（run 分发已端到端
验证：打包 exe 跑完整 m2 全链路 GREEN）。

## DPI

驱动进程 per-monitor-v2 感知，坐标/像素均为物理像素。模板与 DPI 绑定：
换显示缩放需重新采集模板（env_check 会告警）。

## 人机统一入口：MCP server（2026-08-30，M1）

`mcp_server.py` 把 driver 层暴露为 MCP stdio 工具，AI agent（ZCode 等）与
CustomTkinter 薄 UI 是同一 harness 层的两个平等客户端。协议零依赖
（手写 JSON-RPC，不用 mcp 包）；harness 的 print() 在启动时全部改道 stderr，
协议通道只有原始 stdout 一个写者。

**服务端不变量**（把 README 的坑编码成强制，而非提示词）：
- 无 kill 工具——`app_close` 只走 `AppSession.close()`（优雅 WM_CLOSE，坑 #11）
- `click` 拒绝 app 窗口外的坐标（合成点击落进用户窗口 = 事故）；无裸 SendInput 工具
  （SendInput 仅存留于用例脚本的菜单路径内部）
- `app_launch` 恒为隔离 datadir + 隐身 watchdog 启动
- 会话锁 `%LOCALAPPDATA%\vision_gui\mcp_session.lock`：同一时刻一个司机
  （UI runner 尚未接入该锁，为已知缺口）

**工具（M1+M2+M3，15 个）**：
- 交互原语：`app_launch / app_close / app_status / window / shot / click /
  type_text / key / ocr`（shot 返回 MCP image content + 落盘 artifacts/mcp/shots/）
- 用例执行（M2）：`list_cases`（扫 m\d*/diag_* 脚本+docstring 摘要）、
  `run_case(script,args,timeout_s)`（持锁跑整条用例；超时只杀驱动不杀 app，
  随后按 WM_CLOSE 清扫沙盒孤儿 app；解析 m3 verdict 块/退出码两种判定约定）、
  `get_artifacts(subdir,limit)` / `get_artifact(path)`（图返 MCP image、文返文本，
  路径逃逸一律拒绝）
- 用例起草（M3）：`case_scaffold(name,goal)`（生成 drafts/ 草稿，带人工 review
  checklist 头注释）、`crop_template(shot,x,y,w,h,name)`（裁模板图，draft_ 前缀
  标记未 review）

**验证**：`mcp_smoke.py` 全链路（initialize → tools/list → launch → shot →
click → 窗口外点击拒绝 → close）一次通过；ZCode 注册于
`~/.zcode/cli/config.json` → `mcp.servers.vision-gui`（备份
config.json.bak-visiongui）。

**M3 流程（AI 起草 → 人类拍板）**：agent 用 case_scaffold 生成 drafts/ 草稿 +
crop_template 裁模板（draft_ 前缀）→ 人类按草稿头部的 checklist 跑通并 review
→ `git mv drafts/mXx_*.py mXx_*.py` 入正册 + 去 draft_ 前缀 + 写 BLACKBOX_CASES.md
→ 提交。草稿未 review 前不得进正册、不得进 batch。

**冒烟**：`mcp_smoke.py` 覆盖 15 工具全链路 + 4 条护栏（窗口外点击、交互期
run_case、artifacts 路径逃逸、scaffold/crop 清理），全部 GREEN。

## License / 出处

harness 部分内容（如 `env_check.py` 的门禁逻辑）移植自 Snapmaker_Orca
（AGPL-3.0）源码；被测 app 本身即 AGPL 项目。正式 LICENSE 文件待定，先以本节
注记来源。
