# ZCode / GLM-5.3-Flash 接入核对

2026-11-17，按用户要求核对使用既有 ZCode 套餐替换 GUI demo 的原生 Codex actor。结论：模型与产品能力适合，但本机内置 CLI 尚未通过连接验收；未切换现有 GUI demo，也没有发起新的 GUI run。

后续更新：用户明确改为使用ZCode已配置的 **Snapmaker供应商**，不继续独立编程套餐。公司Flash路线现已通过原生app-server、受限MCP和独立3MF/G-code真实业务验证，见[最终运行记录](zcode-snapmaker-2026-11-17.md)。下文保留早期套餐探针的原始失败结论，不代表公司供应商路线仍被阻断。

## 已确认

- 本机 ZCode 桌面正在运行，安装在 `C:\Program Files\ZCode`；捆绑的 `resources/glm/zcode.cjs --help` 返回 CLI 0.17.1，支持 `--prompt`、JSON、会话、MCP 与进程级禁用工具。
- bundle SHA256：`d9afd58d694f98a5279bf548cdc7646413c125762e86730605a6071f9e0346d6`。
- 既有桌面模型配置包含启用的 BigModel Coding Plan 及 GLM-5.3-Flash；同时存在 API Key 通道，不能仅凭模型同名断言使用同一额度。
- 当前官方内置模型目录使用 `account:bigmodel-individual-coding-plan` 等 provider ID；旧桌面配置出现 `builtin:bigmodel-coding-plan`。两种表示不能直接混用。
- 官方说明 Coding Plan 下的 GLM-5.3-Flash 支持图片输入，ZCode 支持 MCP；这不等价于本机 CLI 已获得可用套餐模型。

参考：[官方模型能力](https://zcode.z.ai/cn/docs/configuration)、[官方 MCP](https://zcode.z.ai/cn/docs/mcp-services)、[官方 CLI 配置](https://github.com/zai-org/ZCode/blob/main/apps/zcode-cli/docs/usage/03-config.md)。当前源码指南与安装二进制存在行为差异，验收以本机实际生效收据为准。

## 两次受控兼容性探针

原始记录：本仓 `artifacts/zcode_probe/20261117-1/`、`artifacts/zcode_probe/20261117-2/`。两次均保存独立 provider 配置及日志；仅请求 GLM-5.3-Flash 对应的 BigModel 个人编程套餐，不加入其他 provider 供静默回退。第一轮是固定短文本探针，第二轮尝试本地 `/model` 查询。

两次 CLI 均 exit1，错误 `Select a model before sending a message`，未获得模型回复。该错误不足以判定账号未登录或套餐失效，也不能声称实际模型/额度已确认。当前 help 未提供 `--model`；未尝试未声明的参数或修改全局默认模型来绕过。

另发现项目级关闭扩展的配置未完全生效：启动日志仍显示13个启用插件、MCP及用户级hook。此次没有模型工具调用或GUI操作，但该启动方式尚不满足“只暴露客机受限GUI工具”的接入要求，不能直接用于正式demo。

两次宿主owned Job均自然结束，最终active=0、forced_termination=false。个人运行配置、旧模型配置、新provider配置的前后SHA256一致；未显式登录/登出、未提取或复制ZCode/Codex认证、未改代理与守卫配置。原生CLI自行管理登录态，不将这些检查解释为认证存储的全面审计。

探针启动前检查本机clash-guard `/status`，运行中每3秒检查一次；接口不明或ready不为true则回收本轮Job。两轮启动前及结束前观察均为ready=true。使用本地状态接口凭据时只保留内存，不输出或归档凭据。该短探针检查不补认旧Codex GUI run具有相同门禁。

## 接入验收边界

保留原生ZCode agent，替换actor，不重写GUI调度器：ZCode/GLM看图规划 → 现有受限Windows-MCP → win11-test；停止输入后继续复用现有独立3MF/G-code verifier。

真正切换前必须取得：可用套餐provider/model的有效选择、最小模型回复及图片工具结果、仅允许本轮MCP的生效工具清单、启动与持续守卫收据、取消及owned进程清理。优先使用原生会话协议传入模型和会话工具权限；如果本机捆绑CLI仍不能安全复用套餐，使用桌面原生会话，不从桌面导出token或改走另一个API Key通道冒充。

本记录只完成可行性核查并暴露接入阻点，不声明ZCode业务GUI跑通、不计GREEN/SHADOW业务样本，也不写回飞书覆盖基线。

## Harness 自检

执行前加载harness-driven-review及tool-calling、input-validation、error-handling、logging。输入/日志(N)：参数数组、固定路径及受限状态字段、状态凭据不落盘；资源/异常(C)：owned Job、120秒上限、守卫失败停止、退出归零收据；权限与有效配置(C)：发现实际扩展清单超出目标即拒绝晋级，未把配置文件意图写成隔离成功。无生产适配代码变更，不以探针编译检查代替产品/GUI验证。
