# Windows-MCP 客机兼容性探针审查

结论：源码自检 APPROVE with documented limits，仅允许隔离兼容性探针。真实 Codex→Windows-MCP→Orca 链路尚未验证，不能计 GREEN。

本次使用已加载的 harness-driven-review Part A/B。范围为数据传输桥、固定探针入口、进程生命周期、纯单测及离线依赖清单；不修改用户 launcher/profile/farm_runner、不改上游、不改全局 Codex 配置。作者自检，不冒充独立审查。

## Harness 条件、动作与 tier

- input-validation Items 1–4（N）PASS：模型输入先 bounded readline/JSON、显式 method/tool/type 白名单；工具参数由原版 MCP schema 校验。run ID/guest root 复用严格限定。解释器仅固定代码加参数化 base64 数据，动态路径采用 PowerShell 单引号编码；HTTP URL/端口固定。
- input-validation Items 2–7（C）PASS with limits：本地 run 目录拒绝重复；PS Direct 读取路径链拒绝 reparse point；32 MB 宿主输出预算、4 MB 传输上限、20 tool calls。文件与收据属于同一可信测试用户，未声称实现跨用户 ACL 隔离。
- tool-calling-and-agent-control Items 1–7（C/A）PASS：原版 Snapshot/Screenshot/Click/Wait/ControlStatus；禁 shell/registry/file tools。隔离客机上 UI 原语有完整桌面权限，因此不接生产桌面。唯一单桌面、串行 relay；20 次调用/480 秒 Codex/720 秒客机硬上限；模糊动作失败不重试；认证 token 只存客机、关闭 telemetry；模型结果不能作为通过判定。
- error-handling Items 1–7（C）PASS：异常向边界传播并记录 run ID；初始 server TCP 连接重试有上限，GUI 动作无自动重放；宿主/客机采用 owned Job，异常时仅回收本 Job；正常先自然关闭 SUT，再结束精确 MCP server。未知页签色标只记 unknown，不计通过。
- risk-and-verification-plan Items 1–5（C/A）PASS：依赖/进程属于较高风险；先纯单测与 PS parser，再固定客机探针。独立连续两帧观察 Prepare→Preview→Prepare；该 oracle 只证明页签选中，不能证明切片/持久化/回归覆盖。无发布动作。
- dependency-management Item 1（N）PASS：requirements/windows-mcp-probe.lock 固定 86 个 wheel 版本及 SHA256，仅 probe runtime，不加入宿主/base harness 依赖。
- dependency-management Item 2（N）PASS for this evaluation：构建时 OSV querybatch 对全部 86 个精确版本查询，2026-11-17 返回零条；原始结果 artifacts/windows_mcp_eval/osv.json。探针不加入 CI；正式接入 CI 时必须把同等扫描变成每次构建门禁，当前不声称长期安全。
- dependency-management Items 3–6（C）PASS with documented limits：提交 CycloneDX SBOM；便携 Python 3.14.10 和 runtime 双端 SHA256 验证。没有签名 SLSA attestation，原因是一次本地隔离实验、不发布二进制。Windows-MCP 自身 MIT，fuzzywuzzy/Levenshtein/python-Levenshtein 含 GPL；本地使用不等于允许把整包并入商业产品分发，分发前单独审核。86 个依赖约 61 MB zip，保留原版以检验现实接入成本。
- pytest-patterns Items 1–5（C/A）PASS：纯函数反例测试与已有单测分开；不启动宿主 GUI。首次把测试放 tests 下触发宿主 rig gate，未执行；已移至既有 unit_tests 后执行成功。

## 验证

- python -B -m pytest unit_tests -q：729 passed, 1 skipped（24.85 秒）；skip 保持已有 Windows Job 平台边界。
- hv_go.ps1 / hv_harvest.ps1 PowerShell parser：无解析错误。
- 客机 Python 3.14.10 + windows-mcp 0.8.9 serve --help：exit 0；runtime ZIP 双端 SHA256 9b8fd5d91cab3c6bcbff201d37d9c535fb0c65fcc18c6da779c56ee056c690de。
- 真实 GUI：NOT VERIFIED，下一步仅通过 hv_go -WindowsMcpProbe 启动。

## 首轮真实联调（NON_GREEN）

run 7078bc61be5b4f5aac4fb755a9d6e03d，host/guest source 7222f88。Orca/MCP 服务正常启动；Codex MCP initialize 被 401 拒绝，未发生输入。server.log 显示 `/mcp/` 返回 307 → `/mcp` 返回 401；PowerShell 5.1 redirect 丢失 Authorization。桥改用 canonical `/mcp` 并禁重定向；不改上游服务或关闭认证。

worker 无错误、自然关闭 SUT，MCP server 已停止；guest Job ActiveProcesses=0，forced=false；host Job ActiveProcesses=0，forced=false。worker 自身 exit 0 仅表示生命周期完成，不表示任务通过。已由 hv_harvest -WindowsMcpRunId 回收原始报告及初始截图。保留本轮失败，不计入 GREEN，也不写飞书基线。

## 第二轮真实联调（NON_GREEN）

run 42203831e02244778f60e59567543d45，source f2eb317。认证与 MCP initialize/tools/list 已成功；原版 Snapshot 在 pillow 后端返回真实 Orca 1920×1080 PNG（180864 字符 base64），但桥收到的 SSE 文本被 PowerShell 默认编码误解码，产生 U+0085；Python splitlines 又把 JSON 字符串中的合法 Unicode 分隔符当作 SSE 边界，导致 JSONDecodeError。修复为从 RawContentStream 严格 UTF-8 解码、仅按 ASCII LF 切 SSE；新增三个 Unicode 回归反例。

本轮 CLI exit 0，但原生事件明确记录 Snapshot/ControlStatus failed；因此整轮是 NON_GREEN。宿主新增按原生 completed tool events 审计，禁止仅按 CLI exit 判断工具成功。worker/process 原始报告及截图已经 hv_harvest 回收；guest/host Job 均 active=0、forced=false；无输入动作、SUT 自然关闭。

## 第三轮真实联调（NON_GREEN）

run 50d3d4d34395492385c10b15f3d88ecf，source 1144897。原生 Snapshot、Screenshot、ControlStatus 已成功；Codex 自行看图选择 Click(loc=[253,49])，但 Click 在 CLI 默认 noninteractive approval_policy=never 下被拒，根本未送达 MCP 服务。宿主审计正确判 native_tools_failed_or_unused，未将 CLI exit 0 写成成功。

按官方配置 https://learn.chatgpt.com/docs/extend/mcp 的 tools.<tool>.approval_mode，给本次固定 guest bridge 的 Click 增加仅子进程有效的 approve 设置。用户已授权隔离 GUI 测试及可逆输入；这不是 auto-review 拒绝，不涉及修改全局策略或放开宿主 shell。服务端/桥的五工具白名单、单客机、20 调用预算及只读 shell sandbox 继续适用。原始失败已 harvest，guest/host Job 均 0 且无强杀。

修复后纯单测累计 734 passed, 1 skipped（22.60 秒），PS 两入口 parser 无错误。
