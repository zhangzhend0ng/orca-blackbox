# 性能采样归属与回收验证

日期为 2026-11-20。此次运行用来验证采样和回收链路。

| 客机用例 | 实际提交 | 性能批次 ID | 功能结果 | 采样 |
| --- | --- | --- | --- | --- |
| 旧入口 `m2_slice_chain` | `de48893` | `23061045c38b457a8eb4e7387d93ab3a` | 通过，JUnit 已回收 | ctypes，116 个进程样本，启动、切片和预览阶段 |
| v3 Script `m0_boot_check` 首轮 | `8961f37` | `6d30bbe1d15d4c7680b1d665b6e43991` | SHADOW | ctypes，87 个进程样本，套件汇总的 Script run ID 原先留空 |
| v3 Script `m0_boot_check` 复验 | `b8e5621` | `91f82d098b724d65a0d250d6946eb346` | SHADOW | ctypes，81 个进程样本，套件和 JSONL 的 run ID 一致 |

上述运行均经 `hv_go.ps1` 从 `win11-test` 启动，核对客机实际提交。JSONL 和批次清单按 ID 经 `hv_harvest.ps1 -PerfBatchId` 回收并校验 SHA-256，原始文件在 `artifacts/perf_harvest/<batch_id>/`。三轮 JSONL 均有终止记录。复验的 run ID 为 `41b3f9be04104038a8264b8694f14109`，从套件报告、样本头和终止记录独立核对。

本机单测中，性能组 17 项通过，包含真实 Windows ctypes、psutil 和两个并行 Windows Job 的进程采样隔离。其余单测 1393 项通过、1 项跳过。另用本地 PowerShell 模拟传输，验证分块回收、哈希比对、重复回收和同名不同内容拒绝。

客机三轮均使用 ctypes 降级。并行验证使用同名的测试进程。双 Orca GUI 并发、Linux/macOS 上的原生运行和采样开销对照待验证。此批用于诊断，发布基线沿用既有覆盖。

回收后客机恢复为 `software_testing` 的 `534cfee`，工作树干净，suite 为 Ready，Orca 进程数为 0。
