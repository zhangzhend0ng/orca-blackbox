"""deploy_fw.py — push the repo's virtual_u1_mqtt.py to the Mac mini, restart
the broker, and reconnect the CLI (the broker restart drops the CLI's MQTT
link and it does not self-heal — test_l2 scenario 7 path).

    python tools/deploy_fw.py            # from the orca-virtual-u1 repo root
"""
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import test_l2                       # noqa: E402

BASE = "http://127.0.0.1:30996"


def main():
    test_l2.KEY = os.path.expanduser("~/.ssh/id_ed25519_codex_mac_gateway")
    assert test_l2.KEY and os.path.exists(test_l2.KEY), "ssh key missing"
    local = os.path.join(REPO, "virtual_u1_mqtt.py")
    digest = hashlib.sha256(open(local, "rb").read()).hexdigest()[:16]
    subprocess.run(["scp", "-i", test_l2.KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
                    local, test_l2.MAC + ":sc_probe/virtual_u1_mqtt.py"], check=True)
    out = test_l2.ssh("shasum -a 256 ~/sc_probe/virtual_u1_mqtt.py | cut -c1-16; "
                      "python3 -c \"import ast; ast.parse(open('/Users/coilwin/sc_probe/virtual_u1_mqtt.py').read())\" && echo syntax-ok; "
                      "pkill -f virtual_u1_mqtt.py; sleep 1; cd ~/sc_probe && "
                      "(nohup python3 virtual_u1_mqtt.py 7125 > mqtt_out.log 2>&1 &) ; sleep 2; "
                      "pgrep -f virtual_u1_mqtt >/dev/null && echo broker-up")
    print(out)
    assert out.splitlines()[0] == digest, "remote copy differs from local"
    assert "broker-up" in out, "broker did not come up"
    ok, res = test_l2.reconnect_via_node(BASE)
    print("connect ok=%s %s" % (ok, res[:120]))
    end = time.time() + 45
    while time.time() < end:
        d = json.load(urllib.request.urlopen(BASE + "/api/cache/all", timeout=10))["data"]
        if d["connection"].get("connected") and d["objects"].get("print_stats"):
            print("cache ok msm=%s" % json.dumps(d["objects"]["machine_state_manager"]))
            return 0
        time.sleep(3)
    print("cache never recovered")
    return 1


if __name__ == "__main__":
    sys.exit(main())
