# 业务探索状态与入口

路线与下一阶段以[主方案](V3_PLAN.md)为准。本页只保留业务状态和运行入口；停止继续相似扩样，先恢复/停输，再画布，最后冻结held-out评估。检查器可并行开发，唯一客机GUI与relay必须串行。

| scenario | 目标 | 当前证据与边界 |
|---|---|---|
| quality_a | 层高.24，初层.4 | b6b15eb一次SHADOW；旧29f567e矩阵仍严格7/8 |
| pilot_strength | Wall loops2→3，层高/初层.4 | b6b15eb一次SHADOW，保存配置及实际68层挤出；非物理三墙独立计数 |
| pilot_material | 对象逻辑filament slot2 | b6b15eb一次SHADOW，3MF extruder2、对象T1、68层；非物理喷头/实印 |
| pilot_transform | cube全局X正移10mm | 输入范围与画布权限不足，预检blocked；禁止为试通放宽全局门禁 |
| pilot_infill | 稀疏填充15%→30% | 本批NON_GREEN，多次foreign拒绝后actor仍继续；尚无可信保存重切闭环 |
| pilot_material3 | 对象逻辑slot3 | 本批not_run，不能用纯检查器结果填为通过 |

用户已授权多业务探索，但这些目标均参与设计/调试，属于开发集，不算held-out。各次开始、失败、阻塞和未执行分母保留，见[2026-11-18扩样记录](runs/zcode-expansion-2026-11-18.md)；首批旧证据见[2026-11-17运行记录](runs/zcode-business-pilots-2026-11-17.md)。

执行仍是原生ZCode agent、Snapmaker new-provider/glm-5.3-flash、七项Windows-MCP，只有固定业务目标与独立oracle，不预设导航或坐标。初始化/退出/重开切片由可信阶段完成，不计AI自主跨进程能力。

保留入口为`python -B tools/zcode_matrix.py --suite pilots --batch-id <32hex>`；须先提交/push并同步客机同一clean HEAD，GUI唯一入口native_save_demo→hv_go。当前不得据此继续启动相似扩样；主方案A/B修复通过后再登记一次冻结评估。

内容检查不替代权限即时终止。foreign拒绝后缺少永久撤销闩锁是当前必须先修的共享缺口；最终NON_GREEN不等于当时已停止actor。只允许有明确未派发证据的owned控件类型拒绝进入新版本有限恢复，不能把foreign错当可恢复输入。

产物仍在artifacts/zcode_pilots/<batch>、windows_mcp_host/<run>和windows_mcp_harvest/<run>。所有新业务仅SHADOW/NON_GREEN，不改旧7/8、不更新87条或飞书GREEN、不作发布放行。
