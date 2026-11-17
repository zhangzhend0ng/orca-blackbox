# 材料槽 2 独立业务线

最新root试跑（cc2ae83）：真实SHADOW：对象槽2、实际逻辑T1与68层通过，非物理喷头映射证明。run `91933c76b0cc4064ab0e581dd08883a2`；见[完整记录](../runs/zcode-business-pilots-2026-11-17.md)。

以下保留子agent初始交付记录，其中NOT VERIFIED/尚未GUI描述交付当时状态，最新实际状态以上述run为准。

状态：纯检查器与合成正反例已实现；本业务尚未在真实 GUI 中验证。case 为 `pilot_material_slot2`。没有安装、运行模型/GUI/VM/relay、提交或推送。

目标：AI 自主把已加载的唯一 cube 分配给 **filament slot 2** 并保存，保持几何、常规/首层 0.40 mm、全局材料/喷嘴映射及其他工艺不变。英文 `GOAL` 不含坐标、菜单路线或点击次序。后续由公共入口执行停输、自然退出、冻结文件、独立 profile 重开及真实 GUI 切片；本模块只读接收原始 3MF、固定 fixture、导出 G-code，不能自行证明上述来源链。

## 材料索引与可证明边界

已读取 `fixtures/agent_layer_cube.3mf`，SHA-256 `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`：

- `model_settings.config` 唯一 object extruder=1；五个材料槽中，槽1为 Generic PETG，槽2为 Snapmaker PLA Silk；喷嘴数组只有四项。
- 板级 `filament_map_mode=Auto For Flush`、`filament_maps=1 1 1 1 1`。这两个字段须保持，不能用于证明物理喷头对应关系。
- 上游只读源码 `src/libslic3r/PrintObject.cpp:3378-3392` 明确 object extruders 返回 0-based，并将 volume extruder 减1；`GCode.cpp:9217` 将工具ID传入 `next_extruder`；`GCodeWriter.cpp:455-474` 输出 `T` 加工具ID。fixture 的 change-filament 脚本亦输出 `T{next_extruder}`。因此本线预期 **逻辑槽2 → G-code 工具T1**，仍须读取本轮实际对象挤出验证，不能凭配置猜通过。
- `src/libslic3r/Format/bbs_3mf.cpp:7791-7798` 明写序列化 hack，所有 filament_maps 均输出1。这进一步说明板级数组不能当物理映射 oracle。
- 现有 `tests/mixing/m4i_mixing_slice.py` 仅数 distinct T 指令，包含非对象动作；`tests/engine/m7j_change_filament.py` 混用菜单状态、用量和旧 extruder 属性。两者均不足以证明本线“唯一对象实际使用T1”。本线复用 `analyze_gcode` 的对象边界、XYZ/E模式与正XY/E移动解析。

本模块成功返回只证明：保存的对象分配2、几何不变、限定配置保持、实际对象挤出仅使用T1、68层、末Z27.2。JSON结果明确 `physical_nozzle_mapping_verified=false` 与 `printing_verified=false`。设备连接/发送映射、固件执行与实印均不在本线范围。

## 检查策略

`verify_business(project, fixture, gcode, *, cancelled=...)` 校验固定fixture哈希；调用共享 `inspect_project(..., layer_height='0.4', expected_extruder='2')`，保留其尺寸、几何、重复metadata、paint/part override等检查；校验两项板级映射未变；核对全局配置；再解析实际对象G-code。原始输入不改写，结果hash对应真实原始bytes。错误使用 `_InvalidEvidence`，取消贯穿解析与配置比较。

全局配置不允许任意删除、新增或修改。只接受历史 GUI 产物 `artifacts/windows_mcp_harvest/482f2e13c8d44169ade4159d5be3d240/projects/0001.3mf` 已证实的序列化变化：固定46项字符串转同值单元素数组；固定 `(fixture.3mf)` 预设别名；版本2.3.6→2.4.0；8项指定新增默认值；Generic预设首个catalog ID变空（其完整配置、名称、其余ID仍核对）。这些是版本兼容白名单，不是业务可修改项。新增差异必须保留失败并单独审查，不能为通过临时泛化忽略。该旧产物是格式证据，**不是本材料业务的GUI成功证据**。

root 负责提取共享配置审计及注册执行场景，本模块不修改共享runtime、authority、executor或原fixture。

## 验证与 Harness 自检

命令：`python -B -m pytest unit_tests/test_pilot_material.py -q`。结果：**27 passed in 0.26s**（2026-11-17，纯测试，无GUI）。

纯测试覆盖：不同ZIP顺序合法；已证实格式迁移合法；未改/错材料槽；T1仅出现在purge或注释；对象混合工具；其他工艺/喷嘴/材料参数改变；未知新增项；板级映射变化/重复；part覆盖；破损ZIP；错误fixture；开始及中途取消；错误层序但正确echo；首层变化。合成G-code仅验证检查器，不替代真实GUI或切片结果。

- (N) input-validation / python-input-deserialization：固定fixture哈希，复用有界ZIP/XML/JSON解析，严格目标和配置白名单；不执行输入内容。
- (C) error-handling：明确 `_InvalidEvidence`；不吞取消，不把解析失败当通过；没有自动重试。
- (C) pytest：隔离bytes fixture、参数化有区分度反例，无网络/GUI依赖。
- (A) differential-oracle：逻辑索引有只读源码与fixture依据；格式迁移来自真实历史产物。未运行当前二进制的材料场景，不能声称源码等同实测。
- (C) tool-calling：本模块无工具输入/GUI权限；只返回业务事实，来源与晋级仍由公共runtime控制。

下一步仅由root通过 `hv_go` 串行真实试跑：取得GUI保存文件及可信阶段实际G-code，检查器通过后仍是业务SHADOW。若对象T1、格式迁移或来源证据不满足，保留NON_GREEN及具体原因；不得修改fixture或放宽到“出现过T1”来制造通过。
