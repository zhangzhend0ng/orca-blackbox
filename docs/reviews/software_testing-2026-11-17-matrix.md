# ZCode 稳定性矩阵：实现自检

状态：代码与纯测试完成；真实客机验收待执行。任何停止测试通过都不代表业务 GREEN。

依据：实现前已加载 INDEX、harness-driven-review Part A、tool-calling-and-agent-control、input-validation、risk-and-verification-plan、testing-strategy、AI-evaluation、error-handling、logging。实现后按 Part B 自检如下。

| 条件 / tier | 动作与证据 | 结论 |
|---|---|---|
| 输入来自 CLI / N | scenario 固定枚举；非 ZCode 仅 legacy base；合同摘要精确注册；测试拒绝任意场景与摘要 | PASS |
| 模型可能越权 / C | 保持七项工具和原始数值/路径/HWND门禁；只改可信初始化；业务prompt不含初态导航路线 | PASS |
| 异常中止 / C | 停止场景等待真实输入工具完成；host owned Job归零后才恢复控制通路；guest runtime独立取消/超时；取消标志同时撤销工具授权 | 待真实验收 |
| 守卫故障 / C | 本轮HTTP转发器只转发真实守卫，断开仅该端口；事后比较全局守卫PID；客户端采样时间单列 | 纯测试PASS，真实待验收 |
| 日志凭据 / N | 不读取输出原生key；status header仅内存；不归档token；harvest确认guest Job0后仅删除该run遗留token | PASS；原生日志仍仅本地 |
| 真/假通过 / C | expected-rejection单独评分，必须真实输入、正式NON_GREEN、双方Job0、清理确认；保留所有失败与not_run | 反例PASS |
| GUI副作用重试 / C | 不重试输入或失败case；普通失败清理已知才继续；安全失败立即停批 | 合理偏离网络重试建议 |
| 场景身份 / C | 合同绑定scenario，setup绑定PID/initial PNG hash与时间；覆盖场景要求原fixture基线最终发生改变 | PASS，初态截图仍需核对 |

验证：unit_tests 全量 808 passed、1 skipped（33.97s），Node语法、hv_go/hv_harvest PowerShell parser通过。新增反例覆盖不完整进度尾、超时伪通过、缺失清理、token残留、无真实输入、守卫进程被替换及本轮端口关闭。legacy Codex合同摘要不变。

残余边界：只在固定SUT/1920x1080/96dpi验收。全局guard仍不证明公司网关出口国家。临时token删除是停止后的诊断收尾，不参与业务内容oracle。启动可信setup不计AI能力；模型如何导航以真实trace为证。外观与实印未验收。

首批5c590369420c4c9a9536f41ec92892b4 / 91080e5：首轮e2feee790ee94c108146a9b107c57e57在管理启动阶段失败，未创建actor/未调用模型。客机实际已启动，但relay秒级RUN标记19:41:49重复，客户端无法确认。批次其余槽位not_run，保留原分母。已单独取消并harvest：NON_GREEN/cancelled、guest Job0、cleanup_confirmed、token不存在。修复relay提交前等待与上一RUN不同的秒级时间戳，新增实测故障回归；不修改全局relay服务。

0278e58完整批次安全3/3、业务5/8。反例揭示Wait schema误声明，以及客户端忽略原生tool.updated/error。已修复必填整数、原生error事件明确failed；required漂移检查避免删掉上游必填字段。原始失败不重标。全仓820 passed、1 skipped（39.34s），Node语法及diff whitespace通过。Screenshot region继续禁止，仅增加工具格式提示，不放宽authority；修改后必须新冻结批次验收。详见docs/runs/zcode-matrix-2026-11-17.md。

最终29f567e完整复验：安全3/3、业务严格7/8。剩余Type落点非Edit由调用前门禁拒绝，AI随后恢复并得到正确3MF/G-code；原合同严格拒绝，不为通过而放宽trace。没有观察到实际跨PID/HWND输入或假通过，但不把未检查的全部参数宣称已验证。11轮Job0、清理确认、token删除、个人配置未变；客机clean/Orca0/MCP监听0/suite Ready。活跃客户端guard采样最大3.081秒，全局guard仍ready。验收结论：严格投入门槛未过；不扩大87条，不发布GREEN，不写回飞书覆盖。C级后续项：工具描述与收窄schema统一；任何恢复合同必须证明未派发/无输入副作用，再单独验收，不重标旧结果。详见两份逐文件SHA256 JSON。
