# 飞书 #239 删除所有并撤销

飞书记录 reczz28aa4fiaX5K。在 win11-test 的 test 交互会话以同一提交 9d6017a8861c4a81cbe33c405aebcbb6d8317db9 连续执行两次独立单例。环境见[产品版本和摘要](build.json)。

使用两个形状、位置和名称均不同的对象 Alpha 与 Bravo。在两者之间的空白盘位置右键，确认原生 Delete All 菜单项后执行。两轮侧栏 Objects 的 OCR 均由 Alpha、Bravo 变为空，Ctrl+Z 后两项均恢复。对 (1058,521) 和 (1284,528) 的 24 × 24 像素窗口分别重算，两个位置的彩色像素均从 576 降至 0，再恢复至 576。保存前后世界坐标下的全部三角面完全相同。将删除前的截图替换到清空阶段，并更新清单哈希，离线重判仍会拒绝。

| 运行 | 开始（北京时间） | 结束 | 场景耗时 | 客机结论 |
| --- | --- | --- | ---: | --- |
| [第 1 轮收据](9d6017a8-run1-receipt.json) | 19:52:16 | 19:53:50 | 93.922 秒 | [GREEN 日志](9d6017a8-run1-case.log) · [工件摘要](9d6017a8-run1-object_artifacts.json) |
| [第 2 轮收据](9d6017a8-run2-receipt.json) | 19:56:10 | 19:57:44 | 93.202 秒 | [GREEN 日志](9d6017a8-run2-case.log) · [工件摘要](9d6017a8-run2-object_artifacts.json) |

照原运行重判归档文件：

```powershell
python tools/replay_case_evidence.py docs/runs/evidence/feishu-239-2026-11-25/9d6017a8-run1-receipt.json docs/runs/evidence/feishu-239-2026-11-25/9d6017a8-run2-receipt.json
```
