"""Misc rows: 267 (shells/pattern), 269 (infill structure), 274 (accelerations), 275 (jerk), 285 (ooze),
plus follow-ups for 257 (first-layer inset, holes), 258 (model height from the fixture's 3mf).

    python -B misc.py
"""
import collections
import io
import json
import math
import os
import re
import sys
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402


def cfg(g, keys, b=None):
    for k in keys:
        print("  config %-32s %s | base %s" % (k, an.config(g, k), an.config(b, k) if b else ""))


def feat_layers(g, name):
    S = g["S"]
    f = an.feat(g, name)
    return sorted(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f))


print("#267 shells / patterns  run 728e77c7  base e9aa6f88")
r, b = gparse.load("728e77c7"), gparse.load("e9aa6f88")
cfg(r, ["top_shell_layers", "bottom_shell_layers", "top_surface_pattern", "bottom_surface_pattern", "internal_solid_infill_pattern",
        "top_color_penetration_layers", "bottom_color_penetration_layers", "wall_loops", "sparse_infill_layers"], b)
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    n = len(g["layers"])
    for name in ("Top surface", "Internal solid infill", "Bottom surface"):
        L = feat_layers(g, name)
        print("  [%s] %-20s on layers %s" % (tag, name, L if len(L) <= 12 else "%s ... (n=%d)" % (L[:12], len(L))))
    for L in (n - 4, n - 3, n - 2, n - 1, n):
        f = an.feat(g, "Top surface") if L == n else an.feat(g, "Internal solid infill")
        seg = an.segs_of(g, L, [g["feat_names"][f]])
        ch = an.chains(g, L, g["feat_names"][f])
        closed = sum(1 for c in ch if an.chain_closed(g, c, 0.15))
        d = seg[:, 2:] - seg[:, :2]
        ang = collections.Counter(int(round((math.degrees(math.atan2(dy, dx)) % 180.0) / 5.0)) * 5 % 180 for dx, dy in d)
        print("     layer %d %s: chains %d (closed %d), moves %d, directions (deg, share) %s, median move len %.2f" % (
            L, g["feat_names"][f], len(ch), closed, len(seg), " ".join("%d:%.0f%%" % (a, 100.0 * v / len(seg)) for a, v in ang.most_common(4)),
            float(np.median(np.hypot(d[:, 0], d[:, 1])))))
    segb = an.segs_of(g, 1, ["Bottom surface"])
    chb = an.chains(g, 1, "Bottom surface")
    db = segb[:, 2:] - segb[:, :2]
    angb = collections.Counter(int(round((math.degrees(math.atan2(dy, dx)) % 180.0) / 5.0)) * 5 % 180 for dx, dy in db)
    print("     layer 1 Bottom surface: chains %d, moves %d, directions %s" % (len(chb), len(segb), " ".join("%d:%.0f%%" % (a, 100.0 * v / len(segb)) for a, v in angb.most_common(4))))
    print("     layer 2/3 internal solid infill directions: %s" % [
        " ".join("%d:%.0f%%" % (a, 100.0 * v / len(an.segs_of(g, L, ["Internal solid infill"]))) for a, v in collections.Counter(
            int(round((math.degrees(math.atan2(dy, dx)) % 180.0) / 5.0)) * 5 % 180
            for dx, dy in (an.segs_of(g, L, ["Internal solid infill"])[:, 2:] - an.segs_of(g, L, ["Internal solid infill"])[:, :2])).most_common(3)) for L in (2, 3)])
br_ = [(round(S["x0"][i], 3), round(S["y0"][i], 3), round(S["x1"][i], 3), round(S["y1"][i], 3)) for i in range(len(b["S"]["k"])) if b["S"]["k"][i] == an.X and b["S"]["F"][i] == an.feat(b, "Bottom surface")]
rr_ = [(round(S["x0"][i], 3), round(S["y0"][i], 3), round(S["x1"][i], 3), round(S["y1"][i], 3)) for i in range(len(r["S"]["k"])) if r["S"]["k"][i] == an.X and r["S"]["F"][i] == an.feat(r, "Bottom surface")]
print("  bottom-surface move sequence identical run vs base: %s; same multiset: %s" % (br_ == rr_, collections.Counter(br_) == collections.Counter(rr_)))
print("  first 4 bottom-surface moves run %s | base %s" % (rr_[:4], br_[:4]))

