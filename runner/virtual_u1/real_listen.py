"""real_listen.py — passive MQTT listener on a REAL U1's broker.

Authorized capture (2026-11-23): subscribes '#' on the device broker and
logs every publish (topic + props + payload) to real_capture.log. This
reveals the exact wire format of the device's config responses — the one
byte-level detail our virtual broker is missing.
"""
import socket
import struct
import sys
import time

TARGET = sys.argv[1] if len(sys.argv) > 1 else "172.18.6.59"
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 1884
LOG = open("/Users/coilwin/sc_probe/real_capture.log", "a", buffering=1)


def mask(d):
    k = b"\x11\x22\x33\x44"
    return b"".join(bytes([b ^ k[i % 4]]) for i, b in enumerate(d))


def send(s, op, p=b""):
    n = len(p)
    h = bytes([0x80 | op, 0x80 | n]) if n < 126 else \
        bytes([0x80 | op, 0x80 | 126]) + struct.pack(">H", n)
    s.sendall(h + mask(p))


def rexact(s, n):
    d = b""
    while len(d) < n:
        c = s.recv(n - len(d))
        if not c:
            raise EOFError
        d += c
    return d


def frame(s):
    h = rexact(s, 2)
    op, ln = h[0] & 0xF, h[1] & 0x7F
    if ln == 126:
        ln = struct.unpack(">H", rexact(s, 2))[0]
    elif ln == 127:
        ln = struct.unpack(">Q", rexect(s, 8))[0]
    return h[0], (rexact(s, ln) if ln else b"")


s = socket.create_connection((TARGET, PORT), timeout=8)
# rumqttc defaults: MQTT 3.1.1 (level 4), clean_session=false (flags 0x00)
cid = b"\x00\x0ecap-%010d" % int(time.time())
payload = b"\x00\x04MQTT\x04\x00\x00\x3c" + cid
s.sendall(bytes([0x10, len(payload)]) + payload)

# Register on the bootstrap channel FIRST: publish a confirm_lan_status
# request exactly like a real client. Only then subscribe.
def mask_send(op, p, flags=0):
    n = len(p)
    hh = bytes([0x80 | flags | op, 0x80 | n]) if n < 126 else \
        bytes([0x80 | flags | op, 0x80 | 126]) + struct.pack(">H", n)
    s.sendall(hh + mask(p))

_req_topic = b"12345678/config/request"
_req = (b'{"jsonrpc":"2.0","id":' + str(int(time.time() * 1000)).encode() +
        b',"method":"server.client_manager.confirm_lan_status",'
        b'"params":{"clientid":"cap-listener"}}')
mask_send(3, struct.pack(">H", len(_req_topic)) + _req_topic + _req)
print("bootstrap request published")
time.sleep(1)
h0, data = frame(s)
LOG.write("%s CONNECT->CONNACK h0=0x%02x %s\n" % (time.strftime("%H:%M:%S"), h0, data.hex()))
print("CONNACK 0x%02x %s" % (h0, data.hex()))
if (h0 & 0xF0) != 0x20:
    print("connect refused")
    sys.exit(1)
subs = [b"12345678/config/response", b"12345678/config/notification",
        b"8110026072410277M0P2/status", b"8110026072410277M0P2/notification"]
pid = 1
for topic in subs:
    # v3.1.1 SUBSCRIBE: fixed header MUST be 0x82 (flags=0b0010)
    n = 2 + 2 + len(topic) + 1
    p = struct.pack(">H", pid) + struct.pack(">H", len(topic)) + topic + bytes([0])
    hh = bytes([0x82, 0x80 | n]) if n < 126 else bytes([0x82, 0x80 | 126]) + struct.pack(">H", n)
    s.sendall(hh + mask(p))
    s.settimeout(20)
    h0, data = frame(s)
    LOG.write("%s SUBACK(%s) %s\n" % (time.strftime("%H:%M:%S"), topic.decode(), data.hex()))
    print("SUBACK", topic.decode(), data.hex())
    pid += 1
s.settimeout(2)
end = time.time() + 240
while time.time() < end:
    try:
        h0, data = frame(s)
    except socket.timeout:
        continue
    except Exception as e:
        LOG.write("%s END %s\n" % (time.strftime("%H:%M:%S"), e))
        break
    op = h0 & 0xF
    if op == 3:
        qos = (h0 >> 1) & 3
        tl = struct.unpack(">H", data[0:2])[0]
        topic = data[2:2 + tl].decode("utf-8", "replace")
        i = 2 + tl
        if qos:
            i += 2
        plen = 0
        mult = 1
        while True:
            b = data[i]
            i += 1
            plen += (b & 0x7F) * mult
            if not b & 0x80:
                break
            mult *= 128
        props = data[i:i + plen]
        i += plen
        payload_bytes = data[i:]
        LOG.write("%s PUB qos=%d retain=%d topic=%s props=%s payload=%r\n" % (
            time.strftime("%H:%M:%S"), qos, h0 & 1, topic, props.hex(),
            payload_bytes[:800]))
        print("PUB", topic, payload_bytes[:100])
    elif op == 9:
        send(s, 10, data)
    elif op == 8:
        LOG.write("%s CLOSE\n" % time.strftime("%H:%M:%S"))
        print("CLOSED")
        break
LOG.write("%s listener exit\n" % time.strftime("%H:%M:%S"))
