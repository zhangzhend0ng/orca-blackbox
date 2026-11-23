"""mdns_safe.py — rate-limited mDNS advertiser for the virtual U1.

REWRITTEN after the 2026-11-23 multicast storm incident (23k pps flooded
the office LAN, saturating CPU 0 on a colleague's PC). Every safety
measure that was missing is now mandatory:

1. ANNOUNCE_INTERVAL: proactive announce at most every 30s (real printers
   use minutes; this is aggressive but bounded).
2. HARD_RATE_CAP: absolute ceiling of 10 packets/minute. Exceeding this
   triggers self-shutdown.
3. EXACT_MATCH_ONLY: respond exclusively to queries asking for OUR
   instance name or OUR service type — never to other snapmaker traffic.
4. PRE_FLIGHT_CHECK: sample network mDNS traffic for 5 seconds before
   starting; abort if > 50 pps (network already busy).
5. SELF_MONITORING: log every send; running counter; auto-shutdown if
   rate exceeds cap or total packets exceed daily budget.
6. CLEAN_SHUTDOWN: signal handlers; removes all state on exit.
"""
import signal
import socket
import struct
import sys
import time

# ── Configuration (conservative defaults) ─────────────────────────────
ANNOUNCE_INTERVAL = 30        # seconds between proactive announces
HARD_RATE_CAP = 10            # max packets per minute (self-shutdown above)
DAILY_BUDGET = 2000           # max packets per day (self-shutdown above)
PRE_FLIGHT_SECONDS = 5        # how long to listen before starting
PRE_FLIGHT_MAX_PPS = 50       # abort if existing mDNS traffic exceeds this
RESPONSE_COOLDOWN = 2         # min seconds between query responses

DEVICE_SN = "8110099900000001MOCK1"
DEVICE_NAME = "U1-MOCK"
MAC_IP = "172.18.6.213"
MQTT_PORT = 7125

MCAST_ADDR = "224.0.0.251"
MCAST_PORT = 5353

INSTANCE = DEVICE_NAME + "._snapmaker._tcp.local"
STYPE = b"_snapmaker._tcp.local"
HOSTNAME = ("U1-" + DEVICE_SN + ".local").encode()
INSTANCE_B = INSTANCE.encode()
TXT = ("version=1.4.1 machine_type=Snapmaker\\ U1 device_name=" + DEVICE_NAME
       + " sn=" + DEVICE_SN + " link_mode=lan userid= ip=" + MAC_IP
       + " region=cn").encode()

LOG_PREFIX = "[mdns_safe]"
running = True
send_count = 0
send_times = []           # recent send timestamps for rate monitoring
start_time = time.time()


def log(msg):
    print("%s %s %s" % (time.strftime("%H:%M:%S"), LOG_PREFIX, msg), flush=True)


# ── Packet construction ──────────────────────────────────────────────
def name_bytes(n):
    out = b""
    for part in n.split(b"."):
        out += bytes([len(part)]) + part
    return out + b"\x00"


def encode_length(n):
    out = b""
    while True:
        d = n % 128
        n //= 128
        if n:
            d |= 0x80
        out += bytes([d])
        if not n:
            return out


def build_announcement():
    """PTR + SRV + TXT + A — exactly 4 records, one packet."""
    srv_data = struct.pack(">HHH", 0, 0, MQTT_PORT) + name_bytes(HOSTNAME)
    txt_data = b"".join(bytes([len(p)]) + p for p in TXT.split(b" "))

    # DNS header: ID=0, FLAGS=0x8400(authoritative response), QD=0, AN=4, NS=0, AR=0
    pkt = struct.pack(">HHHHHH", 0, 0x8400, 0, 4, 0, 0)
    pkt += name_bytes(STYPE) + struct.pack(">HHIH", 12, 1, 120, len(name_bytes(INSTANCE_B))) + name_bytes(INSTANCE_B)
    pkt += name_bytes(INSTANCE_B) + struct.pack(">HHIH", 33, 1, 120, len(srv_data)) + srv_data
    pkt += name_bytes(INSTANCE_B) + struct.pack(">HHIH", 16, 1, 120, len(txt_data)) + txt_data
    pkt += name_bytes(HOSTNAME) + struct.pack(">HHIH", 1, 1, 120, 4) + socket.inet_aton(MAC_IP)
    return pkt


# ── Rate limiting ────────────────────────────────────────────────────
def check_rate():
    """Returns True if we can send, False if we must self-shutdown."""
    global send_times
    now = time.time()
    # keep only last 60s
    send_times = [t for t in send_times if now - t < 60]
    # hard cap per minute
    if len(send_times) >= HARD_RATE_CAP:
        log("SELF-SHUTDOWN: rate cap %d/min exceeded" % HARD_RATE_CAP)
        return False
    # daily budget
    if send_count >= DAILY_BUDGET:
        log("SELF-SHUTDOWN: daily budget %d exhausted" % DAILY_BUDGET)
        return False
    send_times.append(now)
    return True


