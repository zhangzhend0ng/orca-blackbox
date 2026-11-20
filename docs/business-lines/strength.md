# 工艺业务试点：Wall loops

最新root试跑（cc2ae83）：真实SHADOW：壁环数3保存、独立重开和实际68层切片通过。run `74d5b3e9f21545af8dc4856e29566571`；见[完整记录](../runs/zcode-business-pilots-2026-11-17.md)。

以下保留子agent初始交付记录，其中NOT VERIFIED/尚未GUI描述交付当时状态，最新实际状态以上述run为准。

状态：只读业务oracle与纯反例验证已实现，**GUI、模型调用、重开切片尚未验证**。不是原m5c稀疏填充用例的覆盖或GREEN。父任务负责提交、共享接线和唯一客机执行，本子任务没有操作GUI/relay/VM或认证。

目标：固定27 mm cube的Wall loops从2改成3；常规层高0.4、初层0.4、形状、位置、材料与其他设置保持。AI只收到目标和保存路径，自主选择GUI路线。CASE_ID为`pilot_strength_wallloops`，预期scenario为`pilot_strength`，Quality初态，原始夹具SHA256固定。

## 接线

`harness/pilot_strength.py`导出CASE_ID、GOAL和`verify_business(project, fixture, gcode, *, cancelled=...)`，返回JSON-safe证据摘要，拒绝时使用既有`_InvalidEvidence`。由既有NativeSaveVerifier在全部输入停止、旧SUT退出、保存字节冻结、新profile重开和GUI切片导出之后调用。模块本身不证明GUI路径、进程身份、时序或cleanup；这些不能由内容检查成功替代。

检查顺序：固定fixture身份 → bounded 3MF结构、无对象覆盖、相同物理模型 → 保存的wall_loops字符串3 → fixture其他字段逐项语义一致 → G-code实际对象正向XY/E挤出、常规/初层0.4、68层/末Z27.2、对象工具0 → 唯一CONFIG_BLOCK中的所有wall_loops回显为3。单独伪造配置注释、旧切片、缺失实际挤出、冲突回显均拒绝。

这证明目标配置进入已重切产物，**不宣称独立重建并数出了每层三条物理壁线**；返回`physical_wall_count_verified=false`。壁线物理计数需要额外的路径拓扑oracle，实印强度也未验证。

## 已知序列化等价

原fixture含578项设置，已观测冻结2.4.0 SUT保存586项。除wall_loops外，默认要求原值严格相同；仅允许明确列出的速度/加速度字段scalar变为等值singleton list、固定`(fixture.3mf)`预设别名、首个filament ID从原值变空、版本2.3.6→2.4.0、`different_settings_to_system`增加wall_loops，以及8个固定新增默认字段。未知设置、新默认值改变、额外工艺变化均拒绝。该白名单来自已保存文件的只读观察，没有按本试点未执行的GUI结果调整。

主agent可将`_same_settings`提取到共享pilot_common；本子任务没有修改共享oracle，也没有用AI输出本身当新预期值。真实保存若出现白名单外迁移，应保留NON_GREEN后定位，不能自动扩大允许集。

## Harness自检

实现前加载INDEX、harness-driven-review、tool-calling、input-validation、testing-strategy、AI-evaluation；错误传播沿用既有异常策略。

| 条件/tier | 动作 | 状态 |
|---|---|---|
| 外部产物/N | 固定fixture摘要、复用bounded ZIP/XML/JSON和G-code解析；无shell、无写文件 | PASS |
| 允许目标改变/N/C | 仅wall_loops2→3，其余字段默认严格一致，迁移有固定白名单 | PASS |
| 真实证据/C | 配置只在CONFIG_BLOCK接受，要求实际对象挤出和正确层序；不把echo当物理墙计数 | PASS（内容层） |
| AI评估/C | 不提供导航/坐标；反例与GUI结果分账，未执行GUI不写GREEN | PASS |
| 错误/C | 安全错误码上抛给统一verifier，无吞错/自动修复/重试 | PASS |
| 运行权限/C | 子任务未启动工具会话或VM，不触碰provider/guard设置 | PASS |

纯测试命令：`python -B -m pytest unit_tests/test_pilot_strength.py -q`。反例涵盖旧Wall loops、错误类型、无关配置篡改、错误新增默认、错层高、遗漏/冲突/块外G-code回显、无实际挤出、错误fixture身份。测试分类为本地文件fixture集成型，不计模型/GUI覆盖。本子任务最终结果为16 passed（0.23s）；diff whitespace检查通过。父任务提取共享helper后需再次跑受影响测试。

依据：旧`tests/engine/m5c_strength_infill.py`明确Strength页首行是Wall loops；它的正式业务目标是稀疏填充，不能把新Wall loops试点冒称完成该旧case。已有真实G-code只读核对可见`wall_loops = 2`，因此该字段确实由当前生成器回显；本子任务没有运行wall_loops3的新切片。
