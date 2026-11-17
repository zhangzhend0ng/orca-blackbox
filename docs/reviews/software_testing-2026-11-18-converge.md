# v3 收敛实现审查（2026-11-18）

适用协议：harness-driven-review Part A/B；已加载 tool-calling-and-agent-control、input-validation、logging-standards、AI evaluation、risk-and-verification。用户授权并行实现与真实客机试验，原有账号/代理/守卫保持不变。

应用清单：`common/ai/tool-calling-and-agent-control.md` Items 1–7 PASS（高影响试验沿用本会话授权）；`common/security/input-validation.md` Items 1–4,6–7 PASS，5 N/A（无上传入口）；`common/ai/ai-evaluation-and-regression-strategy.md` Items 1–7 PASS（真实能力与发布门槛仍待验）；`common/planning/risk-and-verification-plan.md` Items 1–5 PASS。`common/logging/logging-standards.md` Items 1–4 PASS；5–7限定为可信隔离客机开发证据，非生产ACL/日志服务，私有原生日志不提交。

## 范围与条件

- (N) 输入边界：模型不选approval/profile/检查器；固定registry、run/contract/scope绑定，保留数字/精确保存路径白名单。PFD缺失不自动降级。
- (C) 行为权限变化：永久fatal闩锁适用于所有新运行；有限恢复仅新`recovery_owned_edit`/`canvas_trial`合同，旧严格合同和历史7/8不重判。
- (C) 独立验证：原保存/自然退出/冻结/新profile重开切片链保留；新恢复逐行重放；画布原始观察按hash重放，每次Type核对父链、焦点、几何、ctime、桌面及同位置Click。
- (C) 并发：server lock和同步bridge串行实际dispatch；driver检测并行native调度则拒绝该run。这是事后检测意图，不保证在所有排队请求派发前阻断并行意图。
- (N/C) 日志：只记录校验后的数字/路径/按键与受控窗口证据；配置与认证不提交。trace写失败也锁存fatal。原生个人日志留本地，非OS ACL安全沙箱。

## 交叉审查发现与处置

| Tier | 发现 | 修正/证据 |
|---|---|---|
| C | b6试验外部窗口拒绝后仍继续调用 | guest持久revoke/abort；worker停MCP；host读取受信bridge回执，不信原生包装的成功文本 |
| C | trace写失败后还可派发 | 日志异常锁存fatal；目录故障反例证明第二次不派发 |
| C | scope场景字符串即可启恢复 | server交叉canonical contract/manifest/run/actor/scenario/output/PID/HWND |
| C | sidecar额外尾/半行/重复调用可能被忽略 | 每条seq/tool/run/request ID、终态记录数、非空原生call ID、重复事件及并行检测反例 |
| C | canvas中间父窗禁用未检查 | 父链每层owned/visible/enabled/DPI/geometry |
| C | 后续业务失败抹去已发生恢复 | verifier异常分支和runtime cleanup均保留独立recovery flags；无记录恢复仍拒绝 |

## 验证

- 主纯测试（排除已单独运行的driver新协议文件）：1206 passed，1 skipped，41.40秒；skip是宿主无symlink权限。
- driver新协议：34项独立fake Node测试均通过（31项组和3项ID反例分开执行）；另交叉专项106 passed有重叠，不重复累计。
- Node语法、hv_go/hv_harvest PowerShell parser、diff whitespace通过。
- 纯测试不计GUI。尚需冻结客机真实`authority_probe`验证原版FastMCP结果和致命拒绝后未派发；随后`recovery_owned_edit`和`canvas_trial`串行实测。

## 结论

静态/纯测试层面无剩余已证实N/C阻断，可做已授权受控试验。不是发布放行；普通`pilot_transform`仍blocked。画布仅明确授权已观察专用控件的有限数字尝试，`pfd_verified=false`、`internal_numeric_field_verified=false`，Click令牌不证明内部字段编辑态。最终3MF/实际G-code不满足则保留NON_GREEN。泛化评估必须等本能力阶段验收再冻结，不能用开发集冒称未见任务。
