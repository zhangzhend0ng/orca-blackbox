# scripts/ 里有什么、怎么跑

两类文件。都在仓库根目录（含本目录的 checkout）下运行，统一 `set PYTHONDONTWRITEBYTECODE=1`、用 `python -B`，不在任何 checkout 里写字节码。它们只读本目录的证据文件和收割件，不启动 GUI、虚拟机或网络。

## 一、整理这份证据时写的生成脚本（输出就是上级目录里的表）

| 脚本 | 输出 | 命令（在仓库根目录） |
|---|---|---|
| `build_stage.py`（用 `build_common.py`、`gcode_signature.py`） | `stage-timings.json`、`stage-timings.md` | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_stage.py` |
| `build_native.py` | `native-pairing.json` | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_native.py` |
| `build_family.py` | `family-regression.json`、`family-regression.md` | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_family.py --repo .` |
| `build_feishu.py` | `feishu-216-ninehour.json`、`feishu-216-ninehour.md` | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_feishu.py --repo . --combined <11-24 的 combined.json>` |
| `build_dispatches.py` | `dispatch-failures.json`、`dispatch-failures.md`（没有跑起来的派发，一条一行） | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_dispatches.py [--artifacts <artifacts 根目录>]` |
| `record_rows.py` | 运行记录「逐条对照」一节里其余触及行的那张表（打印到 stdout；`finalize_record.py` 会调用它） | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/record_rows.py` |
| `finalize_record.py`（用 `run-record.template.md`，调用 `record_rows.py`） | 运行记录 `docs/runs/glm54-nine-hour-run-2026-11-25.md` | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/finalize_record.py --repo .` |

- 顺序：先刷新 `ledger.jsonl` 和 `receipts/`（命令见上级目录的 `README.md`），再依次跑 `build_stage.py`、`build_native.py`、`build_family.py`、`build_feishu.py`（它要读前面几个的输出和 `facts.json`、`negative-controls.json`）、`build_dispatches.py`，最后才是 `finalize_record.py`。
- `run-record.template.md` 是运行记录的底稿：正文是手写的，其中的 `@@…@@` 占位符由 `finalize_record.py` 从 `ledger.jsonl`、`feishu-216-ninehour.json`、`family-regression.json`、`stage-timings.json`、`dispatch-failures.json` 填上（四类汇总、逐行表、切片复现的计数、最终引擎上的确认、回归结果和换机器复核、补覆盖各批、派发清单和原因、机器占用）。手写的部分不经过脚本，要靠对照表逐项核对。
- `build_stage.py` 通过每份收据里的 `run_dir` 打开收割件（`exports/0001.gcode`、`proof/0001.3mf`、`setup.json`），`build_native.py` 读 `windows_mcp_host/<run_id>/host.json`，`build_family.py` 和 `build_feishu.py` 读没通过的 run 的 `result.json`，`build_dispatches.py` 读客机各 run 的 `native_save_demo/<run_id>/launch.json` 和 fa706g3 的任务日志：收割件还在原处时才能重跑。`finalize_record.py` 和 `record_rows.py` 只读本目录的文件。
- `build_family.py` 和 `build_feishu.py` 调 `--repo` 指向的 checkout 里的 `tools/param_closure_list.py`，取参数族 42 个用例的场景名；飞书记录号和标题取仓库里的快照 `docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22/`。
- 标签怎么归类（`build_common.py` 的 `ROLES`）：台账提交号是 `2a17376` 或 `62cddee` 的 run 算在最终引擎上（两者引擎相同）。`regress-final` 在最终引擎上的，跑在该行分到的机器上的算它的回归结果，跑在另一台机器上的算换机器复核；其余 `regress-final` 是 d5fc2fa 上先跑的那一部分，只留作记录。`second-sample` 是 fa706g3 对客机那一半的第二样本，也算换机器复核。`retry-*` 是失败后的重试。`final2-*` 是最终引擎上的复核，`final-*` 是 d5fc2fa 上的复核。`backlog-*`、`guest-twins`、`guest-twins-b`、`fa-shapes` 是补覆盖，单独记账，不计闭环。没有收据的 run 是派发失败：没有评级，不归入任何一类运行，只由 `build_dispatches.py` 逐条列出。
- 孪生场景归到哪一行：`build_common.py` 的 `feishu_row_of` 取「已登记场景名 + 下划线 + 后缀」里最长的那个已登记场景名，例如 `uia_param_support_filament_fdmt2` 归 `uia_param_support_filament` 所在的行。
- `build_feishu.py` 的 `--combined` 是 11-24 23:34 的 `artifacts/feishu216-audit/combined.json`（`artifacts/` 不入库，所以它不在本目录）；脚本断言全表 216 行的前 15 列与该文件逐行相同、行序不变。
- `record_rows.py` 把飞书原文（前置条件的模型、步骤 1、预期 2 以后）从仓库里的快照逐字取出来，不从记忆或别的转述里抄；「今晚的运行」一列取自 `feishu-216-ninehour.json`。
- `gcode_signature.py` 可以单独比较两个导出件：`python -B docs/runs/evidence/ninehour-2026-11-25/scripts/gcode_signature.py A.gcode B.gcode`。它按「`;TYPE:` 段 × 层 × 进给」累计挤出长度、按「`;TYPE:` 段 × 层」累计耗料，容差 0.05 mm；输出逐项差异和 `same`。

## 二、当晚复算用的脚本（原样拷贝自会话暂存目录）

`facts.py`、`negative_controls.py`、`verify_feeds_awk.awk` 是复算 agent 在 11-25 02:44–02:55 写在会话暂存目录 `C:\coil\vm_setup\ninehour_1125\recompute\` 里的文件，原样拷贝，没有改过。**它们里面的路径是当时的绝对路径**（主 checkout `C:\coil\Projects\SnapmakerOrca\external\orca-blackbox` 及其 `.worktrees\glm` 的收割根、暂存目录本身），要读的 run 号也写死在 `facts.py` 的 `RUNS` 里；换一台机器、或那些收割件不在原处，就不能原样重跑。当晚的命令（也记在两个 JSON 的 `command` 字段里）：

```
set PYTHONDONTWRITEBYTECODE=1
python -B C:\coil\vm_setup\ninehour_1125\recompute\facts.py [--verbose] [--out facts.json]
python -B C:\coil\vm_setup\ninehour_1125\recompute\negative_controls.py [--out negative_controls.json] [--keep]
awk -f verify_feeds_awk.awk <file.gcode>
```

- `facts.py` 只读地导入当时主 checkout（提交 636a733）的仓库代码，从收割的 G-code 和保存件算业务事实，把结果写到自己旁边的 `facts.json`（当晚 12.0 秒）。它的 stdout 是上级目录的 `facts_stdout.txt`。
- `negative_controls.py` 把每个 run 的保存件和导出件拷到暂存目录的 `scratch_negative_controls\` 下，在副本上做反例，再交给套件用的三种判据：`business`（`result.json` 里 `checks.business` 背后的调用）、`paired`（只有 #276，宿主侧对固定基线的配对）、`full`（`verify_saved` 跑在整个 run 目录的副本上；收割件里没有 `manifest.json` 的 run 做不了）。结果写到自己旁边的 `negative_controls.json`（当晚 33.7 秒）。它的 stdout 是上级目录的 `nc_stdout.txt`。
- `verify_feeds_awk.awk` 与仓库和 `facts.py` 不共享代码，独立数一遍按 `;TYPE:` 段和模态 F 的挤出移动，用来交叉核对 `facts.py` 的读数。

这两份 JSON 的上游是 02:55 的收割件；之后的候选运行、最终引擎回归都不在它们里面。
