# 飞书 #242 删除盘

记录 reczz28aa4fiZIaq 要求工程含两盘、当前盘上有对象。打印板空白处右键「删除盘」后，盘列表减少一项、原盘上的对象保留，无错误。两个客机会话从新的进程和配置启动，运行提交 7bed4701ca6709d455da7f40f98e6d60b779b1d8，Snapmaker Orca 2.4.0，U1 0.4 mm、PLA、0.20 mm Standard。[构建摘要](build.json)

| 会话 | 原始结论 | 场景耗时 | 离线复核 |
| --- | --- | ---: | --- |
| [首轮收据](7bed4701-run1-receipt.json) | GREEN | 90.010 秒 | 通过 |
| [第二轮收据](7bed4701-run2-receipt.json) | GREEN | 91.070 秒 | 通过 |

两轮都从 Keep 和 Remove 两个已占用的盘启动。删除 Remove 后仅余 Keep，Alpha 仍在 Keep，Bravo 完整保留在未分配区域，两件的全部世界坐标三角面都与删除前一致。驱动检测到的编辑器仍存活且无预期外模态。飞书的「盘上对象保留」在本夹具上的实际去向为未分配区域。[首轮逐步分析](7bed4701-run1-analysis.json) · [第二轮逐步分析](7bed4701-run2-analysis.json)

反例覆盖什么也没删，以及删盘同时删掉对象。改初态的返工和历史人工耗时均为未测。

```powershell
& runner/hv_go.ps1 -Cases m7x_242_delete_plate
python tools/replay_case_evidence.py docs/runs/evidence/feishu-242-2026-11-25/7bed4701-run1-receipt.json docs/runs/evidence/feishu-242-2026-11-25/7bed4701-run2-receipt.json
```
