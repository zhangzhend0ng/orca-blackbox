# 三业务线探索入口

用户已授权并行推进工艺、模型编辑、材料分配。三路内容检查器/反例并行准备，真实GUI仍唯一客机win11-test串行执行，不与原8次稳定性分母混合。旧层高matrix仍7/8，发布闸不变。

| scenario | 新业务目标 | 内容证据 |
|---|---|---|
| pilot_strength | Wall loops 2→3，常规/初层.4 | 3MF目标及其他全局设置保持、Gcode配置与实际68层挤出；不独立数物理墙线 |
| pilot_transform | cube全局X正移10mm | fixture推导三角面/矩阵、assembly保持原值、实际Gcode移动后XY范围及68层 |
| pilot_material | 对象分配filament slot2 | 3MF对象extruder2、全局及板级映射保持、实际对象T1与68层；非物理喷头/实印证明 |

仍用原生ZCode agent与Snapmaker new-provider/glm-5.3-flash，七项原版Windows-MCP工具；不提供操作路线或坐标。唯一新增的是固定业务合同和检查器，不自建agent规划循环。

准备：提交/push；Git bundle同步客机同一clean HEAD。后台管理员relay启动：`python -B tools/zcode_matrix.py --suite pilots --batch-id <32hex>`。该入口先跑quality_a旧目标一次回归，再依次三个pilot。每轮仍通过native_save_demo→hv_go，独立profile，AI保存后停输、退出、冻结、新profile重开实际切片。

产物：artifacts/zcode_pilots/<batch>/plan.json、events.ndjson、summary.json；每轮host与harvest证据沿用原路径。普通业务失败清理已知才继续；身份越界/配置漂移/清理不明停批。没有自动重跑，失败和not_run保留。新业务只能SHADOW/NON_GREEN，禁止覆盖飞书GREEN或87条基线。

当前只有纯测试完成，真实试跑待执行。源代码自检及范围限制见[审查记录](reviews/software_testing-2026-11-17-pilots.md)，各线细节见business-lines/三个文件。
