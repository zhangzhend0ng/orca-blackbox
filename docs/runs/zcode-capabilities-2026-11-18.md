# 停止、纠错与画布能力试验 2026-11-18

路线与阶段以[V3_PLAN](../V3_PLAN.md)为准。本记录只包含开发能力验收，既不是未见任务泛化，也不改变旧7/8或发布基线。

## 真实停止闩探针

源5ab5e8c2ea8a91927ef268ab0a82128f4b1273a6；run `3383fa72db0e4b22902f61a400fd5c11`。唯一hv_go入口、win11-test、无模型、无成功原版输入。

1. 只读命中的外部窗口点[10,1070]，Click返回isError=true、`native_target_not_owned`、dispatched=false。
2. 持久input_revoked/authority_abort已存在；只读确认前台与中心点仍属于SUT，再请求Click，明确返回`native_authority_already_revoked`、dispatched=false。
3. 原版FastMCP真实HTTP保留structuredContent.authority和isError；worker error=null、自然退出code0、Job0、cleanup确认、token删除。

独立authority_probe.json标fatal_latched=true、subsequent_input_dispatched=false。正式runtime结果仍NON_GREEN/verified_pass=false，这是预期的无业务诊断结果，不能计业务通过。原始证据：artifacts/windows_mcp_harvest/3383fa72db0e4b22902f61a400fd5c11。

此探针不验证成功工具的outputSchema；随后18f30dd修复成功返回包装，保留原版structuredContent的result等顶层字段再附authority，避免把原字段错误嵌套到data下。

## 新恢复合同首次真实接线

源18f30dd6a02116ad1171e246392f6dc0b91d1c25；run `d62fbde619b9490fb91e034f0575889b`。沿用层高目标，Others初态，公司Snapmaker new-provider/glm-5.3-flash。

首个Screenshot成功，受信bridge回执decision=completed/dispatched=true，原生result成功；之后客户端对全部tool.updated事件检查call ID，触发`native_tool_call_identity_missing`结束。原始payload未保留，无法确认触发事件的具体kind；只读安装bundle确认存在不要求call ID的信息类映射，因此收窄为只对动作事件校验。没有执行业务输入，正式NON_GREEN；host Job0、无强杀、guest cleanup确认、token删除，个人配置未变。未完成全轮model-io审计，不冒充模型/业务验收通过。

最小修复：只有scheduled/error/result动作事件参与call ID及受信回执关联，其他信息事件只记录kind，不授予动作。缺ID的实际scheduled/error/result仍终止；旧失败保留，新run复验。单次原生turn不重启，host不生成下一步。

## 修复后正常路径

源87a57dbfc638c9ea10cf6e98b1e89a4569285bfd；run `8cb6ee5f048f4562b3b26f87d65f5d3c`。15次工具调用均completed，无可恢复拒绝；实际信息事件记录为started/batch，未参与动作授权。actor/host error=null，完整model-io核对公司供应商/模型/七工具，个人配置未变、守卫已检查。

保存3MF后停止输入、自然退出、冻结同一文件、新profile重开实际112层G-code，独立业务通过；正式SHADOW、cleanup确认、双方Job0、token删除。`recovery_used=false`，独立native_recovery计数0。此轮证明新合同正常路径与成功MCP结果包装兼容，**不证明拒绝后的真实原生恢复**。

## 画布试验与实际中止原因

同一源87a57db；run `38a1ac07714949f8a4e6d347df00e0af`。共30次实际MCP调用，trace无工具拒绝；seq22/25在AI自主选择的位置各执行一次canvas_numeric，输入145.50/145.5，均为clear=false、caret=idle、press_enter=false。这不是预置业务坐标。

回收后独立重放`verify_canvas_trace`：canvas_numeric_count=2，native_edit_count=0，原始观察hash、同run身份、父链、焦点及同位置Click关联审计通过。pfd_verified/internal_numeric_field_verified仍false；不能由输入派发推断内部数值最终正确。

