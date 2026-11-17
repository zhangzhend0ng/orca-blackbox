# 三业务线并行开发与受控试验自检

用户最新授权并行尝试其他业务线；此处是三个新SHADOW pilot，不是旧层高8/8门槛豁免或87条全量放行。三子agent分别独占模块/测试/说明，root做文件交叉审查、公共接线、统一提交及客机串行执行。未让多个agent抢同一桌面或relay。

实现前加载INDEX、harness-driven-review Part A以及tool-calling、input-validation、risk/verification、testing-strategy、AI-evaluation、error-handling、logging；提交前依Part B自检。

| 条件/tier | 动作 | 结论 |
|---|---|---|
| 外部选择case/checker / N | native_pilots只映射三个固定模块；合同绑定case/goal/version；native_spec精确digest注册，修改case或host合同拒绝；native runtime保留exact executor/verifier类型 | PASS |
| 业务扩大导致权限变更 / C | 保持七工具、数值/精确保存路径、owned HWND/PID、40动作/900秒/零重试；三目标无需新快捷键、任意输入路径或Shell | PASS |
| 工具说明与schema冲突 / C | 七项description统一为收窄能力；原版MCP包与参数门禁不变；旧业务一轮真实回归待验 | 纯测试PASS，GUI待验 |
| 独立结果 / C | 停输/自然退出/冻结原字节/新profile重开切片的共同证据链不变；每线独立检查3MF与实际对象挤出；AI不能写pass | 纯正反例PASS，GUI待验 |
| 参数保持 / N/C | pilot_common逐项核对578项fixture设置；仅已审核的序列化等价和wall_loops2→3白名单；未知新增/缺失/值改变拒绝 | PASS |
| 模型平移 / C | 预期从固定fixture数学推导；源码确认Prepare移动build但assemble保持原值；检查实际对象XY范围与跨度 | 内容反例PASS，GUI待验 |
| 材料槽映射 / C | 只证明逻辑slot2和实际对象T1，不将filament_maps全1当物理喷头证据；板级仅严格检查两项映射 | 限定范围PASS |
| 壁环数 / C | 保存wall_loops3、Gcode CONFIG_BLOCK回显3和真实68层挤出；不宣称独立物理墙线计数 | 限定范围PASS |
| 密钥/日志 / N | 公司原生配置只通过现有路径供ZCode读取；凭据不复制/打印/入库；原始私有模型日志留本地；受限参数trace不接受任意文本 | PASS |
| 并发 / C | 文件所有权分工后由root交叉审查提取共享helper，三agent停止修改再全量测试；GUI唯一客机串行，批次按冻结HEAD | PASS；GUI待验 |
| 证据诚实 / C | 旧matrix7/8与全部失败不重标；新pilots独立分母，未执行槽位not_run；越界身份或未知清理立即停批 | PASS |

全量纯测试896 passed、1 skipped（40.58s）；受影响pilot/合同/来源包装测试76 passed；Node语法、hv_go PowerShell parser和diff whitespace通过。纯测试不计GUI覆盖。上述表中的GUI待验在真实run后另行追加，不能提前写通过。

C级范围限制：pilot共同配置比较不声称对任意新SUT版本自动兼容；模型变换XY只验证固定cube范围/跨度；材料不证明物理硬件路由或实印；壁环数不证明逐层物理轮廓数；板级非映射工艺覆盖未全面审核。允许作为用户已授权的受控探索，不满足发布GREEN。未引入外部依赖/认证变更/上游源码修改。
