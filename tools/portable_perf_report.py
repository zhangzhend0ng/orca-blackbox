"""Create a local, offline report from the existing benchmark artifacts."""

from collections import Counter
import csv
import html
import json
from pathlib import Path
from statistics import median
import subprocess

from tools.perf_report import main as summarize

MODELS = {"showcase_dense": "Ribbed Towers", "showcase_snapmates": "Snapmates"}
CANVASES = {"prepare": "Prepare", "preview": "Preview", "assemble": "Assemble"}


def traces(path):
    points = {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    samples = [row for row in rows if row["ev"] == "proc" and row["pid"] == rows[0].get("anchor_pid")]
    for key, label in (
        ("cpu_pct", "CPU % · 单核=100%"), ("rss_mb", "工作集 MiB"),
        ("private_mb", "私有内存 MiB"), ("read_bytes", "累计读取 MiB"), ("write_bytes", "累计写入 MiB"),
        ("page_faults", "累计页错误"), ("handles", "进程句柄"),
        ("gdi", "GDI 对象"), ("user_obj", "USER 对象"),
        ("gpu_engine_pct", "GPU 最忙引擎 %"), ("gpu_dedicated_mb", "GPU 专用显存 MiB"),
        ("gpu_shared_mb", "GPU 共享显存 MiB"),
    ):
        scale = 2 ** 20 if key.endswith("_bytes") else 1
        points[label] = [[r["t_rel"], r[key] / scale] for r in samples if r.get(key) is not None]

    frame_csv = path.with_suffix(".render.csv")
    if not frame_csv.exists():
        return {label: series for label, series in points.items() if series}
    with frame_csv.open(encoding="utf-8", newline="") as file:
        frames = [row for row in csv.DictReader(file) if row["swap_succeeded"] == "1"]
    counts = Counter()
    prior = {}
    for row in frames:
        now = float(row["t_rel"])
        canvas = CANVASES[row["canvas_type"]]
        identity = canvas, row["canvas_id"]
        counts[canvas, int(now)] += 1
        if identity in prior:
            points.setdefault(f"提交间隔 ms · {canvas}", []).append([now, (now - prior[identity]) * 1000])
        prior[identity] = now
        points.setdefault(f"渲染至提交 ms · {canvas}", []).append([now, float(row["render_before_swap_ms"])])
        points.setdefault(f"SwapBuffers ms · {canvas}", []).append([now, float(row["swap_call_ms"])])
    for canvas in dict.fromkeys(canvas for canvas, _ in counts):
        duration = int(max(row["t_rel"] for row in rows))
        points[f"应用提交帧／秒 · {canvas}"] = [[t, counts[canvas, t]] for t in range(duration + 1)]
    return {label: series for label, series in points.items() if series}


def link(path, label):
    return f'<a href="{html.escape(path.name, quote=True)}">{html.escape(label)}</a>'


def playback(video, encoder):
    if encoder is None or not video.is_file():
        return video
    target = video.with_suffix(".playback.mp4")
    if target.is_file() and target.stat().st_mtime_ns >= video.stat().st_mtime_ns:
        return target
    pending = video.with_suffix(".encoding.mp4")
    completed = subprocess.run([str(encoder), "-nostdin", "-hide_banner", "-loglevel", "error",
                                "-y", "-i", str(video), "-an", "-c:v", "libx264",
                                "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
                                "-movflags", "+faststart", str(pending)],
                               capture_output=True, timeout=180, check=False)
    if completed.returncode == 0:
        pending.replace(target)
        return target
    pending.unlink(missing_ok=True)
    return video


def scenario(path, encoder):
    summary = json.loads(path.with_suffix(".summary.json").read_text(encoding="utf-8"))
    name = MODELS[summary["meta"]["label"]]
    cards = []
    for key, title in (("launch_to_model_visible", "启动至可见"),
                       ("slice_click_to_export_enabled", "切片至可导出"),
                       ("export_request_to_stable_file", "导出至文件稳定")):
        events = summary.get("measurements", {}).get(key, {}).get("events", [])
        observed = [event["duration_ms"] / 1000 for event in events
                    if event.get("status") == "observed" and event.get("duration_ms") is not None]
        value = f"{median(observed):.2f} 秒" if observed else "缺测"
        cards.append(f"<li>{title} <strong>{value}</strong></li>")
    native = summary.get("native_frame_trace", {})
    captured = [row for row in summary.get("frame_captures", [])
                if (row.get("frame_summary") or {}).get("metrics")]
    display = "显示帧已采集，按动作与交换链查看汇总" if captured else "实际显示 FPS 缺测"
    native_note = f'应用帧记录 {native["frames"]} 条（{native["status"]}）' if native.get("frames") else "应用提交帧缺测"
    artifacts = [link(path, "进程与动作 JSONL"), link(path.with_suffix(".summary.json"), "指标汇总")]
    for suffix, label in ((".render.csv", "逐帧应用 CSV"), (".render.bin", "原生逐帧文件"),
                          (".frames.csv", "显示帧 CSV"), (".video.json", "录像时间轴")):
        target = path.with_suffix(suffix)
        if target.is_file():
            artifacts.append(link(target, label))
    original = path.with_suffix(".mp4")
    try:
        video = playback(original, encoder)
    except (OSError, subprocess.TimeoutExpired):
        video = original
    if original.is_file():
        artifacts.append(link(original, "原始录像"))
    movie = f'<video controls preload="metadata" src="{html.escape(video.name, quote=True)}"></video>' if video.is_file() else ""
    series = traces(path)
    gpu = "GPU 引擎和显存见可用曲线" if any(label.startswith("GPU ") for label in series) else "GPU 指标缺测"
    data = json.dumps(series, separators=(",", ":"), ensure_ascii=False, allow_nan=False).replace("<", "\\u003c")
    return (f'<section><h2>{name}</h2><ul>{"".join(cards)}</ul><p>{native_note} · {display} · {gpu}</p>'
            f'{movie}<div class="chart"><label>性能指标 <select></select></label>'
            f'<canvas role="img"></canvas><script type="application/json">{data}</script></div>'
            f'<p>{" · ".join(artifacts)}</p></section>')


def build_report(directory, encoder=None):
    run_file = directory / "run.json"
    machine = json.loads(run_file.read_text(encoding="utf-8")) if run_file.is_file() else {}
    inputs = sorted(path for path in directory.glob("showcase_*__*.jsonl")
                    if path.name.split("__")[0] in MODELS)
    if inputs:
        summarize([str(path) for path in inputs])
    chunks = [scenario(path, encoder) for path in inputs if path.with_suffix(".summary.json").is_file()]
    status = {0: "主流程通过", 1: "主流程未通过"}.get(machine.get("exit_code"), "运行记录")
    title = f"Orca 性能测试 · {status}"
    error = f'<p role="alert">{html.escape(machine["error"])}</p>' if machine.get("error") else ""
    meta = " · ".join(link(directory / name, label) for name, label in
                      (("run.json", "机器与构建信息"), ("run.log", "执行日志")) if (directory / name).is_file())
    body = "".join(chunks)
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orca 性能测试</title>
<style>
:root{color-scheme:light dark}body{font:16px/1.55 system-ui,sans-serif;margin:0}
main{max-width:1000px;margin:auto;padding:24px}section{border-top:1px solid #8885;margin-top:24px;padding-top:8px}
ul{display:flex;flex-wrap:wrap;gap:8px 32px;padding-left:20px}video{display:block;width:100%;max-height:65vh}
.chart{margin-top:14px}canvas{display:block;width:100%;height:255px;margin-top:8px}select{font:inherit;max-width:100%}
</style><main>
<h1>PAGE_TITLE</h1>ERROR<p>META</p>SCENARIOS
</main><script>
for (const panel of document.querySelectorAll(".chart")) {
  const series = JSON.parse(panel.querySelector("script").textContent);
  const select = panel.querySelector("select");
  const chart = panel.querySelector("canvas");
  for (const metric of Object.keys(series)) select.add(new Option(metric, metric));
  const firstFrameMetric = Object.keys(series).find(k => k.startsWith("应用提交帧"));
  if (firstFrameMetric) select.value = firstFrameMetric;
  if (!select.options.length) { panel.hidden = true; continue; }
  function draw() {
    const data = series[select.value];
    const width = chart.clientWidth;
    const height = chart.clientHeight;
    if (!width || !height) return;
    const scale = window.devicePixelRatio || 1;
    chart.width = width * scale;
    chart.height = height * scale;
    const ctx = chart.getContext("2d");
    ctx.scale(scale, scale);
    ctx.font = "12px system-ui";
    const color = getComputedStyle(chart).color;
    ctx.fillStyle = color;
    const left = 52, top = 13, bottom = height - 32, right = width - 18;
    const maxX = data.reduce((maximum, p) => Math.max(maximum, p[0]), 1);
    const maxY = data.reduce((maximum, p) => Math.max(maximum, p[1]), 1);
    const x = t => left + (right - left) * t / maxX;
    const y = v => bottom - (bottom - top) * v / maxY;
    ctx.strokeStyle = color;
    ctx.globalAlpha = .22;
    for (let i = 0; i <= 4; i++) {
      const v = maxY * i / 4;
      ctx.beginPath();ctx.moveTo(left,y(v));ctx.lineTo(right,y(v));ctx.stroke();
    }
    ctx.globalAlpha = 1;
    const fmt = new Intl.NumberFormat("zh-CN", {maximumFractionDigits:1,notation:"compact"});
    for (let i = 0; i <= 4; i++) {
      const v = maxY * i / 4, t = maxX * i / 4;
      ctx.fillText(fmt.format(v), 4, y(v) + 4);
      ctx.fillText(fmt.format(t), Math.min(x(t),right - 15), bottom + 17);
    }
    ctx.fillText("距启动（秒）", Math.max(left,(left + right) / 2 - 44), height - 2);
    ctx.strokeStyle = matchMedia("(prefers-color-scheme: dark)").matches ? "#65c8fb" : "#1266a4";
    ctx.fillStyle = ctx.strokeStyle;
    ctx.lineWidth = 1.5;
    const points = select.value.startsWith("提交间隔") || select.value.includes(" ms · ");
    ctx.beginPath();
    data.forEach(([t,v],i) => {
      if (points) { ctx.moveTo(x(t)+2,y(v));ctx.arc(x(t),y(v),2,0,Math.PI*2); }
      else if (i === 0) ctx.moveTo(x(t),y(v));
      else ctx.lineTo(x(t),y(v));
    });
    if (points) ctx.fill(); else ctx.stroke();
    chart.setAttribute("aria-label", select.value + "，" + data.length + " 个样本");
  }
  select.addEventListener("change", draw);
  new ResizeObserver(draw).observe(panel);
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change",draw);
  draw();
}
</script></html>"""
    rendered = (page.replace("PAGE_TITLE", html.escape(title)).replace("ERROR", error)
                .replace("META", meta).replace("SCENARIOS", body))
    (directory / "index.html").write_text(rendered, encoding="utf-8")
