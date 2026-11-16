# v3 固定层高业务评估计划

2026-11-16 冻结。本批只做 `m3d_param_reslice / ai-layer-1` 的 **5 次新 profile AI 重复运行 + 3 类真实故障探针**，完成后再决定是否进入第二业务。已有 6bfe 正例和四次失败作为历史基线，不填入本批分母。并行仅用于准备、审阅和只读分析；客机桌面、VM/relay 始终由协调者串行独占。

## 固定条件与分母

- guest 生产基线：`ac0306a8697b45ffdc7264ec3929ac57dc2a1226`；不修改 worker、工具、runtime、checker、契约或夹具来适配本批结果。宿主故障驱动单独审阅、记录其提交/文件 hash，不改变生产 ModelPort/控制流程。
- SUT SHA：`5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`；夹具 SHA：`ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`；契约摘要：`a84be6d0070374966f50ae053a41fe8779ed483f7863fd2055ce75ce99e81114`。
- A1–A5 各分配新的 run_id、独占 run 目录和新建 profile，由既有 seed/fresh=False 路径初始化；“新 profile”不意味着启用旧 fresh=True 全局清理。每次均从固定 .40 输入开始，不沿用上一轮状态。
- AI 来源必须是 codex_cli，保持相同 prompt 模板、工具 schema、CLI 可执行 hash/配置和显示条件；实际图片、历史及 prompt hash 按调用记录。精确模型 ID 若 CLI 不返回则 unknown，不能据此声称模型版本完全锁定。
- **固定计划分母为 5**。启动前登记槽位与 run_id；一旦向 guest 调度入口发出该 run 的执行请求，即占该槽，后续启动失败、模型/工具错误、超时、unknown 均保留，不能用“再来一次成功”替换。纯预检未发起执行的阻塞单列。中止时报告“已发起 k/5、通过 p、失败 f、未执行 5−k”，不得把未执行写成通过，也不输出完成的 5 次成功率。
- 已结束但补跑或诊断的新 run 单独登记，不进入原五槽。生产代码、SUT、夹具、checker、prompt 模板、权限或 CLI 配置一旦改变，结束原冻结批并保留结果；新版本另开完整批次，不拼接出 5/5。

本批标识 `layer_eval_20261116_01`，启动前计划保存在 `artifacts/v3_eval/layer_eval_20261116_01/plan.json`。bundle SHA-256 为 `d02a48b73d20b59648ce74dea9d0dd34001821bb16757307feb1e1112b84ac21`；CLI 用显式 --codex 固定本机 native 路径，SHA-256 为 `094d4db493de22025712cc5963854e7654b7c97f4cee795e3e986270a0f4f6b4`。精确模型 ID 仍 unknown。下表为预先冻结身份，不是结果：

| 槽位 | run_id |
|---|---|
| A1 | `e3edd6094d6647178a4b8f52987ac0c1` |
| A2 | `674984ffcf5f447f97f44dadcf2a4cf4` |
| A3 | `d76fd3dd443c4520a2a508c5b22664ac` |
| A4 | `163a43f22709498c8b39afd1d5452479` |
| A5 | `9025995ff8904a70a133d36b0f0af50f` |

## 五次 AI 的接受条件

每槽必须有真实 CLI 图像输入→原始结构动作→MCP→guest 最新观测/请求关联；不得用固定脚本、chat decision 或历史动作补足失败步骤。独立重放应同时确认：

1. 固定输入身份、baseline slice/export → GUI edit .24 → reslice/export → finish 的完整路径；新文件的 hash/时间/操作收据可追溯。
2. A/B 回显 .40/.24，初层 .40；实际对象正 XY/E 层序分别 68/112、末 Z 27.20/27.04，对象单工具且 A/B 一致。运动条数和整个文件 hash 可因路径变化而不同，不能要求复制历史文件。
3. path/business pass、evidence_complete/execution_compliant true，guest SHADOW/verified_pass=true；自然 exit=0、Job active=0、forced_termination=false、cancel_reason=null、cleanup_confirmed=true。模型 finish、工具 rc=0 或仅 A/B 成立不足以通过。

报告每槽 verdict、失败阶段/类别、模型/工具次数、host/guest 耗时、原始 usage、ZIP hash 与清理方式；报告五槽全部明细及通过数，不只展示成功截图。5/5 仅是本批工程门槛，不据五次样本外推可靠率、跨版本稳定性或发布资格，所有结果仍为 SHADOW/NON_GREEN。

## 三类真实故障：单独分账

探针通过现有 ModelPort 接口提供**固定动作**，继续走真实 MCP、guest GUI 和同一独立 checker。来源必须与 codex_cli 分开，固定动作不是模型推理；不得计入五次 AI 成功率。既有独立图像/产物检查和权限约束不变。

故障批次 `layer_faults_20261116_01` 的独立 plan.json 位于同名 `artifacts/v3_eval/` 目录，guest 基线仍为 ac0306a：N1=`f71361067b3c48b48bc3eb2a5507405a`，N2=`98053dc9877a456b961efc5fea635b34`，N3=`053062a751b74a49b1911dc495a75c5d`。这些身份不属于 A1–A5 分母。

