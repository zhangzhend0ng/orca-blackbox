# v3 层高业务重复运行与故障检错记录

状态：本批 **A1–A5 已独立核证为完整 SHADOW（5/5 已完成）**。三个固定故障探针均已实际命中并被相关业务规则/工具门禁拒绝（3/3 合格检错）。执行跨至 2026-11-17（Asia/Shanghai），沿用 11 月 16 日冻结的批次名与 guest source，不重命名或重开分母。本记录保留预先冻结的五槽分母；历史 6bfe 正例和固定故障动作不计入。

## 冻结范围与分母

计划见 [V3_LAYER_EVALUATION.md](../V3_LAYER_EVALUATION.md)。正例批次 `layer_eval_20261116_01` 的五个 run_id 在执行前登记于 `artifacts/v3_eval/layer_eval_20261116_01/plan.json`；一旦发起执行便占槽，失败/超时/unknown 不得替换成成功补跑。当前已发起 5/5、已完成 5、通过 5、失败 0、进行中 0、未执行 0。

guest 生产基线 `ac0306a8697b45ffdc7264ec3929ac57dc2a1226`，bundle SHA `d02a48b73d20b59648ce74dea9d0dd34001821bb16757307feb1e1112b84ac21`。SUT SHA `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`；夹具 SHA `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`；契约摘要 `a84be6d0070374966f50ae053a41fe8779ed483f7863fd2055ce75ce99e81114`。每槽独占新 profile，由既有 seed/fresh=False 初始化，不沿用上一轮应用状态。

五次 AI 均使用 codex_cli 与显式固定 native 路径，CLI SHA `094d4db493de22025712cc5963854e7654b7c97f4cee795e3e986270a0f4f6b4`。精确模型 ID 与 USD 成本未知；max_cost_usd=0 不代表美元费用已机械封顶。guest 源码/SUT 身份由每轮 setup/harvest 日志补证，原 manifest.metadata 为空。只读审计的内部证据一致性不代替这些外部版本绑定。

## AI 五槽逐项结果

| 槽 | run_id | 当前结果 | AI edit | host / guest process 秒 |
|---|---|---|---|---|
| A1 | `e3edd6094d6647178a4b8f52987ac0c1` | SHADOW，已核证 | `(291,764,"0.24")` | 177.419 / 201.082 |
| A2 | `674984ffcf5f447f97f44dadcf2a4cf4` | SHADOW，已核证 | `(294,765,"0.24")` | 187.560 / 205.947 |
| A3 | `d76fd3dd443c4520a2a508c5b22664ac` | SHADOW，已核证 | `(285,764,"0.24")` | 164.694 / 193.914 |
| A4 | `163a43f22709498c8b39afd1d5452479` | SHADOW，已核证 | `(292,764,"0.24")` | 164.857 / 266.780 |
| A5 | `9025995ff8904a70a133d36b0f0af50f` | SHADOW，已核证 | `(298,764,"0.24")` | 170.526 / 195.064 |

A1–A5 均为 6 次实际 CLI 看图决策、7 次工具：observe → slice → export A → edit → slice → export B → finish。path/business pass，evidence_complete/execution_compliant true；execution/runtime completed、verified_pass=true、release_eligible=false。五轮均自然 exit=0、Job active=0、forced_termination=false、cancel_reason=null、cleanup_confirmed=true；driver/app 分别为 6660/1512、4700/8264、7548/6496、4576/5576、4840/1528。

五轮 A 均为 68 层×0.40、首/末 Z=0.40/27.20、1907 次正 XY/E 运动；B 均为 112 层×0.24、首/末 Z=0.40/27.04、2882 次运动；对象工具均 T0。运动条数在本五轮恰好相同，不作为后续必须相同的黄金值。架构师分别比较 ZIP 48 文件与提取内容、重放完整检查器，并核对 9 阶段事件链、真实 CLI 图像/动作/usage 与 guest 请求关联；CLI/契约摘要匹配冻结 plan。

| 槽 | input tokens | output tokens | reasoning tokens | cached input |
|---|---:|---:|---:|---:|
| A1 | 101,888 | 416 | 72 | 0 |
| A2 | 101,828 | 380 | 50 | 0 |
| A3 | 101,849 | 424 | 84 | 0 |
| A4 | 101,791 | 388 | 62 | 0 |
| A5 | 101,865 | 405 | 67 | 0 |
| 合计 | 509,221 | 2,013 | 335 | 0 |

