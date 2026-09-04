# UIA 向导探针方案（uia_probe `--wizard` 模式）—— 对抗修订版

> 2026-09-03。回答"黑盒能力能否扩展到 Orca 内嵌 web 内容"的第一步（route A）：
> 对 Setup Wizard（wxWebView 渲染的 HTML）做 UIA 通道的 检测/定位/驱动 分级实弹评估。
> 本方案已经过独立对抗子 agent 证伪（VERDICT: APPROVE，3 major + 8 minor 全部处置，
> 见 §六）。工具增量 ≤120 行，不注册 cases.py、不进任何回归路径（--dialog-sample 先例）。

## 一、目标与交付物

**一句话目标**：判定 UIA 通道对 Setup Wizard HTML 内容能到哪一级——L1 定位（命名
元素 + rect + pattern 表）、L2 驱动（结构化触发后状态真变化）；L0 检测已被
UIA_EVAL §五.2 回答（raw walk 114 节点含 webview 子树），本探针不复述 L0 结论。

交付物：
1. `runner/uia_probe.py` 增 `--wizard` 模式（OUT_SUFFIX `_wiz`）；
2. 客机实跑产物 `uia_probe_{out,compact}_wiz.json` + `_report_wiz.txt`；
3. `docs/UIA_EVAL_0903.md` 增 §七（向导分级结论）；
4. `PITFALLS_0901.md` §3 修订（"web 无可枚举结构"前提已被 raw walker 推翻；
   "OCR+坐标点 HTML 太脆"结论保留）。

**非目标**：WCP 首页 WebView2（联网测试类，另立）、CDP 通道（纯度决策大，另立项）、
向导正向走完的正式用例（本探针只点一次做判据，用例化是后续决策）。

## 二、状态空间（Shape 清单 + 退化输入×消费者矩阵）

| Shape | 判别 | 状态 | 方案处置 |
|---|---|---|---|
| W1 | 向导可见+HTML加载+UIA子树暴露（--raw 实测：Chrome_RenderWidgetHostHWND、"Welcome to Snapmaker Orca"/"Get Started"） | UNDERSTOOD | 主路径 |
| W2 | 向导可见但 Chromium a11y 树未建/内容未加载（子树空/无名） | NOT UNDERSTOOD | 单次空子树=inconclusive+2s 后自动二走；二走仍空=inconclusive 落盘，**不判"web 不可见"** |
| W3 | 向导不存在（已被关/fixture boot 不弹，坑#2） | UNDERSTOOD | 显式输出 `not_present`，照常收尾 exit 0 |
| W4 | 驱动后向导整个消失（"Get Started" 语义无源码证据，可能是关向导） | NOT UNDERSTOOD | 重走前先查向导 hwnd 存活；hwnd 消失=L2 结果之一 `wizard_closed`（驱动生效但语义=关闭） |
| W5 | zh_CN 变体（en∩zh 仅 11/63 同名） | 部分理解 | zh 只采样 L1（pattern+rect），**不做驱动**（英文名门必落空） |
| W6 | win32 可见但 UIA 子树不可见（a11y 懒激活稳定性） | NOT UNDERSTOOD | 同 W2 处置；114 节点实证 UIA 查询自身即激活触发，风险降级但保留二走 |

| 退化输入＼消费者 | 检测结论 | 驱动判据 | 清理收尾 |
|---|---|---|---|
| a11y 未激活/时序 | inconclusive+二走，禁误报 | — | — |
| 深度/节点帽截断 | cut 标记随 WalkStats 落盘，禁当"无按钮" | — | — |
| invoke 抛异常 vs 静默无效 | — | 重走比对状态，不信"没抛异常=成功" | — |
| 向导缺席（W3） | not_present | — | finally 收尾不变 |
| close 部分路径退 app（坑 §19.1） | — | — | 不用 send_keys ESC 收尾（wx 模态框 ESC=Cancel 同风险）；只走 close_setup_wizard + session.close()（finally 必跑，app 已退则 no-op 安全） |

## 三、设计（已并入对抗修订）

