# Windows #244 添加模型与实体机 #254 层高复核

2026-11-25 从飞书读取了[两个原行](feishu-before.ndjson)。#244 的自动化状态为空，#254 为待实现。

## #244 打印板右键添加模型

在 win11-test 的 test 交互桌面单跑。首版 5ea9ba21 的两轮均打开了正确文件并恢复 20 mm 网格，runner 报 PASS，但保存件使用 Default Printer，printer_model 为空，两轮都只计部分覆盖。

修订版 e7ba1cd2 从具名 Snapmaker U1 0.8 mm 模板新建独立工程，移除模板模型，观察空盘，再在打印板空白处打开 Add Models。两轮均确认原生对话框列出 STL、3MF、OBJ，文件名框读回本轮 cube_20mm.stl 路径。保存后该路径与 3MF 的源文件记录一致。唯一打印板上只有一个实例，完整 12 个三角面匹配 STL，世界尺寸为 20 × 20 × 20 mm。准备态和导入后均保留同一具名打印机。独立重跑使用新的目录、进程和 STL 副本。

| 运行 | 客机结论 | 场景墙钟 | 证据 |
| --- | --- | ---: | --- |
| 首轮 | GREEN | 94.742 秒 | [收据](win11-test/e7ba1cd2-run1-receipt.json) · [逐步计时、过滤器和保存读数](win11-test/e7ba1cd2-run1-analysis.json) |
| 复跑 | GREEN | 92.337 秒 | [收据](win11-test/e7ba1cd2-run2-receipt.json) · [JUnit](win11-test/e7ba1cd2-run2-junit.xml) |

从仓库根目录复跑可用 `runner/hv_go.ps1 -Cases m7x_244_add_model`。离线重判可用 `python tools/replay_case_evidence.py docs/runs/evidence/multi-244-254-2026-11-25/win11-test/e7ba1cd2-run1-receipt.json`。用模板冒充导入结果会被拒绝。

## Windows 实体机的 #254

fa706g3 使用与客机一致的 2.4.0 可执行文件，738 份 Snapmaker 预设与客机清单匹配。本轮未改变该机正在使用的测试引擎提交 b193585f。每次确认 glm_line 空闲后从独立 profile 编辑、保存并启动新进程重切，三次收据均有独立 PID 和成功清理。

| 样本 | 首层 Z | 后续增量 | 层数 | 末层 Z | 结论 |
| --- | ---: | ---: | ---: | ---: | --- |
| 附加立方体 | 0.25 | 0.20 | 135 | 27.05 | SHADOW，附加样本 |
| 飞书标准球，保存默认配置 | 0.25 | 0.20 | 100 | 20.05 | SHADOW，基准 |
| 同一球，设置组合参数 | 0.25 | 0.20 | 100 | 20.05 | SHADOW，参数组 |

球体输入均与仓库的 feishu_std_sphere.3mf 字节相同，保存件为 U1 0.4 mm、PLA、0.20 mm 标准工艺。基线本来就是常规 0.20、首层 0.25。相同的层序支持飞书的输出预期，单凭这一相同输出不能证明曾经改动参数。独立核验了每份工程、G-code 和 proof.json 的哈希及所有层 Z 增量。三条 run ID 及配置见[实机对照](fa706g3/comparison.json)。机器版本和配置随证据保留。

Windows #244 的 GUI 实现和客机实跑与模型判据审阅分别计账。各模型实际回复情况见[模型回执](agent-dispatch.json)。

#244 已加入默认回归。2026-11-25 17:04（北京时间）通过宿主写回工具将该记录的自动化状态更新为「已自动化」，随后按记录 ID 读回并验证成功。#254 保持「待实现」。Mac 实机运行与对应证据见[Mac 实验记录](../mac-254-2026-11-25/README.md)。
