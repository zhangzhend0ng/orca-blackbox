"""virtual_u1_mqtt.py — minimal MQTT broker + moonraker status simulator.

The device side of the virtual Snapmaker U1: the printer runs a local MQTT
broker (mosquitto) and moonraker publishes klipper status there every 2 s
(retained, QoS 1, topic "moonraker/status" — measured from u1-moonraker's
lava/moonraker.conf and components/mqtt.py). snapmaker_control connects to
the SRV-advertised port and speaks MQTT (verified live 2026-11-23: the CLI
attempted an MQTT connect to our advertised port).

Pure stdlib, single client focus (the CLI). Supports protocol levels 3/4/5,
CONNECT/CONNACK, SUBSCRIBE/SUBACK, PUBLISH QoS 0/1 with retain, PUBACK,
PINGREQ/PINGRESP, DISCONNECT.

Device state machine: reads a state file (JSON) each tick; the test flips
print_state / progress / temps / fault there and this publishes it.
"""
import asyncio
import json
import struct
import sys
import time
from pathlib import Path

STATE_FILE = Path(__file__).with_name("device_state.json")
DEVICE_SN = "8110099900000001MOCK1"   # must match mdns_advertise.py
STATUS_TOPIC = DEVICE_SN + "/status"           # CLI subscribes <sn>/status
NOTIFICATION_TOPIC = DEVICE_SN + "/notification"   # moonraker/notification bridged by unisrv
TLS_PORT = 8883                                # mTLS broker port advertised in notify_lan_auth
CERT_DIR = Path(__file__).with_name("certs")
# Bound LAN clients (the real U1 keeps them in printer_data/mqtt/client.json).
# A listed client's confirm_lan_status succeeds without a touchscreen prompt,
# so a slicer that paired once reconnects silently after a device restart;
# an unlisted one is "unauthorized", which Orca reports as "The device
# authorization has been removed". Delete the file to re-trigger pairing.
CLIENTS_FILE = Path(__file__).with_name("authorized_clients.json")
ACCESS_CODE = "12345678"     # LAN access code; also the CLI's config-topic prefix (spec DEFAULT_CODE)

# Active machine exceptions, in the shape the web UI parses out of
# server.exception.query / notify_exception_status: id, index, code, level
# (ints), message, timestamp (epoch number). Identity of the stock fault is
# error_0002053200000001 in the UI's strings ("Possible Foreign Object
# Detected on Print Bed"): level 2, id 0x532, index 0, code 1.
FAULT_DEFAULT = {"level": 2, "id": 0x532, "index": 0, "code": 1}
_fault_since = {}     # exception identity -> epoch of first sight


def known_clients():
    try:
        return set(json.loads(CLIENTS_FILE.read_text()))
    except Exception:
        return set()


def remember_client(clientid):
    clients = known_clients()
    if clientid and clientid not in clients:
        clients.add(clientid)
        CLIENTS_FILE.write_text(json.dumps(sorted(clients)))


def mint_client_cert(clientid):
    """One-shot CA + per-client cert via the openssl CLI (macOS/Linux).

    A real U1's C++ LanManager mints these; we reproduce the shape the CLI
    expects (ca/cert/key PEM strings + port) per the n3o pairing spec."""
    import subprocess
    CERT_DIR.mkdir(exist_ok=True)
    ca_key = CERT_DIR / "ca.key"
    ca_pem = CERT_DIR / "ca.pem"
    if not ca_pem.exists():
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(ca_key), "-out", str(ca_pem), "-days", "3650",
                        "-subj", "/CN=virtual-u1-ca"], check=True, capture_output=True)
    ckey = CERT_DIR / (clientid + ".key")
    ccsr = CERT_DIR / (clientid + ".csr")
    cpem = CERT_DIR / (clientid + ".pem")
    subprocess.run(["openssl", "req", "-newkey", "rsa:2048", "-nodes",
                    "-keyout", str(ckey), "-out", str(ccsr),
                    "-subj", "/CN=" + clientid], check=True, capture_output=True)
    subprocess.run(["openssl", "x509", "-req", "-in", str(ccsr), "-CA", str(ca_pem),
                    "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(cpem),
                    "-days", "3650"], check=True, capture_output=True)
    return {"ca": ca_pem.read_text(), "cert": cpem.read_text(), "key": ckey.read_text()}

