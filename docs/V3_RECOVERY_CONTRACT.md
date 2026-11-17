# 有限恢复合同与 fatal 输入熔断

2026-11-18。本文件定义新恢复能力，不改写旧合同含义。本模块只提供纯协议与审计；guest持久熔断、原生Agent连接及实际GUI验收由root统一接线。本轮不操作GUI/VM/relay/模型，不改既有server/driver/session，不提交。

## 已知事故与首要约束

infill run `0b338e3f5925485b89d82c9200205078` 的guest trace在seq4记录`native_target_not_owned`，seq7起多次`native_foreground_not_owned`，但actor仍以无error完成33calls。原生工具错误可能被包装成普通内容，不能仅凭native事件状态或`isError`决定是否安全继续。原NON_GREEN证据不改写。

**guest authority是停输权威。** 任意fatal拒绝，先持久写本run的authority_abort/input_revoked，再向模型返回结果；后续任何输入立即拒绝，worker不得继续独立proof。持久写失败也必须停MCP/worker并留失败，不能因为native Agent还在运行而继续派发。内存RecoveryGate不能代替跨进程持久标志。

## 最小恢复白名单

只有新注册合同（建议 `recovery_owned_edit`）显式启用；默认legacy `enabled=False`，任何拒绝都fatal。恢复不扩大工具权限：只容许模型重新观察并在原有权限内自主选择下一步。

恢复必须同时满足：

- tool为Type，code精确为`native_type_requires_owned_edit`；
- `dispatched`严格为False，原版工具尚未被调用，绝非超时后猜测未执行；
- text为有界纯数字（0..999.9999，无符号/指数/换行/任意文本），并已通过该场景自己的原权限校验；本模块数字格式仅辨认安全拒绝，不授予新数值范围；
- 可信guard证据显示app_pid/foreground_pid/target_pid均为相同正整数，foreground/target HWND有效，target_class明确非Edit；
- 本run未fatal，未等待前次拒绝后的新观察，恢复次数小于2。

不扩展Wait、参数格式、路径、未知错误或其他拒绝。foreign HWND、foreground丢失、身份/desktop/session改变、撤销、超预算、未知工具、已派发异常、传输结果不明全部fatal。错误不能通过改写error_code重分类；window/arguments证据必须由可信guard采集，不能引用模型自报字段。

## 纯 API

```python
gate = RecoveryGate(run_id, enabled=False)
receipt = gate.reject(row)
gate.before_input()
gate.observed(seq)
summary = gate.audit_state()
summary = audit_trace(trace, run_id, enabled=False)
```

拒绝row包含`run_id,seq,tool,error_code,dispatched`；候选恢复还要求`arguments.text`及`window={app_pid,foreground_pid,target_pid,foreground_hwnd,target_hwnd,target_class,...}`。`reject`输出`protocol=native-recovery-1/run_id/seq/tool/error_code/dispatch_state/decision/requires_observation/budget_used/facts_sha256`，摘要绑定拒绝事实，不能给另一次调用套用receipt。多余窗口事实也参与摘要。拒绝序号必须递增。

`decision`只有recoverable/fatal。fatal永久保持；未知、缺失或格式错误导致`RecoveryViolation`并永久标fatal。调用层捕获该异常时也必须持久熔断，而不是仅转成工具错误文本。

输入前调用`before_input()`；若仍等待新观察或已fatal，它会标fatal并抛异常。只有成功完成的新Screenshot/Snapshot才调用`observed(seq)`；旧seq、未知观察或fatal后观察都拒绝。Wait、旧截图、native完成文字不解锁。除观察门禁外不指定动作路线、不生成下一动作、不重启turn、不自动重试原调用。

每次拒绝都占原40次工具预算与原总deadline，最多两次恢复，不重置预算。root还须保留取消/输入串行化与权限检查；观察成功不能覆盖新的foreign HWND或撤销。

## 新协议轨迹与独立审计

`audit_trace`只读最多40条连续seq记录。每条必须有run_id/tool/error/dispatched；成功行要求error=None、dispatched=True，无error_code或recovery；拒绝行要求具体error、error_code及完全匹配的recovery receipt。审计独立重建计数/观察门禁，任何fatal、未知工具、缺receipt、改事实摘要、缺新观察、末尾恢复悬空均失败。

成功返回`protocol/recoveries/first_attempt_success/recovery_complete`；不返回GREEN。完整业务通过仍要求原有停输、自然退出、冻结原文件、fresh profile可信重开、真实切片产物与独立oracle。原始错误永不删除：恢复后成功与首次成功分开计数，人工救援不算自主恢复，原始分母不缩减。

旧合同不自动接入宽松规则；新合同版本/能力摘要明确记录恢复开关和2次限额。原有历史记录缺新字段时不能默认补成成功。

## 可信结果传递（root负责）

guest每call返回独立`native-authority-1` envelope，包含completed/recoverable/fatal、run/seq/tool/dispatched及recovery子receipt；bridge将权威envelope在转发结果给Agent前完整追加到宿主sidecar，driver不依赖工具错误文本。

必须关联调用：建议记录出站JSON-RPC id、调用序号和规范化参数摘要，关联native toolCallId；仅同名工具的完成顺序不能辨别重复Type。若采用顺序关联，应机械拒绝多调用同时未完成，不猜并行结果。半行、缺失、重复、乱序、错run/tool、dispatched不一致均fail closed。call_next返回不代表工具成功，真实结果isError/error状态仍须检查。

guest持久熔断不等待driver消费sidecar；driver层是补充防线。worker在任何authority_abort存在时禁止proof。恢复只让原生同一次ZCode turn继续，turn.failed不应被壳重新发起另一次turn洗成成功。

## 验证与验收门槛

纯测试命令：`python -B -m pytest unit_tests/test_native_recovery.py -q`。结果：**49 passed in 0.17s**（2026-11-18，纯合成证据，无GUI/模型）。

覆盖有证据的owned数字预派发拒绝、默认无恢复、所有其他错误fatal、已派发/未知派发、foreign身份、缺证据/非数字、2次限额、第三次拒绝、未观察再输入、Wait不解锁、旧观察、receipt/seq/run/事实篡改、未知成功工具、悬空恢复和坏schema持久内存fatal。

GUI验收仍待执行：相同现有业务目标中，一次可信预派发拒绝后由原生Agent自行取得新观察并完成独立业务proof；另外fatal注入必须立即停输，后续输入和proof均被禁止。注入本身不算AI成功，纯测试不计GUI覆盖。若协议不能可靠传回给原生循环，先保留fatal，不扩白名单掩盖问题。

Harness：已加载input-validation、tool-calling、error-handling、risk-verification及AI-evaluation。 (N) 类型/范围与闭合白名单；(C) fatal不可恢复、完整错误证据、预算不重置、独立审计；(C) 正/反例与真实GUI边界明确。持久熔断、Win32身份采集和native envelope接线尚不由本纯模块证明。
