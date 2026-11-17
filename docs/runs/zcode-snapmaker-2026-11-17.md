# ZCode / Snapmaker Flash：真实 GUI demo

2026-11-17 已通过一次完整独立验证，结果 **SHADOW**、verified_pass=true、cleanup_confirmed=true、release_eligible=false。使用用户指定的 ZCode `Snapmaker` 供应商 `new-provider / glm-5.3-flash`，没有改用个人 ChatGPT 额度或 BigModel 编程套餐。

## 成功轮次

- run：`4ba6b094412d435398826502d94f69e9`。
- 冻结源码：`02a6201a62c7a4522df25518c02840217472383d`。
- 原生ZCode CLI 0.17.1，bundle SHA256：`d9afd58d694f98a5279bf548cdc7646413c125762e86730605a6071f9e0346d6`。
- SUT SHA256：`5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`；Windows-MCP 0.8.9，客机 `win11-test`。
- 客机整轮约239.72秒；原生MCP调用16次，客机trace无调用错误，17条模型请求收据均绑定指定provider/model及恰好七项GUI工具。原生模型请求日志含图像消息，确认不是只有最终文字摘要。

AI收到业务目标、合法工具说明和本run的保存位置，没有预设坐标或点击步骤。它自行看图定位，输入常规层高0.24、初层0.4；先尝试Ctrl+S遇到应用的保存失败提示，再自行关闭提示并改用Ctrl+Shift+S另存，输入完整目标路径，检查标题与字段后释放控制。这里是实际观察到的GUI内恢复，不是框架自动动作重放；runtime的recovery_used=false只描述框架恢复计数。

停止原生输入和MCP后，旧Orca自然exit0；可信阶段冻结AI保存的同一3MF，用新profile重开该副本并GUI切片导出。独立只读检查确认模型几何不变、常规层高0.24、初层0.40、实际112层、末Z27.04。重开进程自然exit0，host/guest Job均active=0，forced_termination=false。visual检查仍为unknown；没有实物打印或外观验收。

3MF SHA256：`b81ce91248e8bbd43d9e7636898c6e400c11b7d1a2f7a7195247b337e420b9c3`。

G-code SHA256：`87751eb525b39c5b13ddaced9690c6b3b47b49eecc2ca52243bec2528dda63a0`。

## 所有真实启动均保留

| 轮次 / run前缀 | 源码 | 结果 | 原因 |
|---|---|---|---|
| 1 / 77cf7e8e | 27a55ca | NON_GREEN | 客户端误按HTTPS校验用户已有HTTP网关；无模型请求/GUI输入 |
| 2 / 2ac0a1c3 | e879187 | NON_GREEN | 原生会话模型初始化缺reasoning选项；无业务模型请求/GUI输入 |
| 3 / 5efb10ab | 0ed9f78 | NON_GREEN | 客户端会话ID字段错误；无业务模型请求/GUI输入 |
| 4 / 3464272d | cea30fe | NON_GREEN | 九次调用中三个Click坐标为字符串，被整数数组门禁拒绝；模型未完成保存 |
| 5 / d5f41d1f | f394ea3 | NON_GREEN | Windows进度文件替换与读取竞争；模型请求被取消，无GUI输入 |
| 6 / 4ba6b094 | 02a6201 | SHADOW | 完整业务证明通过 |

每次都在定位原因、修改并验证后换新run，没有把原结果重新标为通过。六个真实启动中五个NON_GREEN、一个SHADOW；不能从不同修订的开发样本推导稳定成功率。纯文本探针及两个静态MCP传输夹具另外记录，不计GUI分母。各轮完整ID、原始结果与文件hash见[机器索引](zcode-snapmaker-2026-11-17.json)。

## 配置、额度及守卫

沿用ZCode现有 `http://ai-gateway.s.com/v1` / Anthropic配置，由原生运行时读取现有Key。每个会话明确选择Snapmaker Flash及low推理，不修改全局默认，不导出Key或复制认证。成功轮次三份个人配置前后hash一致。

成功轮次原生usage汇总：inputTokens=258019、cacheReadTokens=233920、outputTokens=1258、totalTokens=259277。缓存读计数不再重复加到input；这些是网关返回的token收据，不是美元或公司内部计费结论。失败与传输探针也可能消耗额度，原始记录保留，未将其记成零成本。用户改为指定Snapmaker后，早先启动的BigModel官方CLI授权进程已停止；未取得该授权成功结果。

本轮保存45份守卫检查收据，全部通过ready与新鲜度校验；启动和模型运行中均检查，目标轮询间隔3秒。本次未实测运行中撤销，也未保存客户端采样时间以认证硬性的≤5秒时限；收据time是守卫发布快照的时刻。既有守卫探测OpenAI分组，**不证明Snapmaker网关同样使用美国出口**。没有修改Clash规则或守卫配置。

## 收尾与复跑

harvest后的客机复核：源码仍为成功轮次冻结提交且clean、Orca进程0、suite Ready、本轮临时MCP token已删除。宿主原有launcher/profile/farm_runner/draft改动保留。仅提交代码、文档与证据索引；大产物在本地artifacts中，不写入飞书GREEN基线。

入口：`python -B tools/native_save_demo.py --actor zcode`。要求提权relay、客机与宿主同一已提交HEAD、已安装原版运行时及空闲桌面。省略actor仍是历史Codex入口；本路线明确传zcode，不隐式回退供应商。

证据位置：`artifacts/native_save_demo/<run>/summary.json`、`artifacts/windows_mcp_host/<run>/`、`artifacts/windows_mcp_harvest/<run>/`。后者含原始3MF、冻结副本、G-code、截图、trace及进程/合同/结果收据；不含认证原文。

schema修复后的全仓单测796 passed、1 skipped；最后的进度记录修复受影响协议测试29 passed。静态传输夹具验证了真实ZCode/公司模型的工具调用和类型；真实业务只有本页列出的成功轮次。三种初态各两次加两个干扰的八次矩阵、真实取消与跨版本稳定性仍未完成。本结果只证明接入可行，不代表87条回归或发布GREEN。
