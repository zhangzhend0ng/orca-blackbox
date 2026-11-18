# GUI v3 泛化评估登记 2026-11-18

受控纠错和画布分别通过完整业务验收后，启动此轮。冻结同一 SUT、fixture、ZCode bundle、Snapmaker `new-provider/glm-5.3-flash`、七项工具、权限和 oracle。运行时由 `tools/zcode_matrix.py --suite generalization` 在首槽前写入八个 run ID、完整 source SHA 与各合同摘要。所有 GUI 只由 `hv_go.ps1` 在 `win11-test` 串行启动。

| 槽位 | 组别 | 目标与初态 |
|---|---|---|
| `general_wall` | 开发锚点 | Quality 初态，Wall loops=3 |
| `general_slot2` | 开发锚点 | Quality 初态，现有逻辑材料槽 2 |
| `general_top_strength` | 新目标 | Strength 初态，Top shell layers 3→5 |
| `general_top_quality` | 新目标 | Quality 初态，Top shell layers 3→5 |
| `general_scale_quality` | 新目标 | Quality 初态，全局 X 尺寸 27→40.5 mm，保留 Y/Z、中心及旋转 |
| `general_scale_others` | 新目标 | Others 初态，同一单轴尺寸目标 |
| `general_combo` | 新组合 | Quality 初态，填充 30% 加逻辑材料槽 3 |
| `general_combo_dialog` | 受控干扰 | 同一组合，预置 owned Save As 对话框 |

目标与初态在首槽前一次登记。新目标只用合成 3MF/G-code 正反例验证 oracle。顶层验证同一保存项目的设置、配置块回显及实际 Top surface XY/E 挤出。缩放验证物体完整世界坐标三角面、中心和相同重开切片中的 XY 挤出。组合同时验证同一项目的设置、槽位、真实 T2 与稀疏 XY/E。每槽最多一次，模型只能通过七项工具完成自己的操作。合约总预算 900 秒，原生 turn 540 秒，40 次尝试，同一 turn 最多两次受信的可恢复拒绝。

投入阈值为开发锚点 2/2，两个新目标各至少一次成功且新目标槽总计至少 3/4，组合与干扰 2/2。实测越界、致命停止后仍有输入派发、未知清理或不一致的通过证据触发整批停止。门禁拒绝、普通失败、基础设施失败及未执行槽均保留。对缺少可审计纠错证据的成功样本，纠错分类记 unknown。所有结果限 SHADOW，历史通过率和发布覆盖率沿用原判定。

## 冻结结果

源 `68525b5d1dd42ca8dcea854805a660a66bc4b188`，batch `e65553929d821c3d0c31901fd0849c0b`。八槽均只执行一次，串行协调累计 38 分 35 秒。正式通过 4/8，开发锚点 2/2，新目标 1/4，组合及干扰 1/2，未达到投入门槛。计划、事件及摘要位于 `artifacts/zcode_generalization/<batch>/`，原始 3MF、G-code 和运行证据位于 `artifacts/windows_mcp_harvest/<run>/`。

| 槽位 | Run | 冻结判定 | 调用 / 已落盘模型收据 | 证据摘要 |
|---|---|---|---|---|
| Wall loops | `ba415a61a99f44229cdafbaab5030bde` | SHADOW | 22 / 23 | Wall loops=3 的保存配置与新 profile 68 层挤出通过。 |
| 材料槽 2 | `a43e11d6baf0488288d484e29a22ec40` | SHADOW | 25 / 26 | 槽位 2 与实际物体 T1 挤出通过。 |
| 顶层数 / Strength | `56314009509d4e58855a443b94432735` | SHADOW | 10 / 11 | 保存值 5、G-code 配置块和实际 Top surface XY/E 通过。 |
| 顶层数 / Quality | `51aea0cd441e492281524bae6a09e674` | NON_GREEN | 4 / 5 | seq4 Click 命中非 Orca 目标，在派发前拒绝并锁存撤销。 |
| 单轴尺寸 / Quality | `2df4240470c943a78bb013a657eb6526` | NON_GREEN | 16 / 17 | 完成保存和新 profile 重切，冻结 oracle 拒绝装配矩阵。 |
| 单轴尺寸 / Others | `5abfa4a7404d4aae92c76d46264f3d25` | NON_GREEN | 20 / 21 | 同上。 |
| 填充 30% + 槽 3 | `42c05a6a48484e1aa57fe80e6943c0b6` | NON_GREEN | 27 / 27 | ZCode 并行工具调度触发串行合同 `native_parallel_tool_calls_rejected`。 |
| 同一组合 + Save As | `a003967c6c7a4fefb51f208ab9ac809b` | SHADOW | 28 / 29 | seq2 点击已登记 owned 对话框的按钮，随后成功保存、重开、重切；T2 带实际稀疏挤出。冻结分类对 GUI 纠错次数记 unknown。 |

八槽均回收，配置哈希一致，宿主及客机 Job 0。只读复核客机 Orca=0、MCP 监听=0、suite Ready、checkout clean，本会话两项业务验收、前置失败和八槽泛化的 run token 均不存在。冻结提交的完整纯测试 1,316 通过、1 跳过。

## 批后缩放 oracle 复核

两个原始 3MF 的世界尺寸均为 40.50 × 27 × 27 mm，中心保持 (135.5, 136, 13.5) mm。装配矩阵与 build 矩阵都只把 X 比例改为 1.5。上游只读源码 `Selection.cpp` 的实例缩放明确同步调用 `set_assemble_transformation`，原 oracle 沿用平移情形的未缩放装配矩阵，造成两次拒绝。

批后将缩放 oracle 的装配矩阵期望改为从可信 fixture 推导的同一 X 比例，继续检查 Y/Z、中心、旋转、设置及真实挤出。两份现有产物分别用修订检查器离线复核，G-code 均为 68 层、T0 和 X 115.66–155.34、Y 122.91–149.09 mm。旧装配矩阵反例仍会拒绝，关联纯测试 116 项通过。此为批后诊断，冻结两槽均保留 NON_GREEN。未重跑这些保留集任务，发布范围未变化。
