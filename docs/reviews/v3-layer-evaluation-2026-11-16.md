# v3 层高评估工具与故障探针审阅（2026-11-16）

结论：**APPROVE（限定实验范围）**。本批宿主固定探针、只读审计器和限定 N3 注入脚本无未关闭的阻断发现；允许协调者按冻结计划执行。A1–A5 已独立核证完整 SHADOW（5/5），N1–N3 均实际命中并被相关规则拒绝（3/3 合格检错，guest 仍 NON_GREEN）。工程 gate 允许进入第二业务，不开放发布或推导通用可靠性。实际执行跨至 2026-11-17（Asia/Shanghai），保留原 11 月 16 日冻结批次及源码基线。

## 范围与独立性

审阅 `tools/v3_layer_fault_probe.py`、`tools/v3_layer_audit.py` 及对应纯单测；另只读审阅 `runner/experiments/layer_collision_20261116.ps1`：该版本化副本与已审阅的本地 `artifacts/v3_eval/layer_faults_20261116_01/inject_collision.ps1` 逐字节相同。guest 生产代码仍固定 ac0306a，未修改 worker、runtime、契约、夹具或业务 oracle。架构师未编写这些实现，未调用 VM/relay/GUI 或执行注入；本计划与运行记录由架构师撰写、协调者复核。

审阅前已加载 INDEX、harness-driven-review、README 跑批纪律、PITFALLS，以及以下适用 harness。并行仅准备/审阅/分析，协调者独占真实桌面。原始失败与 probe 来源分账，不用后续成功覆盖既有裁决。

## Harness: AI Evaluation (`common/ai/ai-evaluation-and-regression-strategy.md`)

Items 1–7 — PASS (C/A)：五槽身份预登记，历史 6bfe 不入分母；启动即占槽，不成功补位。正例必须 CLI 图→动作→真实 MCP/GUI→独立路径及对象挤出层序→自然 Job 清理。N1 改错初层、N2 漏第二 slice、N3 导出目标冲突均是固定 probe，明确 ai_trial=false/model_inference=false。故障 audit 只有实际命中且相关拒绝成立才输出 EXPECTED_NON_GREEN，不把任意 NON_GREEN、强制回收或缺报告当成功。精确模型/美元成本未知，token 字段不重复相加。

## Harness: Tool Control (`common/ai/tool-calling-and-agent-control.md`)

Items 1–7 — PASS (C/A)：复用生产 host.run_host 及取消/cleanup；只注册三个固定序列，固定 case、1920×1032 布局、edit 文本/坐标与 exact run/sequence observation_id。无任意命令、路径、VM 名或插件入口。N3 在无未完成 RPC 时等待限定 request/ack，60 秒及整体 deadline 较早者到期即停止。注入权限只在协调者；模型与 probe 不执行 relay 或 shell。CIM 命令行只在内存比较，不记录凭据/命令行内容。

## Harness: Input Validation (`common/security/input-validation.md`)

Items 1–4 — PASS (N/C)：按原 harness 保留 N-tier 的信任边界验证、白名单、解释器注入防护和精确类型要求；C-tier 覆盖 canonical 路径、范围/长度/格式。严格 schema、身份、相对路径与 hash；拒绝 bool/int 混淆、旧 run、跳号/跨 run 观测、错误 ack、额外模型调用。解释器只接固定脚本/已验证整数 PID 或常量，不接受模型生成命令。审计器有界读取并拒绝链接/重解析路径；契约必须匹配应用注册的完整 digest，不接受仅内部自洽的新契约。

Items 6–7 — PASS (C)：不静默修补非法输入；输出稳定错误码，JSON 序列化，不向日志透出未验证内容。

Item 5 — N/A：无外部上传服务；本地产物通过有界文件读取、身份与 hash 校验处理。

## Harness: Review Checklist (`common/code-review/review-checklist.md`)

Item 1 — PASS WITH RATIONALE (C)：总 diff 超过 400 行，采用分阶段独立审阅而非一次笼统放行。第一轮审正例 audit 的文件读取、注册契约、生命周期、CLI lineage、聚合结果及对应反例；第二轮审故障 audit 的 prefix/receipt、N1/N2/N3 命中与拒绝规则、固定动作来源及对应反例。probe/注入脚本另按各自接口与副作用单独审阅，最后核对共用入口及跑组合测试。未为行数拆成新框架。

Item 6 — PASS WITH RATIONALE (C)：_probe_lineage 等验证函数较长，保留在单一只读审计文件内，按可信输入→观测/动作→副作用收据→裁决顺序核查；固定三故障分支共享读取与身份约束，避免复制整个检查器。其范围仅冻结实验，不宣称通用审核框架；后续业务扩展需重新评估结构。

Items 2–5,7 — PASS (C)：主链复用，没有第二套 guest 框架。独立复核发现并关闭以下问题：

| 条件与发现 | 动作与结果 |
|---|---|
| probe 原 observation_id 只要求字符串/未复用，不能证明本 run 下一帧 | 在任何 summary/request 写入前要求 exact run_id + 四位序号，补跨 run/跳号反例。 |
| audit 原只验证自洽契约与事件 hash，缺应用注册及完整生命周期语义 | 绑定 agent_contract digest，要求固定执行/验证/两组 cleanup 顺序；补改 goal 后重算所有 hash、重排/删除 cleanup 后重算链的语义反例。 |
| N3 依赖未验证 guest PATH 查 git | 固定已验证 MinGit 路径并核 LASTEXITCODE 与精确 HEAD。 |
| N3 在 PSDirect 查询交互 HWND，运行会话适用性未经证明 | 删除 USER32 查询；仅 worker ready/最新 slice response 关联 GUI 身份，CIM 核 live app/driver 父子、相同非零 session、固定 run profile/run_id。 |
| N3 请求常量按 LF 计算，Windows 生产 _once 实际写 CRLF | 用真实 _once 临时写盘再 read_bytes，独立确认 343 bytes/CRLF；限定脚本绑定真实 raw hash 7397d53f…，不修改冻结 probe。 |

