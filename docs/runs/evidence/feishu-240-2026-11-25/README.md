# 飞书 #240 自动摆放

记录 `reczz28aa4fiZxR7` 要求从打印板空白处右键执行「自动摆放」，三个原本互相重叠的对象排布后两两不重叠，且全部在盘面边界内。

两次在 win11-test 的 `test` 交互桌面通过 `runner/hv_go.ps1 -Cases m7x_240_arrange` 启动，每轮使用独立 Orca 进程和配置目录。测试提交为 `76e4c004b3e7cb3a72472e9cfdb4de2d218e3369`，产品为 Snapmaker Orca 2.4.0，工程采用 Snapmaker U1 0.4 mm、0.20 mm Standard 和 Generic PLA。场景耗时从调度计到用例日志完成。脚本内耗时另见分析文件。[产品构建摘要](build.json)

| 会话 | 客机 | 场景耗时 | 离线 |
| --- | --- | ---: | --- |
| [首轮收据](76e4c004-run1-receipt.json) | GREEN | 94.166 秒 | 通过 |
| [第二轮收据](76e4c004-run2-receipt.json) | GREEN | 97.600 秒 | 通过 |

两轮的三个实体长方体均贴盘。初态三对具有体积交集，排布后三对的 XY 投影均无正面积交集。保存件完整保留三个网格，所有最终顶点均落在有效盘面范围 X 0.5–270.5 mm、Y 1–271 mm。反例覆盖质心错开但投影仍重叠、投影分开但越界，以及一开始就没有重叠。[首轮分析](76e4c004-run1-analysis.json) · [第二轮分析](76e4c004-run2-analysis.json)

两个同提交会话复用相同初态。改用其他初态的返工耗时和历史手工操作耗时均为未测。

```powershell
python tools/replay_case_evidence.py docs/runs/evidence/feishu-240-2026-11-25/76e4c004-run1-receipt.json docs/runs/evidence/feishu-240-2026-11-25/76e4c004-run2-receipt.json
```
