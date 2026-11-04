# FEISHU_BASELINE — 飞书「基线用例」表 → vision-gui 黑盒套件映射

> Base `EDUAbYWcbaL2HOsgFM1cXmBpn5f`, table `tblvh0eGrID9JQ02`「基线用例」(107 records,
> snapshot 2026-09-16, all records shipped as 自动化状态=未覆盖). Static source
> research against SnapmakerOrca_dev @ b2508370af (09-16 build).
>
> Dispositions: COVERED (existing case) · NEW->m8x (implemented this batch) ·
> PARTIAL (core automated, sub-steps degraded — noted) · MANUAL (needs a real
> device / cloud backend) · SKIP (fixture gap / feature absent) · OUT-OF-SCOPE.
>
> 预设/种子事实：datadir seed 预设源 = dev build exe 旁 resources（08-28 版）——
> 21 官方耗材 colours JSON、U1(0.4) printer_flow_support、SET_PURIFIER_MODE 机器模板均在。

## GUI业务 (6)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 139 | 【正向】首次启动Orca软件进入主页 | P0 | COVERED | m7a 启动进准备页 (m7a_boot_shutdown) |
| 140 | 【正向】正常关闭Orca软件无残留进程 | P0 | COVERED | m7a 关闭无残留进程 (m7a_boot_shutdown) |
| 141 | 【正向】新建项目清空当前模型数据 | P0 | COVERED | m7b 新建项目清空模型 (m7b_new_project) |
| 142 | 【正向】热重启后软件状态完全恢复 | P0 | SKIP | 热重启功能在本 build 不存在(源码 grep 09-16, 同旧表 #10) |
| 143 | 【正向】导入本地STL模型文件并正确显示 | P0 | COVERED | m7c 导入 STL (m7c_import_stl) |
| 144 | 【正向】右键删除模型后恢复空白打印板 | P0 | COVERED | m7h 右键删除模型 (m7h_context_delete) |

## AI监控 (14)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 1 | Orca端-打印偏好设置按钮可见与可点击 | P0 | MANUAL | 需已连接缺陷检测设备(Control 页) |
| 2 | Orca端-打印偏好设置弹窗完整展示 | P0 | MANUAL | 同上 |
| 3 | 首次进入-查询并展示设备实际配置 | P0 | MANUAL | 同上 |
| 5 | 设备离线-Orca端弹窗置灰不可操作 | P0 | MANUAL | 设备离线场景 |
| 6 | Orca端-打开炒面检测：默认灵敏度low立即下发 | P0 | MANUAL | 需设备下发 |
| 7 | Orca端-关闭异物检测：灵敏度隐藏立即下发 | P0 | MANUAL | 同上 |
| 8 | 炒面检测-切换灵敏度 low↔high 立即下发 | P0 | MANUAL | 同上 |
| 9 | 异物检测-切换灵敏度 low↔high 立即下发 | P0 | MANUAL | 同上 |
| 10 | 关闭检测项-灵敏度栏隐藏不可操作 | P0 | MANUAL | 同上 |
| 11 | 打印中关闭炒面检测-弹出二次确认弹窗 | P0 | MANUAL | 打印中状态 |
| 12 | 二次确认-点击「确定」：下发关闭、UI更新 | P0 | MANUAL | 同上 |
| 13 | 二次确认-点击「取消」：不下发、状态不变 | P0 | MANUAL | 同上 |
| 14 | Orca端-WCP推送后UI实时刷新 | P0 | MANUAL | WCP 推送 |
| 15 | 开启检测项-默认灵敏度low自动下发 | P0 | MANUAL | 设备下发 |

## 一键还原视图 (6)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 16 | 选中任意盘触发Fit | P0 | NEW->m8a | Fit: 选中盘触发 (multi-plate fixture) |
| 17 | 切换选中盘后触发Fit | P0 | NEW->m8a | Fit: 切换盘后再触发 |
| 18 | 选中单个模型Fit | P0 | NEW->m8a | Fit: 选中单模型 (zoom_to_selection) |
| 19 | 选中多个模型Fit | P0 | NEW->m8a | Fit: 多选并集包围盒 |
| 20 | 导入模型已含装配关系 | P0 | SKIP | STEP 装配夹具缺失(OCCT 导入链已核实, 待补 fixture) |
| 21 | 导入模型无装配关系 | P0 | NEW->m8a | 装配视图: 无装配关系多模型布局(探测降级) |

## 耗材管理 (8)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 44 | 官方耗材颜色列表展示 | P0 | NEW->m8b | 官方颜色列表 FilamentColorDialog 分类卡 |
| 46 | 更改颜色后点击确定颜色生效 | P0 | NEW->m8b | 色盘确定->颜色登记(色块像素) |
| 47 | 更改颜色后点击取消不登记新颜色 | P0 | NEW->m8b | 色盘取消->颜色不变 |
| 48 | 模态弹窗基本布局展示 | P0 | NEW->m8b | 模态弹窗布局: 颜色卡片+名称+SKU(OCR) |
| 55 | 用户可选择双拼/渐变色作为耗材类型 | P0 | NEW->m8b | 渐变耗材 PLA Rainbow 预设切换 |
| 56 | 模型渲染显示双拼/渐变耗材主色 | P0 | NEW->m8b | 渐变主色渲染(模型色度) |
| 58 | 混色耗材切片生成对应Gcode | P0 | NEW->m8b | 渐变耗材切片 gcode 生成 |
| 59 | 切片预览展示双拼/渐变色的主色 | P0 | PARTIAL | 切片预览主色=视觉冒烟(与 m2 色度共用) |

## 同步耗材 (4)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 36 | 【有模型时弹出同步弹窗】当前工程有模型时点击"同步耗材信息",弹出设备耗材信息同步弹窗,默认显示匹配映射 | P0 | MANUAL | 需连接设备(同步耗材) |
| 37 | 【覆盖-立即同步】覆盖模式下点击"立即同步",设备耗材同步到左侧耗材栏并更新模型 | P0 | MANUAL | 同上 |
| 38 | 【匹配-耗材相近自动映射】设备耗材按照种类和颜色相近规则自动与模型耗材映射匹配 | P0 | MANUAL | 同上 |
| 40 | 【匹配-立即同步】匹配模式下点击"立即同步"，设备耗材按映射关系同步到左侧耗材栏并更新模型 | P0 | MANUAL | 同上 |

## 混色功能 (8)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 78 | 【比例-新增】选2/3种同类别耗材,调整比例→确认登记,预览实时渲染 | P0 | COVERED | m3t/m3u 比例新增+登记 (m3t_mixing_add_ratio/m3u_mixing_ratio_flow) |
| 80 | 【循环-新增】合法输入→确认登记,预览实时渲染 | P0 | COVERED | m3v 循环输入校验+登记 (m3v_mixing_cycle_input) |
| 82 | 【匹配-Hex】输入#FF5733→1s内完成匹配→推荐列表+预览区同步展示混色效果与色差值 | P0 | COVERED | m3x Match-Hex 匹配 (m3x_mixing_match #FF5733 重算) |
| 83 | 【匹配-色盘+默认】点目标色块出色盘选色→1s匹配,默认加载1-3号(50%/25%/25%) | P0 | COVERED | m3x 取色器色格+默认配比 (m3x_mixing_match) |
| 84 | 【匹配-新增】选择目标色或输入目标色Hex值匹配→确认登记,预览实时渲染 | P0 | COVERED | m3x 匹配登记 (m3x_mixing_match OK 登记+重开保模式) |
| 86 | 【渐变-新增+方向】选2种同类别耗材→默认下到上(底层→顶层)→线性插值渐变→确认登记F1→F2,可切换方向 | P0 | COVERED | m3y 渐变默认 F3->F2/交换/方向 (m3y_mixing_gradient) |
| 88 | 【耗材删除】删除物理耗材只剩1种→添加混色按钮置灰,删除被混色引用的耗材→二次弹窗确认级联删除 | P0 | COVERED | m4d trash 删除/级联删除二次确认 (m4d_mixing_filops) |
| 89 | 【混色切片打印】分别用4种模式进行混色并为模型涂色,执行切片、打印 | P0 | COVERED | m4i 混色切片+导出 (m4i_mixing_slice); 打印段=MANUAL |

## 混色匹配映射 (11)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 91 | 【推荐耗材】耗材选择区展示下拉框，hover展示序号颜色类型TD值，下拉框可选其他耗材颜色 | P0 | PARTIAL | m3s/m3l hover tooltip 已冒烟; 下拉框 TD 值文案细节=人工 |
| 92 | 【自定义耗材】弹窗展示4组主耗材选择控件及约束勾选框，默认加载本地前四个耗材 | P0 | COVERED | m4b 批量弹窗 4 槽同标签+无选择 combo (m4b_batch_manual) |
| 95 | 【匹配后视图】匹配前为缺省状态；匹配完成后实时渲染混色效果且颜色与映射列表一致，渲染完成后所有交互按钮恢复可用 | P0 | COVERED | m3k 匹配后映射列表渲染 (m3k_mixing_match 色度双轮) |
| 96 | 【匹配中状态】所有按钮全量屏蔽，进度条实时更新，支持停止匹配 | P0 | COVERED | m3r 匹配中进度条+Stop Matching (m3r_mixing_progress) |
| 100 | 【有颜色模型】按钮正常可点击，唤起混色匹配弹窗 | P0 | COVERED | m3j 入口门禁:有颜色模型->弹窗 (m3j_mixing_entry) |
| 101 | 【2~4个物理耗材无混色】2~4个物理耗材且无混色耗材进行混色匹配 | P0 | COVERED | m4a 2~4 物理耗材门禁 (m4a_mixing_gates) |
| 103 | 【自动模式·默认】弹窗打开或重开默认选中CMYW，匹配可用 | P0 | COVERED | m4b Auto 卡默认选中 (m4b_batch_manual) |
| 104 | 【自动模式·匹配】默认CMYW点击开始匹配，生成颜色映射列表 | P0 | COVERED | m4b Auto 默认匹配生成映射 (m4b_batch_manual) |
| 105 | 【自动模式·组合变更】更换耗材组合重匹配，映射按新组合计算 | P0 | COVERED | m4b 行选择变更后重匹配 (m4b_batch_manual) |
| 106 | 【推荐模式-有效色域】任意4色组合匹配，单色混色比例均在0%-70% | P0 | PARTIAL | m3m 色域 banner 文本 0%-70% 已断言; 任意组合遍历=抽样 |
| 107 | 【确定保存】点击确定后弹窗关闭，颜色映射结果生效 | P0 | COVERED | m3k Confirm 关闭+映射生效 (m3k_mixing_match) |

## 联机业务 (14)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 145 | 【正向】局域网内正常发现可用设备 | P0 | MANUAL | 联机发现 |
| 146 | 【正向】通过设备发现绑定云联设备 | P0 | MANUAL | 云联绑定 |
| 147 | 【正向】通过PIN码绑定云联设备 | P0 | MANUAL | PIN 绑定 |
| 148 | 【正向】已绑定云设备点击卡片进入控制页 | P0 | MANUAL | 云设备卡片 |
| 149 | 【正向】通过局域网发现并绑定设备 | P0 | MANUAL | 局域网绑定 |
| 150 | 【正向】已绑定局域网设备点击连接 | P0 | MANUAL | 局域网连接 |
| 151 | 【正向】解绑设备后卡片消失 | P0 | MANUAL | 解绑 |
| 174 | 【正向】切片后发起打印任务到设备 | P0 | MANUAL | 打印任务到设备 |
| 175 | 【正向】打印过程中暂停后恢复继续打印 | P0 | MANUAL | 打印暂停恢复 |
| 176 | 【正向】打印过程中终止打印任务 | P0 | MANUAL | 终止打印 |
| 177 | 【正向】打印过程中监控画面正常显示 | P0 | MANUAL | 监控画面 |
| 178 | 【正向】取出/放回打印头并调节温度 | P1 | MANUAL | 打印头 |
| 179 | 【正向】调整热床温度和高度 | P1 | MANUAL | 热床 |
| 180 | 【正向】LED灯和风扇调节正常 | P1 | MANUAL | LED/风扇 |

## 主流程-用例 (11)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 152 | 首次安装后新建项目并完成打印 | P0 | PARTIAL | m7t73+m7t74 新建/创建/变换切片; 设备绑定+打印=MANUAL |
| 153 | 多模型布局与本地文件直接打印 | P0 | PARTIAL | m7t75 布局/删除/切片; 上传打印=MANUAL |
| 155 | 用户登录绑定设备后打印 | P0 | MANUAL | 登录+云设备绑定全链设备操作 |
| 156 | 模型快速调整与局域网打印 | P0 | PARTIAL | m7t74 调整切片; 局域网打印=MANUAL |
| 157 | 涂色多材料打印并上传本地任务 | P0 | PARTIAL | m4e+m4i 涂色+切片; 上传=MANUAL |
| 158 | 模型布局优化与多设备切换打印 | P0 | PARTIAL | m7t75 布局; 多设备切换=MANUAL |
| 159 | 用户登录预打印参数修改本地打印 | P0 | PARTIAL | m3e+m4d 预设/耗材; 登录打印=MANUAL |
| 160 | 设备绑定异常与恢复打印 | P0 | MANUAL | 设备绑定异常恢复=设备链 |
| 161 | 设备局域网IP连接设备控制 | P0 | MANUAL | 局域网 IP 连接=设备链 |
| 181 | 打开并切片打印模型库/模型站模型 | P0 | OUT-OF-SCOPE | 模型站后端可控状态, Flutter WebView UI, 非本仓 wx 黑盒 |
| 182 | 比较预设 | P0 | COVERED | m3e 预设参数差异->gcode diff |

## 主流程-模板 (3)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 164 | 单模型切片调整测试 | P0 | COVERED | m7t74 单模型变换+切片 (m7t74) |
| 166 | 模型打印参数切换与验证 | P0 | COVERED | m3e 预设切换->gcode 跟随 (m3e_preset_switch) |
| 170 | 模型创建旋转涂色切片  | P0 | COVERED | m7t89 创建+旋转+涂色+切片 (m7t89) |

## 顶盖1.4.0 (13)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 108 | 顶盖控件显隐与三端入口 | P0 | MANUAL | 顶盖控件=Control 页设备 |
| 109 | 待机状态交互 | P0 | MANUAL | 同上 |
| 111 | 低温+高温耗材混用拦截禁止切片 | P0 | NEW->m8c | PLA+ABS 混用->Slice 置灰+无法切片 |
| 112 | 低温+低温（同类）混用允许切片 | P0 | NEW->m8c | PLA+PLA支撑->切片通过 |
| 113 | 保温模式GCode各参数值符合工艺定义 | P0 | NEW->m8d | ABS->保温: MODE=3 DESIRE_TEMP=45 无 ALARM_TEMP |
| 114 | 弱冷模式GCode参数值符合工艺定义 | P0 | NEW->m8e | PETG->弱冷: MODE=3 DESIRE_TEMP=0 无 ALARM_TEMP |
| 122 | 修改耗材槽位类型后切片GCode参数同步更新 | P0 | NEW->m8d | 槽位 PLA->ABS: gcode 强冷->保温 |
| 123 | 修改耗材预设的软化温度改变温类归类后GCode更新 | P0 | PARTIAL | 需预设管理器改软化温度(深层 Tab UI), 首批缓行 |
| 125 | 工艺全局辅材冲突，打开偏好后，可以正常切片并打印 | P0 | PARTIAL | 2 plate 全局辅材冲突+偏好开关, 用例步骤自相矛盾, 缓行 |
| 126 | 高温耗材 ABS 被正确识别为保温模式 | P0 | NEW->m8d | ABS 识别为保温(与 #113 同链路) |
| 127 | 高温耗材 PC 被正确识别为保温模式 | P0 | NEW->m8d | PC 识别为保温 |
| 128 | 保温模式 GCode 参数完整写入起始位置 | P0 | NEW->m8d | 保温参数完整: MODE/DESIRE_TEMP/FAN_SPEED/DELAY_OFF(DYNAMIC_FAN_CONTROL 表写 stale, 模板实为 FAN_SPEED) |
| 129 | 弱冷模式 GCode 参数完整写入起始位置 | P0 | NEW->m8e | 弱冷参数完整: MODE=3+弱冷风扇 |

## 高流量热端 (5)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 133 | 【默认状态】打开Orca喷嘴设置界面，验证喷嘴直径和流量默认展示 | P0 | NEW->m8f | 喷嘴 1-4 Tab+直径 0.4mm+流量 Standard 默认(表写 0.2-0.8 可选=待实测核对) |
| 134 | 【喷嘴信息同步】点击喷嘴信息同步按钮验证同步喷嘴直径+流量类型 | P0 | MANUAL | 喷嘴信息同步=设备端同步(Plater.cpp:2230 设备链) |
| 135 | 分别用标准以及高流量切片对比gcode文件差异 | P0 | NEW->m8f | Standard vs High Flow 切片 gcode diff(开发脚本语义=记录差异) |
| 136 | 工艺参数一致的情况下，编辑耗材单一参数对比gcode文件差异 | P0 | NEW->m8f | Standard 模式下改高流量参数不影响 std gcode(确定性对比) |
| 137 | 耗材丝配置、打印配置、工艺配置有流量喷嘴标标志图的参数对比 | P0 | PARTIAL | 三类配置 flow 标志参数遍历, 抽样缓行 |

## 延时摄影导出 (4)

| # | 用例标题 | 优先级 | 处置 | 映射/备注 |
|---|---|---|---|---|
| 60 | 【正常进入】满足全部前置条件，进入延时摄影页面，列表正常加载文件 | P0 | MANUAL | 延时摄影=设备文件 |
| 63 | 【刷新成功-有变化】设备端有新文件和删除文件时刷新，列表更新 | P0 | MANUAL | 同上 |
| 66 | 【全部成功】3 个文件全部下载成功后，Toast 提示且各文件标记已完成 | P0 | MANUAL | 同上 |
| 68 | 【全部成功】3 个文件全部删除成功后列表项淡出消失且存储空间更新 | P0 | MANUAL | 同上 |

## 2.4.0 复跑结论（2026-09-28，基线 33 例）

在同一台 Hyper-V 客机上、用 `cases.py` 的 `baseline` 套件（33 例，由各用例头部的
`# feishu: baseline#N` 注解驱动）跑 2.4.0 portable 构建：

| 结果 | 用例 |
|---|---|
| GREEN 33/33 | 混色 17（m3j/k/l/m/r/s/t/u/v/x/y、m4a/b/d/e/i、m2_slice_chain）、界面 4（m7a/b/c/h）、主流程 4（m7t73/74/75/t89）、m8a、顶盖与净化 3（m8c/d/e）、高流量 2（m8f/m8g）、m8b_official_color |

### m8b（#44/#46/#47/#48/#55/#56/#58）在 2.4.0 上的实测差异

1. **取色入口与官方色卡库**：官方色卡库**存在**，入口是侧栏槽位的**编号色块按钮**
   （`Button` text='2'，底色即耗材颜色）——点它直接弹出官方列表
   （`Official Filaments` + 当前色名 + `sku NNNNN` + 色卡格 + `+ Other Colors`）。
   其右侧的 16×25 小按钮走的是 **Edit/Delete/Merge 右键菜单 → Material settings →
   colourpicker → 传统取色器**（Windows 原生色盘）那条老链。用例曾误点后者，
   因此一度误判"2.4.0 无官方色卡库"——**该结论已作废**。
2. **分类映射（测试方口径）**：纯色 = 非官方耗材 → 回退传统色盘；双拼 = 官方
   PLA Silk → 官方列表（有命名色 + SKU）；渐变 = PLA Rainbow → 官方列表
   （当前色为自定义色时显示十六进制、无 SKU，列表本身仍在）。三类均有断言。
3. **侧栏色块恒灰**：老断言读的那个"色块"在 2.4.0 上读出恒定 `[213,213,211]`
   （它是固定图标，不是实时色块）；真正的颜色面是**编号色块**与**弹窗读数**，
   两者都已用于断言（#46 观察到色块像素随改色变化）。
4. **工程覆盖 vs 系统预设**：夹具工程内嵌 50 个 `filament_*` 覆盖项，槽位因此带
   `*`（Orca 的"预设已修改"标记，只出现在部分窗口文本中）。用例现在会**先把槽位
   重选回系统预设**，并以"改耗材子菜单里该行无 `*`"作为断言证据。
5. **预设下拉的滚动**：该弹窗**无视消息级滚轮**，必须用真实滚轮输入才能滚动——
   否则字母序在打开位置之上的预设（如 PLA Rainbow）无法被搜索到。

### 台架环境说明（跑批沙盒 vs 用户环境）

跑批用 `--datadir artifacts/m3_profile`（由 `harness/profile.py` 现场播种的沙盒）。播种时会从应用
的 `resources/profiles` 拷入 **Snapmaker + BBL（Bambu Lab）两个厂商包** —— 装第二个厂商包是为了
让**首次启动向导**不出现（它的门槛是"机器列表里存在非默认打印机"，09-03 实测：只装默认厂商时向导会
弹出来挡住界面）。**副作用**：我们的耗材/预设下拉里会多出 **Bambu 与第三方（eSUN、Valment 等）**
条目，而用户自己的配置目录里看不到这些（用户侧多半累积了厂商/机型过滤）。

用例按**名字**匹配预设（`Snapmaker PLA Silk`、`Snapmaker PLA Rainbow` 等），多出的条目不影响判定。
若以后需要严格贴近用户配置，建议把厂商列表做成**可配置开关**（仅 Snapmaker / Snapmaker+BBL），
而不是手搓一个桩厂商包（vendor.json + 机型继承的维护成本与风险都不低）。

> 时间戳口径：客机原先时区是 `Pacific Standard Time`（与宿主的 `China Standard Time` 差 15 小时，
> **UTC 一直是准的**），09-28 已改为 `China Standard Time` 并 resync；此前按客机时间记录的
> 截图/录像时间戳需要 +15 小时换算。

## 飞书「待实现」逐条落地（2026-09-29）

基线表里标 `待实现` 的行按「跑通一条、写回一条」推进；已落地的三条（均在 Hyper-V 客机
2.4.0 构建上实测，录像存 `artifacts/videos/`，写回已回读校验）：

| 行 | 用例 | 结果 |
|---|---|---|
| #123 修改耗材预设的软化温度改变温类归类后 GCode 更新 | `m8x_123_softening_temp` | GREEN 17/17（含 GCode 里 `MODE/DESIRE_TEMP` 分支翻转） |
| #137 耗材丝配置、工艺配置有流量喷嘴标志的参数对比 | `m8x_137_flow_param_tabs` | GREEN 15/15 |
| #125 工艺全局辅材冲突，打开偏好后可以正常切片 | `m8x_125_aux_mix_pref` | GREEN 19/19 |

### #125 的口径与那个"点不动"的坑（2026-09-30）

* 测试方口径：**主材 = 对象的耗材丝；辅材 = 涂色**（painted）。高低温混用门禁对二者生效。
* 预期链路：冲突时 Slice **置灰 + 红条 `Detected both high and low temperature` + 点击被吞**
  （无法切片）→ 打开偏好 `Allow high/low temperature filament mixing` → 点 Slice 弹
  `Confirm slicing`（正文点名 High `[1] Generic ABS` / Low `[2] Snapmaker PLA Silk`）→
  Confirm → 应用切到 Preview，切片发起。
* **坑**：偏好里那一行是**复选框**，点它会**立刻弹出** `…Material Mixing Risk`
  （"Do you want to enable this feature?"），**只有按 Confirm 才真正启用**。把"弹框盖住
  复选框造成的像素变化"当成开关翻转、接着用 WM_CLOSE 关偏好窗口，会把改动一起丢掉 ——
  症状是门禁永不解除、点 Slice 毫无反应（排查花了大半天）。
* 另一个自伤：`page()` 原来按文字取最左的 tab，**永远返回 Prepare**（截图里已在 Preview），
  于是"切片已发起"被判成超时。现在按"哪个 tab 是高亮绿色"判定。

### #137 的两个面在哪里（测试方两次纠正后的实测结论）

* **耗材侧** = `Material settings` 对话框里的 `[Standard flow] / [High flow]` 子 tab。
* **工艺侧** = 侧边栏 `Process` 面板 **先把 `Advanced` 开关打开**，才会出现 **`Speed`** tab
  （默认只有 Quality/Strength/Support/Multimaterial/Others 五个），Speed 页上同样有
  `[Standard flow] / [High flow]`。预设名右侧三个图标是 `[保存][删除][搜索]`（点中间那个
  弹的是 `Delete Preset`），右键/双击预设名都没有参数对话框 —— 工艺侧的流量面就在 Speed 页。
* **带标志参数** = 测试包（`resources/user/default/`）里声明成两档值的键，例如耗材包
  `nozzle_temperature=['210','220']`、`filament_flow_ratio=['0.95','0.966']`，工艺包
  `process_flow_support=['standard','high_flow']`、`initial_layer_speed=['60','50']`、
  `outer_wall_speed=['550','500']`。用例对两侧都做了**动手改值**的验证：改 A 模式后
  B 模式仍读自己的值、且全页找不到新值；不带标志的参数（Idle temperature）两侧同步。
* 踩坑：耗材编辑器的 `Cancel` 在 1920×1080 下**在屏幕外**，必须用 `Esc` 关闭并回读确认
  —— 对话框没关时模态会吃掉后面所有侧边栏点击（工艺侧曾因此整段 FAIL）。
