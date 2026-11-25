# #264 欧特克 FDM 测试模型验收复核

场景 `uia_param_overhang_speeds_fdmt`，飞书记录 `reczz28b6mRB0mjp`。校验器提交 `b193585f1980fc8356c1c4dbe62287d5bc17cbc1`。

验收检查保存工程中的目标值和导出件配置块、460 层的 Z 序列及原模型悬垂墙路径。悬垂墙和桥接两处路径及模态进给合计都与默认切片相同时，拒绝该导出。判断使用排序后的路径签名，避开行序和内部实心填充的复现差异。普通区只对同几何的顶面抽样核对，桥接进给集合的差异可证变化，集合相同不足以验证逐段一致。

## 负对照

从仓库根目录运行。输入来自已有收割目录，脚本将副本写到 `artifacts`。完整校验入口的测试为替代文件重算收据中的 SHA-256，验证业务判据对替代内容的识别。

```powershell
python -B docs/runs/evidence/ninehour-2026-11-25/scripts/negative_controls.py --check-264-fdm --out artifacts/row-264-fdm-controls.json
```

原导出来自客机 `b697f7c24c6c49849c05b22c2a8ed1a3`，默认导出来自实体机 `0cccce4a3b3f40798bcab64c8a815680`，另一模型导出来自客机 `7484bd43c9114b5b8f8d098a6ac978e3`。

| 对照 | 送入的 G-code | 业务与完整校验结果 |
|---|---|---|
| 1 | 原导出 | 均接受 |
| 6 | 同模型默认参数导出 | 均拒绝，`comparison_export_key:overhang_1_4_speed` |
| 6b | 另一模型导出 | 均拒绝，`param_264_fdm_layer_grid` |
| 6c | 截断至 2000 字节 | 均拒绝，`comparison_export_config_block` |
| 6d | 原路径配默认配置 | 均拒绝，`comparison_export_key:overhang_1_4_speed` |
| 6e | 默认路径配正确配置 | 均拒绝，`param_264_fdm_default_export_body` |

另外以本判据重放同模型六份历史原始导出，含路径顺序及内部实心填充分段不同的样本，全部通过导出完整性检查。定向单测 117 条通过。

## Windows 实体机复跑

fa706g3 使用 `glm_line` 交互计划任务。运行前确认队列空闲、无 Orca 进程且检出干净，用 Git bundle 切换到校验器提交。实体机磁盘上 738 个 Snapmaker 预设文件与留存客机清单逐项匹配，比较路径、大小和 SHA-256，差异 0。实体机清单留在 `artifacts/fa264-fa-snapmaker-profiles.txt`，对照源为 `C:/coil/vm_setup/fa_line/guest_profiles.txt`。

- 运行 `87277192709b489cae0f99e37dcec436`，2026-11-25 12:36:03 至 12:39:38（北京时间，含收割）。从 `.worktrees/glm/artifacts/windows_mcp_harvest/87277192709b489cae0f99e37dcec436` 复核 `result.json`、`proof.json`、`execution_host.json`、`proof/0001.3mf` 和 `exports/0001.gcode`。
- 运行结果为 SHADOW，保存后新进程重开及切片导出通过，清理确认完成。执行标识为 `DESKTOP-FA706G3`，`hyper_v_guest=false`，`ORCA_BB_ALLOW_TESTBOX`。被测 2.4.0 构建的 SHA-256 为 `5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`，与客机固定构建一致。导出 SHA-256 为 `1b3270839ad0bfd3a16b7978363ca23251b59b23902e98e204d620d1d582e2cf`，项目 SHA-256 为 `fef1d1f7996f493feac5268edd4e8d0c3190bad7ae1af61b3e36581d510bf2e3`，均由收割文件重新计算核对。
- 识别悬垂、悬垂降速均为 1，四档值为 40/30/20/10，配置与导出一致。当前构建缺少第五档。悬垂墙只观测到 F1980、F3000，目标 F2400/1800/1200/600/300 均未出现。桥接进给集合从 F960/3000 变成 F660/780/1740/1800/1980/3000，路径相同的顶面进给也有变化。预览未核对，飞书原行仍有未满足的预期。
