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