这些是原始 CLI usage 字段，reasoning 不再次加到 output；没有填充不存在的模型 ID 或美元价格。五槽共 30 次实际模型调用、35 次工具调用，未重试/替换槽位。host 耗时中位数 170.526 秒，均值 173.011 秒，范围 164.694–187.560 秒；guest process 中位数 201.082 秒，均值 212.558 秒，范围 193.914–266.780 秒。host 是 controller 生命周期，guest 是 OwnedJob 进程生命周期，二者起点不同，不相加。五次样本只满足本批重复运行门槛，不外推可靠率。

## 固定故障探针：独立分账

| 探针 | run_id | 来源 / 状态 |
|---|---|---|
| N1 改错相似参数 | `f71361067b3c48b48bc3eb2a5507405a` | fault_probe_wrong_parameter，命中并正确拒绝 |
| N2 漏重切（observe 替代第二 slice） | `98053dc9877a456b961efc5fea635b34` | fault_probe_missing_reslice，命中并正确拒绝 |
| N3 导出目标占位冲突 | `053062a751b74a49b1911dc495a75c5d` | fault_probe_export_collision，命中并正确拒绝 |

N3 使用已版本化的限定实验脚本 `runner/experiments/layer_collision_20261116.ps1`，SHA-256 `4a0588f5acc7c6ce713993163d1f029f6e0e21a07e04cbc5ad453884d604794d`；其内容已与审阅的本地副本逐字节比对，仍只绑定固定 run/path，raw 证据不因此变成长期归档。

故障来源是固定 ModelPort 动作，不是 AI 推理，也不是三个 AI 成功。必须核对实际故障命中及相关拒绝理由；任意 NON_GREEN、异常清理或缺报告都不足以算检错成功。N3 仅挑战防覆盖，不称 GUI 保存或 OS 写盘失败。三项实际结果与清理方式如下，保持各自 guest NON_GREEN 裁决。

### N1：改错初层参数，命中且正确拒绝

宿主工具提交 `108939e5db1fdc619c98ec99044c2f20c6e947ce`，guest 生产仍为 ac0306a；故障批 `host_source.json` 绑定 probe、audit、限定注入脚本三文件 hash，架构师已核对当前文件一致。setup/harvest 另绑定 guest source 与 SUT。

固定 6 次决策 / 7 次真实工具走完整 slice/export/edit/reslice/export/finish；实际 edit `(298,794,"0.24")` 改变 First layer height，常规层高仍 .40。A 为 .40/初层 .40、68 层、首/末 Z=.40/27.20、1907 次正 XY/E；B 为 .40/初层 .24、68 层、首/末 Z=.24/27.04、1903 次运动，均对象 T0。由实际 G-code 证实“改错相似字段”，不是应用吞掉正确参数。

完整 guest 结果 NON_GREEN，path pass / business fail，detail=`gcode_layer_height_mismatch`；只读 fault audit 为 EXPECTED_NON_GREEN，ai_trial=false，不是业务通过。自然 exit=0、forced=false、cancel=null、Job active=0、cleanup_confirmed=true；host 73.115 秒 / guest process 124.097 秒。没有模型推理，不填 token usage。

ZIP `artifacts/v3/layer_faults_20261116_01_1.zip`：3,923,861 bytes / 48 文件，SHA-256 `d5acc38ef5092cff16560c40fae84ab9dd7f913ead68d33839f4408032fcc8f8`；架构师逐文件比对并重放 full/fault checker、9 阶段事件和固定动作/图片关联。raw 不修改，N1 不加入五槽 AI 分母。

### N2：漏第二次 slice，导出门禁拒绝

真实序列 observe → slice → export A → edit `(298,764,"0.24")` → observe → export（seq6），最后返回 `export_not_ready`，没有第二次 slice、没有 B，也未执行 finish。原计划用 observe 保持可到达完整 7 工具的路径，但实际在第 6 工具已命中相关门禁，因此只有 5 次固定决策；不为凑数量继续发动作。

guest execution/runtime=`failed`、NON_GREEN、verified_pass=false，path/business 原结果为 unknown/not checked；独立 full checker 的 unknown/detail=`process_not_quiescent` 来自 exit=1 的完整成功门槛，不表示有残留进程。实际 Job active=0、forced_termination=false、cancel_reason=null、cleanup_confirmed=true：worker 失败退出后清空，既不是自然完整完成，也不是 Job 强杀。host 记录 cancel_request_written=true 只证明发过取消请求，不推导 process 已因 cancel 终止。