宿主随后因`ValueError:native_progress_limit`触发停止，原因是进度文件增长达到读取上限，属于当前运行记录实现的限制。host owned Job被回收至0；guest worker报告native_actor_failed并自然退出，正式NON_GREEN、cleanup确认、token删除。没有完成保存/重开/实际G-code业务oracle，完整model-io审计也未完成，不能当画布业务通过或把失败直接归因模型。

收尾时虽已提出取消意图，但核对进程时actor已由上述条件停止，没有执行人工taskkill；此样本不记为用户取消验收。原始证据：artifacts/windows_mcp_harvest/38a1ac07714949f8a4e6d347df00e0af。

## 收尾边界及下一阶段候选

用户要求停止新增实现后，受控故障诊断仅保留两个未接线候选：`harness/native_diagnostic_recovery.py`及对应测试，55项纯测试通过。默认关闭；使用独立注入错误码、保留真实Edit class和guard_allowed/dispatched事实，绝不假报非Edit；需要受信同session/同turn收据、新观察以及原业务oracle。生产RecoveryGate对此错误码仍fatal。

候选尚未接入scenario/contract/authority/driver/verifier，未调用GUI或模型；MECHANISM_ONLY不计自然恢复成功率。下一阶段先处理重复全量进度快照的增长/有界读取，再接一次性诊断并实测，不通过重复跑批等待偶发错误。本文未将候选测试或正常路径通过写成纠错能力已验收。

最终客机只读postflight：Orca=0、MCP监听=0、suite Ready、上述四轮token均不存在、checkout clean。所有结果已harvest；本阶段无发布GREEN，不做飞书覆盖写回。原有launcher/profile/farm_runner及草稿目录未纳入本轮提交。

## 尚待验收

- 新恢复合同：真实预派发拒绝→同一原生turn重新观察→自主修正→独立保存/重开切片通过。
- canvas_trial：仅已批准wxGLCanvas、最窄数字选项、30秒同位置Click一次性关联；至少实际一次canvas_numeric且X+10的3MF/真实G-code oracle通过。
- 普通pilot_transform仍blocked；A/B未完成前不启动泛化批次或新增相似业务。

## 基线后的进度日志修复与受控纠错

源 `bf13401717073b9dc03fa9e7fa5ec52921d4e5c5`。进度文件仅在已完成调用列表变化时追加精简 JSON 行，宿主有界读取且忽略无换行的尾部，完整调用证据仍由 `actor.json` 和受信收据保存。用原画布失败样本的 554 条快照重放，4,003,584 字节压到 31 条、19,576 字节，末条仍包含全部 30 次完成调用。250 项纯测试及 6 项针对变更的原生协议替身测试通过。

单独注册 `recovery_diagnostic_once`，只在真实 guard 放行的首个 owned numeric Edit 的 Type 上、原工具派发前注入一次。独立验收要求同一原生 turn、准确匹配的宿主和客机回执、拒绝后重新观察并成功派发相同数值，以及原层高业务检查通过。通过后的样本也仅记 `MECHANISM_ONLY`。

| run | 已观察到的动作 | 独立业务与清理 |
|---|---|---|
| `4b46a8ba64a7eab94d5e78e386788e34` | seq5 guard 放行的原生 Edit 命中受控拒绝，未派发。seq6 Screenshot，seq7 和 seq8 派发 0.24。seq9 同点已是 wxWindowNR，拒绝后永久停输，未观测到后续派发。 | NON_GREEN。turn 未正常完成，未保存、重开或切片。宿主 Job 0，客机 Job 0 且记录了强制收尾，token 已删。宿主配置哈希比对失败，CLI 文件在启动窗口内被修改，写入来源未确认。离线核对已落盘的 10 份请求收据使用指定模型和七工具。进度文件 1,329 字节。 |
| `104f5606a6a070cbdff5b700cad71b1e` | 同一提交复验。seq5 同类预派发拒绝，seq6 Screenshot，seq7 派发 0.24，seq8 Tab。seq11 保存快捷键因前台归属失配而在派发前 fatal，未观测到后续派发。 | NON_GREEN。turn 未正常完成，未保存、重开或切片。配置哈希一致，离线核对 12 份已落盘的请求收据。宿主及客机 Job 0，客机记录强制收尾，token 已删。进度文件 2,071 字节。 |

