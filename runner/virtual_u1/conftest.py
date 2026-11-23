# Standalone scripts with their own command lines, not pytest modules —
# test_mdns_safe.py runs its checks and exits on import, which breaks any
# pytest collection that sweeps this directory (a runner or an IDE).
collect_ignore = ["test_l2.py", "test_loop.py", "test_mdns_safe.py"]
