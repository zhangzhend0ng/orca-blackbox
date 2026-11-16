# v3 最小运行时架构

后续接口扩展：同一 `run_once` 已新增显式 `execution_mode="guest_script"`，首个真实 Script 仅支持客机 m0 bootstrap，仍为 SHADOW、不开放发布；精确接线与验证边界见 [V3_SCRIPT_ADAPTER.md](V3_SCRIPT_ADAPTER.md)。下文保留最初 synthetic 骨架的设计与验收窗口，不能将其未实现项直接当作后续版本现状。

后续 `execution_mode="guest_agent"` 已接入固定 AI 页签任务，codex_chat 与无人值守 codex_cli 均取得真实客机 SHADOW，另有无变化反例 NON_GREEN；当前接口和验证边界见 [V3_AGENT_ADAPTER.md](V3_AGENT_ADAPTER.md) 及 [运行记录](runs/v3-agent-2026-11-16.md)。

状态：2026-11-16，单次 synthetic 运行骨架设计与接口说明；本文不代表 GUI 或发布验收通过。实现验收状态见文末。

本批先把契约、调度、执行、独立验证与收尾接成一条可运行主链，再替换真实执行器。验收使用纯 synthetic adapter，不启动 Orca，不调用模型服务，不新增第三方依赖。交付目标是一套 core runtime + ports，避免继续堆没有调用者的 helper。本批不修 m5，不调整旧 launcher、profile 或 farm_runner。

## 现有能力与本批边界

已读取并复用：

| 现有模块 | 已有能力 | 本批如何连接 |
|---|---|---|
| `run_contract.py` | 不可变 v1 契约、严格字段校验 | 入口加载；不把自然语言 goal 当作可执行权限策略 |
| `run_evidence.py` | 独占创建、追加事件、一次 finalize | 只有 runtime 持有 writer，所有阶段留下事件 |
| `run_verdict.py` | 分项聚合、未知不通过、AI 默认 shadow | 只由 runtime 调用，不暴露给 executor |
| `artifact_check.py` | 文件事实与可选独立预期检查 | verifier 调用；非空不代表切片语义正确 |
| `tools/v3_session.py` | validate / init | 保持兼容，增加显式 synthetic 入口接主链 |

当前 v1 契约没有完整初态、工具权限和路径策略。本批不谎称补齐这些语义；用应用代码注册的、绑定精确契约摘要的 synthetic 定义提供预期和能力。真实 GUI adapter 在注册前仍须完成初态、可信工具采集、宿主门禁及权限约束。当前同进程对象边界没有 Windows ACL 防护，不抵御同权限恶意进程。

## 模块与依赖方向

新增两个核心模块，另加一个 synthetic 组合模块及集成测试；所有生命周期控制集中在 run_once。

```text
tools/v3_session.py  [composition root：显式选择 synthetic]
        |
        +-- synthetic adapter / verifier / 固定注册定义
        |
        v
harness/runtime.py  [唯一 run_once 生命周期]
        +-- runtime_ports.py  [DTO / Protocol，无 GUI 导入]
        +-- run_contract / run_evidence / run_verdict

verifier adapter --> artifact_check
未来 Script / MCP / Midscene adapters --> runtime_ports
```

runtime 不导入具体 adapter、GUI 工具或厂商 SDK；adapter 不依赖 runtime 实现，也不持有 writer、聚合函数或晋级注册表。注册表由应用代码构造并注入，不从契约文本动态 import、执行文件或加载模型插件。第一版只注册 synthetic 实现；预留三种 executor key 不等于三种真实接入已完成。

## 精确端口

以下对应本批 `runtime_ports.py` / `runtime.py` 接口。DTO 为 frozen dataclass；它不自动使嵌套 mapping 深度不可变，也不提供 ACL 隔离。

```python
class CleanupHandle(Protocol):
    def poll(self) -> Pending | Done: ...

class OperationHandle(Protocol):
    def poll(self) -> Pending | Done: ...  # Done 表示本操作已停止读写
    def cancel(self, reason: str) -> None: ...  # 发出取消请求，不等于已停止
    def start_cleanup(self) -> CleanupHandle: ...

class ExecutorPort(Protocol):
    synthetic: bool
    kind: str
    def start(self, context: ExecutionContext) -> OperationHandle: ...

class VerifierPort(Protocol):
    synthetic: bool
    def start(self, snapshot: VerificationSnapshot) -> OperationHandle: ...

def run_once(contract, executor, verifier_registry, *, root,
             desktop_id="synthetic", run_id=None,
             verify_timeout_s=30, cleanup_timeout_s=10,
             clock=time.monotonic, sleep=time.sleep,
             cancelled=lambda: False) -> dict: ...
```

`Done.value` 依次承载 ExecutionOutcome、VerificationOutcome 或 CleanupOutcome，由 runtime 校验类型。端口的 start/poll/cancel/start_cleanup 都必须短时返回；真实阻塞 I/O 将来放在 adapter 管理的可终止进程或受控异步工作中，不能把任意同步 execute 包上计时器就称为可取消。首版只验证合作式 fake handle；Python 主线程无法强制中止违反端口契约的函数，这不是已解决的硬隔离能力。

