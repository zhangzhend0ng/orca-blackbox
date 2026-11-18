# 两条复合用例的扩展试验

同一 Orca 二进制、`fixtures/agent_layer_cube.3mf`、`Quality` 初态。两条业务分别先跑手写基线，再由 ZCode 公司模型以目标式提示执行。只有收回并验收通过的轨迹可生成脚本。脚本无模型回放和手写基线分别记录操作段、导出和启动到回收，保留每条失败和未运行阶段。客机为 `win11-test`，用例串行，新 profile，保存后再独立重开切片。结果范围为 SHADOW 或 NON_GREEN。

| 用例 | 手写来源 | 产物验收 |
|---|---|---|
| `uia_quality_enums` | `m5h_ironing_combos` 的 Quality 页面双下拉操作，使用统一立方体 fixture | 熨烫类型 `topmost`、接缝位置 `random` 在 3MF 与重切配置同时读回，其他设置和几何保持；重切含 68 层实际对象挤出。 |
| `uia_move_layer` | 组合 `m6a_transform_verify` 和 `m3d_param_reslice` 的现有输入与读回 | 同一立方体全局 X+10 mm，常规层高 0.24、首层保持 0.40；112 层实际挤出落在移动后范围，其他设置和维度保持。 |

## 手写基线与首次目标式探索

源 `6500072`。平移加层高的手写基线 `ade567f58be97ef89c3d01f102c61a70` 通过，完整 192.848 秒。双下拉框手写基线 `ac1a27061be1bf83bd6171920b4c7c57` 通过，完整 232.489 秒。两条都用同一独立验收，记为 SHADOW。平移和层高单独成功的两份历史产物，都被新组合判据拒绝。双下拉产物离线注入错误接缝配置和过期熨烫配置时，独立判据也正常拒绝。

- 平移加层高，run `e03952d4b9238cd3be63f09f85589919`，NON_GREEN。画布字段提交后，模型沿用切换前的 UIA Edit 选择器，层高输入在派发前被 `native_uia_target_not_observed` 拒绝。未保存。受控复验先改层高，再触碰画布，并要求切换后重新观察。
- 双下拉框，run `e5c7410fcf2d1c1f8eda1babc795fdb8`，NON_GREEN。侧栏坐标点击没有打开下拉框。此时请求未实际绑定的 `wx_process_popup` 裁图，被 `native_uia_visual_region_not_observed` 拒绝。未保存。受控复验要求先确认下拉框已经打开，再请求弹层裁图。

两次失败均已回收，应用、监听和令牌均清理。首次目标式探索 0/2，无可录制轨迹。
