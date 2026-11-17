# Orca 桌面 AI 自动化测试选型调研

调研日期：2026-11-17。范围：Windows 原生 Snapmaker Orca，包含 wxWidgets、自绘控件、原生文件对话框、WebView 和 GL 画布。目标是复用已经提供测试执行能力的系统，减少自建 agent 的投入。

## 决策结论

推荐停止扩展当前手写的模型动作循环；采用现成 AI 测试系统做执行层。首个可执行的开源候选是 **Midscene Test 1.18.0 + Computer 平台**，商业产品只保留 **AskUI Desktop** 作为第一对照。现有 Hyper-V 隔离、run 身份、独立 3MF/G-code 检查和失败记录继续保留。

这是有证据支持的选型方向，不是已经完成 Orca 兼容性验收或采购的结论。本次完成公开资料、官方部署/限制文档、源码说明、许可证及发布元数据核验；没有安装候选、注册试用、联系供应商、购买许可证或将项目上传到第三方。

直接选择 Midscene 完整测试 runner，避免再用 Deep Agents/LangGraph 拼装另一个 agent，也避免只取 Midscene 的定位 API 后继续自建循环。若团队明确愿意用商业平台换取更低维护负担，AskUI 是优先试用的成品应用；正式采购必须先通过下述同一组 Orca 验收。

## 1. 本项目真正需要解决的问题

此前实现证明模型、客机工具与检查器可以连通，也取得固定业务的 SHADOW 结果；它主要采用明确步骤、窄业务工具和逐步图像推理。该结果不证明自主规划、自由探索或跨版本适应能力。

选型必须分别回答：

1. **目标执行**：只给业务目标与约束，系统是否自行寻找入口、分解动作、根据最新状态调整计划？
2. **测试生产**：能否根据需求与探索生成可复用的测试候选，而非仅执行人工写好的逐步操作？
3. **探索发现**：能否在预算内发现新的状态或失败，给出可验证的复现材料？
4. **业务判定**：如何证明保存内容、重开来源和实际切片正确，而不仅是画面看起来正常？
5. **运行工程**：是否已有 runner、报告、超时、清理、CI、状态保存和可取消执行？

支持 Windows 的测试编辑器，不一定能测试 Windows 原生应用；支持原生应用，也不自动代表支持其自绘/GL 区域。自然语言、视觉定位、自动生成脚本、自主目标执行和无脚本探索也必须分别记录。

## 2. 证据方法与边界

- 优先使用官方产品手册、已发布包、源码和限制页面；市场宣传仅作为能力声明。
- 将“官方声明支持”“源码/包可确认”“本项目已实测”分开。本次第三方候选均未取得 Orca 实测结果。
- 对冲突资料优先使用当前打开的官方价格页和版本化文档，保留需要供应商澄清的部分；不引用搜索摘要中的旧价格作采购依据。
- 没有找到原生 Windows 支持证据，记为未确认，不能直接断言产品永远不支持。
- 星数用于说明社区规模，不作为可靠性评分。第三方成功率和厂商基准不转换成 Orca 通过率。

