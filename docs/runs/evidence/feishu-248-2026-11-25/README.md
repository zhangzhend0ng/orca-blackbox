# 飞书 #248 选中对象右键删除，Ctrl+Z 撤销

飞书行 reczz28aa4fiZM5b 要求右键删除选中的 A，观察盘面与对象列表，再用 Ctrl+Z 恢复。用例在同一块盘放置 20 mm 立方体 Alpha 和 16 × 14 × 12 mm 的 Bravo，两者 X 中心相距 100 mm。

2026-11-25，win11-test 用提交 4005cf1862d57638a525cc8decdc115fbd279f3b 单跑两轮。两轮均从新的工程和 Orca 配置启动，场景耗时分别为 105.553 秒和 106.609 秒。两轮在点击模型时打开的原生菜单均包含 Delete，真实 Ctrl+Z 操作后对象恢复。[首轮收据](4005cf18-run1-receipt.json) · [复跑收据](4005cf18-run2-receipt.json)

| 检查 | 删除前 | 删除后 | Ctrl+Z 后 |
|---|---|---|---|
| 两轮侧栏 Objects 的实际 OCR | Alpha、Bravo | Bravo | Alpha、Bravo |
| Alpha 在盘面中心采样区域的彩色像素 | 576 | 0 | 576 |
| Bravo 在盘面中心采样区域的彩色像素 | 576 | 576 | 576 |
| 保存工程中唯一打印板的对象 | Alpha、Bravo | Bravo 的 12 个世界坐标三角面完全相同 | 两个对象的名称、网格、世界坐标全部恢复 |

视口图像为 1920 × 1032。两个 24 × 24 像素窗口以 (1058,521) 和 (1284,528) 为中心，色彩通道最大值减最小值超过 45 计一个彩色像素。两次真实运行的六张图得到相同读数。运行中三次快照均检查编辑器存活与可见模态框，未观察到错误提示。[首轮读数](4005cf18-run1-analysis.json) · [复跑读数](4005cf18-run2-analysis.json)

宿主经 hv_harvest 收割两份 JUnit 和现场日志。工件清单逐个记录了客机 SHA-256；离线重判重新核对清单和原始网格，未删除的对照输入被拒绝。

```powershell
& runner/hv_go.ps1 -Cases m7x_248_delete_object
python tools/replay_case_evidence.py docs/runs/evidence/feishu-248-2026-11-25/4005cf18-run1-receipt.json docs/runs/evidence/feishu-248-2026-11-25/4005cf18-run2-receipt.json
```
