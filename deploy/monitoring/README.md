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
