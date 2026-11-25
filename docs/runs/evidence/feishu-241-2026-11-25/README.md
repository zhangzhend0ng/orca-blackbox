# 飞书 #241 自动朝向

飞书记录 reczz28aa4fiYqu6 的前置条件是盘上有两个朝向不佳的对象。执行打印板空白处右键「自动朝向」，观察两件，分别验证朝向改变和贴盘面积增加。

win11-test 上运行 Snapmaker Orca 2.4.0，夹具使用 U1 0.4 mm 喷嘴、PLA、0.20 mm Standard。两轮均经 hv_go 启动，使用独立 Orca 进程和新配置，保存前后工程。测试提交为 1f8b8ac35e4fec4bd513e415cd130461cdaa7432。[构建摘要](build.json)

| 会话 | 原始结论 | 场景耗时 | 离线复核 |
| --- | --- | ---: | --- |
| [首轮收据](1f8b8ac3-run1-receipt.json) | GREEN | 96.610 秒 | 通过 |
| [第二轮收据](1f8b8ac3-run2-receipt.json) | GREEN | 96.850 秒 | 通过 |

| 两轮共同测量 | 盘面法向在模型坐标中的变化 | 贴盘面积（mm²） |
| --- | --- | --- |
| Alpha | +Z → +X，约 90° | 263.175 → 1815 |
| Bravo | +Z → +X，约 90° | 424.125 → 2418 |

离线复核逐件读取 3MF 中的变换，计算位于 Z=0 的共面三角形面积，并确认对象仍在有效盘面体积内。反例拒绝原样保存、只绕 Z 旋转、旋转后悬空。正式两轮复用了相同的初态。换初态返工和历史人工耗时均为未测。[首轮逐项读数](1f8b8ac3-run1-analysis.json) · [第二轮逐项读数](1f8b8ac3-run2-analysis.json)

```powershell
& runner/hv_go.ps1 -Cases m7x_241_orient
python tools/replay_case_evidence.py docs/runs/evidence/feishu-241-2026-11-25/1f8b8ac3-run1-receipt.json docs/runs/evidence/feishu-241-2026-11-25/1f8b8ac3-run2-receipt.json
```
