# perf 采样首个真实客机验证（m2_slice_chain）

日期：2026-11-20 凌晨。目标：验证 `harness/perf_monitor.py`（8f68b11）+ `hv_go -Perf`
穿透（af4fba1）在真实客机 GUI 用例上能采到进程指标并回收。

## 结论

**链路全通，证据有效；psutil 缺失触发 ctypes 降级（按设计工作，覆盖降）。**
m2_slice_chain 本批 GREEN（`SUMMARY: PASS=1 FAIL=0`）。本批是 perf 探针验证，
不是 87 条回归批次，不写飞书 GREEN。

## 证据链

- 入口：relay → `hv_go_detached.ps1 -Cases m2_slice_chain -Perf`；宿主日志
  `[3] launching suite: 1 cases (warmup=False perf=ON)`，SYNC_OK @ af4fba1。
- 实际沙箱：`C:\coil\orca-blackbox-v3-r1`（宿主 relay 环境残留
  `ORCA_BB_GUEST_SANDBOX` 指向 v3-r1；`_common.ps1` 默认值被 env 覆盖，非本批
  引入）。客机该沙箱本批临时切 glm，批后已还原 software_testing（534cfee）。
- 生成脚本确认含 `$env:ORCA_BB_PERF='1'` + per-case label（客机
  `C:\coil\run_suite.ps1` 原文核对）。
- 挂载证据（m2 日志头）：`[perf] attached label=m2_slice_chain
  out=...artifacts\perf\m2_slice_chain__20261120_011836.jsonl`。
- 采样数据（45 样本，回收 MD5 MATCH，base64 relay 224 chunk）：
  CPU avg 42.5% / max **246.9%**（多核切片），private 峰值 **431.0MB**，
  **GDI 1068 → 265**（启动期对话框高 GDI，关闭后回落——真实泄漏/回收信号）。

## 本批暴露的问题与处置

1. **客机 venv 无 psutil** → 自动降级 ctypes 单 pid 模式（日志
   `[perf] psutil missing — degrading`）。后果：无 name 发现/连接数/整机网络行
   （sys samples=0）。处置：后续把 psutil 装进客机 venv 即恢复全量模式；
   降级路径本身按设计工作。
2. **meta 行 mode 误标**：降级判定原在采样线程首 tick（meta 行之后），
   首批 jsonl meta 写了 `psutil` 实际跑的是 ctypes。已修：start() 先探测
   psutil 再写 meta（本提交）。
3. **relay 诊断打到宿主**：relay 守护在宿主执行，前几轮裸 `Get-Content
   C:\coil\...` 轮询读的是宿主文件（宿主遗留 8 月 run_suite.ps1 造成误判）。
   处置：新增 relay-safe 的 `runner/guest_progress.ps1` / `guest_cat.ps1`
   （PSDirect 包装），`guest_git.ps1` 顺带修了单分支 clone 拉不到指定分支的
   refspec 问题。

## 边界

- ctypes 模式的 GDI/USER 对锚进程有效；conn/network/sys 行仅 psutil 模式有。
- 本批单用例、单次；采样开销（0.5s 间隔单 pid）未观察到对 m2 判定的影响，
  但未做多批对照。
