# 模型编辑试点：全局 X 正向平移 10mm

最新root试跑（cc2ae83）：NON_GREEN：Type数值范围及原生Edit限定阻塞，40动作预算耗尽；后续执行入口已预检阻塞。run `cf9b252849044022822255bfc5627820`；见[完整记录](../runs/zcode-business-pilots-2026-11-17.md)。

以下保留子agent初始交付记录，其中NOT VERIFIED/尚未GUI描述交付当时状态，最新实际状态以上述run为准。

状态：独立目标与只读检查器已实现，纯反例验证完成；真实 GUI / AI 执行仍为 NOT VERIFIED，不计覆盖或发布 GREEN。

业务目标为将固定 27mm cube 沿全局 X 正向移动 10mm，保留形状、尺寸、旋转、Y/Z、常规与初层 0.4、材料及工艺设置。GOAL 不含菜单、键盘路线或点击坐标；fixture 的原 X=135.5 是检查器内部预期值来源，不预置给模型。

## 接口与独立检查

`harness/pilot_transform.py` 提供 `CASE_ID=pilot_model_move_x`、`GOAL`、`verify_business(project, fixture, gcode, *, cancelled)`。runtime 身份、原生工具权限、停止输入、自然退出、冻结字节及重开导出的来源链由共同 NativeSaveVerifier 负责，本模块不能自行认证 GUI 来源。

1. 校验固定 fixture SHA256；只从可信 fixture 推导 build translation X=145.5，线性矩阵、Y=136、Z=13.5保持。
2. 复用 bounded ZIP/XML 与物理三角面比较：唯一 cube、27mm 形状/尺寸、part matrix、extruder=1 等条件保留。预期几何在内存中由 fixture 推导，实际产物从不被改写或当作 golden。
3. 装配视图的 assemble transform 必须保持原值，不能猜它会随 Prepare 页上的 Move 更新。只读源码依据：`GLCanvas3D.cpp:6251–6259` 在普通画布仅更新 `set_transformation`，装配画布才更新 assemble；`bbs_3mf.cpp:7891–7916` 单独保存 assemble transform。共享 `inspect_project` 的可选 expected_assembly_transform 用于保留该语义，默认旧合同不变。
4. 调用共同 `pilot_common.inspect_preserved_settings` 对 fixture 配置逐字段做序列化等价检查；只允许已知版本迁移，拒绝任意新字段或其他设置改变。
5. G-code 必须有真实对象正 XY/E 挤出，常规/初层0.4、68层、末 Z27.2、对象工具T0。另检查对象挤出线段起止点均在移动后 cube XY AABB 的1mm容差内，两个方向均覆盖至少23mm；未移动的旧 G-code、无挤出、只写配置注释或短线伪造均拒绝。采用常量空间累计包围范围并检查取消。

XY检查是固定无支撑 cube 的范围/覆盖检查，不是完整逐段刀路几何或固件执行证明。大 brim、支撑、其他模型或切片模式不在此试点范围。

## Harness 自检

实现前已读取 INDEX、harness-driven-review（Part A）、input-validation、testing-strategy；共享上下文已加载工具控制、风险/验证、AI评估 harness。

| 条件 / tier | 动作 | 结论 |
|---|---|---|
| 不可信文件 / N | SHA、类型/大小、有界ZIP/XML、有限Decimal、固定场景白名单 | PASS |
| 不能让AI自签 / C | 预期来自fixture数学推导；检查实际对象挤出与XY；来源链留给runtime | 纯检查器PASS，真实GUI待验 |
| 变换语义 / C | 查源码区分Prepare与Assembly，不将两个transform一起平移 | PASS |
| 测试真实性 / C | Synthetic正例和反例，无模型/GUI/relay；不混入覆盖率 | PASS |
| 不扩大权限 / C | 模块纯读取，未启动进程、访问网络、改上游或公共配置 | PASS |

反例覆盖未移动、反方向、错误距离、错误轴、Z变化、缩放、mesh变形、assembly意外移动、其他工艺变化、旧Gcode、无挤出、错误层高、局部短线伪造、仅注释Gcode以及伪fixture。真实首轮如出现不在已证实范围的格式，保留 NON_GREEN 分诊，不自动放宽。

验证命令：`python -B -m pytest unit_tests/test_pilot_transform.py unit_tests/test_agent_project_verify.py unit_tests/test_agent_layer_verify.py -q`，最终118 passed（6.16s），其中本线17项。共享assembly扩展落地后重跑通过；`git diff --check`通过。没有运行GUI、VM、relay或模型，也未提交推送。