print("\n#269 infill structure  run 3c6a8dc5  base 0cccce4a")
r, b = gparse.load("3c6a8dc5"), gparse.load("0cccce4a")
cfg(r, ["infill_combination", "infill_combination_max_layer_height", "minimum_sparse_infill_area", "internal_bridge_support_thickness",
        "bridge_angle", "detect_narrow_internal_solid_infill", "ensure_vertical_shell_thickness", "sparse_infill_density", "internal_bridge_support_all_locations"], b)
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    f = an.feat(g, "Sparse infill")
    per = collections.Counter()
    em = collections.defaultdict(float)
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] == f and 300 <= S["L"][i] <= 331:
            per[S["L"][i]] += an.seg_len(S, i)
            em[S["L"][i]] += S["e"][i]
    seq = [(L, int(per.get(L, 0)), round(em.get(L, 0) / per[L], 4) if per.get(L) else 0) for L in range(300, 317)]
    print("  [%s] sparse-infill length and E/mm per layer 300..316: %s" % (tag, seq))
    # small sparse-infill islands: chain length and approximate area of tiny regions
    small = collections.Counter()
    for L in range(50, 450, 5):
        for c in an.chains(g, L, "Sparse infill"):
            small["<2mm" if an.chain_len(g, c) < 2 else "2-5mm" if an.chain_len(g, c) < 5 else ">=5mm"] += 1
    print("       sparse-infill chains by length (sampled layers): %s" % dict(small))
    f2 = an.feat(g, "Bridge")
    d = an.segs_of(g, 430, ["Bridge"])
    for name in ("Bridge", "Internal Bridge"):
        dd = an.segs_of(g, 0, [name]) if False else None
    for name in ("Bridge", "Internal Bridge", "Internal solid infill"):
        f3 = an.feat(g, name)
        ids = [i for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f3]
        ang = collections.Counter()
        for i in ids:
            a = int(round((math.degrees(math.atan2(S["y1"][i] - S["y0"][i], S["x1"][i] - S["x0"][i])) % 180.0) / 5.0)) * 5 % 180
            ang[a] += an.seg_len(S, i)
        tot = sum(ang.values())
        print("       %-20s blocks %d layers %d, length %.0f mm, direction (by length) %s" % (
            name, g["types"].get(name, 0), len(set(S["L"][i] for i in ids)), tot, " ".join("%d:%.0f%%" % (a, 100.0 * v / tot) for a, v in ang.most_common(3))))

print("\n#274 accelerations  run 0b0d9c99  base 5994d5e6")
r, b = gparse.load("0b0d9c99"), gparse.load("5994d5e6")
cfg(r, ["default_acceleration", "initial_layer_acceleration", "outer_wall_acceleration", "inner_wall_acceleration", "sparse_infill_acceleration",
        "travel_acceleration", "top_surface_acceleration", "bridge_acceleration", "internal_bridge_acceleration", "internal_solid_infill_acceleration",
        "support_acceleration", "support_interface_acceleration", "machine_max_acceleration_x", "machine_max_acceleration_y", "machine_max_acceleration_z",
        "machine_max_acceleration_e"], b)
for tag, g in (("run", r), ("base", b)):
    # map each SET_VELOCITY_LIMIT ACCEL line to the feature block it is in (and to the feature block that follows if it sits between blocks)
    per = collections.defaultdict(collections.Counter)
    last_type_line = None
    S = g["S"]
    # walk the file: need order of TYPE and SET_VELOCITY_LIMIT lines: use events with layer + index of last move
    type_events = []
    with open(g["path"], encoding="utf-8", errors="replace") as fh:
        cur = None
        for ln, raw in enumerate(fh, 1):
            if raw.startswith(";TYPE:"):
                cur = raw[6:].strip()
            elif raw.startswith("SET_VELOCITY_LIMIT"):
                m = re.search(r"ACCEL=([0-9.]+)", raw)
                if m and cur:
                    per[cur]["%g" % float(m.group(1))] += 1
    for name, c in per.items():
        print("  [%s] %-24s ACCEL (x lines): %s" % (tag, name, " ".join("%s x%d" % kv for kv in sorted(c.items(), key=lambda kv: -kv[1])[:5])))

print("\n#275 jerk  run 9f47af1f  base 818ecfc6")
r, b = gparse.load("9f47af1f"), gparse.load("818ecfc6")
cfg(r, ["default_jerk", "initial_layer_jerk", "outer_wall_jerk", "inner_wall_jerk", "infill_jerk", "travel_jerk", "top_surface_jerk",
        "bridge_jerk", "internal_bridge_jerk", "internal_solid_infill_jerk", "thick_bridges", "enable_arc_fitting", "spiral_mode"], b)
