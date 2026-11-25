# macOS 壁环数保存后重开读回

2026-11-25 在 macOS 26.6.2 arm64、Snapmaker Orca 2.4.1 上运行。前台由 coil（UID 501）占用，控制台未锁。仓库入口通过固定指纹 SSH 将本轮工作器送入专用 coilwin（UID 502）的后台 Aqua 域。

[a8e89341](repair-a8e89341-result.json) 复现了两处视觉识别问题。[原始 OCR 日志](repair-a8e89341-worker.log)显示，宽裁剪将 Quality 和 Strength 合为一条识别结果。用同帧窄裁剪读到 Strength 后，基线读到壁环数 2，编辑后读到 3 并保存。独立进程已重开副本，Wall loops 行的数值与左侧重置图标被合为 `5÷3`。旧逻辑提取数字得到 `53`，在 `reopen.wall` 等待超时。本轮保留 NON_GREEN。

[c6f52879](repair-c6f52879-result.json) 检验了先点击，再通过 AX 读取的方案。该轮保存的 3MF 含 `wall_loops=3`，独立重开后点击前的画面也显示 3。局部观察可见值格横跨 x606–726，spinner 控件在左缘，原点击落在它的向下箭头上。点击后实际 AXValue 为 2。该轮保留 NON_GREEN。

重开点击前的原始 PNG 留在本地 `artifacts/mac_project_copy/c6f52879097d43b1836b20ff71401dee/reopen-strength-pre-click.png`，SHA-256 为 `74492135908663520faff8e24215b82822ee839fef294cea3a0d171ad2264527`。用同一份 Mac Vision 脚本以 `624 825 36 25` 裁剪该 PNG，原始输出是 `626,829,12,13<TAB>3`。

修复在编辑阶段点击文本区，并核对编辑框的 AXHelp 参数键。独立重开时用图片定位 Wall loops，再从同一帧单独裁剪数字区域。横坐标取窗口原点加 264，纵坐标取当前 Wall loops 标签顶边减 5，排除重置图标和 spinner。重开读回过程只观察屏幕，记录原始 OCR 字符和裁剪坐标，并将实际数字写入阶段记录后判定。保存件差分、进程身份和切片收据仍按原判据检查。

主机上的两个 Mac 测试文件共 14 例通过。窄测覆盖合并页签的同帧重读、读取真实数字 3 和 4，以及合并的 `5÷3`、多个候选或空结果被拒绝。

[efdaba36](repair-efdaba36-result.json) 在修复版上实跑为 **SHADOW**。基线、编辑、独立重开使用三个不同的 PID（37459、38069、38920），分别读到 2、3、3。[重开工作器原始日志](repair-efdaba36-worker.log)记录裁剪与读数。原夹具前后 SHA-256 一致，保存副本通过差分与几何判定。两次切片均为 68 层，独立重开的 G-code 回显 `wall_loops=3`，正向 XY 挤出移动计数由 1907 增至 2154。收据绑定各自的进程、工程及切片 SHA-256。工作器清理通过。

完整本地收割件在 `artifacts/mac_project_copy/efdaba36fb6946e9883270e5ca0a4045`，含基线和副本 G-code、保存工程及运行收据。另用 c6f52879 保存件离线复算，原值 3 通过差分判定，只把存档参数改成 2 或 4 都被 `pilot_wall_loops_target` 拒绝。

此用例按 Mac 实机 SHADOW 口径记账。切片件来自 GUI 切片进程的临时 G-code。GUI 导出和原生 Save As 未测。
