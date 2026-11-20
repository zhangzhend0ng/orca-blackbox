# v3 首批底座独立审查（2026-11-16）

## 结论与范围

**Verdict：APPROVE，仅限受信调用方使用的底座原语。** 无未解决的 N／C 级代码发现；这不是 GUI 回归、agent 隔离或发布门禁验收。

审查对象：`harness/run_contract.py`、`harness/run_evidence.py`、`harness/artifact_check.py`、`harness/run_verdict.py`、`tools/v3_session.py`。不包含用户既有 launcher／profile／farm_runner 改动、m5 修复和设计草稿。

在读代码前重新扫描 dev-guidelines INDEX 并加载适用 harness。按两个片段执行审查：契约／证据／CLI（约 346 物理行），产物检查／结果聚合（约 249 物理行），分别小于 400 行；两段的接口摘要和跨模块 digest 在第二片段统一复核。

## 必须保留的调用边界

- 这些 API 面向可信调度器／检查器，不是可直接暴露给操作 agent 的自报通过接口。`aggregate_result` 不认证 `CheckResult`、证据引用、布尔标志或 `Promotion` 的真实来源（run_verdict.py:76–85）。
- `RunEvidence` 为单 writer 的排他创建、追加和 finalize-once 机制；同权限程序仍可直接修改文件。未实现 Windows ACL、跨进程隔离、宿主／客机访问控制或不可篡改外部存储（run_evidence.py:1–5）。
- 产物新鲜度、hash 和配置 echo 是文件事实，不证明完整 gcode、工具路径或实际 GUI 操作正确；需由调用方提供独立完成性预期／业务检查（artifact_check.py:21–32）。
- `v3_session init` 只创建记录；`validate` 只验证契约。没有启动 GUI、调度 agent、执行预算或生成通过结论（tools/v3_session.py:21–43）。
- 发布所需的构建／初态／禁止路径／晋级来源尚未成为完整契约；当前状态在 docs/V3_FOUNDATION.md 中明确披露。此 schema 不应被宣称为完整 v3 发布契约。
- 敏感字段拒绝与标识符约束不是通用 DLP。可信调用者必须传递脱敏、去标识数据；任意文本内容不能因为通过 JSON 校验便认定无敏感信息。

## 片段一：契约、证据与 CLI

### Harness：Input Validation (`common/security/input-validation.md`)

Items 1–4,6 — PASS：精确字段集合、字段与数值类型、范围、有限费用、重复检查／步骤拒绝；CLI 使用 argparse，不拼接 shell。证据 run_id 限定为标识符，事件相对引用拒绝绝对路径、分隔符混淆、点段与根外解析结果。依据 run_contract.py:19–33,76–111；run_evidence.py:52–55,65–97,108–126；tools/v3_session.py:21–43。

Item 5 — N/A：该片段不接受上传二进制；JSON 文件的大小限制已在反序列化项审查。

Item 7 — PASS：JSON 序列化负责输出编码；CLI 错误只输出异常类型，不回显用户输入或文件系统异常正文（tools/v3_session.py:36–42）。

### Harness：Python Input Deserialization (`python/security/input-deserialization.md`)

Items 1–5 — PASS：UTF-8 JSON；不使用 pickle／marshal／对象构造；64 KiB 读取上限；重复 key、非有限数字、深层解析错误和未知字段被拒绝；输出转为独立不可变 dataclass 快照。依据 run_contract.py:37–111,114–136。

### Harness：Logging Standards (`common/logging/logging-standards.md`)

Items 1–4 — PASS：事件采用带时间、level、message、run_id context 的 JSON 行；事件字段限制为标识符／相对证据引用，metadata 字段白名单；常见敏感字段名与非有限值被拒绝。依据 run_evidence.py:21–49,65–75,108–139。标识符值本身仍由可信调用方负责脱敏，不能据此宣称任意输入已脱敏。

Item 5 — PASS（API 范围）：run 目录排他创建，contract／manifest／result 使用 `xb`；事件在持有对象内追加且加锁、flush／fsync，finalize 后拒绝继续写；hash 链提供有限完整性材料。依据 run_evidence.py:77–106,127–163。**存储 ACL、外部审计及完整 hash 链验证／尾部锚定尚未实现，不属于本次批准的保障。**

Item 6 — 范围例外：此原语不执行轮转／保留策略。单记录 64 KiB 限制已存在；总 run 大小、保留期限与访问策略由后续可信调度／存储层落实，在该层完成前不得作为无限制日志服务使用。

Item 7 — N/A：本地证据原语不是生产日志服务；CLI 将简短状态输出到 stdout、错误输出到 stderr。

