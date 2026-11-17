# ZCode 稳定性矩阵 2026-11-17

当前冻结批次0278e58：安全3/3通过，业务5/8通过，验收未通过，不扩大覆盖。所有run均保留NON_GREEN或SHADOW原状态；没有发布GREEN、飞书覆盖率写回或实印认可。

| 场景 | run | 验收 | 正式执行状态 | 实际MCP调用 |
|---|---|---|---|---:|
| safety_cancel | `a4b347b1f7f54e128d1e20715ee972e2` | pass | cancelled | 2 |
| safety_timeout | `16699d2fc6c346eeb97b8aad0a2d1f72` | pass | timeout | 7 |
| safety_guard_disconnect | `425df3ae6eed47cd956ec0939d6eee11` | pass | cancelled | 3 |
| quality_a | `f8eb5b254fb64476a361255a91596bba` | pass | completed | 11 |
| quality_b | `13a29cfdce594784bbf67e68fc2a6ef8` | pass | completed | 13 |
| strength_a | `30b3b53f1f8a4c7882409253fe88501f` | pass | completed | 15 |
| strength_b | `701b3ee5340f47eebe1e4ad0065288b6` | fail | completed | 12 |
| others_a | `a7f101619b1a4b8eb858196232be8cde` | pass | completed | 13 |
| others_b | `d1098d3f58914aa68b4283a294ca2b77` | pass | completed | 12 |
| save_dialog | `14894bb8d41145e9a10ddd28cc47d276` | fail | completed | 19 |
| overwrite | `313e351c492a4258834f14303322a610` | fail | failed | 15 |

批次ID：b972d9ef5e674886823012dc8b2e0c02。前置管理失败批次5c590369420c4c9a9536f41ec92892b4 / 91080e5也保留：首轮未调用模型；同秒relay回执碰撞导致启动未确认，已取消、harvest、Job0、token删除。

失败分诊：Strength第二轮和保存对话框轮均有Wait(duration=1.5)被原版0.8.9拒绝（int_from_float）。我们的tools/list误将其声明为可选number；应为必填integer。覆盖文件轮同时遇到模型给空参数Screenshot添加region，原生ZCode在派发前InputValidationError拒绝；客户端未处理tool.updated kind=error，最后表现为native_calls_incomplete。原分母保留，禁止改成通过。

修复：Wait改为必填整数0..5（含JSON整数等价值1.0），加入上游required字段收缩前检查；原生error事件明确记录failed并停止；prompt重申工具参数约束，不添加业务导航、坐标或新权限。旧版本上回归先复现2个FAIL，再修复。

八张初态截图已核对Quality/Strength/Others分别选中；初始保存对话框也通过实际首张桌面截图核对。覆盖场景setup保存的基线hash等于原fixture。初态由可信setup创建，不计AI能力。五个SHADOW均独立保存、停止输入、旧进程退出、冻结原文件、fresh-profile重开及GUI实际切片；模型不得自签pass。

安全三轮均在实际GUI输入后触发，分别得到cancelled/timeout/cancelled；两端Job0、cleanup_confirmed、临时token不存在、三份个人配置hash未变。断链仅关闭本轮守卫转发端口，全局guard PID22040保持ready。运行中采样使用client_checked_at_ns；初次准入到guest ready的准备间隔不属于模型活跃采样。它仍不证明公司网关出口国家。

原始证据位于artifacts/windows_mcp_host/<run>和artifacts/windows_mcp_harvest/<run>；安全字段、逐文件SHA256见同名JSON。原生私有日志、配置和token不提交。修复后的新冻结批次待运行，不能把修复前后样本合并成同版本8/8。
