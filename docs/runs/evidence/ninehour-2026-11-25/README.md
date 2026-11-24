# 九小时一轮（2026-11-25）的证据包

T0 是 2026-11-25 01:29:12（北京时间）。三台机器从 636a733 起跑，合并提交是 d5fc2fa（引擎 e3bfdfe）。本目录只放文件和由文件生成的表；叙述见[运行记录](../../glm54-nine-hour-run-2026-11-25.md)。**本轮没有发布 GREEN**：客机 win11-test 是回归证据机，fa706g3 和 Mac 的结果最高记 SHADOW（README「跑批纪律与收尾」第 6 条）。

刷新本目录的顺序（都在 d5fc2fa 的 checkout 根目录，`set PYTHONDONTWRITEBYTECODE=1`）：

1. 复制台账：`cp C:/coil/vm_setup/ninehour_1125/ledger.jsonl docs/runs/evidence/ninehour-2026-11-25/ledger.jsonl`（台账在跑批期间一直在长，复制时刻决定下面各表的范围）。
2. 出收据：`python -B tools/ninehour_receipts.py C:/coil/Projects/SnapmakerOrca/external/orca-blackbox/artifacts/windows_mcp_harvest --runs <台账里收割目录下有 result.json 的 run id，逗号分隔> --ledger docs/runs/evidence/ninehour-2026-11-25/ledger.jsonl --json docs/runs/evidence/ninehour-2026-11-25/receipts`，stdout、stderr 分别存成 `receipts-table.md`、`receipts-notes.txt`。收据工具只读收割件。
3. 依次跑 `scripts/` 里的 `build_stage.py`、`build_native.py`、`build_family.py --repo .`、`build_feishu.py --repo . --combined <combined.json>`（命令见 [scripts/README.md](scripts/README.md)）。

## 文件

| 文件 | 内容 | 怎么来的 | 限度 |
|---|---|---|---|
| `ledger.jsonl` | 会话台账的原样副本，一行一个 run：机器、场景、标签、run ID、提交、起止、秒数、评级 | 第 1 步，复制于 2026-11-25 04:44（72 行、71 个 run） | 同一 run ID 以最后一行为准。fa706g3 在 02:25–02:43 的 4 条没有记提交号；两条没有收割件（`467e62b1` 启动被拒，`91175532` 场景名带 CR）；`retry-*` 标签是回归里失败后的重试，算作同一行的回归运行；最终引擎回归在复制时还在跑 |
| `receipts/<run_id>.json` | 每个收割到的 run 一份收据：身份、评级、各口径秒数、阶段行、产物哈希复核，每个值都注明来自哪个文件的哪个键 | 第 2 步，`tools/ninehour_receipts.py`（69 份） | `null` 表示没有、不写成 0。fa706g3 的收据没有宿主整轮秒、没有 `teardown.json`；收据里的 `run_dir` 是本机收割件的绝对路径，收割件不在时无法复核 |
| `receipts-table.md` | 上一步打印的全部 run 的一张表 | 同上，stdout | 秒数四舍五入到三位小数；精确值和出处看 JSON |
| `receipts-notes.txt` | 上一步写到 stderr 的说明：缺了哪些文件、哪些配对是离线补的 | 同上，stderr | — |
| `stage-timings.json` | #276、#264 各场景各机器的逐 run 秒数、叶段和父段的逐阶段秒数、整轮比较、导出件与保存件对照、切片复现 | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_stage.py` | 636a733 的 #264 日志没有阶段行，阶段参照是计时版；fa706g3 的整轮用机内进程秒；fa706g3 计时版 `76b85931` 的提交号台账未记 |
| `stage-timings.md` | 同上的人读版：口径、每组一张 run 表、叶段表、父段表、整轮表、切片复现 | 同上 | 父段 `field.*` 不与子段相加；样本每格一到两次 |
| `negative-controls.json` | 判据的反例结果：319 条对照，其中 41 条是「该拒不拒」 | 复算 agent 02:55:26 写在会话暂存目录，原样复制；命令见 `scripts/README.md` | 只覆盖 636a733 上 #276、#264 的基线 run；在副本上做；fa706g3 的 run 收割件里没有 `manifest.json`，整目录验证器没有跑 |
| `facts.json` | 从收割的 G-code 和保存件算出的业务事实：目标值、回显、层、悬垂与桥接段的 F、对基线的逐类型比较，逐项带文件哈希 | 复算 agent 02:55:38 写在会话暂存目录，原样复制 | 只读了 9 个 run（当晚 02:55 之前的 #276、#264 基线和两份对照基线）；候选运行和最终引擎回归不在里面 |
| `facts_stdout.txt`、`nc_stdout.txt` | 上面两份 JSON 生成时打印的人读摘要 | 同上 | — |
| `scripts/` | 五个生成脚本（含给运行记录出逐行表的 `record_rows.py`）和 `gcode_signature.py`；当晚复算用的 `facts.py`、`negative_controls.py`、`verify_feeds_awk.awk` 的原样拷贝 | 见 [scripts/README.md](scripts/README.md) | 复算脚本里是当晚的绝对路径和写死的 run 号 |
| `native-pairing.json` | 两次原生模型运行（glm-5.4）：场景、工具调用按工具计数、失败签名、宿主秒数，以及本该与之配对的 Script run | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_native.py`，读 `windows_mcp_host/<run_id>/host.json`、台账和收据 | 只取 `host.json` 里有的；没有读会话库，所以没有模型请求数和 token（`findings-sheet.md` 记的是 11 次和 42 次请求）。配对为 0 |
| `mac/` | Mac 线的台账、8 次探针日志、03:42 的控制台会话列表、一张截图 | 原样复制自会话暂存目录；见 [mac/README.md](mac/README.md) | 首次运行的 run 号和 NON_GREEN 只见于 `findings-sheet.md`；没有收割件 |
| `feishu-216-ninehour.json` | 11-24 的 216 行对照表（行序、前 15 列原样）加 7 个新列；`summary` 是四类汇总，`touched_detail` 是每个触及行的 run 清单 | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_feishu.py --repo . --combined C:/coil/Projects/SnapmakerOrca/external/orca-blackbox/artifacts/feishu216-audit/combined.json` | 源表 `combined.json` 不入库（它的 sha256 记在 `source_table`）；没被本轮触及的行新列全是 `null`；回归行只填台账复制时已有的结果 |
| `feishu-216-ninehour.md` | 上表里被触及的行 | 同上 | 未通过项只写文件里查得到的 |
| `family-regression.json` | 参数族 42 行在最终引擎上的回归：每行的场景、机器、顺序、run 和结果 | `python -B docs/runs/evidence/ninehour-2026-11-25/scripts/build_family.py --repo .` | **占位，回归进行中**；没有结果的行留空，由总控在结束后补入 |
| `family-regression.md` | 上表的人读版：两台机器各 21 行的场景名 | 同上 | 同上 |
| `findings-sheet.md` | 总控整理的事实表（03:51 版），每条带来源 | 原样复制自会话暂存目录 | 它是总控的笔记，不是这里重算的；凡只有它作来源的地方，运行记录里都注明 |

## 这份证据包不能回答的

- 发布评级：没有一条是发布 GREEN；fa706g3、Mac 最高 SHADOW。
- 飞书预期的逐项核对：今晚只对 #276、#264 读了 G-code（`facts.json`），其余行的运行只过了脚本自检。
- 引擎改动之外的行为：切片本身在同设置下不完全可复现（`stage-timings.md`「切片复现」），原因没有查。
- 人工分钟、排队时间：没有记录；台账能算出的机器占用见运行记录。