### Harness：Error Handling (`common/error-handling/error-handling-strategy.md`)

Items 1–5 — PASS：契约使用 ContractError／ValueError，文件系统异常上抛，CLI 在边界转换为 exit 2 和无敏感载荷的结构化错误。写入失败不会覆盖原始记录。依据 run_contract.py:15–16,123–136；run_evidence.py:94–106,141–163；tools/v3_session.py:27–43。

Items 6–7 — N/A：本片段不作远程请求或自动恢复，失败由调用方处理，未引入无界重试。

## 片段二：产物检查与结果聚合

### Harness：Input Validation (`common/security/input-validation.md`)

Items 1–4,6–7 — PASS：检查器参数有类型／范围限制；路径拒绝绝对路径、盘符、ADS、点段、保留设备名、尾空格／尾点及控制字符；路径组件检查 reparse／符号链接，文件身份、硬链接、新鲜度、大小及读中变化均检查；异常输出 fail／unknown。依据 artifact_check.py:33–112。边界为调度器独占的 run root，不承诺对恶意同权限竞态的安全隔离。

Item 5 — PASS（声明的文件事实范围）：最大读取 64 MiB，regular file、尺寸／hash／尾标记可校验；未声称按扩展名验证文件格式。对于任意 gcode 完整性，仍需显式完成性预期或专用格式检查，默认 min_size 不能证明未截断。

### Harness：AI Evaluation and Regression (`common/ai/ai-evaluation-and-regression-strategy.md`)

Items 1–5,7 — PASS（底座范围）：完成状态、证据完整、执行合规、恢复留痕、必需检查的结果与证据共同约束 verified_pass；缺项补 unknown，fail 不被平均掉；AI 默认为 shadow，晋级绑定完整契约 digest。依据 run_verdict.py:76–137。挑战测试覆盖缺项、N/A、假布尔、原始模型字典、旧产物、截断和路径逃逸。

Item 6 — 范围例外：模型／提示词升级的 canary 和晋级注册尚未实现；Promotion 仅承载可信注册项，并不能证明审批真实发生。不得把手工构造 Python 对象等同外部批准。

### Harness：Tool Calling and Agent Control (`common/ai/tool-calling-and-agent-control.md`)

Items 1–3,5–7 — PASS（原语范围）：模块说明与接口明确受信调用者、输入、副作用、错误、资源上限及审计输出；不执行 GUI、模型或网络调用。单 writer 约束和外部隔离责任明确，未因提供 append-only API 就宣称 OS 级隔离。依据 run_evidence.py:1–5,58–63；run_verdict.py:1–5,80–85；artifact_check.py:1–5；tools/v3_session.py:1–4。

Item 4 — N/A：该变更没有增加发布、删除、发送消息或实际 agent 工具执行入口；后续暴露工具或接入发布须独立审查。

### Harness：Code Review (`common/code-review/review-checklist.md`)

Items 1–5,7–8 — PASS：按两个片段审查；作者自检与负例测试可核查；标准库实现、无新增依赖；文件读取有上限，契约／结果验证失败关闭。

Item 6 — 有理由的 C 级偏离：artifact_check.check_artifact 与 aggregate_result 超过建议 40 行。接受本次偏离：两者均为单一、顺序化且 fail-closed 的检查流程；条件短路与证据形成放在一处便于审计，当前没有交织 GUI／网络逻辑。后续扩展检查种类时应抽取独立阶段，避免继续增长。

## 已解决事项与剩余风险

集成中已解决并复核：aggregate_result 对完整契约重新验证；contract_digest 与落盘 contract.json 的规范化和尾换行一致。依据 run_verdict.py:37–43,87–98；run_evidence.py:68–69,88,94；跨模块测试 test_promotion_digest_matches_saved_contract_snapshot。未重复列为新发现。

未解决 N／C 代码发现：无。上述调用边界和范围例外不是已实现功能；后续执行器接入、权限隔离、预算执行、轨迹真实性和发布检查均需新增验收，不能从本次原语审查外推。

## 验证与 B6

2026-11-16 执行：`python -B -m pytest unit_tests/test_run_contract.py unit_tests/test_run_evidence.py unit_tests/test_artifact_check.py unit_tests/test_run_verdict.py -q`，103 passed、1 skipped。跳过项为当前 Windows 账户不能创建符号链接；另有模拟 reparse flag 的负例。宿主纯单测不是 GUI 回归证据。

B6 已以官方脚本 `--dry-run` 检查本报告，输出 `No signals detected.`；dev-guidelines 为只读，未向其反馈日志写入。此报告没有未归属发现、误导／覆盖不足标记或已识别的 harness 改进信号。
