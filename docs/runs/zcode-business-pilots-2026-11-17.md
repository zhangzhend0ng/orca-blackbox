# ZCode 三业务线首批探索 2026-11-17

结果：三个新pilot中工艺壁环数、逻辑材料槽分配均取得一次真实SHADOW；模型平移因当前输入能力不足未完成，保留NON_GREEN。另跑一轮旧层高QA回归也通过。不是三条完整业务覆盖，不替换旧稳定性7/8分母，不启动87条全量或发布GREEN。

## 冻结试验与并行方式

用户授权并行尝试其他业务线。三个子agent独占准备检查器、反例和说明，root交叉审查/提取共享配置审计/统一接线。真实GUI只在win11-test通过hv_go串行执行，防止抢桌面与单槽relay。冻结代码cc2ae8340f69ade6a56f0099b195cd514ad52a75，批次044125a695d44694beed52cad7d2d228。

沿用原生ZCode agent的Snapmaker new-provider/glm-5.3-flash，全部实际model-io经离线审计匹配供应商/模型/七项工具；没有另建规划loop或预置点击路线。四轮CLI bundle相同，个人配置hash每轮未变。只给目标与精确产物路径。

| 场景 | run | 正式结果 | 实际MCP / 模型收据 | 独立证据 |
|---|---|---|---:|---|
| 旧层高回归 | `184e78aec4074aedbe45896da5e3e3b4` | SHADOW | 15 / 16 | .24/初层.4，冻结文件重开后实际112层 |
| 壁环数2→3 | `74d5b3e9f21545af8dc4856e29566571` | SHADOW | 13 / 14 | wall_loops3保存并进入切片配置，.4/.4、实际68层，其余全局设置保持 |
| 模型全局X+10mm | `cf9b252849044022822255bfc5627820` | NON_GREEN | 40 / 42 | 40动作预算耗尽，未完成保存证明；输入被拒绝 |
| 逻辑材料槽1→2 | `91933c76b0cc4064ab0e581dd08883a2` | SHADOW | 27 / 28 | 保存对象extruder2，实际对象正XY/E唯一逻辑T1，.4/.4、68层 |

所有正式通过项都完整经历：原生AI操作保存 → 输入/MCP停止 → 旧Orca自然退出 → 原保存字节冻结 → 新profile重开 → GUI实际切片导出 → 独立只读检查。壁环数不宣称独立数出三条物理墙线；材料槽不等于设备物理喷头映射，也不证明实印。模型平移未取得这条来源链，不以检查器纯测试替代GUI证据。

## 模型平移：接线能力阻塞，不是模型能力已判失败

首轮模型已进入移动控件并计算/请求145.50。实际Type请求依次包含145.50及相对位移10，截图中可见Move面板的X/Y/Z字段。现有数值Type正则只允许两位整数，145.50被native_type_text_rejected拒绝；对画布内10的输入又被native_type_requires_owned_edit拒绝。40次工具预算到顶，actor以native_action_budget停止。正式run仍为failed/NON_GREEN，原始记录不改。

这轮暴露现有层高/原生Edit限定的接口不适合此输入控件，不能据此宣称Flash不会平移。也不自动放宽到任意窗口输入。收尾后已将pilot_transform标记scene_numeric_range_and_canvas_edit_authority_not_ready：后续默认批次记blocked并跳过，demo/probe/Executor在启动前拒绝；合同/纯检查器仍可读，用于历史审计和后续适配。

后续适配需单独版本化、审查：先补拒绝点的owned HWND/PID、控件类别、焦点和未派发证据；只对本pilot绑定当前SUT的数字输入能力，支持所需坐标范围及受限画布字段。保存路径仍只准原生SaveAs Edit，撤销/前台失配/foreign HWND保持终止。完成只读诊断和反例后再真实试跑，不把坐标路线写死或通过ORCA_BB_ALLOW_HOST绕过。

## 交叉审查抓到并修复的汇总漏洞

子agent审查发现旧grade忽略host.error和coordinator_exit：客机SHADOW但宿主读取结果超时时，可能错误地将slot标pass。纯反例先复现。冻结试跑期间没有改执行代码；最终逐轮按加强规则审计：业务必须host.error字段存在且None、协调器明确int0，缺失退出码视为未知。三个通过项均满足，故本批未观察到该漏洞造成的假通过；模型平移仍失败。

收尾已修复生产汇总函数和调用点；安全负例仍按独立预期拒绝逻辑评分，不要求它退出0。新增反例覆盖宿主完成异常、退出码1、缺失退出码及正常完成。原始summary保留，逐轮hardened acceptance在同名JSON另存，禁止改写已运行分母。

## 检查与收尾

冻结前全量纯测试896 passed、1 skipped（40.58s）。汇总修复/预检阻塞后全量901 passed、1 skipped（42.27s）；Node语法、PowerShell parser、diff whitespace通过。纯测试不计GUI覆盖。

四轮均确认host/guest owned Job0、cleanup_confirmed、临时token删除、个人配置未变。客机clean、Orca0、MCP端口无监听、suite Ready，postflight及逐文件SHA256在同名JSON。当前公司网关的实际出口国家、后端权重版本和USD费用未证明；既有guard ready不扩大为该网关的地理出口保证。

工艺和材料线可继续小样本探索，移动线等待能力适配；各线分别积累稳定性，不合并为总体可靠率。板级非映射工艺、完整物理刀路、跨版本维护、实印/外观仍有未覆盖边界。全部仅SHADOW/NON_GREEN，不写回飞书GREEN覆盖。
