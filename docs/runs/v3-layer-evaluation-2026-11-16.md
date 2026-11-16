# v3 层高业务重复运行与故障检错记录

状态：本批 **A1–A5 已独立核证为完整 SHADOW（5/5 已完成）**。三类故障探针尚无已核证结果。本记录保留预先冻结的五槽分母；历史 6bfe 正例和固定故障动作不计入。

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
| N1 改错相似参数 | `f71361067b3c48b48bc3eb2a5507405a` | fault_probe_wrong_parameter，未执行/未核证 |
| N2 漏重切（observe 替代第二 slice） | `98053dc9877a456b961efc5fea635b34` | fault_probe_missing_reslice，未执行/未核证 |
| N3 导出目标占位冲突 | `053062a751b74a49b1911dc495a75c5d` | fault_probe_export_collision，未执行/未核证 |

N3 使用已版本化的限定实验脚本 `runner/experiments/layer_collision_20261116.ps1`，SHA-256 `4a0588f5acc7c6ce713993163d1f029f6e0e21a07e04cbc5ad453884d604794d`；其内容已与审阅的本地副本逐字节比对，仍只绑定固定 run/path，raw 证据不因此变成长期归档。

故障来源是固定 ModelPort 动作，不是 AI 推理，也不是三个 AI 成功。必须核对实际故障命中及相关拒绝理由；任意 NON_GREEN、异常清理或缺报告都不足以算检错成功。N3 仅挑战防覆盖，不称 GUI 保存或 OS 写盘失败。所有结果、取消与清理方式待真实证据到达后填写。

## 原始证据与当前结论

raw ZIP/截图/G-code 为本地忽略产物，未声称长期上传。正例 ZIP 位于 `artifacts/v3/layer_eval_20261116_01_<槽号>.zip`，提取与审计结果位于同名批次的 `artifacts/v3_eval/` 目录；宿主 CLI 原始记录在 `artifacts/v3_host/<run_id>/`。

| 槽 | ZIP bytes / 文件数 | 独立计算 SHA-256 |
|---|---|---|
| A1 | 3,874,026 / 48 | `75dc2628d698f83a357b96667b8ce1a5a3c4ec33653de84e3f247fa175402d23` |
| A2 | 3,896,579 / 48 | `4dabd708ae3468bc75b4d580da479dc86e20fc5f2d55dfc956d6b429efb025af` |
| A3 | 3,879,197 / 48 | `365a97dba13d0ca37500437192d736ba67b9b321fb05bb1a7cef3d90515391a6` |
| A4 | 3,898,459 / 48 | `6661cffe03bb452422a2492fdadf48886a2bc2d55d5ff386dcc8e1757cee0c45` |
| A5 | 3,882,130 / 48 | `ba9f7a0b7d3df2c01e151b534fe68621fd19562933ba0c8c7dff79f32463edd7` |

当前已达到“五槽完成且 5/5 SHADOW”的重复运行门槛；三类真实故障命中与检错仍待验证，整个批次评估尚未完成，不能提前进入第二业务或发布 GREEN。全部验证仍限固定单材 cube 的参数/切片/导出流程，不代表其他业务、固件或实物打印。
