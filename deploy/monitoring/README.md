# deploy/monitoring — 指标看板（L5 层，可选后置）

本目录是「整套指标方案」的看板半边：**进程级 jsonl（harness/perf_monitor.py）
是主证据道，永远先于本目录启用**。这里只做整机趋势与跨 run 对齐。

## 分 lane 事实（先读）

- **宿主 farm lane（本目录直接可用）**：宿主机装 windows_exporter，Prometheus
  直接拉 `localhost:9182`。
- **客机 win11-test lane（当前不可拉取）**：该客机**没有可用 NIC**
  （docs/WINDOWS_MCP_PROBE.md 传输桥一节），PS Direct 不是 HTTP 通道——
  Prometheus 拉不到客机。客机侧继续走 jsonl（`artifacts/perf/*.jsonl` 随
  hv_harvest 回收）；等客机有 IP 后在 prometheus.yml 里取消注释
  `windows-guest` job 即可，harness 侧零改动。

## 启动（宿主，一次性）

```powershell
# 1) windows_exporter（MSI，装成服务）
msiexec /i windows_exporter-<ver>.amd64.msi /
  ENABLE_COLLECTORS="cpu,memory,net,gpu,process" /
  LISTEN_PORT=9182
# process collector 只盯被测 app（可选，减基数）：
#   在服务参数里加 --collector.process.whitelist="snapmaker-orca\.exe"

# 2) Prometheus + Grafana
docker compose -f deploy/monitoring/docker-compose.yml up -d
```

Grafana (`http://localhost:3000`)：加 Prometheus datasource（URL
`http://prometheus:9090`）→ Dashboards → Import → ID **12949**（Windows
主机模板，社区公认）。

## 用例步骤 ↔ 指标对齐

跑用例前导出两个变量，perf_monitor 会在每步边界打 Grafana 区间标注：

```bash
export ORCA_BB_PERF=1
export ORCA_BB_GRAFANA_URL=http://<grafana-host>:3000
export ORCA_BB_GRAFANA_TOKEN=<service account token>   # 无匿名写入时必填
```

看板 Annotations 里按 tag（label / step / perf-run）过滤即可看到步骤色带
叠在指标曲线上。

## 深挖工具（instrumented 用例按需挂，平时不跑）

| 指标 | 工具 | 一条命令 |
|---|---|---|
| 帧率/帧间隔 | PresentMon (Intel) | `PresentMon.exe -process_name snapmaker-orca.exe -output_file fps.csv -timed 120 -simple -stop_existing` |
| 文件/注册表事件 | procmon (Sysinternals) | `procmon /AcceptEula /Quiet /Minimized /BackingFile case.pml` … `/Terminate /SaveAs case.csv` |
| 每进程网络字节 | ETW (Windows 自带) | `wpr -start GeneralProfile -filemode` → `wpr -stop trace.etl`（WPA 看，或 Performance Toolkit SDK 解析） |
