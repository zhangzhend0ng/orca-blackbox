# 性能采样与看板

Orca 的进程样本按实例写入 JSONL。Schema 2 记录运行 ID、实例 ID、进程创建时间、实际客机提交、阶段和单调时钟。v3 使用已有 run ID，fixture 子用例通过阶段里的 case_run_id 引用共享实例；重开验证生成新实例文件。报告也读取已有 schema 1 文件。

## 客机采集与回收

```powershell
$id = [guid]::NewGuid().ToString('N')
& runner\hv_go.ps1 -Cases m2_slice_chain -Perf -PerfBatchId $id
# 等 suite 停止后执行
& runner\hv_harvest.ps1 -PerfBatchId $id
Get-ChildItem "artifacts\perf_harvest\$id" -Filter *.jsonl |
  ForEach-Object { python -B tools/perf_report.py $_.FullName }
```

`-Perf` 也支持 `-V3` 和 `-WindowsMcpProbe -NativeSave`。省略 `-PerfBatchId` 时，启动日志会给出生成的 ID。性能回收按 ID 拉取并校验 SHA-256，常规 JUnit 和 v3 回收仍用各自的入口。只有批次清单而没有 JSONL 时，查看对应的用例日志；无终止记录的 JSONL 会显示为 partial。

Windows 有 psutil 时采集主进程和可归属的子进程，缺 psutil 时使用 ctypes 采集主进程。装包应针对 `ORCA_BB_GUEST_PYTHON` 指定的解释器。Linux 和 macOS 的独立采样需要 psutil，权限和平台所限的字段为 null。采样器统一支持显式 PID；按名称采集用于人工诊断。各平台的 GUI 执行器独立验收。

### m2 性能场景

```powershell
& runner\hv_go.ps1 -Cases m2_slice_chain -Perf -PerfViewport -PerfCycles 3
# 已备好 PresentMon 2.x CLI 时，追加 -PresentMonExe，传客机绝对路径。
```

- **动作耗时**：记录启动到稳定主窗和模型可见、切片点击到按钮变更及完成态、预览点击到观测到刀路。保留尝试编号和未观察到的结果。启动包含安全等待，预览包含稳定性确认。计时终点是驱动看到视觉判据的时刻。
- **视口交互**：`-PerfViewport` 分别尝试旋转、平移、缩放和预览层切换，记录输入到首次检测到视口变化的时间和观察区间。通过验证的动作才进入逐帧采集。PresentMon CSV 按 Orca PID、动作时段和交换链解析。输出显示 FPS、P50/P95/P99 帧时间、最长帧、慢帧率（超过 33.3、50、100 ms）、丢帧数与比例、帧开始到显示的延迟、可用的 CPU/GPU 忙碌时间。多条交换链保留各自数据。工具、事件或数据不足会写入原因。CSV 和 JSONL 随批次回收。
- **导出与重复操作**：`-PerfCycles` 记录 G-code 导出菜单发起到保存对话框、发起到文件稳定和确认保存到文件稳定。随后在同一 Orca 进程中以固定 STL 重复导入、切片和清空，分别记录每个阶段耗时。取每轮清空后的空闲样本中位数，记录 RSS、私有内存、进程句柄、GDI、USER 及相对首轮空闲的差值。
- **进程指标**：报告保留 CPU、内存、系统提供的进程工作集峰值、Windows 句柄、GDI/USER 和可用的线程数。I/O 是进程读写字节累计量，系统还能返回累计页错误数。报告展示从首个到最后一个有效样本的增量。缺失值保留为 null。整机 CPU、内存和网络走独立诊断采样。

性能试跑按固定构建、夹具、渲染器、分辨率和输入序列比较。Mesa 软件 GL 客机的帧时间只代表该环境。产品流畅度基线需要有代表性的 GPU 环境和重复试跑。

```powershell
python -B tools/perf_attach.py --pid 1234 --seconds 10
```

## Grafana

宿主的 windows_exporter 监听 9182 时，Docker Desktop 内的 Prometheus 通过 `host.docker.internal:9182` 访问。无可达网络的客机通过 JSONL 回收。主机趋势和进程样本可以按时间对照。

```powershell
docker compose -f deploy/monitoring/docker-compose.yml up -d
$env:ORCA_BB_GRAFANA_URL = 'http://localhost:3000'
# 在当前环境提供 ORCA_BB_GRAFANA_TOKEN，再按需导出。
python -B tools/perf_report.py --grafana path/to/run.jsonl
```

在 Grafana 添加 Prometheus 数据源 `http://prometheus:9090`。标注可按标签或 run ID 过滤。
