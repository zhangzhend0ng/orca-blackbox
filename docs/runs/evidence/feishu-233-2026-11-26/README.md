# 飞书 #233 合并导出

记录 `reczz28aa4fiZ49b`（P1）要求盘上有立方体和球体两个模型时，点击「文件→导出→导出所有对象为单个 STL…」，选路径保存，再用第三方查看器打开。预期「生成 .stl 文件，包含两个模型的合并几何；文件非 0 字节，可正常打开」。

测试提交 `6bdf66b396c6de2f58a4269864524eb68b546c3f`，Snapmaker Orca 2.4.0，U1 0.4 mm、Generic PLA、0.20 mm Standard。[构建摘要](build.json)

| 会话 | 客机 | 场景耗时 | 离线复核 |
| --- | --- | ---: | --- |
| [首轮收据](6bdf66b3-run1-receipt.json) | GREEN | 121.875 秒 | 通过（43 项） |
| [第二轮收据](6bdf66b3-run2-receipt.json) | GREEN | 122.475 秒 | 通过（43 项） |

两个会话都在 win11-test 的 `test` 交互桌面经 `runner/hv_go.ps1` 启动，各自是新的 Orca 进程、配置目录和工程。初态在用例里搭：加载 `fixtures/feishu_std_cube.3mf`，在空白处右键 Add Primitive > Sphere 加一个球（32,040 面），此时球压在立方体上；右键 Arrange 把两件分开，存为 [首轮初态](6bdf66b3-run1-before.3mf)。

| 飞书预期 | 两轮读数 |
| --- | --- |
| 生成 .stl 文件 | File→Export 的 `Export all objects as one STL...` 打开 `Export STL file:`，类型只有 `STL files (*.stl)`；输入不带扩展名的 `all-objects`，应用落盘为 `all-objects.stl` |
| 包含两个模型的合并几何 | 一个文件 32,052 个三角面：立方体 12 面在 X 122–149、Y 137–164，球 32,040 面在 X 122–149、Y 108–135，逐面与保存工程里两件的世界坐标三角面配对，最大顶点偏差 0.0000077 mm（容差 0.0001） |
| 文件非 0 字节 | 1,602,684 字节，二进制 STL |
| 可正常打开 | F3D 4.0.1 打开同一字节文件（SHA‑256 一致）渲染出 800×600、163,108 个网格像素的图，347 种着色；同一 F3D 打开一份损坏的 STL 返回 1 |

两轮的 `all-objects.stl` 和 F3D 渲染图逐字节相同。[首轮导出件](6bdf66b3-run1-all-objects.stl) · [渲染图](6bdf66b3-run1-f3d-view.png) · [对话框](6bdf66b3-run1-export-dialog.png) · [逐步读数](6bdf66b3-run1-analysis.json)

离线复核用 `tools/replay_case_evidence.py`：先核对清单里的字节数与 SHA‑256，再只从归档文件独立重算，并做 16 个反例，每轮一个独立进程，各 19 秒。反例包括只导出一个对象、两个对象被挪到一起、少一个面、空文件、偏移超过容差、F3D 空白图、清单不符、把 analysis 改成 PASS。

```powershell
& runner/hv_go.ps1 -Cases m7x_233_export_merged_stl -NoSync
python tools/replay_case_evidence.py docs/runs/evidence/feishu-233-2026-11-26/6bdf66b3-run1-receipt.json docs/runs/evidence/feishu-233-2026-11-26/6bdf66b3-run2-receipt.json
```

计时：用例内每轮约 101 秒（加球 5.4、另存并读重叠 25.5、Arrange 2.4、导出 14.9、读 STL 1.6、查看器 4.5），宿主派发到收割 125 / 129 秒。领取到首次客机通过（00:41:47）约 86 分钟，其间一次失败轮：用例自己的保存件里球网格成员有 2.5 MB，共享的 3MF 读取器当时上限 2 MB，读不了；总控把上限放宽到 16 MB 后通过。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。

实体机 fa706g3 在 `81dbcf1` 上有一次 SHADOW（94.9 秒），导出件与这里的逐字节相同，只计 SHADOW。
