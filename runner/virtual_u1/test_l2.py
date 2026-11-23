#!/usr/bin/env python3
"""test_l2.py — L2 monitoring scenario regression for the virtual U1.

Scenarios from the L2 plan. Each one writes a complete device state to
~/sc_probe/device_state.json on the Mac mini and checks two layers of what
Orca's device panel is fed:

  cache   the CLI's device cache (GET /api/cache/all over the SSH tunnel) —
          the state the web UI's data layer consumes
  ui      --ui: what the web UI really renders on its device control page,
          in a headless Chrome started with --remote-debugging-port. Read
          through the semantics tree (exact text) plus one pixel check (the
          task card's progress bar, measured off a screenshot).

The page is opened once in preflight and then left alone: every ui check is a
live update of the already open page — how monitoring is watched for real.

The device control page is reached by URL (the Orca desktop embedding entry),
not by clicking the device card's Control button, which does not answer
synthesized clicks.

Usage (host, tunnel 30996 up):
    python test_l2.py [--base http://127.0.0.1:30996] [--ui] [--cdp-port 9224]
                      [--artifacts DIR] [--negative-control]

--negative-control runs the same flow but judges each ui check by a
deliberately wrong expectation: it first waits for the correct one to hold
(page is live), then requires the mutated one to fail on that same page state.
A check that cannot go red proves nothing, so a red run has to precede
believing a green run.

Exit code: 0 = all PASS, 1 = any FAIL.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))

MAC = "coilwin@172.18.6.213"
KEY = None          # resolved from ~/.ssh/id_ed25519_codex_mac_gateway
STATE_FILE = "/Users/coilwin/sc_probe/device_state.json"
SN = "8110099900000001MOCK1"
SETTLE_S = 4.0      # prompt: flip -> wait 4s -> verify
UI_TIMEOUT_S = 25.0  # page pushes arrive every 2 s; leave room for reconnects
BAR_TOL = 0.02      # progress-bar fill is measured to about a pixel / 5.5

FILE = "test_cube.gcode"
PRINTING = {"print_state": "printing", "filename": FILE, "progress": 35.0,
            "print_stats": {"total_layer": 68, "current_layer": 34}}
LAYERS = {"card": {"percent": 35, "layer": "34/68"}}


def ssh(cmd):
    assert KEY, "ssh key not resolved"
    r = subprocess.run(
        ["ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
         MAC, cmd],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("ssh failed: %s %s" % (r.returncode, r.stderr[:200]))
    return r.stdout.strip()


def run_py(py):
    """Run a python snippet on the Mac — base64 transport avoids every
    layer of shell/quote escaping."""
    b64 = subprocess.run(
        ["python", "-c", "import base64,sys; sys.stdout.write(base64.b64encode(sys.stdin.read().encode()).decode())"],
        input=py, capture_output=True, text=True, check=True).stdout.strip()
    ssh("echo %s | base64 -d | python3 -" % b64)


def device_state(**kw):
    """A complete benign device state with kw applied (print_stats is merged
    into the nested dict)."""
    s = {"print_state": "idle", "progress": 0.0, "filename": "",
         "extruder": 22.5, "heater_bed": 22.1,
         "target_extruder": 0.0, "target_bed": 0.0,
         "fault": None,
         "print_stats": {"total_layer": 0, "current_layer": 0}}
    ps = dict(kw.pop("print_stats", None) or {})
    s.update(kw)
    s["print_stats"].update(ps)
    return s


def set_state(state):
    """Replace the Mac's state file wholesale and atomically: scenarios state
    the whole device, so nothing from the previous one leaks in, and the
    firmware (which re-reads every 2 s) never sees a torn file."""
    body = json.dumps(state)
    run_py("import json, os\n"
           "tmp = %r + '.tmp'\n"
           "open(tmp, 'w').write(%r)\n"
           "os.replace(tmp, %r)\n" % (STATE_FILE, body, STATE_FILE))


def device_page_url(base):
    """The device control page as Orca desktop opens it: the CLI advertises
    its page URLs on /api/health and the desktop reads that map
    (upstream GatewayService::web_url). Falls back to the embedding route on
    a CLI that does not advertise the page."""
    try:
        with urllib.request.urlopen(base + "/api/health", timeout=10) as r:
            page = (json.load(r).get("server_url") or {}).get("device_control")
        if page:
            return base.rstrip("/") + page
    except Exception:
        pass
    return "%s/web/flutter_web/index?tab=device_control&mode=1&id=%s&locale=en-US" % (base, SN)


def cache(base):
    with urllib.request.urlopen(base + "/api/cache/all", timeout=10) as r:
        return json.load(r)["data"]


def get_path(d, path):
    for p in path:
        d = (d or {}).get(p) if isinstance(d, dict) else None
    return d


def reconnect_via_node(base):
    """Send action.device.connect over the CLI's WCP endpoint using Node's
    built-in WebSocket (port MUST be explicit — the CLI's stored device
    port is stale after a broker restart)."""
    js = (
        "const ws = new WebSocket('%s/ws');"
        "const t = setTimeout(() => { console.log('TIMEOUT'); process.exit(2); }, 25000);"
        "ws.onopen = () => ws.send(JSON.stringify({jsonrpc:'2.0', id: 1,"
        "method:'action.device.connect', params:{sn:'%s', type:'LAN',"
        "ip:'172.18.6.213', port:7125}}));"
        "ws.onmessage = (ev) => { const d = JSON.parse(ev.data);"
        "  if (d.id) { clearTimeout(t); console.log(JSON.stringify(d));"
        "  process.exit(d.result && d.result.success ? 0 : 3); } };"
        "ws.onerror = () => { console.log('WS_ERROR'); process.exit(4); };"
        % (base, SN))
    r = subprocess.run(["node", "-e", js], capture_output=True, text=True, timeout=40)
    return r.returncode == 0, (r.stdout or r.stderr).strip()[:200]


# ---- ui layer -------------------------------------------------------------

def mutate(expect):
    """Deliberately wrong copy of a ui expectation (--negative-control)."""
    bad = json.loads(json.dumps(expect))
    temps = bad.get("temps")
    if temps == "not rendered":
        bad["temps"] = {"nozzle": (1, 1), "bed": (1, 1)}
    elif temps:
        temps["nozzle"] = (temps["nozzle"][0] + 5, temps["nozzle"][1])
    card = bad.get("card", {})
    if "percent" in card:
        card["percent"] += 10
    if "details" in card:
        card["details"] = [d + "_x" for d in card["details"]]
    if "layer" in card:
        cur, tot = card["layer"].split("/")
        card["layer"] = tot + "/" + cur
    if "state" in card:
        card["state"] = "no-such-state"
    if "texts" in bad:
        bad["texts"] = [t + " (nope)" for t in bad["texts"]]
    if "bar" in bad:
        bad["bar"] = (bad["bar"] + 0.3) % 1.0
    if "dialog" in bad:
        bad["dialog"] = {"exception": "offline", "offline": "exception", None: "offline"}.get(bad["dialog"], None)
    if "dialog_contains" in bad:
        bad["dialog_contains"] = [t + " (nope)" for t in bad["dialog_contains"]]
    return bad


def ui_verify(page, expect, nodes):
    """Observed vs expected on the live page -> (ok, detail)."""
    seen, ok = {}, True

    def want(key, value):
        seen[key] = value
        return value

    if "temps" in expect:
        try:
            temps = uiprobe.temperatures(nodes)
        except LookupError:
            temps = "not rendered"
        ok = want("temps", temps) == expect["temps"]
    if "card" in expect:
        try:
            card = uiprobe.task_card(nodes)
            card = {k: card.get(k) for k in expect["card"]}
        except LookupError:
            card = "not rendered"
        ok = want("card", card) == expect["card"] and ok
    if "texts" in expect:
        have = uiprobe.texts(nodes)
        ok = not want("texts", [t for t in expect["texts"] if t not in have]) and ok
    if "dialog" in expect:
        up = uiprobe.modal(nodes)
        shown = up["kind"] if up else None
        ok = want("dialog", shown) == expect["dialog"] and ok
        if shown == "exception" and "dialog_contains" in expect:
            ok = not want("dialog_contains", [t for t in expect["dialog_contains"] if t not in up["full"]]) and ok
    if "bar" in expect:
        grp = uiprobe.task_group(nodes)
        fill = None
        if grp is not None:
            x, y, w, h = grp["rect"]
            top = y + int(h * 0.6)    # the bar sits under the figures; the strip above is the header
            fill = uiprobe.bar_fill(page.screenshot(None, clip=(x, top, w, y + h - top)))
        fill = None if fill is None else round(fill, 3)
        ok = want("bar", fill) is not None and abs(fill - expect["bar"]) <= BAR_TOL and ok
    return ok, json.dumps(seen, ensure_ascii=False)


class Run:
    def __init__(self, args):
        self.base = args.base
        self.ui = args.ui
        self.negative = args.negative_control
        self.page = None
        self.artifacts = None
        self.shots = 0
        self.results = []        # (verdict, name, detail); verdict PASS | FAIL | INFO

    def record(self, verdict, name, detail):
        self.results.append((verdict, name, detail))
        print("%-4s %-22s %s" % (verdict, name, detail))

    def info(self, name, detail):
        if self.ui:
            self.record("INFO", name, detail)

    def set(self, **state):
        set_state(device_state(**state))

    def objects(self):
        return cache(self.base).get("objects", {})

    def check_cache(self, name, ok, detail):
        self.record("PASS" if ok else "FAIL", name, detail)

    def snapshot(self, name):
        if not (self.ui and self.artifacts):
            return
        self.shots += 1
        self.page.screenshot(os.path.join(self.artifacts, "%02d-%s.png" % (self.shots, name)))

    def check_ui(self, name, expect, ocr=None):
        if not self.ui:
            return
        nodes = self.wait_ui(name, expect)
        ok, detail = ui_verify(self.page, expect, nodes)
        self.snapshot(name)
        if self.negative:
            if not ok:
                self.record("FAIL", name + "-ui", "page never showed the expected state: " + detail)
            else:
                green, green_detail = ui_verify(self.page, mutate(expect), nodes)
                self.record("FAIL" if green else "PASS", name + "-ui",
                            ("UNEXPECTED GREEN: " if green else "mutated expectation rejected: ") + green_detail)
        else:
            self.record("PASS" if ok else "FAIL", name + "-ui", detail)
        if ocr and not self.negative:
            self.ocr_info(name, ocr, nodes)

    def wait_ui(self, name, expect, timeout_s=None):
        """Semantics nodes once `expect` holds on the live page (last nodes on timeout)."""
        end = time.time() + (timeout_s or UI_TIMEOUT_S)
        nodes = self.page.semantics()
        while not ui_verify(self.page, expect, nodes)[0]:
            if time.time() > end:
                break
            time.sleep(1.0)
            nodes = self.page.semantics()
        return nodes

    def ocr_info(self, name, kind, nodes):
        """Non-gating pixel evidence: what the Windows OCR engine reads off the
        painted canvas. Not a gate — the big blue percentage, for one, is
        misread by it."""
        try:
            if kind == "temps":
                clip, digits = uiprobe.temps_rect(nodes), "21021560"
            else:
                clip = uiprobe.exception_dialog(nodes)["rect"]
                digits = "0002133000000001"       # level 2, id 0x532, index 0, code 1
            words = uiprobe.ocr_words(self.page.screenshot(None, clip=clip, scale=2))
        except Exception as e:
            self.info(name + "-pixel", "ocr unavailable: %s" % e)
            return
        read = "".join(re.sub(r"\D", "", w[0]) for w in words)
        self.info(name + "-pixel", "digits=%s expect~%s | %s" % (read, digits, " ".join(w[0] for w in words)))

    def dismiss(self, button):
        """Close a modal through its semantics button (tap action)."""
        if not self.ui:
            return
        node = uiprobe.find_button(self.page.semantics(), button)
        if node is not None:
            self.page.click(node)


# ---- scenarios ------------------------------------------------------------

def scenario_1_temperature(run):
    run.set(print_state="idle", extruder=210.5, target_extruder=215.0, heater_bed=60.0)
    time.sleep(SETTLE_S)
    o = run.objects()
    ext = get_path(o, ["heaters", "extruder"])
    bed = get_path(o, ["heaters", "heater_bed"])
    ext2 = get_path(o, ["extruder", "temperature"])
    run.check_cache("temperature", ext == 210.5 and bed == 60.0 and ext2 == 210.5,
                    "nozzle=%s bed=%s extruder_obj=%s" % (ext, bed, ext2))
    # the page prints whole degrees: 210.5 renders as 210; no modal may be up
    run.check_ui("temperature", {"dialog": None, "card": {"state": "idle"},
                                 "temps": {"nozzle": (210, 215), "bed": (60, 0)}}, ocr="temps")


def scenario_2_progress(run):
    run.set(filename="calibration_cube.gcode", print_state="printing", progress=35.0)
    time.sleep(SETTLE_S)
    prog = get_path(run.objects(), ["display_status", "progress"])
    run.check_cache("progress", prog == 35.0, "display_status.progress=%s" % prog)
    run.check_ui("progress", {"card": {"percent": 35, "state": "working"}, "bar": 0.35})


def scenario_3_filename(run):
    run.set(**PRINTING)
    time.sleep(SETTLE_S)
    fn = get_path(run.objects(), ["print_stats", "filename"])
    run.check_cache("filename", fn == FILE, "print_stats.filename=%s" % fn)
    run.check_ui("filename", {"card": {"details": [FILE], "percent": 35}})


def scenario_4_error(run):
    run.set(fault="Foreign Object Detected", print_state="error", **{k: v for k, v in PRINTING.items() if k != "print_state"})
    time.sleep(SETTLE_S)
    o = run.objects()
    st = get_path(o, ["print_stats", "state"])
    msg = get_path(o, ["display_status", "message"])
    run.check_cache("fault-inject", st == "error" and msg == "Foreign Object Detected",
                    "state=%s message=%s" % (st, msg))
    # the fault surfaces as an exception modal (notify_exception_notification)
    run.check_ui("fault-inject", {"dialog": "exception",
                                  "dialog_contains": ["Exception", "Foreign Object Detected"]}, ocr="dialog")
    run.dismiss("Got it")


def scenario_5_layers(run):
    run.set(**PRINTING)
    time.sleep(SETTLE_S)
    info = get_path(run.objects(), ["print_stats", "info"]) or {}
    run.check_cache("layers", info.get("current_layer") == 34 and info.get("total_layer") == 68, "info=%s" % info)
    # "dialog": None — the fault modal must be gone once dismissed and the fault cleared
    run.check_ui("layers", dict(LAYERS, dialog=None))


def scenario_6_paused(run):
    run.set(print_state="paused", **{k: v for k, v in PRINTING.items() if k != "print_state"})
    time.sleep(SETTLE_S)
    st = get_path(run.objects(), ["print_stats", "state"])
    run.check_cache("paused", st == "paused", "print_stats.state=%s" % st)
    run.check_ui("paused", dict(LAYERS, texts=["Paused"]))


def scenario_7_offline(run):
    ssh("pkill -f virtual_u1_mqtt.py || true")
    time.sleep(SETTLE_S)
    conn = cache(run.base).get("connection", {})
    run.check_cache("device-offline", not conn.get("connected", True),
                    "connected=%s state=%s" % (conn.get("connected"), conn.get("state")))
    run.check_ui("device-offline", {"dialog": "offline", "temps": "not rendered"})


def restart_broker():
    ssh("pkill -f virtual_u1_mqtt.py; sleep 1; cd ~/sc_probe && nohup python3 virtual_u1_mqtt.py 7125 > mqtt_out.log 2>&1 & sleep 2; pgrep -f virtual_u1_mqtt >/dev/null && echo up")


def bound_clients():
    return ssh("cat ~/sc_probe/authorized_clients.json 2>/dev/null || echo []")


def wait_cache_connected(base, timeout_s):
    """Poll the cache until the device is connected again."""
    end = time.time() + timeout_s
    while time.time() < end:
        d = cache(base)
        if d.get("connection", {}).get("connected") and get_path(d, ["objects", "print_stats"]):
            return d
        time.sleep(1.0)
    return None


def scenario_8_online(run):
    # A paired slicer reconnects silently only while the device still knows
    # it. On a fresh setup, pair once first (stands in for the touchscreen tap).
    cid = (cache(run.base).get("connection") or {}).get("client_id")
    if not cid or '"%s"' % cid not in bound_clients():
        print("device-online: pairing %s once so the device remembers it" % cid)
        restart_broker()
        time.sleep(SETTLE_S)
        reconnect_via_node(run.base)
        wait_cache_connected(run.base, 45)
        run.dismiss("OK")
    # the state file outlives the broker: pin what the device comes back as
    run.set(extruder=22.5, heater_bed=22.1, **PRINTING)
    t_up = time.time()
    restart_broker()
    # The CLI's reconnect supervisor does the reconnect by itself (observed
    # backoff ~3/4/5/11/25 s); an explicit connect is only the fallback.
    d = wait_cache_connected(run.base, 60)
    how = "reconnected on its own %.0fs after the broker came back" % (time.time() - t_up)
    if d is None:
        ok, _ = reconnect_via_node(run.base)
        d = wait_cache_connected(run.base, 45)
        how = "no self-heal in 60s, forced connect ok=%s" % ok
    conn = (d or {}).get("connection", {})
    run.check_cache("device-online", bool(d), "%s connected=%s state=%s" % (how, conn.get("connected"), conn.get("state")))
    run.check_ui("device-online", {"dialog": None, "temps": {"nozzle": (22, 0), "bed": (22, 0)}})
    # recovery means live updates resumed, not just a repainted page
    run.set(**dict(PRINTING, progress=80.0))
    run.check_ui("device-online-live", {"card": {"percent": 80}, "bar": 0.80})


SCENARIOS = (scenario_1_temperature, scenario_2_progress, scenario_3_filename,
             scenario_4_error, scenario_5_layers, scenario_6_paused,
             scenario_7_offline, scenario_8_online)


def main():
    global KEY
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:30996")
    ap.add_argument("--ui", action="store_true", help="also assert what the web UI renders")
    ap.add_argument("--cdp-port", type=int, default=9224, help="Chrome --remote-debugging-port")
    ap.add_argument("--artifacts", default=None, help="dir for per-check screenshots (default artifacts/l2_ui/<ts>)")
    ap.add_argument("--negative-control", action="store_true",
                    help="ui checks must reject a mutated expectation (needs --ui)")
    args = ap.parse_args()
    key = os.path.expanduser("~/.ssh/id_ed25519_codex_mac_gateway")
    KEY = key if os.path.exists(key) else None
    run = Run(args)

    # preflight: the CLI behind --base is the Mac fixture's, broker running, device connected
    try:
        d = cache(args.base)
    except Exception as e:
        print("PREFLIGHT FAIL: cannot reach CLI cache (%s)" % e)
        return 1
    if d.get("sn") != SN:
        # a Windows Orca on this host runs its own CLI on 30996 too
        print("PREFLIGHT FAIL: %s serves device %r (connected=%s), not the virtual U1 %s — wrong --base "
              "(another Orca's CLI on this port?), or the virtual U1 is not the CLI's current device"
              % (args.base, d.get("sn"), d.get("connection", {}).get("connected"), SN))
        return 1
    if not d.get("connection", {}).get("connected"):
        print("PREFLIGHT FAIL: device not connected — run action.device.connect first")
        return 1
    print("preflight OK: %s connected" % SN)

    if run.ui:
        global uiprobe
        from cdpclient import Page
        import uiprobe
        if run.negative:
            print("ui: NEGATIVE CONTROL — every ui check must reject a mutated expectation")
        try:
            run.page = Page(args.cdp_port, target="127.0.0.1:%d" % int(args.base.rsplit(":", 1)[1]))
        except Exception as e:
            print("PREFLIGHT FAIL: no Chrome debug port %d (%s) — start tools/chrome_headless.sh" % (args.cdp_port, e))
            return 1
        stamp = time.strftime("%Y%m%d-%H%M%S")
        run.artifacts = args.artifacts or os.path.join(HERE, "artifacts", "l2_ui", stamp + ("-negative" if run.negative else ""))
        os.makedirs(run.artifacts, exist_ok=True)
        print("ui: artifacts -> %s%s" % (os.path.relpath(run.artifacts, HERE), "  [NEGATIVE CONTROL]" if run.negative else ""))
        try:
            url = device_page_url(args.base)
            print("ui: device control page %s" % url.split("://", 1)[1])
            run.page.navigate(url, settle_s=4.0)
            run.wait_ui("preflight", {"card": {"state": "idle"}} if get_path(d, ["objects", "machine_state_manager", "main_state"]) == 0
                         else {"card": {"state": "working"}}, timeout_s=30.0)
            if uiprobe.task_group(run.page.semantics()) is None:
                print("PREFLIGHT FAIL: device control page did not render its Printing Task card")
                return 1
            # a modal left from an earlier fault would shadow the first check
            run.dismiss("Got it")
            run.dismiss("OK")
            print("ui: device control page live (semantics tree ready)")
        except Exception as e:
            print("PREFLIGHT FAIL: device control page (%s)" % e)
            return 1

    try:
        for fn in SCENARIOS:
            try:
                fn(run)
            except Exception as e:
                run.check_cache(fn.__name__.split("_", 2)[2], False, "EXC %r" % e)
    finally:
        cleanup(run)

    gate = [(v, n, dt) for v, n, dt in run.results if v != "INFO"]
    npass = sum(1 for v, _, _ in gate if v == "PASS")
    ncache = sum(1 for _, n, _ in gate if not n.endswith("-ui") and not n.endswith("-live"))
    print("\n==== L2 RESULT%s: %d/%d PASS (cache %d, ui %d) ====" % (
        " [NEGATIVE CONTROL]" if run.negative else "", npass, len(gate), ncache, len(gate) - ncache))
    for v, n, _ in gate:
        if v != "PASS":
            print("  %-4s %s" % (v, n))
    for v, n, dt in run.results:
        if v == "INFO":
            print("  %-4s %-22s %s" % (v, n, dt))
    if run.artifacts:
        print("  screenshots: %s" % os.path.relpath(run.artifacts, HERE))
    return 0 if npass == len(gate) else 1


def cleanup(run):
    # leave the device in a benign idle state
    try:
        set_state(device_state())
    except Exception as e:
        print("cleanup failed:", e)
    if run.page:
        run.page.close()


if __name__ == "__main__":
    sys.exit(main())
