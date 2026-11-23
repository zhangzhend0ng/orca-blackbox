"""test_mdns_safe.py — isolated unit tests for mdns_safe.py.

Tests the logic WITHOUT any network I/O: rate limiter, query matcher,
packet builder, pre-flight thresholds. Run on the host; zero network impact.
"""
import sys
import time
import struct
import socket

sys.path.insert(0, ".")

# Import the module under test
import mdns_safe

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print("  PASS  %s" % name)
    else:
        FAIL += 1
        print("  FAIL  %s  %s" % (name, detail))


print("=" * 60)
print("TEST 1: Rate limiter — hard cap self-shutdown")
print("=" * 60)
mdns_safe.send_times = []
mdns_safe.send_count = 0

# Simulate hitting the cap
for i in range(mdns_safe.HARD_RATE_CAP):
    mdns_safe.send_times.append(time.time())
result = mdns_safe.check_rate()
check("rate cap triggers shutdown", result == False,
      "expected False after %d sends in 60s" % mdns_safe.HARD_RATE_CAP)

# Reset for next test
mdns_safe.send_times = []
mdns_safe.send_count = 0

print()
print("=" * 60)
print("TEST 2: Rate limiter — under cap allows send")
print("=" * 60)
mdns_safe.send_times = [time.time() - 10]  # 1 send, 10s ago
result = mdns_safe.check_rate()
check("under cap allows send", result == True)

print()
print("=" * 60)
print("TEST 3: Daily budget — budget exhausted triggers shutdown")
print("=" * 60)
mdns_safe.send_times = []
mdns_safe.send_count = mdns_safe.DAILY_BUDGET  # exactly at budget
result = mdns_safe.check_rate()
check("daily budget triggers shutdown", result == False)

mdns_safe.send_count = 0
mdns_safe.send_times = []

print()
print("=" * 60)
print("TEST 4: Response cooldown — minimum 2s between responses")
print("=" * 60)
mdns_safe.send_times = [time.time()]  # just sent 0s ago
result = mdns_safe.can_respond()
check("cooldown blocks immediate response", result == False)

mdns_safe.send_times = [time.time() - 3]  # sent 3s ago
result = mdns_safe.can_respond()
check("cooldown allows after 3s", result == True)

mdns_safe.send_times = []

print()
print("=" * 60)
print("TEST 5: Query matcher — exact instance name matches")
print("=" * 60)
names = [mdns_safe.INSTANCE_B]
result = mdns_safe.is_for_us(names)
check("exact instance name matches", result == True)

print()
print("=" * 60)
print("TEST 6: Query matcher — service type matches (for discoverability)")
print("=" * 60)
names = [mdns_safe.STYPE]
result = mdns_safe.is_for_us(names)
check("exact service type matches", result == True)

print()
print("=" * 60)
print("TEST 7: Query matcher — other snapmaker instance does NOT match")
print("=" * 60)
other_instance = b"U1-2._snapmaker._tcp.local"  # a REAL printer's instance
result = mdns_safe.is_for_us([other_instance])
check("other printer's instance rejected", result == False)

print()
print("=" * 60)
print("TEST 8: Query matcher — generic snapmaker substring does NOT match")
print("=" * 60)
# This is the KEY test: the old bug matched any name containing "_snapmaker"
random_name = b"something-with-_snapmaker-in-it.local"
result = mdns_safe.is_for_us([random_name])
check("substring '_snapmaker' rejected", result == False,
      "old code would have matched this!")

print()
print("=" * 60)
print("TEST 9: Query matcher — other service types rejected")
print("=" * 60)
for st in [b"_http._tcp.local", b"_ssh._tcp.local", b"_airplay._tcp.local"]:
    result = mdns_safe.is_for_us([st])
    check("rejects %s" % st.decode(), result == False)

print()
print("=" * 60)
print("TEST 10: Packet builder — produces exactly 4 records in 1 packet")
print("=" * 60)
pkt = mdns_safe.build_announcement()
check("packet is non-empty", len(pkt) > 0, "got %d bytes" % len(pkt))
check("packet is reasonable size", len(pkt) < 1000,
      "got %d bytes (should be <1000)" % len(pkt))
# Parse answer count from DNS header (bytes 6-7, big-endian)
ancount = struct.unpack(">H", pkt[6:8])[0]
check("exactly 4 answer records", ancount == 4, "got %d" % ancount)
# Verify it's a response (QR=1)
qr = (pkt[2] & 0x80) >> 7
check("QR bit set (response)", qr == 1)

print()
print("=" * 60)
print("TEST 11: Announce interval — verify 30s configuration")
print("=" * 60)
check("announce interval is >=30s", mdns_safe.ANNOUNCE_INTERVAL >= 30,
      "got %ds" % mdns_safe.ANNOUNCE_INTERVAL)

print()
print("=" * 60)
print("TEST 12: Pre-flight threshold — verify 50pps limit")
print("=" * 60)
check("pre-flight threshold is <=50pps", mdns_safe.PRE_FLIGHT_MAX_PPS <= 50,
      "got %d" % mdns_safe.PRE_FLIGHT_MAX_PPS)

print()
print("=" * 60)
print("TEST 13: Hard rate cap — verify <=10/min")
print("=" * 60)
check("hard rate cap is <=10/min", mdns_safe.HARD_RATE_CAP <= 10,
      "got %d" % mdns_safe.HARD_RATE_CAP)

print()
print("=" * 60)
print("TEST 14: Daily budget — verify <=2000")
print("=" * 60)
check("daily budget is <=2000", mdns_safe.DAILY_BUDGET <= 2000,
      "got %d" % mdns_safe.DAILY_BUDGET)

print()
print("=" * 60)
print("TEST 15: Rate limiter — old sends expire from window")
print("=" * 60)
mdns_safe.send_times = [time.time() - 120]  # 2 minutes ago (outside 60s window)
mdns_safe.send_count = 0
result = mdns_safe.check_rate()
check("sends older than 60s don't count", result == True)

mdns_safe.send_times = []

print()
print("=" * 60)
print("RESULTS: %d PASS, %d FAIL" % (PASS, FAIL))
print("=" * 60)
sys.exit(0 if FAIL == 0 else 1)
