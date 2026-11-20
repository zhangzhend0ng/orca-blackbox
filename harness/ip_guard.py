"""Read-only local clash-guard admission; no proxy or policy changes."""
import json
import math
from pathlib import Path
import time
import urllib.request


def validate_status(data, now):
    if type(data) is not dict:
        raise ValueError("ip_guard_invalid_status")
    for key in ("time", "last_us_age", "evidence_ttl"):
        value = data.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError("ip_guard_invalid_status")
    if (data.get("ready") is not True or data.get("state") != "OK"
            or data.get("hosts_block_active") is not False
            or data.get("group_on_reject") is not False
            or not -2 <= now-data["time"] <= 12
            or not 0 <= data["last_us_age"] <= data["evidence_ttl"] <= 1800
            or type(data.get("guard_pid")) is not int or data["guard_pid"] <= 0):
        raise ValueError("ip_guard_not_ready")
    return {k: data[k] for k in ("ready", "state", "time", "last_us_age", "evidence_ttl", "guard_pid")}


class IPGuard:
    def __init__(self, *, status_port=39772):
        if type(status_port) is not int or not 1024 <= status_port <= 65535:
            raise ValueError("ip_guard_invalid_port")
        self._url = "http://127.0.0.1:"+str(status_port)+"/status"
        path = Path.home()/"clash-guard/status-token"
        if not 1 <= path.stat().st_size <= 256:
            raise ValueError("ip_guard_invalid_credential")
        self._token = path.read_text(encoding="utf-8").strip()
        if not self._token or any(c not in "0123456789abcdef" for c in self._token):
            raise ValueError("ip_guard_invalid_credential")
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def check(self):
        request = urllib.request.Request(self._url, headers={"X-Guard-Token": self._token})
        try:
            with self._opener.open(request, timeout=1) as response:
                raw = response.read(16385)
            if len(raw) > 16384:
                raise ValueError("ip_guard_response_limit")
            return {**validate_status(json.loads(raw), time.time()), "client_checked_at_ns": time.time_ns()}
        except Exception as exc:
            raise RuntimeError("ip_guard_unverified:"+type(exc).__name__) from None
