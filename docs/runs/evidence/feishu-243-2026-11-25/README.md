# 飞书 #243 添加标准模型并编辑

飞书记录 reczz28aa4fiWgpT。在 win11-test 的 test 交互会话以同一提交 9d6017a8861c4a81cbe33c405aebcbb6d8317db9 连续执行两次独立单例。环境见[产品版本和摘要](build.json)。

使用命名打印机 Snapmaker U1（0.8 mm 喷嘴），在空盘上右键打开 Add Primitive 原生子菜单并选择 Cube。打开子菜单时可见 HMENU 与父菜单项关联，日志保留实际列出的 Cube、Cylinder、Sphere 等条目。3MF 中仅有新对象 Cube，模板物体原名为「立方体」。逐面复核得到 8 个角点、12 个三角面，底面 Z=0，三边均为 27 mm。在 GUI 中选中新立方体并沿 X 编辑后，项目中所有物理三角面均准确平移 +10 mm，Y/Z 保持一致。将编辑前工程作为编辑后输入并同步清单哈希时，离线判据拒绝。

| 运行 | 开始（北京时间） | 结束 | 场景耗时 | 客机结论 |
| --- | --- | --- | ---: | --- |
| [第 1 轮收据](9d6017a8-run1-receipt.json) | 19:53:56 | 19:55:39 | 102.970 秒 | [GREEN 日志](9d6017a8-run1-case.log) · [工件摘要](9d6017a8-run1-object_artifacts.json) |
| [第 2 轮收据](9d6017a8-run2-receipt.json) | 19:57:49 | 19:59:30 | 100.803 秒 | [GREEN 日志](9d6017a8-run2-case.log) · [工件摘要](9d6017a8-run2-object_artifacts.json) |

照原运行重判归档文件：

```powershell
python tools/replay_case_evidence.py docs/runs/evidence/feishu-243-2026-11-25/9d6017a8-run1-receipt.json docs/runs/evidence/feishu-243-2026-11-25/9d6017a8-run2-receipt.json
```