1. **新 flag `--wizard`**，OUT_SUFFIX 按既有规则拼接 `_wiz`。**flag 组合矩阵**：
   `--wizard` + `--dialog-sample` = 非法组合，直接报错退出；`--wizard --zh` 合法
   （zh 只采样不驱动）；`--wizard` 本身主枚举就走 raw walker，无 `--raw` 依赖。
2. **launch_app 用 `dismiss_blockers=True`**：launcher sweep 的 BLOCKER_TITLES 是
   **3 条**（'Configuration update' / 'Snapmaker Orca Update' / 'new version of
   snapmaker orca'，launcher.py:96-100），**不含向导**（坑 §19.1"sweep 不碰向导"）
   → 弹窗类噪声被清扫、向导保持在场。
3. **向导发现不走 wait_idle_boot**（与向导子树无关，无需主窗就绪锚；实测向导在场
   锚也能 score=1.000，跳过只是省 60s 预算）：win32 `toplevel()` 轮询
   `#32770`+'wizard'（复用 dialog_sample_run:702-708 的 40×0.5s 模式）。20s 轮询
   未命中 → `not_present` 收尾。**切勿用 scan_extra_windows 找向导**——desktop
   顶层枚举漏 owned 窗（UIA_EVAL:58-59 实测 extra_windows=0）。
4. **枚举**：comtypes raw walker 从 `ElementFromHandle(wizard_hwnd)` 重根遍历
   （pywinauto 控制视图看不见 web 子树，103 vs 114 实证），独立深度帽 20 +
   MAX_NODES 4000 + 90s 预算（d12 撞帽是主窗根算法的旧论据，重根后深度自然变浅，
   帽子保留只防 HTML 深树）。win32 EnumWindows 的 hwnd 与 UIA ElementFromHandle
   同一 HWND 空间，无 id 映射问题。
5. **L1 pattern 表**：对子树内命名交互元素（Button/Hyperlink/CheckBox）dump
   Invoke/Toggle/LegacyIAccessible pattern 可用性 + rect。HTML 若用 div 自绘
   则无 Button/Invoke——pattern 表本身就是评估结论，LegacyIAccessible.DoDefault
   一并 dump 作回退证据。
6. **L2 驱动（仅 en、仅一次、有门）**：存在带 Invoke 的交互元素时：截图 → invoke
   → 等 2.5s（对齐 try_mixing_invoke 先例）→ 查向导 hwnd 存活 →
   - hwnd 消失 → `wizard_closed`（并记录：向导关闭解锁 post-init 链，t=15s 起
     配置弹窗可能介入，判定完立即收尾不恋战）；
   - hwnd 在 → 重走子树，named 集合 + rect + 结构三维比对：有实质变化 =
     `page_advanced`；无差异/超集同名 = `inconclusive`（不是失败）；
   - 无可驱动元素 → `no_invokable_button`（这是合法结论，不是探针失败）。
   禁止沿用 try_mixing_invoke 的 `send_keys("{ESC}")` 收尾。
7. **清理**：`close_setup_wizard`（attempts=3）+ finally `session.close()`，
   全程无 ESC。
8. **hv_uia_probe.ps1 零改动**（$Modes 任意 flag 透传）。

## 四、判据与验证（NOT VERIFIED 显式化）

| 级 | 判据 | 证据 |
|---|---|---|
| L1 | ≥1 个命名交互元素带 rect + pattern | `_wiz.json` pattern 表 |
| L2 | invoke 后状态变化（三种结果均算"驱动通道已探明"） | 前后截图 + 重走 diff + hwnd 存活位 |
| 驱动不可行 | `no_invokable_button` 或 invoke 恒异常 | pattern 表为空/异常清单 |

验证命令：`hv_uia_probe.ps1 -Modes wizard`（客机 INTERACTIVE 任务，同先例）；
en 跑 1 次，`--zh --wizard` 视 en 结果决定是否补跑。验收 = 产物 JSON 存在且
report 含分级结论行；**若两次实跑均 W3（向导未出现）→ NOT VERIFIED，如实记录，
不降级为"不可行"**。

