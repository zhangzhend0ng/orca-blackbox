# 原生 Codex 业务 demo：编辑保存与独立恢复证明

2026-11-17 冻结目标：Codex 仅凭目标将固定 cube 的常规层高改为 0.24，初层保持 0.40、模型不变，GUI 保存到本 run 的 `projects/0001.3mf`。不提供坐标或菜单清单。此版本只准 SHADOW，不进入 GREEN 基线。

## 唯一主链

`hv_go -WindowsMcpProbe -NativeSave` → 既有 `run_once` / canonical `artifacts/v3` 桌面锁 → NativeSaveExecutor / owned Job → 原生 Codex + 原版 Windows-MCP（薄输入策略） → 关闭输入通道与 MCP 进程 → 旧 Orca 自然退出 → 冻结保存文件 → 独立 profile 重开、GUI 切片导出 → 只读 verifier → 统一收尾。

AI 负责定位、编辑和保存；独立重开与切片由可信检查阶段完成。该结果证明 AI 保存的工程可恢复并切片，不证明 AI 自主跨进程重开。旧逐步 CLI/JSON 和 exact 顺序契约冻结，不沿用其唯一动作顺序。

## 权限及停止条件

- 原版 MCP 包不改源码；项目中间件只限制工具/参数与当前 owned 窗口，不加入规划。开放 Snapshot/Screenshot/Click/Type/Shortcut/Wait/ControlStatus；输入使用 loc，拒绝 label、Shell、App、文件系统与全局快捷键。
- Type 只允许数值或精确 run 保存路径，必须落在 owned Edit；Shortcut 白名单限定保存/编辑确认。拒绝截图任意 save_path。输入前核对会话、前台 PID/HWND、目标 HWND 和 1920×1080；失配停止，禁止自动抢回焦点或盲重放动作。
- 仍使用独占测试客机 `--no-control` 配置；这些薄门禁不能消除 TOCTOU，也不是同权限恶意进程的安全沙箱。一次只允许一个 runtime；第二执行者必须被拒绝。
- 每轮原生工具上限 40、Actor 最多 600 秒，整个 guest 合同 900 秒；取消/失联有界回收 owned Job，清理不明不晋级。USD 未计量，不能声明免费或金额硬封顶。
- 本次用户授权复用已核实的宿主 Codex 登录态。不开新登录、不复制认证文件、不修改全局配置；长期无人值守的独立身份仍待落实。

## 独立证据

停止 MCP 后再关闭旧 SUT，记录自然退出；关闭后读取同一保存文件，冻结副本及 SHA256，用 fresh profile 重开该副本。检查器复用 bounded 3MF 几何/配置与实际 G-code 挤出层序解析，要求 .24 / 初层 .4 / 固定 cube / 112 层 / 末 Z27.04；所有来源、时间和进程收据必须绑定本 run。Agent 不能写通过结论。

本轮先取得一个完整真实 GUI 正例，并用纯策略/文件反例验证边界；不将单测算作 GUI 覆盖。下一阶段再跑三个初态各两次及两个干扰；反例与合法替代路径分账验收，保留首次失败和恢复。任何假通过、越界输入或清理不明立即停止扩展。

## 运行入口与结果

`python -B tools/native_save_demo.py` 为宿主协调入口；要求已有提权 relay、两端同一已提交 HEAD、客机原版运行时已安装且桌面空闲。只通过 hv_go 启动 GUI；PS Direct 只同步/读写数据。

运行状态写入 `artifacts/native_save_demo/<run>/`；模型记录仍在 `artifacts/windows_mcp_host/<run>/`；正式合同、runtime 结果与原始业务证据在 guest `artifacts/v3/<run>/`。收尾通过 `hv_harvest` 回收。真实运行结果另附记录，本文不宣称已经通过。

## 后续晋级路线（尚未执行）

先验收检查器：旧产物、错误层高、对象覆盖和错误来源四类反例必须对应拒绝；额外观察、baseline、修正后再保存、菜单/快捷键替代路径等合法结果必须接受。纯解析样本、固定fault producer、真实AI运行分别统计。取消必须实际确认双端停止，不能仅凭发出cancel。

再跑三个初态各两次与两个可恢复干扰，共八次真实运行；正常六次独立通过、两个干扰自主恢复，零假通过/越界输入/清理不明，才进入下一个受控阶段。所有已启动run保留在端到端分母，首次成功、自动恢复、人工救援、业务失败、基础设施失败分开，未执行项单列。门槛是投入决策，不是统计可靠率。

只允许针对已定位根因修复后全矩阵复测，不无限改提示词重跑覆盖失败。若主要成本仍是runner/报告/维护工程，使用相同目标与oracle对照Midscene；当前不并行建设多平台。通过真实版本升级维护对照后才局部纳入回归，探索后置。未来正式批量前落实专用认证与额度可见性；本demo不修改既有认证。
