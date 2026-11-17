# ZCode Snapmaker actor 自检

结论：允许固定客机SHADOW受控试验；实际GUI尚待验证。此次是原生ZCode会话协议客户端，未自建agent循环。用户已明确指定Snapmaker供应商，固定new-provider/glm-5.3-flash，不继续BigModel个人套餐。

## Harness 条件、动作与tier

- harness-driven-review（A）：实现前加载INDEX、协议及tool-calling、input-validation、error-handling、logging、risk-verification、testing-strategy、AIevaluation。自检和实际运行状态分开，本文保留NOT VERIFIED边界。
- input-validation Items1–4（N/C）：run ID固定32hex；CLI actor枚举；host供应商名称、现有HTTP主机、路径、协议和模型白名单；只使用参数数组调用Node；PS NativeActor为ValidateSet固定枚举。守卫状态检查精确bool、有限数值、时间/TTL与阻断状态；解析错误不放行。
- tool-calling Items1–7（C/A）：保留原生agent；模型无路径脚本/坐标清单。原生allowlist和权限回调只准七项本轮GUI工具，guest仍有owned HWND/PID/数值/保存路径门禁。session原生事件计数、40动作/有界超时、原始错误保留；模型不能直接给业务pass。native model-io再次核验每次实际供应商、模型及工具清单。
- error-handling Items1–7（C）：host使用owned Job，guard失败回收actor进程树；guest关闭输入、自然退出、独立证明沿用已有实现。actor/import失败仍走既有协调器取消与harvest。注册只扩展两个固定合同，原Codex合同hash回归保持；不开放任意执行适配器。
- logging Items1–6（N/C）：客户配置由原生ZCode读取，客户端只输出配置元信息和hash，不归档Key或认证文件。守卫status-token只在内存进入本地header。只归档任务UI和原生调用元信息；native model-io保留本地、只提取安全字段，不作为通用日志DLP证明。
- risk-verification/testing/AI-evaluation（C/A）：本次改模型、会话权限、固定合同，视为高风险；反例覆盖失效守卫、错误供应商、额外工具、假安全收据、模型漂移和Bash权限请求。协议反例通过本地假server验证拒绝，不计真实GUI覆盖。独立业务oracle不随模型更换。

## 验证

初版受影响纯测试60 passed（11.64秒），Python compile、Node语法和hv_go PowerShell parser通过；全仓794 passed、1 skipped（33.50秒）。最后复核发现原生客户端确有session/requestRuntimePreferences请求，已补齐明确关闭搜索/记忆/子agent及自动问答的会话回复；按此最终改动重跑后再冻结。

最终会话偏好回复补齐后，假协议server复核其关闭记忆、子agent和工具搜索；全仓再次794 passed、1 skipped（33.23秒），Python编译及Node语法通过。以下准备冻结同步，在取得实际GUI收据之前仍为NOT VERIFIED。

首轮真实run `77cf7e8ec1724e63b80fe96635b3eace`（27a55ca）因客户端误把既有公司HTTP地址限定成HTTPS，被provider校验拒绝，未发模型请求；guest收到失败收据后自然exit1、active=0、forced=false、cleanup_confirmed=true，保留NON_GREEN。修复为精确匹配用户现有`http://ai-gateway.s.com/v1`，补充真实配置形状正例及Key不输出检查；并把供应商/守卫前置校验移到GUI启动之前。没有修改公司网关地址或凭据。下一轮必须使用新run。

第二轮 `2ac0a1c371a0417cb81e6487113222f2`（e879187）在ZCode session/create阶段被模型初始化拒绝：正式driver漏传最小探针已有的model.options.reasoningLevel。协议需要它和thoughtLevel同时存在；仅后者不足以在bootstrap时创建模型。补齐low/low，并让假server拒绝漏传任一字段以覆盖该差异。该轮没有GUI工具调用、无业务模型请求，host Job自然清空，guest统一结果NON_GREEN且cleanup_confirmed=true，保留原记录。

第三轮 `5efb10ab5c37487c9cf68761490c8370`（0ed9f78）已创建原生会话，但正式driver读取session.id，实际原生协议字段为session.sessionId；最小探针保留了兼容fallback，假server初版则错误返回id，导致漏检。现按原版schema修正driver和假server。该轮未发session/send、无GUI输入，保留NON_GREEN及清理收据。

随后先做真实原生传输验证`artifacts/zcode_probe/20261117-snapmaker-transport-1`：使用同一个正式driver、真实ZCode、真实公司Flash及静态MCP夹具，完成一次Snapshot调用及两次模型请求，回复PROTOCOL_TRANSPORT_OK；actual model-io均为new-provider/glm-5.3-flash、每次恰好七项GUI工具，exit0/active0/未强杀，三份个人配置hash保持。静态夹具不操作桌面、不算GUI覆盖；此验证先于下一轮真实GUI，避免继续用客机发现基础协议差异。

残余边界：用户已启用的插件仍可能在ZCode bootstrap初始化；会话过滤不构成同权限攻击的沙箱。guard检查既有OpenAI组，不证明Snapmaker网关实际出口国家。模型服务真实版本与USD不可见记unknown。实际中途取消、稳定性矩阵与跨版本可靠性尚未验收，单个正例不得推广为87条覆盖。
