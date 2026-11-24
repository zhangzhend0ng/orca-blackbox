"""Exploration 2 for #271 (why closed loops >= 10 mm run at F3000).

    python -B explore_speeds2.py
"""
import collections
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402

r, b = gparse.load("301dcb07"), gparse.load("5994d5e6")
Sr, Sb = r["S"], b["S"]


def chain_by_start(g):
    S = g["S"]
    d = {}
    for layer in range(2, len(g["layers"]) + 1):
        for name in ("Outer wall", "Inner wall"):
            for ch in an.chains(g, layer, name):
                d[(layer, name, round(S["x0"][ch[0]], 1), round(S["y0"][ch[0]], 1))] = ch
    return d


def main_feed(S, ch):
    return collections.Counter("%.0f" % S["fd"][i] for i in ch).most_common(1)[0][0]


dr, db = chain_by_start(r), chain_by_start(b)
pairs = collections.Counter()
rows = []
for key, ch in dr.items():
    if key in db and an.chain_closed(r, ch, 0.06) and an.chain_len(r, ch) >= 10.0:
        mr, mb = main_feed(Sr, ch), main_feed(Sb, db[key])
        pairs[(mr, mb)] += 1
        if mr == "3000":
            rows.append((key[0], key[1], round(an.chain_len(r, ch), 1), len(ch), mb, round(Sr["x0"][ch[0]], 1), round(Sr["y0"][ch[0]], 1)))
print("closed loops >= 10 mm matched by start point: (run main feed, base main feed) -> %s" % dict(pairs.most_common(14)))
print("loops at 3000 in run: %d; by (layer range, base feed):" % len(rows))
c = collections.Counter((row[1], row[4]) for row in rows)
print("   ", dict(c.most_common(14)))
print("    layers with such loops: %s" % sorted(set(row[0] for row in rows)))
print("    lengths: min %.1f max %.1f ; examples %s" % (min(row[2] for row in rows), max(row[2] for row in rows), rows[:10]))

# layer feeds for a few layers
def layer_hist(g, layer):
    S = g["S"]
    out = {}
    for (l, f), ids in an.idx(g).items():
        if l != layer:
            continue
        cc = collections.Counter("%.0f" % S["fd"][i] for i in ids if S["k"][i] == an.X)
        if cc:
            out[g["feat_names"][f]] = " ".join("%s x%d" % kv for kv in cc.most_common(4))
    return out


for layer in (43, 44, 61, 46):
    print("  run  L%d: %s" % (layer, layer_hist(r, layer)))
    print("  base L%d: %s" % (layer, layer_hist(b, layer)))
for k in ("slowdown_layer_time", "slowdown_layer_time_initial", "min_layer_time", "min_print_speed", "slowdown_min_speed",
          "fan_cooling_layer_time", "full_fan_speed_layer", "small_perimeter_speed", "small_perimeter_threshold", "inner_wall_speed",
          "outer_wall_speed", "top_surface_speed", "sparse_infill_speed", "internal_solid_infill_speed", "bridge_speed", "internal_bridge_speed",
          "support_speed", "support_interface_speed", "gap_infill_speed", "filament_max_volumetric_speed", "spiral_..."):
    print("  config %-30s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
