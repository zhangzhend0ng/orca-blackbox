# 从已验收的 AI 轨迹录制层高回归

首个录制目标是 Quality 初态下把常规层高从 0.40 改为 0.24 mm，保持首层与立方体，保存并独立重开切出 112 层。脚本由已回收的 ZCode 轨迹生成。

1. 用 `python -B tools/record_uia_replay.py <通过的 run-id> --output <待审查的文件>` 生成脚本。录制器复核可信运行结果、原工具轨迹、3MF 和实际 G-code。当前仅支持同一层高业务的属性操作序列。
2. 审查录制结果。脚本登记在 [uia_layer.json](../contracts/replays/uia_layer.json)。它绑定源 run、原始轨迹 SHA256 和 fixture，保留 UIA 选择器及写入值。编译器为这组语义操作补齐观察点，用 `$OUTPUT_3MF` 接收新运行的保存路径。依赖坐标输入或发生拒绝的源轨迹暂不支持生成。
3. 用 `python -B tools/native_save_demo.py --actor script --scenario uia_replay_layer --run-id <新 run-id>` 走既有 `hv_go.ps1` 和 `hv_harvest.ps1`。执行器在 win11-test 通过本地 Windows-MCP 重放，逐项核对归属、读回及可信回执。脚本合同绑定录制内容摘要，之后沿用已存在的独立文件冻结、重开、实际切片和清理。该场景以 SHADOW 单独登记。

录制范围是固定 SUT 和初态的一条 UIA 路径。带自绘坐标输入的轨迹尚需可重复定位与专门录制规则。工时须通过同目标的实际作者对照测量。

首轮 `77f4486756e9d260525586556525f433` 完整执行八条操作、生成保存与重切产物。冻结检查因 MCP 进程最后的墙钟时刻比 worker 完成时刻多 2.07 ms，正式记 NON_GREEN。修订在停输前由 worker 绑定已完成轨迹的 SHA256，复核仍要求同一服务端轨迹有序、严格匹配登记脚本。该首轮结果保留。

## 客机结果

从 `0dd94aac26c64ecfb854ee318d2eed23` 与 `bfd5c93af9571ba3ddc53f7099d7e407` 两条独立的已验收 AI 轨迹提取出相同的八步脚本。单次离线复核与组装步骤实测 80.4 ms。

| 新 run | 准备完成到停输 | 独立验收 |
|---|---:|---|
| `8fa0b51e972194cd5d00d9159de1b591` | 12.202 秒 | SHADOW，保存后独立重开切出 112 层 |
| `29fa34d22956104119c44b7fee8f3ff2` | 11.781 秒 | SHADOW，保存后独立重开切出 112 层 |

两次都使用源 `a567e57828c45b2d9f3b90d869fe744d5635fbe5`，新 profile 与新输出路径，实际调用 8 次。模型调用、Screenshot 调用、坐标输入均为 0。原 AI 源 run 在同 SUT、fixture 和 Quality 初态下，同一阶段用时 82.97 秒，来自较早源码版本。关联单测 109 项通过。三次运行均已回收。客机复核 Orca、MCP 监听及本轮 token 均为 0，suite Ready，客机工作树 clean。
