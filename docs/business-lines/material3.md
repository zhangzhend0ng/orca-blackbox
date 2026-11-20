# 材料目标扩样：逻辑材料槽 3

状态：独立目标与纯检查器准备完成，真实 GUI / AI 运行尚未验证，不计业务覆盖或发布 GREEN。本轮只新增三文件，不更改正在执行的旧入口或 HOST_SOURCES。

接口：`harness/pilot_material3.py` 提供 `CASE_ID=pilot_material_slot3`、无菜单路线/坐标的英文 `GOAL`，以及 `verify_business(project, fixture, gcode, *, cancelled)`。公共入口固定目标槽3，不能通过模型参数选择其他槽。所有原始产物只读，返回 JSON-safe 字典，错误用既有 `_InvalidEvidence`。

## 目标与证据

沿用固定 `fixtures/agent_layer_cube.3mf`，SHA256仍为 `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`。该fixture有五个已有材料槽，槽3为 `Snapmaker PLA Silk @U1 0.8 nozzle`、PLA、颜色 `#00C1AE`，无需新增材料。唯一cube从槽1分配到槽3，保持全部全局配置与板级映射、模型几何及常规/初层0.4。

已只读核对上游源码：

- `src/libslic3r/PrintObject.cpp:3377–3392` 明确返回对象使用的0-based索引，对 volume extruder 执行 `extruder - 1`。
- `src/libslic3r/GCode.cpp:9217` 将同一个工具ID写入 `next_extruder`；fixture change-filament脚本以模板表达式 `"T" + next_extruder` 生成工具选择（并非字面 `T{next_extruder}`）；machine_start_gcode另有 `T{initial_extruder}`。
- `src/libslic3r/GCodeWriter.cpp:455–474` 用工具ID输出换料指令。因此槽3对应预期逻辑工具T2，仍须检验本轮实际对象正XY/E挤出，而不能只根据配置或出现过T2判定。

只证明逻辑材料分配，不能把它称作物理喷头3：fixture板级 `filament_map_mode=Auto For Flush`、`filament_maps=1 1 1 1 1`保持不变，喷嘴只有四项；`bbs_3mf.cpp:7791–7798` 的序列化hack亦会输出全1。返回值始终明确 `physical_nozzle_mapping_verified=false`、`printing_verified=false`。

## 复用与失败条件

新增模块内 `_verify_logical_slot` 仅允许固定注册槽2/3，目标与逻辑工具映射是内部常量。slot3入口固定传3。此helper可由root后续统一给slot2复用，避免扩样时复制整份旧检查器；本轮不改已有slot2。板级映射解析复用旧 `_plate_mapping`，配置比较使用 `pilot_common.inspect_preserved_settings`，ZIP/XML和物理几何检查复用共享有界oracle。

root已最小扩展共享 `inspect_project(expected_extruder=...)` 的白名单允许字符串3，默认仍为1。没有开放任意extruder索引，原合同摘要与旧目标不变。

必须同时满足保存对象extruder=3、几何未变、全部限定配置与板级映射保持、实际对象挤出仅使用T2、0.4/0.4的68层与末Z27.2。对象仍在槽2的旧项目、对象使用T1的旧G-code、T2仅出现在purge/注释、混合对象工具以及其他工艺/材料配置改变均拒绝。取消和错误fixture均失败关闭。

本模块不证明run来源链、停输、重开或GUI实际导出；这些仍由公共runtime收据与冻结文件hash验证。合成正反例不作为真实GUI证据。

## Harness 自检

实现前加载INDEX、harness-driven-review，以及input-validation、工具控制、错误处理、AI评估等相关准则。

- (N) 输入验证：固定fixture SHA、严格槽枚举、既有有界ZIP/XML/JSON解析；无自由路径或shell。
- (C) 审计与权限：只读产物，无GUI/VM/relay/模型调用，不修改上游、旧runtime、工具权限或全局配置。
- (C) 错误处理：不吞取消，解析异常统一为证据错误，不重试、不将缺证据当成功。
- (C) 评估：slot2旧结果、错误工具、purge/注释假证据、参数漂移等反例分账；真实运行尚未验证。

2026-11-18，共享expected_extruder白名单1/2/3与scenario注册由root落地后，执行 `python -B -m pytest unit_tests/test_pilot_material3.py unit_tests/test_pilot_material.py -q`，结果 **54 passed in 0.41s**（本线27项、旧材料槽2回归27项）。未运行GUI、VM、relay、模型或Git写操作。真实slot3业务仍待root经hv_go串行验证。