运行经 `hv_go.ps1` 在 `win11-test` 执行，并经 `hv_harvest.ps1` 收回；原始证据位于 `artifacts/windows_mcp_harvest/<run>` 和 `artifacts/windows_mcp_host/<run>`。首轮收尾复查客机无 Orca、无 MCP 监听，suite Ready，目标 token 已删除，checkout clean。

## 基线后的画布业务复验

源 `bf13401`，run `4f0c3992514cede73c5ef48551d11fe0`。seq12 的同位置 Click 后，seq13 派发 145.5，回收后独立 `verify_canvas_trace` 认定 1 次合规画布数值输入。seq14 Screenshot 后没有新 Click，seq15 重复 Type 在派发前被拒并停输。原通用拒绝码为 `native_tool_failed`，同位置点击凭据未更新是可以直接确认的合同违例，现场证据不足以断言它是唯一原因。进度文件 4,636 字节，未触及上限。

正式 NON_GREEN。无 3MF 保存、重开切片及 X+10 独立业务证据。PFD 与内部数值字段证明仍为 false。配置哈希一致，离线核对已落盘的 16 份请求收据。宿主与客机 Job 0，客机记录强制收尾，token 已删。

源 `a6a48b1`，run `4250e066acf920a72055ac131178763b`。Type 工具说明和试验提示明示 Click 单次消费，同时保留缺少 Click 时的具体 fatal 错误码。输入权限和业务判定沿用原合同。相关纯测试 212 项通过。

复验实际派发 31 次工具调用，零工具拒绝。独立 `verify_canvas_trace` 核对 seq13、17、30 的三次合规画布数值派发及各自的 Click、窗口身份和原始观察哈希。进度文件 20,902 字节，超过旧失败 run 的调用数后仍在读取上限内。原生 turn 触发 540 秒 `agent_deadline`，未保存 3MF，也未产生重开与切片证据，正式 NON_GREEN。配置哈希一致，离线核对 32 份已落盘的请求收据。宿主与客机 Job 0，无强制终止，token 已删。

## 阶段结论

进度日志修复已通过历史回放、纯测试和真机跑批检查。受控纠错两次均观察到拒绝、重新观察及继续派发，完整保存重开业务验收仍未通过。画布输入轨迹已通过，X+10 的 3MF 和实际 G-code 业务闭环仍未通过。四轮均经 `hv_harvest.ps1` 回收，最终 `win11-test` 只读复核 Orca=0、MCP 监听=0、suite Ready、checkout clean、四个 token 均不存在。泛化未启动，旧矩阵及发布覆盖率沿用原判定。

## 保存与画布输入根因复盘

- 纠错首轮的原版 Type 工具回执明确读到 seq7 的 `0.24`，随后的 seq8 Type 未打开 clear，读回 `0.240.24`，且该调用还发了 Enter。seq9 才因非 Edit 停输。第二轮 seq7 仍读回 `0.24`，seq8 Tab 后模型在截图中报告已提交。模型把 seq10 的位置当作空白并点击，下一次 Save As 前台检查失败。原始截图像素和失焦目标的身份没有保留，因此具体激活了哪个控件或应用仍未知。历史成功 run `8cb6ee5f048f4562b3b26f87d65f5d3c` 用单次 clear+Type+Enter 提交数值，随后完成保存重开。
- 画布 run `4250e066acf920a72055ac131178763b` 的 seq13、17、30 均报告 `PaneControl GLCanvas` 无法读回。模型在接下来的截图中报告输入文本与原数字混在一起，反复尝试选中和取消，未进入保存。旧 inline 截图像素在 model-io 中被省略。只读核对 `GizmoObjectManipulation.cpp`、`imgui_widgets.cpp` 和原版 0.8.9 wheel，Position 用 `BBLInputDouble`，首次激活全选，旧 Type 在真正送键前无条件再 Click，选中内容可能被第二击缩成插入点。
- `recovery_diagnostic_commit` 强制原生 Edit 数字一次替换并提交，成功读回后观察结果并直接保存。另立 `canvas_replace_trial`，尝试保留首次 Click 的选区，Type 在同一绑定画布只发白名单数字和一次 Enter，每键前重查目标及撤销。一次性单击凭据、30 秒期限和独立产物检查继续生效。两个合同回收最多四张 Type 后的原始截图，便于核对实际 UI。旧合同和失败记录可按原身份读取。