fault audit 为 EXPECTED_NON_GREEN：实际漏 slice 和相关 export_not_ready 有独立 trace、prefix 图片/操作收据/固定动作关联，5 阶段失败/cleanup 事件链完整。baseline A 为 .40/初层 .40、68 层、1907 次正 XY/E、T0。host 54.878 秒 / guest process 126.809 秒。ZIP `artifacts/v3/layer_faults_20261116_01_2.zip`：2,252,902 bytes / 40 文件，SHA-256 `1560e8da459886fdaa035b1f38646bf4df1761b6dcc6e04ebd86931e4e8059d3`，已逐字节比对及重放；guest ac0306a/SUT 未变。该结果检验工具路径门禁，不声称验证了不存在的 B 或“旧文件被导出”。

### N3：导出目标占位冲突，实际注入并拒覆盖

协调者执行版本化脚本（SHA `4a0588f5…`），注入日志为 `collision_created_and_acknowledged`。独立核对真实 request 为 Windows CRLF bytes，SHA `7397d53fcbcd25749b6cf54622ee3a3211fa44b0ffdfa2efd37172017f7a535e`；host ACK/accepted 与 guest `fault_injection.json` 的 run、case、contract、slice5 observation、路径、创建时刻与 hash 一致。当前 run 的 `exports/0002.gcode` 为独占创建的 28-byte sentinel，收割时仍为 SHA `4cf9a39ebecd994965f4a78505383bf804da98713c9e87e580e22d58a9eb1230`。

真实序列完成 baseline/export/edit/reslice，在 seq6 第二 export 返回 `export_exists`，未执行 finish、没有业务 B。fixed probe 为 5 次决策/6 工具，无模型推理；fault audit EXPECTED_NON_GREEN。此例证明“目标存在时拒绝覆盖”，不声称 GUI 保存对话框或任意 OS 写盘失败，也不把 sentinel 当 G-code。

guest execution/runtime=failed、NON_GREEN，exit=1、forced=false、cancel=null、Job active=0、cleanup=true；worker 失败退出后清空，未强杀。完整业务 checker 仍 unknown/process_not_quiescent（exit1 成功门槛），没有借故障检错改成业务 pass。5 阶段失败/cleanup 事件与故障特定证据完整。host 107.587 秒 / guest process 130.804 秒。

ZIP `artifacts/v3/layer_faults_20261116_01_3.zip`：2,634,840 bytes / 42 文件，SHA-256 `de8dd6da24d85787a480ce63e7f0a889f6974a4dee776f2b7c9b82345d3df9c6`；已逐字节比对，重放故障审计并核对 setup/harvest 的 ac0306a 与固定 SUT。注入与取证均由协调者串行执行，审阅者未操作客机。

## 原始证据与当前结论

raw ZIP/截图/G-code 为本地忽略产物，未声称长期上传。正例 ZIP 位于 `artifacts/v3/layer_eval_20261116_01_<槽号>.zip`，提取与审计结果位于同名批次的 `artifacts/v3_eval/` 目录；宿主 CLI 原始记录在 `artifacts/v3_host/<run_id>/`。

| 槽 | ZIP bytes / 文件数 | 独立计算 SHA-256 |
|---|---|---|
| A1 | 3,874,026 / 48 | `75dc2628d698f83a357b96667b8ce1a5a3c4ec33653de84e3f247fa175402d23` |
| A2 | 3,896,579 / 48 | `4dabd708ae3468bc75b4d580da479dc86e20fc5f2d55dfc956d6b429efb025af` |
| A3 | 3,879,197 / 48 | `365a97dba13d0ca37500437192d736ba67b9b321fb05bb1a7cef3d90515391a6` |
| A4 | 3,898,459 / 48 | `6661cffe03bb452422a2492fdadf48886a2bc2d55d5ff386dcc8e1757cee0c45` |
| A5 | 3,882,130 / 48 | `ba9f7a0b7d3df2c01e151b534fe68621fd19562933ba0c8c7dff79f32463edd7` |

本批已满足冻结的工程门槛：五槽 5/5 完整 SHADOW，三个固定故障 3/3 实际命中并被相关规则拒绝，八个 run 均确认 Job 清空与 cleanup。允许进入第二业务的设计与验证；不开放发布 GREEN，不把负例计入 AI 成功，也不从五次样本推导通用可靠性。全部验证仍限固定单材 cube 的参数/切片/导出流程，不代表其他业务、完整几何、固件或实物打印。

协调者最终全套纯测 558 passed / 1 skipped；架构师已独立执行本批相关 78 tests，最终证据收尾未重复跑测试。raw ZIP 仍仅本地，报告中的 hash 不等于已长期归档。
