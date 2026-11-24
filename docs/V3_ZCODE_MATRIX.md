# ZCode 稳定性验收入口

新批次固定使用现有 Snapmaker 供应商 `new-provider/glm-5.4`。历史 `glm-5.3-flash` 批次保留原模型收据。

先提交代码并通过Git bundle同步客机到相同clean HEAD。管理员relay后台执行 `python -B tools/zcode_matrix.py --batch-id <32hex>`；入口逐次调用native_save_demo → hv_go，禁止宿主跑GUI。

固定计划先安全三轮：真实输入后取消、120秒guest运行时超时、本轮守卫HTTP通路断开。三轮均需正式拒绝且清理确认；然后Quality/Strength/Others各两次，初始保存对话框与已存在目标文件各一次。每个run独立profile/产物，业务prompt不含导航路线或坐标，无重试。整个计划冻结一个HEAD，失败和未运行槽位均保留。

证据：artifacts/zcode_matrix/<batch>/plan.json、events.ndjson、summary.json；每轮保留windows_mcp_host及windows_mcp_harvest。先核对实际初态截图，再解释业务矩阵结果。SHADOW只代表数字保存/重开/实际切片闭环，不表示发布GREEN或实物验证。安全用例的pass只表示预期拒绝得到验证。

最新实际结果：29f567e完整批次caff045271da4ec4a6ef62c516b643a1，安全3/3、业务严格7/8，acceptance_pass=false。Others第二轮的owned非Edit输入被拒绝，最终产物正确也保留原失败；当前不扩覆盖。详见[runs/zcode-matrix-2026-11-17.md](runs/zcode-matrix-2026-11-17.md)。
