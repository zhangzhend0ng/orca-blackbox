# ZCode 原生 actor：接口与边界

当前路线、优先级和评估门槛统一见[主方案](V3_PLAN.md)，本页只描述actor。主方案未放发布闸；停止继续相似扩样，先完成恢复/停输和画布能力。

入口为`python -B tools/native_save_demo.py --actor zcode`，GUI只在Hyper-V win11-test由hv_go交互任务执行，沿用run_once、owned Job、canonical桌面锁和独立harvest。宿主与客机须为相同已提交HEAD；上游源码只读。

供应商固定原有Snapmaker `new-provider/glm-5.3-flash`，原有HTTP地址`http://ai-gateway.s.com/v1`、Anthropic协议、reasoning/thought low。原生ZCode app-server持有模型agent循环；项目客户端只创建会话、给目标、限制权限、收集事件与停止，不替模型生成下一动作。客户端不导出Key、不复制到客机、不修改全局模型/账号/代理；三份个人配置hash在每轮前后核对。实际model-io再次核验provider/model和每次七项工具清单。

仅开放Snapshot、Screenshot、Click、Type、Shortcut、Wait、ControlStatus。模型不获shell、文件系统、任意路径或全局快捷键。数值/固定保存路径、owned PID/HWND/控件类型由执行端校验。会话关闭搜索/记忆/子agent等额外能力，未使用插件认证请求拒绝；bootstrap仍可能初始化已有插件，不构成完整OS沙箱。tools/list说明必须与收窄schema及权限一致。

现有逐调用门禁不等于永久撤销：b6b15eb填充轮次出现foreign拒绝后仍继续调用。**fatal latch尚待修复和真实验收**，不能声称失配后即刻终止或整轮没有任何越权输入。后续必须首次fatal原子锁存、停止actor/MCP；只允许有未派发证据的owned控件类型错误按新合同有限恢复。旧严格合同不放宽、旧失败不重标。

宿主模型期间轮询既有clash-guard；guard不可达或未ready停止本轮owned Job。守卫针对既有OpenAI分组，ready不证明公司网关出口美国；不修改Clash/guard规则。前台失配和原版MCP的ControlStatus disabled不是要求开启宿主控制的理由。

AI业务保存后，可信阶段撤销输入、停MCP、自然退出旧Orca、冻结同一3MF字节，fresh profile重开GUI切片，再由只读oracle检查目标、几何/配置、实际G-code和运行时来源/时序。模型回复不是通过证据。清理未知、模型/工具集漂移、缺证明均不晋级。

历史：首个4ba6b094412d435398826502d94f69e9完成16个MCP调用及独立112层G-code，前五个开发失败保留；[原始记录](runs/zcode-snapmaker-2026-11-17.md)。29f567e矩阵安全3/3、业务严格7/8仍不变；[矩阵记录](runs/zcode-matrix-2026-11-17.md)。b6b15eb旧项回归3个SHADOW、填充失败、平移blocked、slot3未运行；[最新扩样记录](runs/zcode-expansion-2026-11-18.md)。这些都不是87条覆盖、跨版本维护或发布GREEN。
