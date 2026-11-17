# 原生 Codex 编辑保存：真实运行记录

2026-11-17，在 Hyper-V `win11-test` 真实执行两轮。第二轮完整通过独立验证，结果 **SHADOW**；首轮 **NON_GREEN** 原样保留。代码与方案已落盘并推送 `software_testing`，未覆盖用户原有 launcher/profile/farm_runner/draft 改动。

## 结果及执行边界

| 项 | 首轮 | 第二轮 |
|---|---|---|
| run ID | `61746aad8bb94c6381a7c96693eb4139` | `f3efeea0073b4e488c6d00e42acd1382` |
| 源码 | `c9f86aa2573501b0698b79dd4ae4414aaa9d5403` | `5b378ccc06a2232b2102965fada5d176f28791eb` |
| 原生 MCP 调用 | 9 | 10 |
| 业务文件离线复核 | .24 / 初层 .4，几何不变，112层 | .24 / 初层 .4，几何不变，112层 |
| runtime 结果 | NON_GREEN，收尾强杀 | SHADOW，verified_pass=true |
| cleanup_confirmed | 不作成功认定 | true，进程自然退出、Job归零 |
| release_eligible | false | false |

AI 仅收到业务目标和本 run 的完整保存路径，没有预置坐标或菜单步骤；原生 Codex CLI 使用原版 Windows-MCP 定位、编辑和保存。第一轮通过Enter保存，第二轮点击Save；没有用唯一动作顺序判断业务成功。

MCP输入停止后，可信阶段自然关闭旧Orca，冻结AI保存的同一3MF，新profile重开该副本并GUI切片导出。独立只读检查器检查3MF配置/几何及实际G-code挤出层序，结果为常规层高0.24、初层0.40、112层、末Z27.04。AI没有负责独立重开阶段，也不能直接写通过结论。视觉验收未执行；本次不证明实物打印效果。

首轮worker已自然完成，但执行器在worker exit0、Job仍短暂active时立即cancel，造成forced=true；整轮因此保留NON_GREEN。未识别具体辅助进程或Job记账延迟。修复为exit0时给10秒自然清理宽限，逾期仍仅回收本Job，再以新run重测。第二轮process收据exit0、active_processes=0、forced_termination=false，旧/新SUT均exit0，MCP与宿主CLI Job归零。

## 证据与版本

第二轮冻结3MF SHA256：`31dcf6da4352cdd35f3c37a66a66effc65858ad86653cde33cb7b0fa895cc0b5`。

第二轮G-code SHA256：`6c70436d1eefd02a5e01eb8889e131bf962f124c5702bcdea7d7a6423ee028bc`。

SUT SHA256：`5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf`；原版Windows-MCP 0.8.9，客机运行时Python 3.14.10；宿主原生CLI SHA256：`094d4db493de22025712cc5963854e7654b7c97f4cee795e3e986270a0f4f6b4`。完整证据索引及逐文件hash见[机器记录](native-save-2026-11-17.json)。原始大产物保留本地artifacts，不提交二进制文件。

- `artifacts/native_save_demo/<run>/summary.json`：入口与统一结果。
- `artifacts/windows_mcp_host/<run>/`：原生CLI日志、prompt与工具收据。
- `artifacts/windows_mcp_harvest/<run>/`：回收的3MF、G-code、截图、合同、结果、进程收据与原生轨迹。
- 客机原始根：`C:\coil\orca-blackbox-v3-r1\artifacts\v3\<run>`。

收尾复核确认客机clean、Orca进程0、suite Ready，第二轮临时MCP token已删除。用户原有宿主Codex登录态按本次授权复用，未复制认证到客机、未修改全局认证配置。实际模型标识及USD金额未返回，均记unknown。

原生CLI usage：首轮input 160736、cached input 132864、output 620、reasoning output 13；第二轮input 160887、cached input 140416、output 636、reasoning output 16。缓存属于input子集，不再相加；这些计数不是美元金额。

## 复跑及后续门槛

宿主入口：`python -B tools/native_save_demo.py`。前提为提权relay可用、两端同一已提交HEAD、客机clean且原版运行时已安装、桌面空闲；GUI仍只经`hv_go.ps1`启动。遇启动确认不明，先检查对应run及owned进程，禁止直接重复启动。

本次最终纯单测767 passed、1 skipped；Python编译与PowerShell解析检查通过。两个真实run都保留在分母，一次NON_GREEN、一次SHADOW。尚未执行三种初态各两次加两个干扰的八次矩阵，未验收真实中途取消或长期身份隔离。本次不代表87条回归或发布GREEN；不向飞书GREEN基线写回。下一阶段及停止条件见[冻结路线](../V3_NATIVE_SAVE_DEMO.md)。
