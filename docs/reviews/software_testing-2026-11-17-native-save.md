# Native Codex 编辑保存 demo：实现审阅

结论：APPROVE for controlled guest trial；实现后两轮真实执行中，首轮 NON_GREEN 保留，修复收尾宽限后第二轮完整 SHADOW。范围仍为固定 win11-test、单个业务目标，不宣称生产安全隔离或已覆盖87用例。

## 范围与 harness

执行层复用原生Codex与原版Windows-MCP；新增一个run_once执行适配器和独立只读verifier，不建第二套调度器。AI只负责编辑保存；停止MCP后自然关闭旧SUT、冻结3MF，再由可信GUI步骤重开切片导出。前置harness加载包括harness-driven-review、tool-calling-and-agent-control、input-validation、error-handling、risk-and-verification-plan、testing-strategy、pytest-patterns、AI evaluation；日志写入另按logging-standards收紧拒绝参数记录。未改上游、未读写认证、不触碰用户launcher/profile/farm_runner/draft。

- input-validation Items 1–4（N）PASS：精确工具/参数类型/数值及路径白名单；禁全局快捷键、任意Type文本与截图落盘。CLI run ID严格32hex；PS动态数据仅受限ID、Git SHA及引号编码路径，JSON/base64参数化。报告字段对exit/count使用精确int；三方文件解析有界、失败不通过。
- tool-calling Items 1–7（C/A）PASS for trial：保留原版通用原语，不传模型坐标或唯一顺序；输入门禁在真正交互MCP进程执行，核会话、前台与owned PID/HWND。模型无Shell/App/FileSystem工具。40次/600秒Actor、900秒guest合同；模糊动作不自动重发；现有用户已授权本次宿主登录态。身份隔离尚未交付，未复制auth至guest。
- error-handling Items 1–7（C）PASS：异常持久化；模型/服务与SUT分开停止，确认MCP owned Job=0后才自然关闭旧SUT。worker退出仍留后代时有界终止本Job。完成信号原子发布，host result半写时有界等待；异常也进入取消/harvest。
- logging Items 1–5（N/C）PASS：run ID关联，结构化日志，拒绝的Type/Shortcut参数不原样落日志；只记录已经验证的数值/固定路径。Token仅guest本轮随机产生，不收集、不回传认证原文。上游工具日志限本次无敏感夹具客机，不声称通用日志DLP。
- AI evaluation Items 1–7（C/A）PASS for scope：固定合同/SUT hash/fixture与工具，确定性3MF与挤出层序oracle，原生调用和AI文字分离。当前用例只验证layer/initial/geometry/support/raft/spiral/printer/nozzle等明确不变量，不声称所有配置逐项等价。开发单测不是GUI分母。
- risk-verification Items 1–5（C/A）PASS：权限/进程/证据属高风险；纯策略反例、文件来源反例、旧runtime回归、PS parser先行，真实UI只走hv_go。
- testing-strategy / pytest-patterns（C/A）PASS with scope：全仓760 passed/1 skipped；新增26个纯策略/真实文件解析挑战；Windows会话、Type控件命中、原版MCP私有API兼容及自然退出仍需真实guest实测。此批不以金字塔比例证明质量。

## 独立审查及闭环

GPT-6 Astra独立只读审阅本次源码，原提出三项C/HIGH，协调者修复后已复核允许受控试验：

1. Host source漂移：HOST_SOURCES执行文件逐项git ls-files并git diff --quiet HEAD；不要求用户已知dirty清零。客机clean HEAD必须一致。
2. host_done半写竞态：CreateNew pending写完后Move；worker ready/scope同目录rename。result读取验证完整JSON后才返回。
3. actor pre-try初始化异常绕过回收：import/调用均纳入捕获，非0路径发送本run cancel，有界等待后harvest并保留summary；不把缺result记成功。

残余边界：启动确认超时可能已开始，禁止直接重跑，需检查该run与owned进程。现有canonical-root锁不隔离同权限恶意进程；焦点check→SendInput存在TOCTOU；--no-control仅用于独占客机，不能推广共享宿主。只读verifier不能代替输入前的权限限制。费用/实际模型ID未返回则unknown。登录态/凭据目录隔离与后续稳定性矩阵不在本次正例完成声明内。

## 实测前验证状态（历史）

- python -B -m pytest unit_tests -q：760 passed, 1 skipped（23.74秒）。
- 后续受影响专项：73 passed；Python compile与hv_go/hv_harvest PS parser通过。
- 真实GUI：NOT VERIFIED，下一步冻结提交、同步后运行唯一入口 tools/native_save_demo.py。

最终提交前全仓纯单测：765 passed, 1 skipped（22.10秒）。独立审查三项修复后再次复核：允许固定客机单次受控试验，无残余阻断。拒绝参数日志另已收紧；本阶段仍不作为生产日志/权限隔离认证。

## 首轮真实执行：NON_GREEN（保留）

run 61746aad8bb94c6381a7c96693eb4139，源码 c9f86aa。原生Codex九次工具调用全部成功，GUI编辑并另存工程；MCP Job停止后，旧SUT自然exit0，冻结同hash文件，新profile重开后可信GUI切片导出，新SUT也exit0。worker error=null；宿主独立离线检查确认3MF层高.24/初层.4、8顶点12三角形几何不变，G-code实际112层、首Z.4、末Z27.04。

整轮仍为NON_GREEN：NativeHandle在worker exit0而Job active>0的短暂窗口立即cancel，process收据forced=true，runtime正确阻止晋级。尚未识别具体辅助进程或Job记账延迟，不归因SUT缺陷。修复为exit0时给10秒自然清理窗口，非0或逾期仅终止本Job。新增两条可控时钟回归验证自然退出不强杀、持续残留有界终止（58项受影响测试通过）。原始结果不重标；下一轮新run重测。

## 第二轮真实执行：SHADOW

run f3efeea0073b4e488c6d00e42acd1382，冻结源码5b378ccc06a2232b2102965fada5d176f28791eb。原生Codex十次MCP调用完成编辑及GUI保存，本轮点击Save，首轮使用Enter；检查器未限制唯一合法动作序列。独立验证path/business=pass，verified_pass=true，cleanup_confirmed=true；进程exit0、Job active=0、forced_termination=false，旧/新SUT均自然exit0。visual=unknown，release_eligible=false，结果仅SHADOW。

最终全仓纯单测767 passed、1 skipped（22.45秒），Python compile和两份PowerShell parser通过；单测不计真实GUI分母。harvest完成后客机复核：源码仍为冻结提交且clean、Orca进程0、suite Ready、本轮临时MCP token已删除。报告与原始产物hash见[运行记录](../runs/native-save-2026-11-17.md)。依据收尾规则，SHADOW/NON_GREEN不写入飞书GREEN基线。八次真实矩阵、真实中途取消与身份隔离仍未验收。