| DTO | 必要字段与约束 |
|---|---|
| 注入的 executor 与 verifier_registry | executor.kind 匹配契约；registry 按精确 contract digest 选独立 verifier；两者均须 synthetic=True。固定预期由 verifier 自己持有；不允许缺 verifier 时退回执行器自判 |
| `ExecutionContext` | run_id、冻结 contract、独占 artifact_dir；没有 writer、结果或基线写入口 |
| `ExecutionOutcome` | status；不含 CheckResult 或 GREEN。Handle 返回 Done 即承诺其工作已停止读写；未停止不得 Done |
| `VerificationSnapshot` | run_id、contract、artifact_dir、manifest、execution；execution 仅作诊断上下文，独立预期来自受信 verifier 注册，不以执行器状态作为 oracle |
| `VerificationOutcome` | 独立 `Mapping[str, CheckResult]`、evidence_complete、execution_compliant；后者只能收紧合规性，不能覆盖 runtime 超时或失败 |
| `CleanupOutcome` | confirmed；仅当执行和验证都静止且清理完成才为 true。错误与执行失败分别保存 |
| 返回 dict | 扁平 dict：run_id、run_dir、manifest_path、result_path，以及聚合事实、runtime_status、cleanup_confirmed、`mode=synthetic`、`gui_executed=False`、`release_eligible=False`、`release_verdict=SYNTHETIC` |

定义不匹配 executor 或摘要时，拒绝启动，不猜测兼容版本。第一版不接受 Promotion，不接发布。即使现有 aggregate_result 对 script 分支得出 GREEN，runtime 只提取其验证事实与 reasons；synthetic 的最终 envelope 不包含可被消费为发布 GREEN 的字段值。

## 单次运行主链

1. 验证契约和注册定义，冻结依赖；失败返回入口错误，不调用 adapter。
2. 独占获取 desktop lease；锁冲突在创建 run 前直接失败，绝不调用 executor 或清理别人的会话。
3. 创建 RunEvidence 和本 run 的 artifacts 目录，记录 `runtime_started`。调用 executor.start；start 部分失败且没有 handle 时不能确认副作用已清理，保留隔离锁。
4. 循环 poll，检查取消和单调时钟 deadline。本批无真实动作或模型调用，不实现动作／费用计量与自动重试；契约中的这些限制保留，但不能声称已由调度器强制。真实工具层接入前须补齐执行前预算检查。
5. 仅执行 Done(completed) 后构造 VerificationSnapshot，启动独立 verifier。其他 execution 状态跳过验证，必需项 unknown；验证通过不能抹掉执行失败。
6. 验证完成、失败或超时后，逆序清理 verifier、executor 的 handle，并限时 poll。保留先前执行错误；cleanup 失败不能覆盖原错，也不能留下可通过的运行。
7. 构造独立 checks 和 runtime 合规／完整性标志，调用 aggregate_result，一次性 finalize synthetic envelope，关闭 writer。
8. 当前实现采取保守释放条件：工作均静止、cleanup confirmed、finalize/close 成功且无待抛异常才释放 lease。其余保留隔离锁；结果只陈述 cleanup_confirmed，不预先声称锁已释放。锁删除失败直接报错，不重写已保存结果。

执行超时或用户取消后请求 cancel，随后通过 cleanup 的确认来判定所有工作是否停止；不并行启动 verifier。verifier 超时也请求取消；cleanup 不得与仍在读写的 verifier 竞争，无法确认停止时隔离资源并结束为非通过。CleanupHandle 没有取消接口，超时后保留锁，不无限等待或假装工作已终止。持久化失败使运行不完整，返回错误，不补写虚构结果。

从 executor.start 前计算 case_deadline，执行与验证共用契约 timeout。验证 deadline 取 case 剩余预算与 verify_timeout_s 的较小值；每个 cleanup 单独使用 cleanup_timeout_s。上限为 case 预算＋至多两个 cleanup 预算，另加须立即返回的端口和本地记录调用开销。单调 deadline 不随 poll 重置；这不是统一的全局 campaign 预算。clock/sleep 与取消谓词可注入，使 fake clock 验收不靠长时间真实等待。

## 桌面排他与失败状态

desktop_id 来自可信部署定义，代表具体 VM + 交互会话，不来自模型或随意的 case_id。所有协调进程必须使用同一 canonical root；锁位于 root/.desktop_locks，以 desktop_id 摘要命名、独占创建并写入 run_id。不同 root 不共享锁，本批不声称跨任意配置的全局排他。锁文件不是 ACL 或租约超时保证。

不按文件年龄、PID 相同或 deadline 到期自动抢锁。崩溃残留及未停止的工作保持隔离，后续需确认桌面、进程和输出状态后由外部恢复流程释放。释放前再次核对锁内 run_id，不删除其他运行的锁。适配器抛错时，即使 cleanup 成功也保留隔离锁，等待人工确认。不同 desktop_id 可独立运行，但本批不构建 VM 农场。