包与源码元数据原始快照保存在本机 `artifacts/research/2026-11-17-ai-testing/`，未作为运行回归证据。公开可复查入口为 [npm test 元数据](https://registry.npmjs.org/@midscene/test)、[Computer 元数据](https://registry.npmjs.org/@midscene/computer)和各仓库原始文件。

## 3. 候选全景与筛选

| 候选 | 实际定位及核实情况 | 本项目处理 |
|---|---|---|
| **Midscene Test / Computer** | MIT；现成自然语言 E2E runner、目标动作、断言、报告与桌面平台 | 开源主选，优先做 Orca 试点 |
| **AskUI Desktop** | 商业成品应用；编写/运行/查看自然语言测试，Windows、CLI、调度与部署选项 | 商业第一对照 |
| **testRigor** | 商业平台；明确支持 Windows Remote Desktop；桌面 teardown 需显式处理 | 第二梯队，RDP/GL 与清理成本先核验 |
| **QA Wolf** | 商业平台/服务；已公布原生 Windows runner、干净 VM、应用投递、录像 | 如考虑托管测试团队再评估；GPU/自绘适配未证明 |
| **TestDriver** | 公开 SDK + 商业服务；Windows 属 Enterprise；self-host 不等于整个平台本地化 | 不以低价 Pro 或公开 SDK 误判为本地完整开源系统 |
| **mabl** | 新发布说明已出现 Windows app training/Driver，旧 Desktop App 概览不能反映全部新能力 | 保留观察；需明确桌面功能可用范围及自绘支持 |
| **Eggplant Functional + DAI** | 成熟商业视觉/模型化测试；可探索不同路径，但需建状态模型并提供操作片段 | 需要系统化模型覆盖、能接受建模成本时考虑 |
| **Tricentis Tosca / Vision AI** | 商业企业平台；有 Agentic Test Automation 与 Vision AI，需云/混合组件 | 无既有采购和运维体系时不作为轻量首选 |
| **TestComplete** | 成熟 Windows GUI 产品，官方有 wxWidgets 支持说明；深入内部对象需特定构建/调试信息 | 传统桌面兜底候选，不能视作已经解决自主探索 |
| **Squish** | 成熟 GUI 工具，AI Assistant/MCP 可协助生成和修复脚本；MCP 为技术预览 | GUI 引擎有价值，Qt 优势不能直接外推到 Orca wxWidgets |
| **Katalon Studio** | 10.4+ 桌面驱动基于 FlaUI，支持 Win32/WPF/WinForms/UWP | 适合低代码/对象测试；自绘和目标驱动能力另验 |
| **UiPath Test Cloud / Autopilot** | 产品总体有桌面自动化；但当前 Autonomous Test Execution 手册明确仅 Web | 不作为 Orca 自主执行主选 |
| **OpenText Functional Testing** | 成熟多技术栈工具，提供 AI/OCR 对象识别和生成式检查 | 企业传统工具候选，不能把对象 AI 识别等同自主测试员 |
| **Appvance AIQ** | 有 Windows Desktop Designer 及 Autonomous Testing；公开材料尚不足以证明二者在任意桌面应用上同等适用 | 待专门桌面演示，不据产品菜单名称下结论 |
| **TESTAR** | BSD-3 主项目；现成无脚本 GUI 探索，依赖可获取的 GUI 状态与所配置的检查 | 开源探索研究候选，不直接解决几何/G-code 业务语义 |
| **Microsoft AutoGenesis** | 原始 LICENSE 为 MIT；Windows pywinauto MCP + BDD/编辑器集成 | 较早期，仍有工具与用例工程，不优于本次主选 |
| **Argus / Pantomime** | 小型开源项目；Argus 宣称 runner、roam 和 Hyper-V Capsule；Pantomime 是 Windows 自然语言测试 | 功能方向相关，独立验证和维护证据不足，不作生产主依赖 |
| **UFO / Deep Agents / LangGraph** | 桌面 agent 或通用编排能力 | 可研究架构，当前不以它们重新搭测试平台 |
| **UI-TARS Desktop / Agent TARS** | 热门公开仓库已 archived，API 元数据亦确认 | 不作新增主依赖；模型与整个产品维护状态分别判断 |
| **TestSprite / Momentic / Playwright Test Agents** | 有自动测试生产/执行能力；本次核实的主要支持范围为 Web/API 或移动平台 | 未确认 Orca 原生 Windows 适配前不列主选，不能用浏览器测试代替原生测试 |

上述逐项依据见第 8 节；表中的“处理”是本项目的工程判断，不是厂商给出的排名。

## 4. 两个主候选深入核验

### 4.1 Midscene Test：使用已经提供的 agent 和测试 runner

官方已提供 `@midscene/test`，用 YAML 描述意图与期望，TypeScript Node 承载精确业务操作。runner 包含生命周期、超时/重试、隔离并发与逐步报告；Computer 平台支持 Windows 原生输入及 RDP。[框架说明](https://www.midscenejs.com/midscene-test/overview)、[桌面环境](https://www.midscenejs.com/platforms/desktop)。

`aiAct` 接受目标，基于新界面持续规划；`deepThink` 将任务分解和定位拆开，重规划次数可限制。因此可直接测试“只给目标”的执行能力，无需另写下一动作 JSON 循环。[Agent API](https://www.midscenejs.com/reference/)。

本次直接读取 npm registry：test 与 computer 均已发布 **1.18.0**，许可 MIT，发布时间分别为 2026-11-16 09:59/09:56 UTC；test 要求 Node `^20.19.0 || ^22.12.0 || >=24.0.0`。仓库未归档。[test 包](https://registry.npmjs.org/@midscene/test/latest)、[computer 包](https://registry.npmjs.org/@midscene/computer/latest)。

重要限制：

- 新 runner 在 v1.12 引入时明确标 Beta；本次没有找到已转为稳定协议的承诺。核心项目规模不能当作新 runner 的成熟度证明。[更新日志](https://www.midscenejs.com/changelog)。
- Computer 的 `destroy()` 释放设备资源，不负责关闭所有受测应用。必须继续使用本项目拥有的进程/VM 清理，不能把 SDK cleanup 等同 Job 清空。[Desktop SDK](https://www.midscenejs.com/sdk/desktop)。
- Windows 不能依赖 Linux Xvfb 式无头运行；RDP 会话、分辨率及 GL 可用性需实测。优先在现有客机交互会话使用本地桌面执行，避免第一轮同时改变显示会话。
- 它提供目标执行与自然语言测试框架，不等于已经交付“给一个 exe 自动发现全部业务预期”的测试员。测试生产、探索与验收分别评估。
- 模型连接仍需先验证。不能假设旧的每步 Codex CLI 调用壳可直接替换为官方模型接口，也不能隐去额外模型费用。

### 4.2 AskUI Desktop：成品应用优先的商业对照

官方产品将测试编写、设备、运行、报告放在一个应用中，提供 CLI/CI、MCP/文件检查等扩展，Windows 由 AgentOS 驱动。测试仍需要业务前提与期望，系统内置观察、决策、操作及检查流程。[平台说明](https://www.askui.com/platform)。

公开资料还提供测试维护候选和偏航监测能力；这不证明它已能自主发现 Orca 的业务缺陷，也不证明模型报告可以替代外部产物检查。[产品说明](https://www.askui.com/)。

当前打开的价格页：14 天本机试用；Team/Enterprise 按组织及并发 agent 报价，无可据此直接采购的统一美元单价。Enterprise 列出 on-premise/air-gap/BYOM。旧搜索摘要和部分 FAQ 的计量描述存在差异，以书面报价、部署范围和合同为准。[当前价格页](https://www.askui.com/pricing)。

试用前的具体问题：可否在现有 Hyper-V 客机运行；服务模式是否保留 Orca GL 画布；能否导出原始动作/截图/运行 ID；如何调用本地独立检查器；私有模型、截图流向、离线许可与 CI 是否包含在报价中。标准桌面安装与无人值守服务的提权要求不同。[技术 FAQ](https://docs.askui.com/docs/faq/technical)。

## 5. 其他产品的关键筛除证据

| 产品 | 影响选型的具体证据 | 判断 |
|---|---|---|
| testRigor | 明确通过 Windows Remote Desktop 测原生应用；专门手册指出无自动桌面 teardown | 能用，但本项目仍要验证会话、GL 和清理；不是零工程 |
| QA Wolf | 2026-10-13 宣布原生 Windows；每次独立 VM，支持安装器和自定义镜像；示例通过 accessibility ID 找控件 | 托管能力真实；wx 自绘/GL 的关键部分仍需实际样例 |
| TestDriver | 当前价目表 Windows 只在 Enterprise；公开 SDK 声明 ISC，平台服务另有合同；self-host 说明仍保留云端 dashboard/录制等 | 公开代码不等于完整免费私有部署；不引用旧 $20/$600 摘要作当前价格 |
| mabl | 2026-11-12 2.77.0 发布说明和 CLI `desktop-tools` 出现原生 Windows 训练/执行 | 不能继续简单说它“只有 Web”；功能范围与成熟度待确认 |
| Eggplant DAI | 探索前须建 States/Actions 模型，并将 Functional 操作片段绑定到模型 | 真有自动选路径能力，但建模与片段维护是成本 |
| Tosca | Vision AI 加 Agentic 生成工具已存在，仍有租户、组件和部署前提 | 与轻量开源 runner 不是同一采购/运维量级 |
| UiPath | 自主执行手册明确排除 desktop，且该模式不能由 schedule/CLI/API 启动 | 总体桌面支持不能推导该自主模式适合 Orca CI |
| TestComplete | wxWidgets 深层访问的官方路线包含 wrapper 或 Debug Info Agent，并可能要求调整构建 | 会接触内部对象的检查必须与本项目 release 黑盒证据分账 |
| Squish | AI Assistant/MCP 使用已有 GUI 引擎生成脚本，MCP 明确技术预览；快照能力首先优化 Qt/QML | 不把 AI 代码辅助与现成自主 Windows 测试系统混为一类 |
| AutoGenesis | Windows 路线为 pywinauto MCP，配合 BDD/编辑器；默认有遥测；原始 LICENSE 为 MIT | 可参考，仍有对自绘、用例资产和治理的接线工作 |
| Argus | PyPI 0.1.8、MIT；README 说明 roam/Hyper-V，并明确 roam findings 当前未调用 Capsule failure-retention hook | 功能方向贴近，证据保留的已知缺口和很小维护规模使其不宜直接承担主回归 |

## 6. 与现有工程怎么衔接

### 成本与采购口径

| 候选 | 查询日的可核验成本边界 |
|---|---|
| Midscene Test | MIT 包，无此包许可证费；模型、Windows VM、调试及维护人时另计 |
| AskUI | 当前价格页为 14 天试用、按并发 agent/组织报价；未取得书面美元报价 |
| QA Wolf | 当前页面桌面列价 $2/run；页面将 run 定义为完整 QA cycle，计费单位、最低承诺及服务范围需写进报价，不能自行当作每个 assertion 的价格 |
| TestDriver | 当前 Pro 为 $24/seat/月另有分钟费，但该档不含 Windows；Windows Enterprise 需报价。旧索引中的 $20/$600 不用作当前成本依据 |
| testRigor / mabl / 企业传统工具 | 本次未取得适用于 Orca 部署与并发范围的可比报价，不伪造每月总价 |

对比总成本时同时记录：首次接入人时、每次界面变化维护人时、模型/平台费、VM 费、人工复核/失败分诊、数据与部署运维成本。比较每个**独立核证成功的业务目标**的总成本，不能按模型声称完成的动作数量摊薄费用。官方价格入口见第 8 节。

### 接入结构

只保留有验证价值的基础设施，不把新产品塞回旧的唯一动作序列：

```text
需求 / 测试目标 / 业务不变量
                ↓
现成测试系统：Midscene Test，或通过对照验收的 AskUI
  自带规划、观察、输入、重规划、运行报告
                ↓
隔离客机中的真实 Orca → 本 run 的项目和 G-code
                ↓
独立业务检查器 + 进程/文件来源检查 → 分项结果
                ↓
保存原始轨迹、首次失败、恢复及最终结论
```

保留：`hv_go` 的正式客机入口、桌面排他、run-owned profile/目录、冻结 fixture、OwnedJob/取消、harvest、3MF 几何与实际 G-code 检查。已有原生 Win32 工具可作兼容对照，但不作为新系统的唯一业务路线。

替换：`harness/agent_model.py` 的逐步 CLI 推理、`v3_agent_host` 的人工动作循环，以及仅为固定业务步骤编写的 prompt。旧能力和历史原始结果保留作回退，不回写为新框架已通过。

必要的本项目扩展仅限：初始化/关闭受测进程、运行目录、读本次产物、独立验证和采集框架报告。工具接口的适配依然是工程工作；不再写自己的 planner、agent memory、恢复决策或另一个测试 runner。

现有 runtime 对 exact executor/verifier 与固定契约摘要有门禁，新执行器必须通过正式注册适配接入。新任务契约按业务因果关系与必要证据验收，不写死所有观察/点击的 seq 或唯一工具序列。原固定契约继续保持原含义，不能直接放宽旧裁决。

## 7. 实施顺序与退出条件

### 第一步：模型与桌面能力烟测

固定 Midscene 1.18.0、模型与配置，先只确认客机截图、鼠标键盘、取消、文件对话框、GL 画面和报告可取。所有 GUI/探针仍由 `win11-test / hv_go` 正式入口运行，不在宿主试点。

这一步不生成业务通过率；若不能用现有交互客机工作，先记录具体限制，不同时改模型、显示通道和业务用例来掩盖原因。

### 第二步：用现成系统证明目标驱动

使用已有可独立核证的三个业务目标：页签状态转换、参数修改影响实际重切、修改跨进程保存重开。每个目标预登记三个初始界面变体，例如 Prepare、Preview 和设置区非目标位置，共 9 个新运行；这些是三个业务任务的状态变体，不记成九种业务覆盖。

给模型：目标、夹具、目标值、禁止改变的配置、允许输出目录和预算。不给：控件坐标、菜单点击列表、保存/导出内部步骤、唯一下一工具顺序。

每个候选另做四类独立负例：修改相似错误参数、漏重切、漏重开、旧/冲突产物。原始失败与首次尝试全部保留。固定注入不算 AI 成功；没有命中指定错误的无关失败也不算检错成功。

建议试点门槛：9 个正例至少 8 个业务/来源检查通过；四个负例全部被相关检查拒绝；13 次运行均确认收尾；不得出现业务失败却被最终系统接受的假通过。该小样本只用于选型，不代表生产可靠率或发布 GREEN。

逐 run 报告模型调用/实际 token、总耗时、首次失败、恢复、人工干预分钟、证据完整性。不能返回美元费用则记未知，不用零代替。每候选限定排障投入，建议最多两个工程日后做继续/停止决定；这是投入上限建议，不是已经证明的交付工期。

### 第三步：商业对照与选择

AskUI 如开展试用，使用同一目标、夹具、初态、构建、负例和独立 oracle。获取试用和报价需要组织身份/合同范围；本次未注册或联系供应商。不得为了对照把产品源码、真实用户数据或上游仓库擅自上传到云端。

若 Midscene 达标且维护投入可接受，采用其 runner 作为主线，保留当前框架作为回退；若 AskUI 达标并显著降低人工维护，总成本及数据部署条款可接受，则采用成品平台。两者都不达标时按失败部位选择 TestComplete 或 Eggplant 做有范围的桌面回归，不回到无限扩张自写 agent。

探索生成测试资产要单独验收：给同一需求区域，不预列操作步骤，检查系统是否产出新增状态、候选测试和可复现缺陷。先核实真实新增覆盖和误报，再接 CI；不能拿三个固定任务的成功声称已完成探索测试员。

## 8. 主要来源与复查索引

以下为本次实际读取的官方来源，查询日均为 2026-11-17。价格、版本及支持范围可能继续变化。

| 主题 | 官方证据 |
|---|---|
| Midscene runner | [框架概览](https://www.midscenejs.com/midscene-test/overview)、[创建与运行](https://www.midscenejs.com/midscene-test/use)、[更新日志](https://www.midscenejs.com/changelog) |
| Midscene agent/桌面 | [目标执行、deepThink、预算 API](https://www.midscenejs.com/reference/)、[Desktop SDK 与 destroy 边界](https://www.midscenejs.com/sdk/desktop)、[桌面环境](https://www.midscenejs.com/platforms/desktop) |
| Midscene 发布与许可 | [test registry](https://registry.npmjs.org/@midscene/test)、[computer registry](https://registry.npmjs.org/@midscene/computer)、[GitHub](https://github.com/web-infra-dev/midscene) |
| AskUI 产品/部署/价格 | [平台](https://www.askui.com/platform)、[当前价目](https://www.askui.com/pricing)、[技术限制](https://docs.askui.com/docs/faq/technical)、[FAQ 计费描述](https://docs.askui.com/docs/faq/pricing-licensing) |
| testRigor 桌面限制 | [Windows 与 teardown](https://testrigor.com/certification/native-desktop-app-testing-overview/)、[桌面配置步骤](https://support.testrigor.com/support/solutions/articles/154000226591-how-to-automate-native-desktop-testing-with-testrigor) |
| QA Wolf | [原生 Windows 发布](https://www.qawolf.com/changelog/windows-desktop-app-testing)、[桌面基础设施](https://www.qawolf.com/desktop-app-testing)、[当前价格与 run 定义](https://www.qawolf.com/pricing) |
| TestDriver | [当前价目与 Windows 分层](https://testdriver.ai/pricing/)、[self-host 范围](https://testdriver.ai/enterprise/)、[服务条款](https://testdriver.ai/terms/)、[SDK package.json](https://github.com/testdriverai/testdriverai/blob/main/package.json) |
| mabl 新 Windows 支持证据 | [2.77.0 发布说明](https://help.mabl.com/hc/en-us/articles/16693999329172-mabl-Desktop-App-release-notes)、[CLI desktop-tools](https://help.mabl.com/hc/en-us/articles/43605432188820-mabl-CLI-command-reference) |
| Eggplant | [DAI 必需建模与片段](https://docs.eggplantsoftware.com/dai/dai-using-eggplant-dai/)、[测试策略](https://docs.eggplantsoftware.com/best-practices/Setting-up-project/framework-design/) |
| Tosca | [Agentic 上手前提](https://docs.tricentis.com/tosca-2026.1/en-us/content/agentic_ai/get_started.htm)、[Vision AI](https://docs.tricentis.com/tosca-2026.1/en-us/content/vision_ai/vision_ai_introduction.htm)、[Cloud 更新](https://docs.tricentis.com/tosca-cloud/en-us/content/release_notes/release_notes.htm) |
| TestComplete | [wxWidgets 支持及构建要求](https://support.smartbear.com/testcomplete/docs/app-testing/desktop/visual-c/wxwidgets-support.html)、[桌面产品](https://smartbear.com/product/testcomplete/desktop-testing/) |
| Squish | [AI/MCP 技术预览与范围](https://www.qt.io/quality-assurance/squish/ai-powered-ui-testing)、[如何使用 AI 助手](https://doc.qt.io/squish/how-to-use-ai-assistants.html) |
| Katalon | [10.4+ FlaUI 与原生支持范围](https://docs.katalon.com/katalon-studio/get-started/supported-applications-under-test-aut/introduction-to-desktop-app-testing-in-katalon-studio) |
| UiPath | [Autonomous Test Execution 仅 Web 的限制](https://docs.uipath.com/test-manager/automation-cloud/latest/user-guide/autonomous-test-execution)、[手工测试转换的对象库要求](https://docs.uipath.com/autopilot/other/latest/user-guide/autopilot-for-testers-best-practices) |
| OpenText | [AI-based testing](https://admhelp.microfocus.com/uftdev/en/26.1-26.3/HelpCenter/Content/HowTo/AI-based-testing.htm)、[产品能力清单](https://www.opentext.com/en/media/data-sheet/opentext-functional-testing-ds-en.pdf) |
| Appvance | [5.2 Desktop Designer 与自主测试说明](https://docs.appvance.net/Content/AIQ/ReleaseNotes/AIQ/AIQ_5.2.x/AIQ_520_RN.htm) |
| TESTAR | [目标、方法与许可证](https://testar.org/about/)、[Windows 与分辨率说明](https://testar.org/wiki/Main_Page) |
| AutoGenesis | [README](https://github.com/microsoft/AutoGenesis)、[Windows 接入](https://github.com/microsoft/AutoGenesis/blob/main/pywinauto-mcp-server/WINDOWS-README.md)、[原始 MIT 许可](https://github.com/microsoft/AutoGenesis/blob/main/LICENSE) |
| Argus / Pantomime | [Argus README 与已知限制](https://github.com/Varun-SV/Argus)、[发布包](https://pypi.org/project/argus-app-testing/)、[Pantomime](https://github.com/patrickiel/pantomime) |
| 通用 agent 与归档 | [UFO 架构](https://microsoft.github.io/UFO/ufo2/overview/)、[Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)、[UI-TARS 已归档仓库](https://github.com/bytedance/UI-TARS-desktop) |
| Web/移动侧候选 | [TestSprite](https://www.testsprite.com/)、[Momentic 支持平台](https://momentic.ai/)、[Playwright Test Agents](https://playwright.dev/docs/test-agents) |

## 9. 本次没有证明的事项

第三方 runner 在 Orca 上的实际通过率、GL/自绘区域输入与截图质量、锁屏/断线后的会话行为、进程树清理、供应商 SLA、具体采购报价、完整源代码许可依赖审查、网络数据流审计以及长期维护成本均未实测。报告据此给出候选和实施路线，不把公开资料调研写成产品验证。