DEFAULT_STATE = {
    "print_state": "idle",       # idle | printing | paused | complete | error
    "progress": 0.0,             # 0..100
    "filename": "",
    "extruder": 22.5, "heater_bed": 22.1,
    "target_extruder": 0.0, "target_bed": 0.0,
    "fault": None,               # e.g. {"code": "0002 0532 0000 0001", "msg": "..."}
    "print_stats": {"state": "idle", "filename": "", "total_layer": 0, "current_layer": 0},
    # G-code file layout the web UI derives print % and remaining time from
    # (server.files.metadata + virtual_sdcard.file_position): g-code body
    # sits between start/end byte, a thumbnail block trails the file.
    "gcode_start_byte": 20000, "gcode_end_byte": 1020000,
    "gcode_size": 1040000, "estimated_time": 3600.0,
}

# machine_state_manager as the real U1 reports it: two integer fields, NOT a
# state string (that was invented here and left the web UI's Printing Task
# panel stuck on idle — it parses main_state/action_code with parseInt and
# keeps the old value when a field is missing). main_state values follow the
# web UI's own table (0 Idle, 1 Working, ..., 7 Error, 14 Offline); action
# codes are klipper ActionCodes per spec/snapmakercloud.py (AC_PRINT_*), i.e.
# the snapshot each job event carries: started 1-0, paused 1-129, complete
# 1-140, error 1-138. What the machine reports *after* complete/error was
# never captured from a real device (assumption) — probe it by setting
# msm_main_state / msm_action_code in the state file.
MSM = {
    "idle":     (0, 0),
    "printing": (1, 0),
    "paused":   (1, 129),
    "complete": (1, 140),
    "error":    (1, 138),
}


_last_good = None


def load_state():
    """Current state file. A torn read (the test rewrites the file while we
    read it) falls back to the last good snapshot instead of resetting the
    file — rewriting it here would silently wipe the scenario under test."""
    global _last_good
    if not STATE_FILE.exists():
        s = dict(DEFAULT_STATE)
        STATE_FILE.write_text(json.dumps(s))
        _last_good = s
        return s
    try:
        _last_good = json.loads(STATE_FILE.read_text())
    except Exception:
        pass
    return _last_good if _last_good is not None else dict(DEFAULT_STATE)


def int_or(s, key, default):
    """State-file int with a default; an explicit null also means "unset"."""
    v = s.get(key, None)
    return default if v is None else int(v)


def fault_message(fault):
    """Text of a state-file fault: a bare string, or a dict with message/msg."""
    if isinstance(fault, str):
        return fault
    return (fault or {}).get("message") or (fault or {}).get("msg") or ""


def exceptions(s):
    """Active exceptions. `fault` in the state file is null, a message string
    (stock identity above) or a dict overriding level/id/index/code/message.
    The timestamp is pinned when an exception first appears so repeated
    status pushes do not read as a fresh exception."""
    fault = s.get("fault", None)
    if not fault:
        _fault_since.clear()
        return []
    if isinstance(fault, str):
        fault = {"message": fault}
    e = {k: int(fault.get(k, v)) for k, v in FAULT_DEFAULT.items()}
    e["message"] = fault_message(fault)
    key = tuple(e[k] for k in ("level", "id", "index", "code")) + (e["message"],)
    if key not in _fault_since:
        _fault_since.clear()
        _fault_since[key] = time.time()
    e["timestamp"] = _fault_since[key]
    return [e]


def file_position(s, start, end):
    """virtual_sdcard.file_position for the loaded file: progress % mapped
    onto the g-code body, i.e. the inverse of the web UI's own
    (file_position - start) * 100 / (end - start)."""
    pct = min(max(s.get("progress", 0.0), 0.0), 100.0)
    return int(start + (end - start) * pct / 100.0)


