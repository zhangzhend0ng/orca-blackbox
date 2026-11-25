# 飞书 #252 导出为一个 STL 并在独立查看器中打开

记录 reczz28aa4fiZ5lv 要求右键选中的 A，执行「导出为一个STL」，选择路径保存，然后用第三方查看器打开。要求 STL 非零、几何完整、可打开。

win11-test 从两个新配置独立执行，提交 74b49b23df4304e2b4822be7bab9484bc3be2f1e，Snapmaker Orca 2.4.0，U1 0.4 mm、PLA、0.20 mm Standard，查看器 F3D 4.0.1。[产品构建摘要](build.json) · [查看器版本输出](74b49b23-run1-f3d-version.log)

| 会话 | 原始结论 | 场景耗时 | 离线复核 |
| --- | --- | ---: | --- |
| [首轮收据](74b49b23-run1-receipt.json) | GREEN | 86.735 秒 | 通过 |
| [第二轮收据](74b49b23-run2-receipt.json) | GREEN | 87.155 秒 | 通过 |

两轮经同一个原生保存对话框写往每轮专用新路径。两壳单对象的 STL 皆为 1284 字节，24 个三角面与源工程的 24 个面逐面相同。每轮将同一字节的 STL 交给 F3D 进程打开并渲染，输出 800×600 的 PNG，网格前景像素 129400。再交给同一 F3D 一个独立的损坏 STL，退出码为 1。离线反例还拒绝外接框相同但少一个面的 STL、透明空图和实体灰色占位图。[首轮导出](74b49b23-run1-selected-object.stl) · [首轮 F3D 渲染](74b49b23-run1-f3d-view.png) · [复跑逐步读数](74b49b23-run2-analysis.json)

客机默认使用 C:/coil/Tools/orca-bb-f3d/bin/f3d-console.exe。便携包 SHA-256 为 7c36b7abc2929dafb7d93fc132354d69dbc1ea05c6bf858e7c70d75676ca56f8。其他 Windows 测试环境可通过 ORCA_BB_F3D 或直接运行用例的 --viewer 指定查看器位置。换初态返工和历史人工耗时均为未测。[F3D 4.0.1 官方发行页](https://github.com/f3d-app/f3d/releases/tag/v4.0.1) · [F3D 命令行文档](https://f3d.app/docs/user/OPTIONS/)

```powershell
& runner/hv_go.ps1 -Cases m7x_252_export_stl_viewer
python tools/replay_case_evidence.py docs/runs/evidence/feishu-252-2026-11-25/74b49b23-run1-receipt.json docs/runs/evidence/feishu-252-2026-11-25/74b49b23-run2-receipt.json
```
