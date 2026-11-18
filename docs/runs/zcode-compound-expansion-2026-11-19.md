# 两条复合用例的扩展试验

同一 Orca 二进制、`fixtures/agent_layer_cube.3mf`、`Quality` 初态。两条业务分别先跑手写基线，再由 ZCode 公司模型以目标式提示执行。只有收回并验收通过的轨迹可生成脚本。脚本无模型回放和手写基线分别记录操作段、导出和启动到回收，保留每条失败和未运行阶段。客机为 `win11-test`，用例串行，新 profile，保存后再独立重开切片。结果范围为 SHADOW 或 NON_GREEN。

| 用例 | 手写来源 | 产物验收 |
|---|---|---|
| `uia_quality_enums` | `m5h_ironing_combos` 的 Quality 页面双下拉操作，使用统一立方体 fixture | 熨烫类型 `topmost`、接缝位置 `random` 在 3MF 与重切配置同时读回，其他设置和几何保持；重切含 68 层实际对象挤出。 |
| `uia_move_layer` | 组合 `m6a_transform_verify` 和 `m3d_param_reslice` 的现有输入与读回 | 同一立方体全局 X+10 mm，常规层高 0.24、首层保持 0.40；112 层实际挤出落在移动后范围，其他设置和维度保持。 |
