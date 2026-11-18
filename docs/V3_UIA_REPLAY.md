# 从已验收的 AI 轨迹录制层高回归

首个录制目标是 Quality 初态下把常规层高从 0.40 改为 0.24 mm，保持首层与立方体，保存并独立重开切出 112 层。脚本由已回收的 ZCode 轨迹生成。

1. 用 `python -B tools/record_uia_replay.py <通过的 run-id> --output <待审查的文件>` 生成脚本。录制器复核可信运行结果、原工具轨迹、3MF 和实际 G-code。当前仅支持同一层高业务的属性操作序列。
2. 审查录制结果。脚本登记在 [uia_layer.json](../contracts/replays/uia_layer.json)。它绑定源 run、原始轨迹 SHA256 和 fixture，保留 UIA 选择器及写入值。截图、重试、坐标新动作和运行期 HWND 不作为脚本步骤，保存路径用 `$OUTPUT_3MF` 参数，观察点由编译器补齐。
3. 用 `python -B tools/native_save_demo.py --actor script --scenario uia_replay_layer --run-id <新 run-id>` 走既有 `hv_go.ps1` 和 `hv_harvest.ps1`。执行器在 win11-test 通过本地 Windows-MCP 重放，逐项核对归属、读回及可信回执。脚本合同绑定录制内容摘要，之后沿用已存在的独立文件冻结、重开、实际切片和清理。该场景以 SHADOW 单独登记。

录制范围是固定 SUT 和初态的一条 UIA 路径。带自绘坐标输入的轨迹尚需可重复定位与专门录制规则。工时须通过同目标的实际作者对照测量。
