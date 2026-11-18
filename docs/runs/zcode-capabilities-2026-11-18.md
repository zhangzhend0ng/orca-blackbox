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