| 探针 / 来源 | 固定故障与操作 | 合格检错证据 |
|---|---|---|
| N1 / `fault_probe_wrong_parameter` | baseline slice/export → 固定 GUI edit `(298,794,"0.24")` 改 First layer height → reslice/export/finish，保留完整 7 工具序列 | 该坐标由协调者查看 6bfe 实际截图确认（regular y=764，first y=794）。必须从 A/B 证明 B 的常规层高仍 .40、初层变 .24；预期 path pass 而 business 因实际层高/初层不符拒绝，完整结果 NON_GREEN。这是“改错相似参数”挑战，不冒称应用忽略正确输入；若未命中字段则不确定。 |
| N2 / `fault_probe_missing_reslice` | baseline 后 GUI edit .24，用 observe 替代第二 slice，再 export/finish；保持 7 工具但不新增输入 | trace 确认无第二 slice；工具可因 export_not_ready 拒绝，或完整检查因路径顺序不符拒绝。observe 避免仅因工具总数不足而提前拒绝。若后台自动重切，仍不能用其冒充契约要求的显式 slice；报告实际拒绝层，不虚构旧文件。 |
| N3 / `fault_probe_export_collision` | 正常 baseline/edit/reslice 后，第二 export 前暂停；协调者在该 run 固定 `exports/0002.gcode` 独占创建 sentinel，再允许 export | 注入前目标不存在；创建/ack 绑定 run、fault、固定相对路径及内容 hash；工具返回 export_exists，sentinel hash 不变，完整结果 NON_GREEN。属于真实导出目标冲突/防覆盖检查，不称 GUI 保存对话框或 OS 写盘失败。 |

N3 只允许协调者在核对 canonical run 根与既有身份后使用版本化的限定实验脚本 `runner/experiments/layer_collision_20261116.ps1`（SHA-256 `4a0588f5acc7c6ce713993163d1f029f6e0e21a07e04cbc5ad453884d604794d`），不是通用注入入口。host probe 不执行 relay、shell 或任意路径操作；模型不能发出注入请求。request/ack 独占发布，ack 身份/路径/hash 不符或等待超时立即停止，不继续导出、不重放模糊动作。碰到已存在的目标不得覆盖、删除或假装注入成功。原始产物、契约、检查器和结果不修改；sentinel 是明确记录的故障条件，不能当业务 G-code。

**NON_GREEN 本身不等于探针成功**：必须证明所选故障实际发生，并且由相关工具/检查规则拒绝。若启动/定位/网络/其他步骤先失败，或注入未确认，仅记“探针未命中/不确定”，保留原 run，另列诊断；不能抵扣对应负例。N1/N2 在自然收尾可行时要求正常退出；N3 等工具错误可按既有 host cancel→runtime OwnedJob 回收，强制清理事实如实记录。

## 停止、预算与下一步

- 单次沿用 host 600 秒、guest 900 秒、最多 8 次模型/12 次工具/6 次 tab 点击，业务 edit/slice/export 各最多 2 次，无业务动作重放；独立控制取消/cleanup 沿既有预算。五次 AI 最多 40 次模型调用，固定探针不伪造 token usage。ChatGPT 订阅通道 USD unknown，max_cost_usd=0 不是已实现美元成本门禁。
- 任一错误条件竟得到 SHADOW、证据身份/来源错配、越权输入、无法确认 Job 静止/cleanup 或桌面锁异常，立即停止后续桌面任务，保留证据并修复；不得靠后续成功平均掉。普通模型/产品失败若清理已确认，可继续剩余预定槽位，但失败仍计入本批。
- 候选进入第二业务的条件：五槽完成且 **5/5 完整 SHADOW**，N1/N2/N3 均有命中与相关拒绝证据，所有 run 清理确认，无未闭合假通过/权限/证据问题。达不到时报告真实缺口，不宣布稳定性达成。此门槛不开放发布 GREEN。

## 审阅与记录责任

协调者负责启动、注入、收割和统一收尾；实现者只新增宿主固定 probe 与纯测试；架构师独立审阅 probe 的固定 allowlist、schema/时序/预算、注入身份、故障来源和异常取消；另一审阅者只读核证运行产物与拒绝理由。raw 保持本地忽略产物，记录 hash/路径，不声称已长期上传。

已按 mandatory harness 读取 INDEX、harness-driven-review、AI Evaluation、Tool Calling and Agent Control、Review Checklist：AI Evaluation 1–7 (C/A) 对应冻结范围/分母/独立 oracle/失败保存/门槛/变更分批/证据；Tool Control 1–7 (C/A) 对应固定宿主探针、单桌面串行、注入约束与停止；Review Checklist 3–5 (C) 要求独立审阅固定序列和故障命中反例，测试不能只复述实现自报。本文是计划，不是已执行结果。