def build_status():
    """Full klipper object snapshot — one source for status pushes AND RPC
    replies (printer.objects.subscribe/query), so the initial subscription
    state equals the following notify_status_update payloads."""
    s = load_state()
    fault_msg = fault_message(s.get("fault", None))
    ext = s.get("extruder", 22.5)
    bed = s.get("heater_bed", 22.1)
    main_state, action_code = MSM.get(s["print_state"], (0, 0))
    start = int(s.get("gcode_start_byte", 20000))
    end = int(s.get("gcode_end_byte", 1020000))
    size = int(s.get("gcode_size", end + 20000))
    name = s.get("filename", "")
    loaded = bool(name)
    pos = file_position(s, start, end) if loaded else 0
    return {
        "print_stats": {"state": s["print_state"], "filename": name,
                        # the web UI prints "current_layer/total_layer" (both read
                        # from info; singular key is the one it looks up)
                        "info": {"print_duration": 0, "total_layer": s["print_stats"].get("total_layer", 0),
                                 "current_layer": s["print_stats"].get("current_layer", 0)}},
        "display_status": {"progress": s.get("progress", 0.0), "message": fault_msg or ""},
        "heaters": {"extruder": ext, "heater_bed": bed,
                    "target_extruder": s.get("target_extruder", 0.0),
                    "target_heater_bed": s.get("target_bed", 0.0)},
        # real moonraker exposes extruder/heater_bed as standalone printer
        # objects too — the CLI subscribes to these field sets directly
        "extruder": {"temperature": ext, "target": s.get("target_extruder", 0.0),
                     "power": 0.0 if s.get("target_extruder", 0.0) <= 0 else 0.5,
                     "can_extrude": ext > 170.0},
        "heater_bed": {"temperature": bed, "target": s.get("target_bed", 0.0),
                       "power": 0.0 if s.get("target_bed", 0.0) <= 0 else 0.5},
        "toolhead": {"position": [0.0, 0.0, 0.0, 0.0]},
        "virtual_sdcard": {"progress": pos / size if size else 0.0,
                           "is_active": s["print_state"] == "printing",
                           "file_position": pos, "file_size": size if loaded else 0,
                           "file_path": name},
        "gcode_move": {"speed": 100.0},
        "idle_timeout": {"state": "Idle" if s["print_state"] == "idle" else "Printing"},
        "machine_state_manager": {"main_state": int_or(s, "msm_main_state", main_state),
                                  "action_code": int_or(s, "msm_action_code", action_code)},
    }


def api_result(method, params):
    """JSON-RPC result for the API channel (<sn>/request). Shapes follow
    stock moonraker: objects.list → {"objects": {name: null}}; subscribe/
    query → {"eventtime": t, "status": {...}} filtered by requested fields."""
    if method == "printer.objects.list":
        return {"objects": {k: None for k in build_status()}}
    if method in ("printer.objects.subscribe", "printer.objects.query"):
        full = build_status()
        want = (params or {}).get("objects") or {}
        status = {}
        for obj, fields in want.items():
            if obj in full:
                status[obj] = {k: v for k, v in full[obj].items()
                               if not fields or k in fields}
        return {"eventtime": time.time(), "status": status}
    if method == "server.exception.query":
        return {"exceptions": exceptions(load_state())}
    if method == "server.files.metadata":
        # stock moonraker file metadata; the web UI's task card reads exactly
        # gcode_start_byte / gcode_end_byte / estimated_time (print % and
        # remaining time are derived from them + virtual_sdcard.file_position,
        # an empty reply leaves the card at 0% / "N/A")
        s = load_state()
        start = int(s.get("gcode_start_byte", 20000))
        end = int(s.get("gcode_end_byte", 1020000))
        return {"filename": (params or {}).get("filename", ""),
                "modified": time.time(), "size": int(s.get("gcode_size", end + 20000)),
                "permissions": "rw",
                "gcode_start_byte": start, "gcode_end_byte": end,
                "estimated_time": s.get("estimated_time", 3600.0),
                "filament_total": 0.0, "first_layer_height": 0.2, "layer_height": 0.2,
                "object_count": 1, "thumbnails": []}
    if method == "printer.info":
        # stock moonraker printer.info — the app gates the device control
        # page on this (empty {} reply left Control dead; broker log showed
        # 3 unanswered-shape calls at each connection setup)
        return {"state": "ready", "state_message": "Printer is ready",
                "hostname": "u1", "software_version": "1.4.1",
                "cpu_info": "Snapmaker U1",
                "klipper_path": "/home/pi/klipper",
                "python_path": "/usr/bin/python3",
                "log_file": "/tmp/klippy.log",
                "config_file": "printer.cfg"}
    if method == "machine.system_info":
        return {"system_info": {
            "cpu_info": {"cpu": "BCM2837", "chip": "BCM2837B0",
                         "units": 4, "memory": "1024 MiB"},
            "sd_info": {"manufacturer": "SD", "capacity": "32 GB"},
            "distribution": {"name": "Snapmaker OS", "version": "1.4.1"},
            "available_services": ["klipper", "moonraker", "unisrv"]}}
    if method == "system.get_device_info":
        return {"sn": DEVICE_SN, "name": "U1", "model": "Snapmaker U1",
                "machine_type": "Snapmaker U1", "firmware_version": "1.4.1",
                "hardware_version": "U1", "ip": "172.18.6.213",
                "port": 7125, "link_mode": "lan"}
    return {}


