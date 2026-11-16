# v3 第一批底座

第一批实现提供契约验证、独立运行记录、产物事实检查和结果聚合；后续运行骨架将这些原语串成单次生命周期。现已扩展首个真实 Script adapter，m0 在客机完成 SHADOW 验证，见 [接入说明](V3_SCRIPT_ADAPTER.md) 与 [运行记录](runs/v3-script-2026-11-16.md)。生产权限隔离、模型执行器与发布系统尚未接通，不能据此宣称完整 v3 已落地或当前 GUI 回归为 GREEN。

## 接口

- `harness.run_contract.load_contract(path)` / `validate_contract(mapping)`：严格校验版本、字段、类型、重复键和资源限制，生成不可变契约。
- `harness.run_evidence.RunEvidence`：独占创建 run 目录、契约和 manifest，追加结构化事件，一次性写入检查结果。
- `harness.artifact_check.check_artifact(...)`：检查本次产物的路径、时间、大小、hash，以及可选的独立预期或配置 echo。
- `harness.run_verdict.aggregate_result(...)`：独立汇总 execution、path、business、visual；缺项、未知、路径违规、缺证据和未留痕恢复均不能通过。AI 默认 SHADOW。

契约示例在 `contracts/examples/m0_boot_check.json`。它只是最小记录契约，尚未覆盖完整 v3 的构建／夹具初态、禁止路径、输入权限及晋级注册等字段，也不会直接驱动现有 m0。schema 需随调度与执行器适配继续演进。

## 无 GUI 的本地检查

从仓库根执行：

```powershell
python -B -m pytest unit_tests -q
python -B tools/v3_session.py validate contracts/examples/m0_boot_check.json
python -B tools/v3_session.py init contracts/examples/m0_boot_check.json
python -B tools/v3_session.py smoke
```

`validate` 不创建运行目录；`init` 创建唯一目录及 manifest，不启动 Orca，也不生成通过结果。显式使用 `--root` 可选择记录根目录。默认位置为 gitignored 的 `artifacts/v3/`。纯单元测试在仓库根 `unit_tests/`，不会载入 GUI 用例专用的 `tests/conftest.py`，也没有关闭或修改其环境门禁。

## 单次运行骨架

精确设计与当前边界见 [V3_RUNTIME_ARCHITECTURE.md](V3_RUNTIME_ARCHITECTURE.md)。`harness/runtime.py` 的 `run_once` 是唯一生命周期入口，依赖 `runtime_ports.py` 的执行与验证端口，不导入具体 GUI／模型实现。`runtime_smoke.py` 在应用组合层注入独立的模拟执行器和文件检查器，实际经过排他锁、运行、验证、清理、聚合和一次证据收尾。

`smoke` 成功仅证明这条 synthetic 调用链及其固定模拟产物通过检查，始终输出 `SYNTHETIC`、`gui_executed=false`、`release_eligible=false`。契约中的 script／agent_mcp／midscene 表示端口类型；当前真实后端仅注册固定 m0 Script，agent_mcp／midscene 尚未接通。桌面锁只在共用的 canonical root 下排他；非阻塞端口是可信合作式接口，不是可强制抢占任意 Python 回调的沙箱。

## 可信边界

证据写入器只提供单 writer 的不可覆盖 API、落盘和 hash 链；它没有实现 Windows ACL 或对同权限恶意进程的隔离。最终记录可接受可信检查器的结果，不自行认证结果真伪。调度器仍须分离执行器与检查器权限，验证轨迹／证据和晋级来源，并落实动作、时间与费用上限。当前聚合 API 不能直接暴露为 agent 自报通过的工具。

文件新鲜、非空和配置 echo 只证明这些事实；检测截断需要独立大小／hash／结束标记或格式检查器，echo 不证明完整工具路径正确性。

## m5 修复与验证范围

本批另修复 `tests/m5_common.py`：菜单未出现或 OCR 无词时不能迭代 None、不能点击；未点击 Delete 不能只凭低色度判断成功；启动后异常会尝试关闭本 session 并保留原错。保持原阈值和有限重试，不宣称已解释菜单失败或文件占用根因。

GUI 验证必须走 `win11-test` 的 `runner/hv_go.ps1`。宿主单测和模拟依赖不是 GUI 回归证据。客机结果与收尾状态另见本批运行记录；未验证项目不得写为 GREEN。