ev_r = [e[3] for e in r["events"]]
ev_b = [e[3] for e in b["events"]]
print("  command lines identical run vs base: %s (run %d lines, base %d)" % (ev_r == ev_b, len(ev_r), len(ev_b)))
print("  command words that could carry jerk (JERK/M204 J/SET_VELOCITY_LIMIT ... J): run %s" % [l for l in ev_r if "JERK" in l.upper() or re.search(r"\bJ[0-9]", l)][:5])
print("  motion identical (all S lists equal): %s" % all(r["S"][k] == b["S"][k] for k in r["S"]))
diff = [(k, len(r["S"][k]), len(b["S"][k])) for k in r["S"] if r["S"][k] != b["S"][k]]
print("  differing S keys: %s" % diff[:8])
la = open(r["path"], encoding="utf-8", errors="replace").read().split("\n")
lb = open(b["path"], encoding="utf-8", errors="replace").read().split("\n")
outside_cfg = [(i, x, y) for i, (x, y) in enumerate(zip(la, lb)) if x != y and " = " not in x][:6]
print("  first differing lines outside 'key = value' (run | base): %s" % outside_cfg)

print("\n#285 ooze prevention  run 46fcf33b  base 02793334")
r, b = gparse.load("46fcf33b"), gparse.load("02793334")
cfg(r, ["ooze_prevention", "standby_temperature_delta", "preheat_steps", "preheat_time", "temperature", "nozzle_temperature", "nozzle_temperature_initial_layer",
        "filament_diameter", "filament_type"], b)
S = r["S"]
print("  tools that extrude in the run: %s ; T commands in events: %s" % (sorted(set(t for t in S["T"] if t is not None)), [e[3] for e in r["events"] if re.match(r"^T\d", e[3])][:10]))
print("  M104/M109 lines in run: %s" % [e[3] for e in r["events"] if e[3].startswith(("M104", "M109"))])
print("  M104/M109 lines in base: %s" % [e[3] for e in b["events"] if e[3].startswith(("M104", "M109"))])
print("  tool-change markers / comments mentioning toolchange in run: %s" % {k: v for k, v in r["markers"].items() if "TOOL" in k.upper() or "CHANGE" in k.upper()})
print("  filament_count %s | wipe_tower_filament %s | enable_prime_tower %s" % (an.config(r, "filament_count"), an.config(r, "wipe_tower_filament"), an.config(r, "enable_prime_tower")))
print("  command lines identical run vs base: %s" % ([e[3] for e in r["events"]] == [e[3] for e in b["events"]]))

print("\n#257 follow-up: first-layer inset and holes")
r, b = gparse.load("3f239cab"), gparse.load("0d6777e0")
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    f = an.feat(g, "Outer wall")
    bb = {}
    for L in (1, 2, 5):
        xs = [S["x0"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f] + [S["x1"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f]
        ys = [S["y0"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f] + [S["y1"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f]
        bb[L] = (min(xs), max(xs), min(ys), max(ys))
    print("  [%s] outer-wall centreline bbox L1 x %.3f..%.3f y %.3f..%.3f | L2 x %.3f..%.3f y %.3f..%.3f | L5 x %.3f..%.3f y %.3f..%.3f" % ((tag,) + bb[1] + bb[2] + bb[5]))
    print("       L1 centreline inset from L2 per side: x- %.3f x+ %.3f y- %.3f y+ %.3f ; nominal (0.5-0.42)/2 = %.3f" % (
        bb[1][0] - bb[2][0], bb[2][1] - bb[1][1], bb[1][2] - bb[2][2], bb[2][3] - bb[1][3], 0.04))
    loops = []
    for c in an.chains(g, 5, "Outer wall"):
        p = an.pts(g, c)
        a = 0.5 * sum(p[j][0] * p[j + 1][1] - p[j + 1][0] * p[j][1] for j in range(len(p) - 1))
        cx = sum(q[0] for q in p[:-1]) / (len(p) - 1)
        cy = sum(q[1] for q in p[:-1]) / (len(p) - 1)
        loops.append((round(cx, 0), round(cy, 0), abs(a), an.chain_len(g, c)))
    loops.sort(key=lambda q: -q[2])
    print("       loops on L5 (cx, cy, area, perimeter): %s" % loops)
print("\n#258 follow-up: mesh height of the fixture (tolerance model)")
for pref in ("dc0f42c3",):
    d = gparse.run_dir(pref)
    z = zipfile.ZipFile(os.path.join(d, "input", "fixture.3mf"))
    names = [n for n in z.namelist() if n.lower().endswith(".model")]
    for n in names:
        xml = z.read(n).decode("utf-8", errors="replace")
        vs = re.findall(r"<vertex\s+[^>]*?x=\"([-0-9.eE]+)\"[^>]*?y=\"([-0-9.eE]+)\"[^>]*?z=\"([-0-9.eE]+)\"", xml)
        zs_ = np.array([float(v[2]) for v in vs])
        print("  %s: %d vertices; z min %.4f max %.4f ; build transform: %s" % (
            n, len(vs), zs_.min() if len(zs_) else float("nan"), zs_.max() if len(zs_) else float("nan"), re.findall(r"<build>.*?</build>", xml, re.S)[:1]))
