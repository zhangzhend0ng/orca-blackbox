# V3 脚本对照

当前开发对照用同一个冻结 Orca 可执行文件、27 mm 立方体 fixture、1920×1080 客机和 Quality 初态。ZCode 与薄脚本进入同一个可信准备及保存后验收流程。脚本走本仓库已有的层高 Edit 定位及 m6a 画布定位。编辑动作通过 GUI 完成，保存后关闭原进程，冻结同一文件，用新 profile 重开和重切。观察阶段结束后调用相同的层高或平移业务检查。

| 对照目标 | 场景 | 独立验收 |
|---|---|---|
| 常规层高 0.40→0.24 mm | `uia_hybrid_layer` | 初层仍为 0.40、立方体保持、独立重切 112 层 |
| 立方体全局 X+10 mm | `uia_hybrid_canvas` | 3MF 世界坐标变换、其它冻结设置与形状保持、实际挤出范围、独立重切 68 层 |

两个路径的入口均为 `python -B tools/native_save_demo.py --actor <zcode|script> --scenario <场景> --run-id <新 run-id>`。执行位置为 `win11-test`，从 `runner/hv_go.ps1` 串行启动，结果由 `runner/hv_harvest.ps1` 回收。脚本采用独立合同和 `script_shadow` 模式。每个配对共享同一准备与验收逻辑，分别保留运行、失败和清理证据。结果限 SHADOW。

脚本的 `native_worker.json` 记录 `script_action_elapsed_ns`，覆盖 GUI 编辑与保存，包含中断前已消耗的时间。另记开始和结束墙钟用于与保存前工具轨迹对齐。ZCode 应单列工具轨迹首尾时间与模型收据。端到端时间用 guest manifest 到结果生成，且单列 host 同步与回收开销。动作时间与端到端时间都有实测后再比较成功样本。代码调整、调试、失败分诊和一次预登记初态变化的修改/复验均另记工程时间；缺失的历史人时以及尚未跑过的扰动记为 `NOT_MEASURED`。
