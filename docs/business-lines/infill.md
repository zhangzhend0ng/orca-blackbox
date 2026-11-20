# 工艺扩样：稀疏填充 15%→30%

状态：新增内容检查器与纯测试已通过，**尚未执行本业务GUI/模型调用/重开切片**。不是旧m5c、87条回归或发布GREEN的覆盖声明。父任务统一接线、提交与客机执行；本子任务没有启动GUI、VM、relay或模型，也没有修改共享文件、认证或网络配置。

## 目标及固定输入

`CASE_ID=pilot_strength_infill30`，已注册scenario为`pilot_infill`（Others初态）。固定LAYER_FIXTURE的原配置为稀疏填充15%、图案grid、Wall loops 2、常规/初层均0.4 mm。英文GOAL仅要求把密度改成30%，保留其他设置与模型并保存到指定3MF；不提供菜单路线或坐标。

## 检查器接线

`harness/pilot_infill.py`提供`verify_business(project, fixture, gcode, *, cancelled=...)`，成功返回JSON-safe证据摘要。调用方仍须先独立确认输入停止、旧SUT退出、保存字节冻结、fresh profile重开、GUI实际切片及两端清理，内容检查不能代替这些运行时证据。

检查器按顺序要求：

1. 固定fixture SHA256，bounded ZIP/XML/JSON及物理模型检查，层高0.4/初层0.4、对象和位置不变。
2. 3MF中的`sparse_infill_density="30%"`、grid、Wall loops 2。共享`pilot_common.inspect_preserved_settings`只允许这一受信目标变化，其他设置默认严格相同，仅接受既有明确的序列化迁移。
3. G-code实际对象正向XY/E挤出形成68层，首Z0.4、末Z27.2，唯一对象工具0。
4. 唯一CONFIG_BLOCK内部的全部密度回显为30%、图案grid、壁环数2；块外注释、缺失回显、冲突回显不接受。
5. 在对象作用域内的`;TYPE:Sparse infill`区，确实存在已知坐标下的正向XY/E运动。只写TYPE注释、只有E轴回抽/挤出、仅在对象外运动、只有solid infill均不接受。解析跟踪G90/G91、M82/M83、G92 E和工具切换，复用上游层序检查先拒绝不支持的坐标模式。

真实旧G-code的只读核对确认生成器使用`;TYPE:Sparse infill`，不是`FEATURE:`；旧文件回显15%/grid/2，其中可识别1365个稀疏区域正XY/E动作。这仅验证解析器理解既有产物格式，不计新业务实跑覆盖。

## 证据边界

当前证明的是“密度意图进入保存与重切配置，且生成了真实稀疏填充挤出”。**尚未从路径间距或材料体积独立测出30%的几何密度**。返回`physical_density_ratio_verified=false`，不得把该标志改述为独立的30%物理密度验证或实印强度认可。若将旧15%工具路径同时伪造项目配置与G-code回显为30%，该检查器没有独立几何密度oracle识别所有此类伪造；因此必须绑定可信重开重切来源，仍然只准SHADOW。

## Harness与纯测试

实现前读取当前AGENTS、README权威纪律、PITFALLS §15/16、dev-guidelines INDEX与Part A协议，并沿用已加载的tool-calling、input-validation、testing、AI-evaluation及错误传播harness。

| 条件/tier | 动作及结论 |
|---|---|
| 外部字节/N | 固定fixture摘要；复用bounded 3MF/G-code解析；无shell、网络或文件写入：PASS |
| 目标与保留/C | 固定30%唯一目标变化；共享字段审计已由父任务接线，完整正例与反例通过：PASS |
| 注释不能冒充真实动作/C | 对象范围、坐标/E模式、正XY/E三条件，solid/对象外/pure-E反例均通过：PASS |
| AI评估/C | 配置、实际挤出、几何密度分开陈述；不虚报GUI覆盖：PASS |
| 故障/C | 用既有_InvalidEvidence拒绝，无自动改值、吞错或重试：PASS |
| 资源边界/C | 仅新增约定三文件；没有编辑共享HOST_SOURCES：PASS |

测试入口：`python -B -m pytest unit_tests/test_pilot_infill.py -q`。纯测试覆盖M82/M83、两种对象标签、旧/错误参数、无关设置改变、错误/冲突/块外配置回显、无真实稀疏运动、对象外伪造标签与pure-E假动作。它们不计模型或GUI覆盖。

首次纯测试结果8 passed、9 failed；9项均因共享pilot_common尚不允许`{'sparse_infill_density':'30%'}`，属于明确的接线缺口，没有跳过或将失败改成通过。父任务需在现有实跑停止后扩充这一固定允许集，再运行完整测试；本子任务不修改共享文件以避免在活动run期间漂移HOST_SOURCES。

共享接线后最终复测：`python -B -m pytest unit_tests/test_pilot_infill.py -q --tb=short`，**17 passed（0.24s）**；diff whitespace检查通过。原9个接线失败已由父任务精确增加30%允许目标解决，没有修改既有允许值或将失败跳过。本子任务现停止修改，真实GUI试跑仍待父任务执行。
