# 飞书 #251 现状探针的样本

2026-11-26 02:33–02:34 在 win11-test 上按提交 `7dc0906` 跑了一次当时登记的 `m7x_251_reload_from_disk`（模型作为启动参数载入，结论键不是飞书原文）。它读到：另存后 20 mm → 磁盘换成 30 mm 并 `Reload from disk` 后 30 mm → 源文件被删后再重载，弹出标题 `Please select a file:` 的文件选择框，取消后仍是 30 mm。

这里只留了三个另存工程和两个 STL（各几十 KB，与客机收割件逐字节相同），供 `unit_tests/test_reload_oracle.py` 当真实样本。按飞书原文改写后的用例、两轮独立会话和结论在 [feishu-251-2026-11-26](../feishu-251-2026-11-26/README.md)。
