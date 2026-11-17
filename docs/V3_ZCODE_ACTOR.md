# ZCode 原生 actor：Snapmaker Flash

入口：`python -B tools/native_save_demo.py --actor zcode`。仅在 Hyper-V `win11-test` 执行 GUI，仍由 `hv_go.ps1` 启动同一 `run_once` / owned Job / canonical 桌面锁。两端须同步同一已提交HEAD、客机空闲，已有relay和Windows-MCP运行时可用。

模型固定为本机 ZCode 已配置的 `Snapmaker` 供应商：`new-provider / glm-5.3-flash`，HTTPS端点 `ai-gateway.s.com/v1`，Anthropic协议，thoughtLevel=low。使用原版ZCode app-server的会话模型选择、MCP和agent循环；客户端只创建会话、给目标、批准受限GUI权限、观察原生事件及回收，不替模型产生下一动作。不导出API Key、不复制认证、不修改全局默认模型，运行前后核对三份个人配置hash。

原版Windows-MCP七项通用工具仍通过既有桥连接客机；native toolAllowlist只准本轮七个完整工具名，权限回调拒绝其他工具。会话关闭搜索、记忆、子agent配置、动态工作流和闲时执行；未使用的官方插件认证请求被拒绝。已有用户插件可能在原生bootstrap中初始化，不能把会话工具过滤称为完整OS沙箱。原生model-io收据的实际provider/model及每次request.toolNames必须精确匹配；缺记录、模型漂移或出现其他工具均不晋级。

宿主先查询本机clash-guard状态；模型运行中每三秒轮询（本地请求超时一秒），不可达/未ready/证据过期时停止本轮owned Job。此守卫的出口检测对象仍是其既有OpenAI分组，**ready不证明Snapmaker网关也走美国出口**；本实现不修改Clash规则或扩大守卫的地理保护声明。

业务目标仍是常规层高0.24、初层0.40、cube不变、GUI保存3MF；模型不负责独立证明。停止原生输入和MCP后，旧Orca自然退出，冻结保存文件，新profile重开GUI切片导出，复用现有只读3MF/G-code verifier。ZCode使用独立固定合同`native-save-zcode-1`，要求额外的模型/供应商/守卫/源配置/工具集收据；原Codex合同摘要保持不变。两条路线均限SHADOW，不计发布GREEN。

2026-11-17接入前，Snapmaker Flash已完成原生会话纯文本回复；此前BigModel独立套餐试验已停止，不是当前选择。真实业务GUI结果见后续运行记录，本文不预先宣称通过。