| 情况 | execution / checks / 对外结果 |
|---|---|
| 缺注册、摘要错误 | 入口错误，未启动，无通过结果 |
| 锁冲突 | 创建 run 前报错，adapter 未启动，没有新结果 |
| 完成且检查通过 | completed，synthetic 验证通过，仍非 GUI/发布 |
| 执行器抛错 | failed，保留原错代码，尝试有界清理 |
| 执行超时／取消 | timeout / cancelled；恢复或清理成功不改成 completed |
| verifier 抛错／超时／缺项 | 对应检查 unknown，完整性 false；不能通过 |
| cleanup 不干净／未静止 | 保留原 execution，合规 false，隔离锁，整体非通过 |
| 证据写入失败 | 运行记录 incomplete，错误退出；不重开旧 run 改写结果 |

## 证据归属与独立判断

RunEvidence.append_event 目前只支持受控标识与相对引用；runtime 不往事件中塞任意异常文本或模型输出。结果包含独立 verifier 报告与运行阶段状态，所有事件在 finalize 前写完。需要结构化 payload 时由可信采集端先写本 run 内不可覆盖文件再引用，不扩展为任意 agent 写文件接口。

synthetic executor 可以制造夹具或故障，verifier 独立读取固定预期与实际文件；检查器不能复用 executor 返回的“实际期望值”。首版仅有 synthetic 事件，不把它当作真实 GUI 路径证据。未来 GUI 接入须由可信工具适配层采集前后状态、目标身份和产物事实，不能仅凭 agent 自报认定点击成功。

失败证据、首次结果和隔离状态都不可覆盖。诊断与修复不在本轮 runtime 中执行；后续候选用新 run_id 重放，不能重新打开旧 writer finalize。manifest 的既有 metadata 白名单保持兼容，额外运行字段放最终 envelope 或受控事件。

## 本批验收与下批接入门槛

synthetic 集成验收通过真实 run_once 主链验证，覆盖目标如下；未纳入自动化的剩余场景在审阅报告中单列：

- happy path：独立夹具检查通过，events/manifest/result 完整，cleanup 执行，锁释放；最终明确 non-GUI/non-release。
- 伪成功：executor completed，但夹具错误、文件缺失或路径记录不足，verifier fail/unknown，整体不通过。
- 执行异常、取消、超时：保留首错，cancel 有界，cleanup 被调用；假时钟验证不会无限循环。
- verifier 异常／超时、cleanup 失败／超时：不误报成功；未静止时保留隔离锁，下一 run blocked。
- 同 desktop_id 跨实例排他、不同 key 不冲突；锁冲突不调用 executor。
- 契约摘要不匹配或缺 verifier 时拒绝启动；执行器无结果写入口；重复 finalize 被拒绝。
- 同目录产物、旧文件、独立预期不匹配分别失败；synthetic 验证不能写成 GUI GREEN。

2026-11-16 集成结果：协调者最终执行 `python -B -m pytest unit_tests -q -rs`，153 passed、1 skipped（宿主缺 symlink 权限），其中包括补充的启动耗时与验证共享整体预算反例；`python -B tools/v3_session.py smoke` 成功，run_id 为 `826a28804b7d4d27aeb662802cf7b215`。架构审阅独立读取了该 run 的 result.json 与事件链：执行、验证、两次清理及收尾均有记录，结果为 SYNTHETIC、gui_executed=false、release_eligible=false。独立审阅时的测试快照为补充两项前的 151 passed／1 skipped，未改写为审阅者未执行过的数量。

本批完成标准是“一个命令走完可审计的 synthetic 纵向闭环”，不是任一真实 GUI case 通过。下批首先接一个 Script adapter 经 win11-test / hv_go 验证生命周期，再接 MCP 和 Midscene；实际输入、工具预算、进程停止及独立路径验证未证明前不开放真实 agent。不得用宿主 fake 测试代替 Hyper-V GUI 回归证据。

## Harness 自检

设计前已加载 harness-driven-review、tool-calling-and-agent-control、risk-and-verification-plan，并沿用 AI evaluation 检查；requirements-gap-analysis 用于限制缺口陈述范围。

- (C) 工具权限与副作用：端口分开、显式注册、无任意插件；动作／费用预算留待真实工具层接入验收；ACL 隔离尚未实现，已限定为可信 synthetic adapter。
- (C) 状态／循环：单调 deadline、取消不是完成、cleanup 独立限时、未静止隔离、跨运行桌面锁。
- (C) 独立验证与证据：executor 不产出检查结论，检查来源绑定契约，首次错误与结果不可覆盖。
- (C) 风险与验收：列出具体集成反例与实际结果；真实 GUI、MCP/Midscene 接入仍为 NOT VERIFIED，未把 synthetic 作为 GUI 或发布证据。
- (A) 取舍：用统一 Handle 而非阻塞 execute；首版不建立通用插件系统、农场、自动修复或全量权限 schema，以单一调用链验证架构。

设计及实现审阅见 `docs/reviews/v3-runtime-2026-11-16.md`。本批已形成可运行 synthetic 骨架；模型执行器、真实 GUI 与发布集成尚未接入。
