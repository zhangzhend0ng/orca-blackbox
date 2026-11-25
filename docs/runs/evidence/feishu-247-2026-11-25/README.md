# 飞书 #247 拆分多壳体并分别操作对象

记录 reczz28aa4fiZuWr 要求一个含不相连壳体的对象。从模型右键执行拆分，观察列表和盘面，验证拆出的对象可分别选中或着色。

在 win11-test 以同一提交 7fdcb8cc966ba45d1af0c7e73f5c099a3dccf5ee，从两个新配置单跑。Snapmaker Orca 2.4.0，U1 0.4 mm、PLA、0.20 mm Standard。[产品构建摘要](build.json)

| 会话 | 客机 | 场景耗时 | 离线 |
| --- | --- | ---: | --- |
| [首轮](7fdcb8cc-run1-receipt.json) | GREEN | 126.068 秒 | 通过 |
| [复跑](7fdcb8cc-run2-receipt.json) | GREEN | 125.065 秒 | 通过 |

菜单操作为 Split > To Objects。原始对象 TwinShell 含两个闭壳。拆成 TwinShell_1 和 TwinShell_2 后，每件仍有 12 面，逐面世界顶点最大偏差 0.000001668 mm。容差 0.00005 mm，实际位移 0.25 mm 和缺面反例均被拒。先清除拆分留下的多选，再用拆分后、着色前记录的左右两个坐标定位对象。左件上色保存件的耗材槽从 1/1 变成 2/1，随后右件变成 2/3。两个色值分别为 #ECED17 和 #00C1AE。[首轮几何与逐步读数](7fdcb8cc-run1-analysis.json) · [首轮对象列表](7fdcb8cc-run1-object-list.png)

前一版本两次因为 3MF 浮点舍入而保留 RED，前后工程均已收割。增加逐面容差后，两次拆分通过，但多对象选中导致弹出集体耗材菜单。清除多选后，前一候选仍两次误选左件。验证器读回 1/1 → 2/1 → 3/1 并拒绝，保留原始证据。锁定着色前坐标后，fa706g3 完整通过，102.088 秒，按 SHADOW 归档。[舍入阶段](d9075238-run1-receipt.json) · [多选阶段](5135a522-run1-receipt.json) · [误选反例](c140c6da-run1-receipt.json) · [实体机收据](fa-25caae945087-done.json)

从仓库根目录执行 runner/hv_go.ps1 -Cases m7x_247_split_shells。使用 tools/replay_case_evidence.py 读取两份客机收据可逐面复核并核对颜色。改初态后的返工和历史人工耗时均为未测。
