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

首个Screenshot成功，受信bridge回执decision=completed/dispatched=true，原生result成功；之后客户端把没有call ID的非动作tool.updated信息事件误判为动作关联缺失，`native_tool_call_identity_missing`结束。没有执行业务输入，正式NON_GREEN；host Job0、无强杀、guest cleanup确认、token删除，个人配置未变。未完成全轮model-io审计，不冒充模型/业务验收通过。

最小修复：只有scheduled/error/result动作事件参与call ID及受信回执关联，其他信息事件只记录kind，不授予动作。缺ID的实际scheduled/error/result仍终止；旧失败保留，新run复验。单次原生turn不重启，host不生成下一步。

## 尚待验收

- 新恢复合同：真实预派发拒绝→同一原生turn重新观察→自主修正→独立保存/重开切片通过。
- canvas_trial：仅已批准wxGLCanvas、最窄数字选项、30秒同位置Click一次性关联；至少实际一次canvas_numeric且X+10的3MF/真实G-code oracle通过。
- 普通pilot_transform仍blocked；A/B未完成前不启动泛化批次或新增相似业务。
