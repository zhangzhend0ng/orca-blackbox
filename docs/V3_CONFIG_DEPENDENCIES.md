# 固定版本的切片配置依赖

规则清单见 [config_dependencies.json](../contracts/config_dependencies.json)。逐条保存 ID、触发条件、影响字段、预期、作用域和源码位置。源码证据用 `source_confirmed` 或 `inference_pending`，客机证据另记 run、SUT 和实际验证层级。源码读取使用 Git 对象，宿主与上游工作树里的本地改动不进入扫描。

## 版本对应

| 输入 | 固定身份 |
|---|---|
| 比较源码 | `936c035a2c557ea5dde24d3951f8395c6914bd97` |
| 比较源码的预设 | `resources/profiles` tree `d0ce1591e66bc330c5a21163d5910baed6a56744`，Snapmaker Profiles gitlink `ba75baf8566992cf319a0c1188b09fea279026c6`，Snapmaker 版本 `02.03.08.00` |
| 构建参考源码 | `56e82d53c85457f530827d2488664015b2eae08e`。构建配置和 DLL 字符串使用短标识 `56e82d53c8` |
| 构建参考源码的预设 | `resources/profiles` tree `9c25299bdf61255e8ba33f8de716289517766943`，Snapmaker `02.03.03.03` |
| 客机 Orca | Windows ProductVersion `2.4.0`，启动器 SHA-256 `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`，`Snapmaker_Orca.dll` SHA-256 `0485166d3c128320195d44c55db18fd43567e2fbbaa4aa5d3f163b71772fba35`。客机 DLL 含上述短标识，编译时工作树状态未知。 |
| 客机系统预设 | Snapmaker `02.02.55.02`（707 个 JSON），BBL `02.00.00.55`（1,140 个 JSON）。文件内容和相对路径联合摘要见清单 `sut.installed_vendors`。 |
| Fixture | `agent_layer_cube.3mf`，SHA-256 `ed1ca79dd1dd1de28e9d21fb55efc5cee12f1215fbad9cac07159e5d7687d8ef`，内嵌配置版本 `2.3.6` |

编辑和独立重开都使用 exe 邻接的 `resources/profiles` 为 profile 提供 Snapmaker、BBL 系统预设。仓库 `resources` tree `54b5b20b80253e4792cd9ec390b007f4f83cc1a5` 提供本仓种子资源。其中平铺的 Snapmaker manifest 同为 `02.02.55.02`，但只有 617 个 JSON，材料继承也有差异。例如客机 Generic PETG 0.8 继承 `Generic PETG @U1 base`，仓库副本继承 `Generic PETG @base2`。实际工程使用 fixture 内嵌 U1 0.8 mm 机器、`0.40 Standard` 工艺及 PETG／PLA Silk 槽位。客机部署包同时包含 `0.40 Standard` 与 `0.40mm Standard` 文件，重存件保留内嵌工艺身份 `0.40 Standard @Snapmaker U1 (0.8 nozzle)(fixture.3mf)`。

## 扫描覆盖

| 入口 | 提取内容 |
|---|---|
| `PrintConfig.cpp` | 字面配置定义、类型，以及靠近定义的默认、上下限、比例基准、枚举值与界面模式 |
| `resources/profiles`、`resources/profiles_template`、固定 Profiles gitlink | 继承声明、兼容列表和表达式、机型、喷嘴、层高范围、材料类型及 manifest 版本 |
| `Preset.cpp`、`PresetBundle.cpp` | 梳理继承覆盖、预设集合选择、列表与表达式的优先级及解析异常行为 |
| GUI C++，含 `ConfigManipulation`、`Tab`、`OG_CustomCtrl`、`GUI_ObjectList` | 索引参数显隐、启用、直接改值及相关条件，复核代表规则 |
| 切片 C++，含 `Print`、`PrintApply`、`PrintObject`、各填充、支撑与 G-code 路径 | 索引直接配置读取和条件，复核对象覆盖、层高校验及熨烫几何门槛 |

扫描输出为 gzip 压缩 NDJSON 与汇总 JSON。条件保留原表达式，包含嵌套括号、析取、阈值和调用。附近分支文本作为定位线索。定义行、预设声明和候选源码行分别计数，表中的声明数含版本与机型等元数据。

