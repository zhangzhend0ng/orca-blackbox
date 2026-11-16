# 首个真实 Script 接入：m0 bootstrap

本批将 v3 同一运行时主链接到真实注册用例 `m0_boot_check`。真实模式只在 Hyper-V 客机运行；通过也只记 `script_shadow / SHADOW / release_eligible=false`。这不是发布门禁，不证明切片、GL 内部语义或完整 AI 测试体系已完成。

## 调用链

```text
hv_go.ps1 -V3（INTERACTIVE suite）
  → tools/v3_session.py run-script m0_boot_check
  → script_session：固定契约、注册能力、canonical artifacts/v3
  → runtime.run_once(execution_mode=guest_script)
  → ScriptExecutor：挂起创建驱动 → 加入 Job → 恢复运行
  → m0：独占 profile、输出目录、截图、报告、archive
  → M0ScriptVerifier：独立只读检查
  → cleanup：确认 Job／检查线程静止
  → result.json（SHADOW 或 NON_GREEN），保留完整事件
```

## 操作入口

正式 GUI 执行仍只有 `runner/hv_go.ps1`。宿主提权窗口或既有 relay 中：

```powershell
& runner/hv_go.ps1 -V3 -Cases m0_boot_check
& runner/hv_harvest.ps1 -V3
```

`-V3` 必须显式选用获准 case，拒绝未登记能力，不执行未留痕 warmup。启动前拒绝已有 Running suite 或现存 Orca，保留他人工作。客机代码同步门禁仍生效；已有 dirty 检出不能被重置或绕过。必要时使用独立干净检出并设置 `ORCA_BB_GUEST_SANDBOX`。

V3 套件写 `C:\coil\v3_progress.txt` 与客机 `artifacts/v3_suite.json`，不污染 legacy 的 GREEN、JUnit 或失败清单。`hv_harvest -V3` 只拉独立套件报告，不把 SHADOW 写回飞书自动化状态。完整 run 位于客机 `artifacts/v3/<run_id>/`；报告及代码同步后再记录实际结果。

## 权限与验证边界

- 应用组合层只注册 m0，case 必须在 cases.py 中启用；不接受任意脚本、argv、模型插件或 executable。固定的 contract digest 同时约束 adapter 和 verifier。
- 即使设置 `ORCA_BB_ALLOW_HOST=1`，真实 Script 入口也拒绝宿主。实际运行 root 固定为该客机检出的 canonical `artifacts/v3`，防止换 root 分裂桌面锁；人工或其他独立入口仍须遵守单执行器纪律。
- 使用新的 run-owned profile，不传 `--fresh`，避免旧 profile helper 的全局同名进程清理。旧 launcher、profile 和 farm_runner 的既有修改不属于本批。
- Windows Job 不启用 breakaway；进程挂起时加入 Job，再恢复。只有主进程退出且 Job 活动进程数归零才可完成；取消只终止本 Job，不能杀其他同名程序。Job assignment／nested-job 能力要通过真实客机验证。
- `process.json` 由适配器独占写入，记录 driver PID、退出码、Job 归零及强杀／取消事实。它不能独立证明 UI 正确；m0 自报报告和 rc=0 也不是充分条件。
- verifier 后台只读 worker 交叉检查进程收据、日志顺序、固定阶段报告及三张完整非纯色 BMP。按块检查取消，cleanup 需确认 worker 静止；未确认则保留锁。有效 BMP 仅是粗粒度渲染／捕获证据，不证明 GL 或切片语义。
- v3 此模式尚未实现通用动作计数、任意 GUI 路径证明、Windows ACL 安全隔离、自动晋级或 MCP／Midscene 后端。Job 的 forced 标记只覆盖 adapter 的终止请求，不等同证明旧 launcher 内部从未使用其关闭兜底。

## 验证

纯单测：`python -B -m pytest unit_tests -q -rs`。它们使用 fake OS 或纯数据，不能代替客机 GUI；真实结果记录于 `docs/runs/`。m0 无飞书基线映射，SHADOW 本身也无写回资格。

Win32 依据：[Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)、[AssignProcessToJobObject](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)、[CreateProcessW](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-createprocessw)。
