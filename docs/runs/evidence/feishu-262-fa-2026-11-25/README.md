# 飞书 #262 表面流量组合，Windows 实体机

2026-11-25 在专用实体机 fa706g3 经 glm_line 交互计划任务执行。使用仓库 fixtures/feishu_std_boat.3mf、U1 0.4 mm 喷嘴、PLA 和 0.20 mm Standard。两次收据均为 SHADOW，cleanup_confirmed 为 true。受测 checkout 是 b193585f，SUT SHA-256 为 5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf。安装目录的 738 个 Snapmaker 预设文件（含厂商索引）与 win11-test 已存清单逐件一致。[预设核对](profile-parity.json)

| 单例 | run ID | 宿主开始至收割结束（北京时间） |
| --- | --- | --- |
| 默认小船 uia_param_boat_save_only | 391ed75583984c55b1d54ef3365b3d4f | 19:41:17 至 19:43:58 |
| 小船表面流量 uia_param_surface_flow_boat | e7db8c2cb262487c9612227cb3d76517 | 19:45:04 至 19:48:13 |

- 顶面配置 1 → 1.1，底面 1 → 0.9，对象流量系数 1 → 1。顶面和底面的实际正挤出量分别是基线的 1.0999962 和 0.9000079 倍。
- 以对象标记过滤 3DBenchy，对每个特征的所有沉积线段按起止 XYZ 和出现次数配对。十类特征的路径全部一致。除顶、底面外，其余八类的正挤出总量各为基线的 1.0 倍，逐段也通过容差核验。两个保存工程的 3D 模型成员字节完全相同，含 112569 个顶点、225154 个三角面。
- 对象标记内累计正挤出从 3789.99001 变为 3798.64435 mm，增加 8.65434 mm（0.22835%）。对象流量倍率确实保持 1；若飞书的「对象整体流量不变」是要求正挤出总量逐毫米相同，则该项不成立。这里度量 G-code 指令，未称量实物。
- 基线对自身被拒绝。仅在顶面将一处 X 改 0.12 mm，路径判据拒绝。同时在内墙两段分别增加和减少 0.005 mm E，维持内墙总量和全部路径，逐段判据仍拒绝。[输入摘要、全特征读数和反例](measurements.json)

原始基线及目标 G-code、冻结 3MF、进程、重开、机器身份、运行结果和比对哈希保存在 [harvest.zip](harvest.zip)，分为 baseline 与 target 两个目录。解压后可从仓库根目录执行：

```powershell
python tools/verify_surface_flow_paths.py --baseline <解压位置>/baseline/export.gcode --target <解压位置>/target/export.gcode
```

fa GLM-5.4 短审阅 75.02 秒到期，未返回完成标记。fa 模型目录中没有登记 DeepSeek Flash，转用 Mac 的同名 Flash 只读会话，已明确读回 low 推理档，12.41 秒后返回 HTTP 401。另在 Mac 将真实的两个倍率和累计正挤出交给 GLM-5.4 审阅，99.0 秒返回正文及完成标记。它指出总量没有严格守恒；模型答复中直接相加顶、底倍率的算法缺少基线权重，未用于数据分析。请求、会话、应答均匹配 new-provider/glm-5.4，本机核对登记入口为 ai-gateway.s.com。模型只参与文字复核。