| 扫描 | C++ 文件 | 预设 JSON | 配置定义 | 预设声明 | 源码分支或调用 | 配置读取 |
|---|---:|---:|---:|---:|---:|---:|
| 比较源码及 Profiles gitlink | 1,302 | 7,989 | 814 | 19,610 | 3,776 | 2,523 |
| 构建参考源码 | 1,264 | 7,949 | 791 | 19,509 | 3,672 | 2,425 |
| 客机系统预设快照 | — | 1,847 | — | 4,352 | — | — |

人工规则清单有 22 条，其中 21 条已从源码确认，1 条材料温度混配辅助检查的正常切片入口可达性仍待确认。

两个 Git 扫描的 JSON 解析失败与无法配对的 C++ 调用括号均为 0。索引中仍待复核的关系包括外层分支和编译宏、动态键名、循环中参数集合、拼装的材料或刀头索引、跨函数别名、联动设置的对话框选择、运行时预设过滤顺序，以及模型几何对实际切片的影响。兼容表达式原样保留，运行时含义由 Orca 的 PlaceholderParser 和活跃配置决定。各板、对象、修改器、模型部件、材料及层范围都有索引入口，实跑限定全局 FFF 工艺及单对象。其他机型、喷嘴、材料、局部覆写及 SLA 候选仍需按各自输入条件复核。

`preset-parent-gaps.json` 保存按同类型、同名搜索存在多个候选或找不到名字的继承引用。比较源码和构建参考源码中分别有 2,618 和 2,625 个多候选引用。客机部署包快照有 296 个多候选、69 个无同类型同名候选。这里的名字搜索跨全部输入文件，实际父级还受 manifest 装载次序及回退集合影响。

预设 UI 的高度边界与切片器判据各有作用。U1 0.8 mm 内嵌机器的范围为 0.16–0.56 mm，工艺编辑越界可提示 Adjust 或 Ignore。切片器单独比较层高与最小在用喷嘴直径。历史支撑记录还保留一处版本差异。构建参考源码 `Print.cpp:1846–1847` 在有机树或默认树支撑时检查尖端直径与挤出宽度，比较源码对应分支仍检查枝条直径，但已移除那条独立的尖端宽度拒绝。先前 U1 0.8 mm 的尖端拒绝 toast 见 [PITFALLS §8](../PITFALLS_0901.md#8-tree-auto-支撑在-u1-08-预设上配置非法)。

## 生成与运行

```powershell
python -B tools/scan_config_dependencies.py
python -B tools/scan_config_dependencies.py --revision 56e82d53c8 --output artifacts/config_dependencies/sut_build_source
python -B tools/native_pairwise_batch.py --family config --plan-only
python -B tools/native_pairwise_batch.py --family config
```

`--family legal` 和 `--family dependency` 可各自生成或串行执行，`--case` 支持选取已登记用例。原批跑入口缺省仍跑原 7 条操作顺序组合。本轮选定三项配置的两个取值。层高的第三个候选 0.9 mm 用于测试生成器筛选，四个交叉组合因 `validate-layer-nozzle` 排除。剩余八个合法值组合中，选取覆盖 12 个两两取值对的四条最小集合，其余四个为冗余。初层、熨烫流量及间距连同选中的默认因子都进入持久化判据。

两条依赖关系使用同一份规则清单。界面用例读取 Basic 初态，开启 Advanced，关闭并重新开启，逐次查询同一 owned Quality 窗口里的 Ironing 组。切片用例用平顶立方体比较 Topmost 与独立的 No ironing 基线。Topmost 判据要求物体最后一层存在 Ironing 角色下正向 XY/E 移动，No ironing 判据要求这一计数为零。正文后的配置回显与实际挤出分别检查。熨烫附属字段本身的显隐、同一会话内把 Topmost 切回关闭再恢复，以及树支撑校验的专用回归保留为待运行候选。

源码索引、部署预设索引及全部摘要位于宿主 `artifacts/config_dependencies/`。清单内 `inventories` 列出三个归档和 SHA-256。客机实测对应的版本、结果及耗时见[本轮登记](runs/config-dependencies-2026-11-19.md)。