class Client:
    def __init__(self, broker, reader, writer):
        self.broker, self.r, self.w = broker, reader, writer
        self.subscriptions = {}   # topic filter -> qos
        self.retains = broker.retains
        self.level = 4            # MQTT protocol level negotiated at CONNECT

    async def send(self, byte):
        import binascii
        self.broker.log("TX %s" % binascii.hexlify(byte[:48]).decode())
        self.w.write(byte)
        await self.w.drain()

    async def read_packet(self):
        first = await self.r.readexactly(1)
        pkt_type = first[0] >> 4
        flags = first[0] & 0x0F           # PUBLISH qos lives HERE (bits 1-2)
        multiplier, value, i = 1, 0, 0
        while True:
            b = (await self.r.readexactly(1))[0]
            value += (b & 0x7F) * multiplier
            if not b & 0x80:
                break
            multiplier *= 128
            i += 1
            if i > 3:
                raise ValueError("bad remaining length")
        body = await self.r.readexactly(value) if value else b""
        return pkt_type, body, flags

    def encode_length(self, n):
        out = b""
        while True:
            d = n % 128
            n //= 128
            if n:
                d |= 0x80
            out += bytes([d])
            if not n:
                return out

    def topic_matches(self, filt, topic):
        if filt == topic or filt == "#":
            return True
        f, t = filt.split("/"), topic.split("/")
        if "+" in f:
            if len(f) != len(t) and not (f[-1] == "#" and len(f) - 1 <= len(t)):
                return False
            return all(a == b or a == "+" for a, b in zip(f, t)) or (
                f[-1] == "#" and all(a == b or a == "+" for a, b in zip(f[:-1], t[:len(f) - 1])))
        return filt == topic

    async def publish_to(self, topic, payload, qos, retain):
        data = payload.encode() if isinstance(payload, str) else payload
        if retain:
            self.retains[topic] = (data, qos)
        for c in self.broker.clients:
            if not any(c.topic_matches(f, topic) for f in c.subscriptions):
                continue
            # Real-device frame (pairing.pcapng #18): [2-byte topic-len][topic][pid if qos][props 0x00][payload]
            body = struct.pack(">H", len(topic)) + topic.encode()
            if qos:
                body += struct.pack(">H", self.broker.next_pid())
            if c.level == 5:
                body += b"\x00"          # v5 property length = 0 (real device sends none)
            body += data
            pkt = bytes([0x30 | (0x02 if qos else 0)]) + self.encode_length(len(body)) + body
            await c.send(pkt)

    async def handle(self):
        try:
            pkt, body, _flags = await self.read_packet()
            if pkt != 1:
                return
            level = body[6] if len(body) > 7 else 4
            flags = body[7]
            keep = struct.unpack(">H", body[8:10])[0] if len(body) > 9 else 60
            props = bytes([0]) if level == 5 else b""
            self.level = level
            # CONNACK: session-present=0, rc=0 (+ 1-byte zero property length for v5)
            await self.send(bytes([0x20, len(props) + 2, 0, 0]) + props)
            self.broker.log("CONNECT level=%d keep=%ds" % (level, keep))
            while True:
                pkt, body, flags = await self.read_packet()
                if pkt == 8:  # SUBSCRIBE
                    pid = struct.unpack(">H", body[:2])[0]
                    i = 2
                    if level == 5:
                        # v5 variable header: properties length is a varint
                        # (always present); skip length byte(s) + properties.
                        plen = 0
                        mult = 1
                        while True:
                            b = body[i]
                            i += 1
                            plen += (b & 0x7F) * mult
                            if not b & 0x80:
                                break
                            mult *= 128
                        i += plen
                    granted = []
                    while i < len(body):
                        tl = struct.unpack(">H", body[i:i + 2])[0]
                        filt = body[i + 2:i + 2 + tl].decode()
                        qos = body[i + 2 + tl] & 3
                        self.subscriptions[filt] = qos
                        granted.append(qos)
                        i += 2 + tl + 1
                        self.broker.log("SUBSCRIBE %s qos=%d" % (filt, qos))
                        # replay retained
                        for topic, (data, rqos) in list(self.retains.items()):
                            if self.topic_matches(filt, topic):
                                await self.publish_to(topic, data, 0, False)
                    codes = bytes(granted)
                    v5props = bytes([0]) if level == 5 else b""
                    await self.send(bytes([0x90]) + self.encode_length(2 + len(codes) + len(v5props)) +
                                    struct.pack(">H", pid) + v5props + codes)
                elif pkt == 10:  # UNSUBSCRIBE
                    pid = struct.unpack(">H", body[:2])[0]
                    await self.send(bytes([0xB0, 2]) + struct.pack(">H", pid))
                elif pkt == 4:  # PUBACK (client acking our outgoing QoS1)
                    pass  # nothing to do — delivery confirmed
                elif pkt == 3:  # PUBLISH
                    qos = (flags >> 1) & 3
                    retain = flags & 1
                    import binascii
                    self.broker.log("PUBLISH-RAW qos=%d hex=%s" % (qos, binascii.hexlify(body[:100]).decode()))
                    tl = struct.unpack(">H", body[0:2])[0]
                    topic = body[2:2 + tl].decode()
                    i = 2 + tl
                    pid = None
                    if qos:
                        pid = struct.unpack(">H", body[i:i + 2])[0]
                        i += 2
                    if level == 5:
                        # v5: properties varint sits before the payload
                        plen = 0
                        mult = 1
                        while i < len(body):
                            b = body[i]
                            i += 1
                            plen += (b & 0x7F) * mult
                            if not b & 0x80:
                                break
                            mult *= 128
                        i = min(i + plen, len(body))
                    payload = body[i:]
                    self.broker.log("PUBLISH %s qos=%d retain=%d %s" %
                                    (topic, qos, retain, payload[:120]))
                    if retain and payload:
                        self.retains[topic] = (payload, qos)
                    if qos == 1 and pid:
                        v5props = bytes([0]) if level == 5 else b""
                        await self.send(bytes([0x40]) + self.encode_length(2 + len(v5props)) +
                                        struct.pack(">H", pid) + v5props)
                    # device command channel: allow state control via topic
                    await self.broker.on_device_publish(topic, payload)
                elif pkt == 12:  # PINGREQ
                    await self.send(bytes([0xD0, 0]))
                elif pkt == 14:  # DISCONNECT
                    self.broker.log("DISCONNECT")
                    return
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass


