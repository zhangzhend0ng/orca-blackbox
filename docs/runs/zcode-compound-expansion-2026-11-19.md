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

## 提供定位提示后的开发复验

源 `b9266e1`。两条仍使用同一业务判据与 GUI 初态。

- 平移加层高，run `e251f0f23b0338083fdb5919edde5f74`，SHADOW，完整 265.220 秒。先通过 UIA 编辑并读回层高，再用五次命名画布裁图定位选择、移动工具并读回位置。保存对话框用 UIA ValuePattern 与 InvokePattern。独立重切验证 X+10 mm、层高 0.24/0.40、112 层对象挤出。录制器从已验收轨迹生成 18 步。
- 双下拉框，run `e5f89dbc84942f150fc33a48dcd05549`，NON_GREEN，完整 122.658 秒。模型尝试坐标点击 Advanced。守卫识别到原生 ButtonControl、AutomationId `5014` 和 InvokePattern，拒绝坐标派发并要求重新观察。模型再次调用 Click，触发 `native_recovery_observation_required`，未保存。下一次提供这个已观察到的 UIA 属性，并要求从新 Snapshot 确认后调用。
- 双下拉框，源 `8886c62`，run `74df4be4db0068074a27be6924b2fb80`，NON_GREEN，完整 125.611 秒。Advanced 通过已观察的 UIA 属性成功 Invoke，随后裁图确认开启。展开后，当前视口显示 Layer height 和 Line width，Seam 与 Ironing 均需导航。滚动条附近的坐标 Click 命中一个存在原生 pattern、当前却无法安全解析为动作选择器的控件，派发前以 `native_uia_target_available` 拒绝。该用例的工具接口未提供参数视口的受控滚动操作。未保存，未录制，无回放计时。两次复验失败均回收并验证清理。

## 平移加层高的无模型回放

脚本 [uia_move_layer.json](../../contracts/replays/uia_move_layer.json) 绑定已验收的公司模型轨迹、fixture 和初态。回放源 `19b9b4d`，run `b1d0ecff0f77bdaedd26dc847dcddfab`，18 步，无模型调用。通过独立重开切片和清理检查，记 SHADOW。

| 同一平移加层高用例 | 本轮启动准备 | 准备完成到停输 | 停输到独立导出完成 | 启动到宿主回收 |
|---|---:|---:|---:|---:|
| 手写基线 | 52.29 秒 | 59.95 秒 | 52.80 秒 | 192.85 秒 |
| ZCode 带定位提示探索 | 52.32 秒 | 131.14 秒 | 54.02 秒 | 265.22 秒 |
| 无模型录制脚本 | 53.47 秒 | 15.84 秒 | 54.66 秒 | 149.04 秒 |

完整用时由宿主 Stopwatch 记录，含启动调度、收尾和回收；阶段由客机时间戳计算。单次配对中，脚本动作少用 44.11 秒，完整少用 43.81 秒（22.7%）。测量均使用常规冷启动和独立重开，范围为同一 Orca 构建、客机布局与立方体 fixture。

本轮手写基线 2/2，首次目标式探索 0/2，带定位提示后 1/2 可生成脚本，且这 1 条无模型回放通过。两条业务均属于开发集。
