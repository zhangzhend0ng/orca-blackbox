# 业务扩样与画布诊断接线审查

用户已授权工艺/材料扩样及画布输入适配。上轮中断后恢复，未改动原用户launcher/profile/farm草稿。新增文件按三个agent独占，root统一交叉审查接线。

实现前加载INDEX、harness-driven-review、tool-control、input-validation、risk/verification、testing-strategy、AI-evaluation；日志/错误处理沿用既有策略。N：场景/模块/fixture白名单，新增允许目标仅sparse15%→30%或逻辑材料槽3，原case默认不变；C：纯检查器核验保存配置与实际对象挤出，不把注释当刀路；未验证物理密度/硬件喷头。

canvas_probe是只读诊断场景，仍hv_go/guest_native/owned Job。启动固定fixture后仅枚举owned窗口/PFD/focus/desktop，不启动MCP或模型，不输入文字；诊断case不形成业务证明，Canonical应NON_GREEN。采集函数guest guard先于Win32；GetDC/ReleaseDC及所有句柄成对收尾；只采visible descendants及identity，最多4096枚举/260记录，截断标incomplete拒绝绑定；观测时间从采集开始计算，避免把漫长采集误作新鲜。

画布纯规则：只能显式批准真实诊断class，绑定run/PID创建时间/main几何/parent-chain/GL标志；canvas可在固定main内变布局，输入前fresh HitTest/focus/foreground/session/desktop校验；path仍仅owned SaveAs Edit。当前规则尚未接入实际输入，也未解封pilot_transform，纯56项测试不代表真实画布输入安全或成功。

纯测试全仓1009 passed、1 skipped（42.42s），相关125项通过。缺少实际class/PFD/焦点证据前，不批准canvas输入。探针真实结果待执行后追加，模型试跑须另冻结版本；不把诊断结果写作GREEN或飞书覆盖。