class Broker:
    def __init__(self, port):
        self.port, self.clients, self.retains = port, [], {}
        self._pid = 0
        self.logf = open(str(Path(__file__).with_name("mqtt_broker.log")), "a", buffering=1)

    def next_pid(self):
        self._pid = (self._pid % 65535) + 1
        return self._pid

    def log(self, msg):
        self.logf.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))

    async def on_device_publish(self, topic, payload):
        # U1 LAN pairing (protocol verified against community reverse
        # engineering + live capture): the CLI sends JSON-RPC requests to
        # <clientId>/config/request; the device answers on .../response and
        # delivers the mTLS material via notify_lan_auth on .../notification.
        if topic == DEVICE_SN + "/request":
            # API channel (u1-moonraker spec/mqtt.py: instance_name/request →
            # instance_name/response, api_qos). Plain JSON payload, no inner
            # framing prefix. Without these replies the CLI times out on
            # printer.objects.list/subscribe and the web UI device page
            # never finishes loading (observed 2026-11-23, WS error -32006).
            try:
                req = json.loads(payload.decode())
            except Exception as exc:
                self.log("API-PARSE-FAIL %s %r" % (exc, payload[:60]))
                return
            method = req.get("method", "?")
            self.log("API-REQ %s" % method)
            body = json.dumps({"jsonrpc": "2.0", "result": api_result(method, req.get("params")),
                               "id": req.get("id")})
            for c in list(self.clients):
                try:
                    await c.publish_to(DEVICE_SN + "/response", body.encode(), 1, False)
                except Exception:
                    pass
            return
        if not topic.endswith("/config/request"):
            return
        try:
            # payloads carry a 2-byte inner framing prefix (\x02\x00) before
            # the JSON body — parse from the first '{'
            i = payload.find(b"{")
            req = json.loads(payload[i:].decode() if i >= 0 else payload.decode())
        except Exception as exc:
            self.log("CONFIG-PARSE-FAIL %s %r" % (exc, payload[:60]))
            return
        method = req.get("method", "?")
        clientid = (req.get("params") or {}).get("clientid", "")
        self.log("CONFIG-REQ %s clientid=%s" % (method, clientid))
        out = topic.replace("/config/request", "/config/response")
        note = topic.replace("/config/request", "/config/notification")

        async def reply(result):
            # Real-device format (captured 2026-11-23, pairing.pcapng frames
            # 18/30): QoS1, id AFTER result, plus cli_time=-1 and dev_time
            # (unix seconds); pretty-style ", " / ": " separators.
            body = json.dumps(
                {"jsonrpc": "2.0", "result": result, "id": req.get("id"),
                 "cli_time": -1, "dev_time": int(time.time())},
                separators=(", ", ": "), ensure_ascii=False)
            for c in list(self.clients):
                try:
                    await c.publish_to(out, body.encode(), 1, False)
                except Exception:
                    pass

        params = req.get("params") or {}
        app_id = params.get("app_id", "")
        if method.endswith("confirm_lan_status"):
            if clientid and clientid in known_clients():
                # bound client. The CLI's confirm classifier only knows
                # "unauthorized" (start pairing) and "success" (already bound),
                # and builds its pairing topics from the success payload —
                # without access_code it subscribes to "" and drops the link.
                # Field set per spec/client_manager.py _local_info(), plus the
                # identity the first-time flow learns from notify_lan_auth.
                await reply({"state": "success", "access_code": ACCESS_CODE,
                             "sn": DEVICE_SN, "clientid": clientid, "app_id": app_id,
                             "link_mode": 1, "userid": "", "username": "",
                             "region": "", "client_count": len(known_clients())})
            else:
                await reply({"state": "unauthorized", "clientid": clientid,
                             "app_id": "", "message": "client is unauthorized"})
        elif method.endswith("request_lan_auth"):
            await reply({"state": "authorizing", "clientid": clientid,
                         "app_id": app_id, "message": "waiting user authorization"})
            # Simulate the touchscreen tap delay before auto-approving —
            # the real device waits for a human; the CLI needs time to
            # process the "authorizing" response and arm its listener.
            await asyncio.sleep(2)
            try:
                material = mint_client_cert(clientid)
                await self.send_lan_auth_notification(note, clientid, material)
                remember_client(clientid)
            except Exception as exc:
                self.log("CERT-MINT-FAIL %s" % exc)
        elif method.startswith("printer."):
            # Printer RPC methods (objects.subscribe, info, objects.query etc.)
            # The CLI subscribes to status objects after connecting; respond
            # with success so it considers the subscription active. The
            # periodic notify_status_update on <sn>/status feeds the data.
            self.log("PRINTER-RPC %s" % method)
            await reply({"ok": "ok", "method": method})
        else:
            await reply({"state": "success"})

    async def send_lan_auth_notification(self, note_topic, clientid, material):
        # DEBUG: send a minimal notify first (no certs) to isolate size vs format
        for c in list(self.clients):
            try:
                await c.publish_to(note_topic, json.dumps(
                    {"jsonrpc": "2.0", "method": "notify_lan_auth", "params": [{"state": "approve", "clientid": clientid, "sn": DEVICE_SN}]},
                    separators=(", ", ": ")).encode(), 1, False)
            except Exception:
                pass
        self.log("NOTIFY-MINI sent")
        entry = {"state": "approve", "clientid": clientid, "sn": DEVICE_SN,
                 "ca": material["ca"], "cert": material["cert"], "key": material["key"],
                 "port": TLS_PORT, "app_id": "orca-virtual-u1"}
        for c in list(self.clients):
            try:
                await c.publish_to(note_topic, json.dumps(
                    {"jsonrpc": "2.0", "method": "notify_lan_auth", "params": [entry]},
                    separators=(", ", ": "), ensure_ascii=False).encode(), 1, False)
            except Exception:
                pass
        self.log("NOTIFY-LAN-AUTH approve clientid=%s tls_port=%d" % (clientid, TLS_PORT))

    async def client_loop(self, reader, writer):
        c = Client(self, reader, writer)
        self.clients.append(c)
        try:
            await c.handle()
        finally:
            self.clients.remove(c)
            try:
                writer.close()
            except Exception:
                pass

    def status_payload(self):
        # Real moonraker format (mqtt.py _publish_status_update):
        # JSON-RPC notification "notify_status_update" with params [status, eventtime],
        # published retained at QoS 1 (default_qos: 1 in u1_moonraker.conf)
        return json.dumps(
            {"jsonrpc": "2.0", "method": "notify_status_update",
             "params": [build_status(), time.time()]},
            separators=(", ", ": "), ensure_ascii=False)

    async def notify(self, method, params):
        """moonraker notification as unisrv bridges it onto <sn>/notification:
        QoS 1, not retained (spec/mqtt.py _publish_notification)."""
        body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params},
                          separators=(", ", ": "), ensure_ascii=False)
        for c in list(self.clients):
            try:
                await c.publish_to(NOTIFICATION_TOPIC, body.encode(), 1, False)
            except Exception:
                pass
        self.log("NOTIFY %s" % method)

    async def simulator(self):
        # moonraker-side: publish retained status every 2 s (status_interval=2)
        last = None
        while True:
            if self.clients:
                payload = self.status_payload()
                for c in list(self.clients):
                    try:
                        # Real device: QoS 1 (default_qos: 1), retained
                        await c.publish_to(STATUS_TOPIC, payload.encode(), 1, True)
                    except Exception:
                        pass
                # exception changes: snapshot for the active list, plus one
                # notification per newly raised exception (the page-load
                # snapshot comes from server.exception.query)
                active = exceptions(load_state())
                now = [tuple(e[k] for k in ("level", "id", "index", "code", "message")) for e in active]
                if last is not None and now != last:
                    await self.notify("notify_exception_status", {"exceptions": active})
                    raised = [e for e in active
                              if tuple(e[k] for k in ("level", "id", "index", "code", "message")) not in last]
                    if raised:
                        await self.notify("notify_exception_notification", raised)
                last = now
            await asyncio.sleep(2)

    async def run(self):
        server = await asyncio.start_server(self.client_loop, "0.0.0.0", self.port)
        self.log("broker listening on %d" % self.port)
        async with server:
            await asyncio.gather(server.serve_forever(), self.simulator())


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7125
    asyncio.run(Broker(port).run())
