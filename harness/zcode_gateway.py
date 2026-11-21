"""Direct network route for the pinned Snapmaker ZCode provider."""

import http.client
import os


SNAPMAKER_GATEWAY = "ai-gateway.s.com"
SNAPMAKER_DIRECT = "snapmaker_gateway_direct"
GATEWAY_READY_STATUSES = frozenset({200, 401})
PROXY_VARIABLES = frozenset({
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "ZCODE_HTTP_PROXY", "ZCODE_NO_PROXY",
})


def check_gateway():
    """Check the configured gateway without sending an API key or following redirects."""
    connection = http.client.HTTPConnection(SNAPMAKER_GATEWAY, timeout=4)
    try:
        connection.request("GET", "/v1/models")
        status = connection.getresponse().status
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError("zcode_gateway_unreachable:" + type(exc).__name__) from None
    finally:
        connection.close()
    if status not in GATEWAY_READY_STATUSES:
        raise RuntimeError(f"zcode_gateway_unavailable:{status}")
    return status


def direct_environment():
    """Keep proxy changes local to the pinned provider's app-server process."""
    env = {name: value for name, value in os.environ.items()
           if name.upper() not in PROXY_VARIABLES}
    no_proxy = "127.0.0.1,localhost," + SNAPMAKER_GATEWAY
    env.update(HTTP_PROXY="", HTTPS_PROXY="", ALL_PROXY="", NO_PROXY=no_proxy,
               ZCODE_HTTP_PROXY="", ZCODE_NO_PROXY=no_proxy)
    return env
