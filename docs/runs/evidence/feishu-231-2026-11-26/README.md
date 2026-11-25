# 飞书 #231 导入 ZIP 压缩包：在 2.4.0 上归档里的模型载不进来（RED）

记录 `reczz28aa4fiY21M`（P1）要求通过「文件→导入→导入 ZIP 压缩包…」导入含 3 个模型的 `models.zip`，预期「zip 内 3 个模型全部载入盘上/对象列表，无遗漏、无乱码文件名」。

**结论：Snapmaker Orca 2.4.0 上，Archive preview 里选中的文件被解到了临时目录（字节与 zip 成员完全相同），随后应用报「Loading of a model file failed.」并停在一个 Loading 框上，盘上没有出现任何对象。** 客机 1 轮、实体机 fa706g3 3 轮，签名逐字相同；对照实验说明这不是归档解压的问题：不经归档、在文件框里一次给出三个 STL 也报同样的错，单文件的归档同样失败。预期不成立，像产品缺陷。飞书状态保持空白。

| 运行 | 机器 | 测试提交 | 结果 | 机内耗时 |
| --- | --- | --- | --- | ---: |
| [客机收据](b2467f7d-run1-receipt.json) | win11-test | `b2467f7d…` | RED | 141.614 秒（场景） |
| [fa 第一轮](fa-688fa115-6613b8f5a64a-analysis.json) · [第二轮](fa-688fa115-a7387bffe129-analysis.json) · [第三轮](fa-688fa115-853a9a7dc6b0-analysis.json)（SHADOW） | fa706g3 | `688fa115…` | RED ×3 | 118.5–118.9 秒 |

四轮都以 `failed to save the imported project` 结束：对象列表等了 25 秒没有出现立方体，随后 File 菜单点不开，因为两个模态框还开着。[构建摘要](build.json)

用例里发生的事（客机 [日志](b2467f7d-run1-case.log)、[analysis](b2467f7d-run1-analysis.json)）：File→Import→`Import Zip Archive...` 打开标题 `Choose ZIP file:` 的文件框，类型 `ZIP files (*.zip)`；选中用例现场生成的 `models.zip`（三个二进制 STL 立方体 10 / 20 / 30 mm，各 684 字节，外加一个 `readme.txt`）后弹出 [Archive preview](b2467f7d-run1-archive-preview.png)，列出三行文件名，默认都没勾。点 `All` 后三行都勾上（[截图](b2467f7d-run1-archive-preview-all.png)），点 `Open` 后预览关闭。约 1 秒后应用弹出：

- 「Snapmaker Orca error」，正文 [Loading of a model file failed.](81dbcf14-census-after-open-1.png)（轮 [census](81dbcf14-census-analysis.json) 留下的截图）；
- 「Loading...」，停在 [Loading file: cube_30mm(2).stl](81dbcf14-census-after-open-2.png)（客机）或 `cube_30mm.stl`（fa），一直到用例结束。

[盘面截图](b2467f7d-run1-imported.png)里盘是空的。三个文件已经解到 `%TEMP%`：`cube_10mm.stl`、`cube_20mm.stl`、`cube_30mm.stl`，各 684 字节，SHA‑256 与 zip 里的成员相同（[从客机读回的清单](guest-temp-files.txt)）。

**对照实验**（同一个新会话里按「最干净的先做」的顺序，[census](a2aafd3d-census-analysis.json)，测试提交 `a2aafd3d`）：

| 做法 | 应用显示 | 盘上 |
| --- | --- | --- |
| 归档里只有 1 个 STL | 同样的错误框，另有一个 Warning：`The file does not contain any geometry data.`（[错误框](a2aafd3d-census-one_file_archive-dialog-1.png) · [Warning](a2aafd3d-census-one_file_archive-dialog-2.png)） | 没有对象 |
| 归档里 3 个 STL | 错误框 + 停在 `trio_10mm.stl` 的 Loading 框（[错误框](a2aafd3d-census-three_file_archive-dialog-1.png) · [Loading](a2aafd3d-census-three_file_archive-dialog-2.png)） | 没有对象 |
| 不经归档：File→Import 的文件框里一次写入 3 个 STL 路径 | 错误框（另一轮记录到错误框 + Loading 框，见 [日志](48e3aa7d-census-case.log)） | 没有对象 |
| 单个 STL 经 File→Import（#227、#244 的正式会话） | 正常 | 对象出现在盘上 |

应用自己的日志里没有这次失败的记录（信息级别的加载日志不输出，见上面那份清单末尾）。原因没有定位到源码；现象是：凡是一次调用里要载入归档解出的文件，或一次载入多个模型文件，2.4.0 都以这个错误结束。

**给测试同事。** 这是一条可以单独提缺陷的产品问题：复现步骤就是本目录的用例（`cube_10mm.stl`、`cube_20mm.stl`、`cube_30mm.stl` 三个二进制 STL 打成 zip，File→Import→Import Zip Archive…，全选，Open）。缺陷修复后，用例不需要改，直接重跑即可判定。

```powershell
& runner/hv_go.ps1 -Cases m7x_231_import_zip -NoSync
```

计时：客机用例内约 73 秒走到失败（空盘准备 11.7、文件框 8.0、预览 1.8、等对象 25.5、尝试保存 26.4）。领取到第一轮实跑约 20 分钟，之后没有改动用例；定位花在总控的对照实验上（5 次普查运行）。换初态的返工耗时和历史手工耗时均为未测。用例过程中没有人工桌面输入。用例登记为可单跑，不进默认回归。