### 受控纠错闭环复验

源 `3ee0945d4f7af5608b9e8848e9df278efd71823d`，run `013885216df9f8e218587d389eeb5e7c`。同一原生 turn 内 seq5 受控预派发拒绝，seq6 Screenshot，seq7 单次 clear+Type+Enter，工具读回 `0.24`，seq8 截图，seq9 直接 Save As。模型首次输入保存路径时把它追加到默认文件名，随后自行打开 clear 重填并保存。四张编辑后截图已回收，哈希与工具轨迹一致。

独立业务与路径均通过，正式 SHADOW，`MECHANISM_ONLY`。冻结 3MF SHA256 `4ed9d469ae12d1b1049ba8703bb1040574c7d683c87ee09a18d69491b0815d5b`，新 profile 重开后导出实际 112 层，初层保持 0.40 mm，G-code SHA256 `17474d91ee2ac477cc0ed9896ba74941544dea28c0403e3a6fd5cb3bddaf0603`。18 次工具尝试、19 份模型收据，模型、七工具和配置完整校验通过。宿主与客机 Job 0、自然退出、run token 已删除。前两轮失败保留。

### 画布复验的传输与派发问题

源 `3ee0945`，run `a8e6ec54c16c2c8490d03d9827f3e717`。seq5、6、8、10、12 的移动面板 PNG 编码 201–212 KiB，超过原生 ZCode 的 200 KiB 阈值。模型只收到文件引用，此隔离合同无相应读图工具。它后来恢复可见画面并选择数值字段，seq22 通过 owned canvas 检查并尝试进入键盘分支，但在送键前导入库失败。安装 wheel 的键盘实现实际为 `windows_mcp.uia`，已切回原版使用的入口。正式 NON_GREEN，无业务产物，配置一致、两侧 Job 0、token 删除，原结果保留。

复验修订让该合同超过阈值的 Screenshot/Snapshot 在宿主桥接层以原像素尺寸编码为低于阈值的 JPEG，留有 20 KiB 余量。已内联的小图和客机回收的原始 PNG 保持原样，大小变化进入宿主受信 sidecar。

源 `8706c8e`，run `a4cb5b4ae35077ab45f7ecc04e2ee37e`。移动视图截图成功内联，seq4、7、9 原编码 206,384–225,828 字节，压缩后 157,484–157,896 字节。seq5 单击后 seq6 保留选区直接输入并提交，回收到的原始 `native_observation_7.png` 显示 X=145.50、Y=136.00、Z=13.50。seq14 的 Save As 输入省略 clear，原版读回 `fixtureC:\…\0001.3mf`，seq15 因保存目标环境已变化而在派发前停输。正式 NON_GREEN，无可回收的业务产物。已将两个新合同的保存路径统一限定为 `clear=true`，原失败证据保留。

源 `673e8c0`，run `961d75925f720669a0dddfc96554631d`。seq6 模型用了双击，seq7 的同点数字输入因单击凭据条件未满足而在派发前停输。Type 要求单击，但 Click schema 此时仍广告双击。将该新画布合同的 Click schema 和输入门统一限定为单击，避免执行会破坏选区且无法授权后续 Type 的双击。本轮判定 NON_GREEN，清理确认，历史失败仍保留。
