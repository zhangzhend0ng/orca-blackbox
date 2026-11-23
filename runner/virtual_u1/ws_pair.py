"""ws_pair.py — raw WCP client with browser-faithful headers.

Speaks the full U1 LAN pairing sequence to the CLI's /ws channel:
action.device.connect -> (MQTT pairing happens in the broker) -> result.
"""
import json
import socket
import struct
import sys
import time

HOST = "127.0.0.1"
PORT = 30996
SN = "8110099900000001MOCK1"

HANDSHAKE = (
    "GET /ws HTTP/1.1\r\n"
    "Host: %s:%d\r\n"
    "Connection: Upgrade\r\n"
    "Pragma: no-cache\r\n"
    "Cache-Control: no-cache\r\n"
    "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36 Edg/158.0.0.0\r\n"
    "Upgrade: websocket\r\n"
    "Origin: http://%s:%d\r\n"
    "Sec-WebSocket-Version: 13\r\n"
    "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
    "Sec-WebSocket-Extensions: permessage-deflate; client_max_window_bits\r\n"
    "\r\n" % (HOST, PORT, HOST, PORT)
).encode()


def mask(d):
    k = b"\x11\x22\x33\x44"
    return b"".join(bytes([b ^ k[i % 4]]) for i, b in enumerate(d))


def send(s, op, p=b""):
    n = len(p)
    h = bytes([0x80 | op])
    if n < 126:
        h += bytes([0x80 | n])
    elif n < 65536:
        h += bytes([0x80 | 126]) + struct.pack(">H", n)
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
        ln = struct.unpack(">Q", rexact(s, 8))[0]
    return op, (rexact(s, ln) if ln else b"")


def drain(s, seconds):
    import zlib
    inflator = [zlib.decompressobj(-15)]   # persistent: server uses context takeover

    def inflate(data):
        try:
            return inflator[0].decompress(data + b"\x00\x00\xff\xff").decode("utf-8", "replace")
        except Exception:
            inflator[0] = zlib.decompressobj(-15)
            try:
                return inflator[0].decompress(data + b"\x00\x00\xff\xff").decode("utf-8", "replace")
            except Exception:
                return repr(data[:80])

    s.settimeout(1.5)
    end = time.time() + seconds
    while time.time() < end:
        try:
            op, data = frame(s)
        except socket.timeout:
            continue
        except OSError as e:
            print("<< CONN-DIED", type(e).__name__)
            return
        if op == 9:
            send(s, 10, data)
            continue
        if op == 8:
            print("<< CLOSE")
            return
        if op in (1, 2):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = inflate(data)
            print("<<", (text or "")[:800])


def main():
    method = sys.argv[1] if len(sys.argv) > 1 else "action.device.connect"
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {"sn": SN, "type": "LAN"}
    s = socket.create_connection((HOST, PORT), timeout=8)
    s.sendall(HANDSHAKE)
    r = b""
    while b"\r\n\r\n" not in r:
        r += s.recv(256)
    print("HANDSHAKE:", r.split(b"\r\n")[0].decode())
    drain(s, 4)
    req = {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params}
    print(">>", method, json.dumps(params)[:120])
    send(s, 1, json.dumps(req).encode())
    drain(s, int(sys.argv[3]) if len(sys.argv) > 3 else 30)


if __name__ == "__main__":
    main()