## 五、预算与风险

- 代码 ≤120 行增量（uia_probe.py 单文件）；1-2 次客机实跑；半天内闭环。
- 风险×对策：驱动误触（只点一次+状态比对）；向导关闭连锁（判定完立即收尾）；
  截断误读（cut 标记强制落盘）；退出语义（探针 exit 0=完成，与发现正负无关）。

## 六、对抗审查结论（2026-09-03，独立子 agent）

VERDICT: APPROVE。3 major 全部采纳进 §三：
- M1 "Get Started"语义未知 → W4/hwnd 存活分支 + `wizard_closed` 结果（原方案会把
  重走死元素 COMError 当 crash）；
- M2 zh 驱动门落空 → zh 只采样不驱动；
- M3 单次空子树误报 → inconclusive+二走。
minor 采纳：sweep 第三标题、ESC 收尾禁用、flag 组合矩阵、2.5s 等待出处、
not_present 显式输出、wait_idle_boot 跳过理由更正、hv ps1 零改动、d12 论据更正。
反驳：无。backlog：WCP/CDP 两条线维持"另立项"，不因本探针结果扩权。

## 七、实施记录（2026-09-04，5 轮实弹闭环；结论并入 UIA_EVAL §七）

| 轮 | commit | 结果 | 教训 → 修订 |
|---|---|---|---|
| 1 | 60297a2 | interactive=1（仅原生 Close），单查即判 | W2 懒激活实锤：Chromium a11y 树 boot 后 ~13s 未建（Document 空）→ poll-rewalk（e079544） |
| 2 | e079544 | rewalks=5 跑满后树激活：Get Started=**Hyperlink**，invoke 全缺、legacy=True | 真结论：InvokePattern 不可得 → LegacyIAccessible.DoDefault 回退（ccbc67e） |
| 3 | ccbc67e | **假 page_advanced**：`DoDefault` 属性不存在（未点击）却置 invoked=True，重走撞上激活噪声 | 方法真名 `DoDefaultAction`（客机 comtypes introspection 一手源）；pre-click 失败不置 invoked；激活门（6307234） |
| 4 | 6307234 | doc-child 弱门放行 15 节点 stub 树 → 点 Close=wizard_closed（顺带证实 DoDefaultAction 真能驱动原生钮） | 激活门升级为 Document 子树命名节点>0（2658b1d） |
| 5 | 2658b1d | **全绿**：doc_named=10 → DoDefaultAction('Get Started') 翻页 named+9/−6、nodes 24→35、向导未关 | W4 定案：前进语义非取消 |

- **预算偏差**：探针代码实际 ~+390 行（方案 ≤120）。超出来自实弹教训驱动的
  守卫（rewalk 循环、两级激活门、pre-click 语义、pattern 表、报告段），每条
  有对应 run 编号，非镀金。
- **zh 采样**：2/2 not_present（20s 轮询内无 #32770 向导）。上游门
  `GUI_App.cpp:7374` 与 language 无关、种子同源，en 5/5 vs zh 0/2 的分叉机制
  **未定存疑**；zh L1 采样在本配置下不可得。
- **证据产物**：宿主 `artifacts/uia_probe_out_wiz.json` +
  `uia_probe_wiz_{before,after}.bmp`（字节级 DIFFERENT，171,894 bytes/454 行，
  集中页面内容区；gitignored）；客机 `C:\coil\uia_probe_report_wiz.txt` /
  `_zh_wiz.txt` / 任务日志。
- **通道代价值**：run 1–5 全程零 WARN/ERROR、com_failures=0；向导 cleanup
  （close_setup_wizard + session.close）五轮全部干净。
- **遗留 backlog**：WCP 首页 WebView2（联网 tier，另立项）；CDP 通道（纯度
  决策，另立项）；zh 向导分叉机制（上游行为课题）；`fetch_mp4.py` 的 `$cred`
  缺赋值 bug（runner 线，本次以 relay_run 手工等价命令绕行未修）。
