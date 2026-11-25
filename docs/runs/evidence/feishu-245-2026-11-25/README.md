# 飞书 #245 克隆并填充

记录 reczz28aa4fial9n 要求右键对象 A → 克隆，数量 1，勾选自动排列，确认后观察原件和副本。再打开 Clone 执行 Fill，观察盘上对象数与排布。

两个独立 win11-test 会话运行 2aa7ab988fddfb8d20b5cd81f8cf8aa4a2ac46be，Snapmaker Orca 2.4.0，U1 0.4 mm、PLA、0.20 mm Standard。[产品构建摘要](build.json)

| 会话 | 客机 | 场景耗时 | 离线 |
| --- | --- | ---: | --- |
| [首轮](2aa7ab98-run1-receipt.json) | GREEN | 118.539 秒 | 通过 |
| [复跑](2aa7ab98-run2-receipt.json) | GREEN | 117.946 秒 | 通过 |

- Clone 对话框读回数量 1 和自动排列已勾选。保存件有两个同形 60×60×24 mm 对象，原件的网格、尺度和朝向保持。原件随自动排列移动，记录位移 (+0.5,+32,0) mm，两件边缘相隔约 2 mm。
- Fill 另作一次原生确认，盘面由两件增至 12 件，逐一验证网格、占地交集和盘界。保持这 12 件的现有位置时，验证任意平面朝向的新副本都没有可放的位置。额外副本至少包含半径 30 mm 的圆，圆心可行域的 36 个子区中，到一件现有矩形的最坏距离上界为 22.203721 mm，严格相交余量为 7.796279 mm。移除一件后留出完整可放空间的反例被拒。[首轮逐步读数](2aa7ab98-run1-analysis.json) · [复跑逐步读数](2aa7ab98-run2-analysis.json)

最初两轮在 OK 停住，94.178 和 94.691 秒，保留原始 RED。随后定向驱动已确认的模态按钮。在 fa706g3 的首次修复实跑中完成两阶段，旧判据没有证明填满。补强后，fa706g3 同版本同判据新会话完整通过，94.402 秒，按 SHADOW 归档。[旧客机证据](07bab89b-run1-receipt.json) · [首次实体机工件](fa-aa12b1df2dc1-done.json) · [完整 SHADOW 收据](fa-71984fd38194-done.json)

从仓库根目录执行 runner/hv_go.ps1 -Cases m7x_245_clone_fill。使用 tools/replay_case_evidence.py 和两份客机收据得到独立逐项结果。改初态后的返工和历史人工耗时均为未测。
