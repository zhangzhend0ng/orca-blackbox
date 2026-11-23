"""cdpclient.py — stdlib CDP client for one page of a --remote-debugging-port
Chrome. The page keeps its state across calls; the client holds one websocket
to the page target. Written for the CLI web UI (Flutter/CanvasKit), where the
only text-bearing DOM is the lazily built semantics tree.

    from cdpclient import Page
    page = Page(9224)                      # first page target
    page.navigate(url)                     # boots Flutter, enables semantics
    page.evaluate("document.title")
    page.semantics()                       # [{id, role, label, text, full, rect, flags}]
    page.screenshot("a.png", clip=(283, 535, 631, 350), scale=2)
"""
import base64
import json
import os
import socket
import struct
import time
import urllib.parse
import urllib.request

SEM_DUMP = r"""(() => {
  const out = [];
  for (const el of document.querySelectorAll('flt-semantics')) {
    const r = el.getBoundingClientRect();
    const own = Array.from(el.childNodes).filter((n) => n.nodeType === 3).map((n) => n.textContent.trim()).join('');
    out.push({ id: el.getAttribute('id'), role: el.getAttribute('role') || '', label: el.getAttribute('aria-label') || '',
      text: own, full: (el.textContent || '').trim().slice(0, 160),
      rect: [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height)],
      disabled: el.getAttribute('aria-disabled'), hidden: el.getAttribute('aria-hidden') });
  }
  return out;
})()"""


def _send(sock, text):
    data = text.encode()
    n = len(data)
    head = bytes([0x81])
    if n < 126:
        head += bytes([0x80 | n])
    elif n < 65536:
        head += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        head += bytes([0x80 | 127]) + struct.pack(">Q", n)
    mask = os.urandom(4)
    body = bytes(b ^ mask[i % 4] for i, b in enumerate(data))   # client frames are masked
    sock.sendall(head + mask + body)


def _recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(min(1 << 16, n - len(buf)))
        if not chunk:
            raise ConnectionError("cdp socket closed")
        buf += chunk
    return buf


def _recv(sock):
    """Next text message: follows fragmentation, answers pings."""
    payload = b""
    while True:
        b1, b2 = _recv_exact(sock, 2)
        fin, op, n = b1 & 0x80, b1 & 0x0F, b2 & 0x7F
        if n == 126:
            n = struct.unpack(">H", _recv_exact(sock, 2))[0]
        elif n == 127:
            n = struct.unpack(">Q", _recv_exact(sock, 8))[0]
        mask = _recv_exact(sock, 4) if b2 & 0x80 else None
        data = _recv_exact(sock, n) if n else b""
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        if op == 9:                                   # ping -> pong
            head = bytes([0x8A, 0x80 | len(data)])
            mkey = os.urandom(4)
            sock.sendall(head + mkey + bytes(b ^ mkey[i % 4] for i, b in enumerate(data)))
            continue
        if op == 8:
            raise ConnectionError("cdp socket closed by peer")
        if op in (1, 2):                               # text / binary start frame
            payload = data
        elif op == 0:                                  # continuation
            payload += data
        if fin and op in (0, 1, 2):
            return payload


class Page:
    def __init__(self, port=9224, target=None):
        targets = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json/list" % port, timeout=5))
        pages = [t for t in targets if t["type"] == "page"]
        hit = [t for t in pages if target and (target in t["url"] or target in (t.get("title") or ""))]
        if not hit and not pages:
            raise ConnectionError("no page target on port %d" % port)
        self.url = (hit or pages)[0]["webSocketDebuggerUrl"]
        self.sock = None
        self.mid = 0

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None

    def _connect(self):
        u = urllib.parse.urlparse(self.url)
        sock = socket.create_connection((u.hostname, u.port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall(("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                      "Sec-WebSocket-Key: %s\r\nSec-WebSocket-Version: 13\r\n\r\n"
                      % (u.path, u.hostname, u.port, key)).encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                raise ConnectionError("cdp handshake closed")
            buf += chunk
        if b" 101 " not in buf.split(b"\r\n")[0]:
            raise ConnectionError("cdp handshake: " + buf[:120].decode("latin1"))
        return sock

    def call(self, method, params=None):
        if self.sock is None:
            self.sock = self._connect()
        self.mid += 1
        try:
            _send(self.sock, json.dumps({"id": self.mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(_recv(self.sock))
                if msg.get("id") == self.mid:
                    if "error" in msg:
                        raise RuntimeError("%s: %s" % (method, msg["error"]))
                    return msg.get("result", {})
        except (ConnectionError, OSError):
            self.close()
            raise

    def evaluate(self, expression):
        r = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in r:
            d = r["exceptionDetails"]
            raise RuntimeError("page exception: " + ((d.get("exception") or {}).get("description") or d.get("text") or "")[:400])
        return r["result"].get("value")

    def wait(self, expression, timeout_s, label=None):
        """Poll `expression` until truthy; returns the value, raises on timeout."""
        end = time.time() + timeout_s
        while True:
            try:
                v = self.evaluate(expression)           # may fail mid-navigation
                if v:
                    return v
            except (RuntimeError, ConnectionError, OSError):
                pass
            if time.time() > end:
                raise TimeoutError("timeout waiting for " + (label or expression))
            time.sleep(0.25)

    def navigate(self, url, settle_s=3.0):
        self.call("Page.navigate", {"url": url})
        self.wait("!!document.querySelector('flt-semantics-placeholder')", 30, "flutter boot")
        # the engine builds the semantics tree only after the placeholder is clicked
        self.evaluate("document.querySelector('flt-semantics-placeholder').click()")
        self.wait("document.querySelectorAll('flt-semantics').length > 0", 15, "first semantics")
        time.sleep(settle_s)

    def semantics(self):
        return self.evaluate(SEM_DUMP)

    def screenshot(self, path, clip=None, scale=1):
        p = {"format": "png"}
        if clip:
            p["clip"] = {"x": clip[0], "y": clip[1], "width": clip[2], "height": clip[3], "scale": scale}
        data = base64.b64decode(self.call("Page.captureScreenshot", p)["data"])
        if path:
            with open(path, "wb") as f:
                f.write(data)
        return data

    def click(self, node_id):
        """Tap the semantics node `flt-semantic-node-<id>` (engine -> SemanticsAction.tap)."""
        return self.evaluate("(() => { const el = document.getElementById('flt-semantic-node-%d'); if (!el) return 'NOTFOUND'; el.click(); return 'clicked'; })()" % int(node_id))