窗口站归属 session、非交互进程不能默认处于交互窗口站，依据 [Microsoft Window Stations](https://learn.microsoft.com/en-us/windows/win32/winstation/window-stations) 与 [Process Connection to a Window Station](https://learn.microsoft.com/en-us/windows/win32/winstation/process-connection-to-a-window-station)。这里移除的是未经证明的跨会话门禁，没有增加 GUI 权限。

Item 8 — PASS (A)：修改反馈直接交给对应实现者，审阅范围保持在本批工具及实验。

## Harness: Pytest (`python/testing/pytest-patterns.md`)

Items 1–5 — PASS (C/A)：架构师独立执行 `python -B -m pytest unit_tests/test_v3_layer_audit.py unit_tests/test_v3_layer_fault_probe.py unit_tests/test_agent_host.py -q`，**78 passed**（42 audit、28 probe、8 既有 host）。覆盖固定真实控制循环配 fake MCP、错误 ack/截止/旧 run、故障特定拒绝、错误初层产物、缺注入收据、sentinel 改写及契约/事件重新 hash。它们不等于 VM 注入或 GUI 验证。

## N3 脚本冻结与限制

最终脚本 SHA-256：`4a0588f5acc7c6ce713993163d1f029f6e0e21a07e04cbc5ad453884d604794d`。只允许固定 N3 run `053062a751b74a49b1911dc495a75c5d` 与 guest checkout，核固定 plan/HEAD/契约、当前 slice5、未发 request6、无 cancel/result/process；逐级拒绝 reparse。只用 CreateNew 写当前 run 的 `exports/0002.gcode`，内容为 28 bytes sentinel，回读 hash 后独占写 guest receipt，再发布 typed ack，不覆盖/删除既有文件、不重试/kill。

真实请求 bytes SHA 为 `7397d53fcbcd25749b6cf54622ee3a3211fa44b0ffdfa2efd37172017f7a535e`；sentinel SHA 为 `4cf9a39ebecd994965f4a78505383bf804da98713c9e87e580e22d58a9eb1230`。执行前脚本经静态审阅、PowerShell AST ParseFile 和生产 _once raw-byte 自检；随后由协调者实际运行 N3，已收割并独立核对注入/拒绝/清理证据。审阅者未执行脚本或操作 VM，未假造 OS 行为单测。脚本已作为限定实验资产版本化，协调者执行该副本；固定 run/path 不提供通用注入接口。raw 证据仍只在本地。

## 已核证结果与剩余边界

A1–A5 的每个 ZIP 48 文件已与提取目录逐字节比较；完整 verifier、9 阶段事件链、CLI 图/hash/action/usage→guest 请求重放通过。另与冻结 plan/setup/harvest 绑定 source、SUT、CLI hash。明细见 [运行记录](../runs/v3-layer-evaluation-2026-11-16.md)。五槽共 30 次模型调用、35 次工具调用。

N1 已独立核证：真实 B 常规 .40/初层 .24，68 层，path pass/business fail（gcode_layer_height_mismatch），自然 exit0/Job0；fault audit EXPECTED_NON_GREEN，固定 6 决策/7 工具，非 AI。ZIP 48 文件逐字节一致（SHA d5acc38e…），host 三工具 hash 与冻结 host_source 一致，guest ac0306a/SUT 未变。

N2 已独立核证：observe 替代第二 slice 后 seq6 export_not_ready，实际无 B；5 固定决策/6 工具、5 阶段失败/cleanup 事件链，ZIP 40 文件逐字节一致（SHA 1560e8da…）。runtime failed，exit1/forcedfalse/cancelnull/Job0/cleanuptrue；是失败退出后清空，不是自然完整完成或强杀。full checker 的 process_not_quiescent 这里由 exit1 门槛触发，不能推断进程残留。fault audit EXPECTED_NON_GREEN 依据实际漏 slice 与相关工具拒绝，未升级业务 unknown。

N3 已独立核证：请求 raw CRLF hash=7397d53f…，版本化脚本执行日志、host ACK/accepted、guest 注入 receipt 及 slice5 归属完整；28-byte sentinel 收割 hash=4cf9a39e…未变，seq6 export_exists。5 固定决策/6 工具、5 阶段失败/cleanup 链，ZIP 42 文件逐字节一致（SHA de8dd6da…）。exit1/forcedfalse/cancelnull/Job0/cleanuptrue，是失败退出后清空；完整业务 unknown 保留。三项故障独立分账，均非模型推理。

audit 本身只证明可信本地收据一致性，不提供密码学来源认证/同权限对抗隔离；外部版本绑定仍需 plan 与同步日志，原 manifest 未记录的版本保持 unknown。prompt_hash 不重算并明确标记；不声称完整几何、固件或实物打印验证。N3 只检验目标已存在时拒覆盖，不证明任意 OS 保存失败。所有运行仍限制 SHADOW/NON_GREEN，不开放发布 GREEN。

## Verdict: APPROVE

无未关闭 (N)/(C) 项。五槽 5/5 与三故障 3/3 均已按冻结身份独立核证，八个 run 清理确认；允许下一业务验证，仍不具发布资格。协调者全套 558 passed / 1 skipped；本审阅相关 78 tests 已独立通过，最终文档更新未重复测试。B6 信号检查使用 --dry-run，保持 dev-guidelines 只读。