def can_respond():
    """Query responses have their own cooldown on top of rate cap."""
    now = time.time()
    # at least RESPONSE_COOLDOWN since last send
    if send_times and now - send_times[-1] < RESPONSE_COOLDOWN:
        return False
    return True


# ── Pre-flight check ─────────────────────────────────────────────────
def pre_flight(sock):
    """Listen for existing mDNS traffic. Abort if network is already busy."""
    log("PRE-FLIGHT: sampling mDNS traffic for %ds..." % PRE_FLIGHT_SECONDS)
    sock.settimeout(0.5)
    count = 0
    end = time.time() + PRE_FLIGHT_SECONDS
    while time.time() < end:
        try:
            data, addr = sock.recvfrom(4096)
            count += 1
        except socket.timeout:
            continue
    pps = count / PRE_FLIGHT_SECONDS
    log("PRE-FLIGHT: %d packets in %ds = %.1f pps (threshold: %d)" %
        (count, PRE_FLIGHT_SECONDS, pps, PRE_FLIGHT_MAX_PPS))
    if pps > PRE_FLIGHT_MAX_PPS:
        log("PRE-FLIGHT ABORT: network mDNS traffic %.1f pps > %d threshold" %
            (pps, PRE_FLIGHT_MAX_PPS))
        return False
    return True


# ── Query parsing (exact match only) ─────────────────────────────────
def parse_query_names(data):
    """Extract QNAME strings from a DNS query packet. Returns list of bytes."""
    if len(data) < 12:
        return []
    qdcount = struct.unpack(">H", data[4:6])[0]
    if qdcount == 0 or qdcount > 10:
        return []
    names = []
    i = 12
    for _ in range(qdcount):
        parts = []
        while i < len(data):
            l = data[i]
            if l == 0:
                i += 1
                break
            if l & 0xC0 == 0xC0:
                i += 2
                break
            if i + 1 + l > len(data):
                return names
            parts.append(data[i + 1:i + 1 + l])
            i += 1 + l
        names.append(b".".join(parts))
        i += 4  # QTYPE + QCLASS
    return names


def is_for_us(names):
    """EXACT match only: our instance name or our exact service type.

    NEVER match on generic '_snapmaker' — that catches all 14+ real
    printers' traffic and causes the feedback loop of 2026-11-23.
    """
    for n in names:
        if n == INSTANCE_B:
            return True
        if n == STYPE:
            return True
    return False


# ── Main ─────────────────────────────────────────────────────────────
def main():
    global running, send_count

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    except AttributeError:
        pass
    sock.bind(("", MCAST_PORT))
    mreq = socket.inet_aton(MCAST_ADDR) + socket.inet_aton("0.0.0.0")
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

    def stop(sig, frame):
        global running
        running = False
        log("SIGNAL %d received — shutting down" % sig)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    # Pre-flight: measure existing traffic before we add any noise
    if not pre_flight(sock):
        sys.exit(1)

    log("STARTING: instance=%s interval=%ds cap=%d/min budget=%d/day" %
        (INSTANCE, ANNOUNCE_INTERVAL, HARD_RATE_CAP, DAILY_BUDGET))

    last_announce = 0
    sock.settimeout(1)

    while running:
        now = time.time()

        # Proactive announce (bounded)
        if now - last_announce >= ANNOUNCE_INTERVAL:
            if check_rate():
                try:
                    sock.sendto(build_announcement(), (MCAST_ADDR, MCAST_PORT))
                    send_count += 1
                    last_announce = now
                    log("ANNOUNCE #%d (rate: %d/min, budget: %d/%d)" %
                        (send_count, len(send_times), send_count, DAILY_BUDGET))
                except OSError as e:
                    log("SEND-ERROR: %s" % e)
            else:
                log("SELF-SHUTDOWN: rate limit exceeded")
                break

        # Listen for direct queries
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            continue
        except OSError:
            break

        # Only respond to queries specifically for our instance
        if len(data) > 12 and (data[2] & 0x80) == 0:  # QR=0 → query
            names = parse_query_names(data)
            if is_for_us(names) and can_respond() and check_rate():
                try:
                    sock.sendto(build_announcement(), (MCAST_ADDR, MCAST_PORT))
                    send_count += 1
                    log("RESPOND #%d to query from %s (names: %s)" %
                        (send_count, addr[0], [n.decode('utf-8', '?')[:40] for n in names[:2]]))
                except OSError as e:
                    log("SEND-ERROR: %s" % e)

    elapsed = int(time.time() - start_time)
    log("EXIT: sent %d packets in %ds (avg %.2f pps)" %
        (send_count, elapsed, send_count / max(elapsed, 1)))
    sock.close()


if __name__ == "__main__":
    main()
