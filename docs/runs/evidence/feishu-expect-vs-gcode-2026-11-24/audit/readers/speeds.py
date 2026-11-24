"""Speed rows: 270, 271, 264, 273, 276 (+272 non-SHADOW with a G-code).

    python -B speeds.py <out.txt>
"""
import collections
import io
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402

out = io.open(sys.argv[1], "w", encoding="utf-8")


def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n")


def hist(c, top=30, scale=1.0):
    items = sorted(c.items(), key=lambda kv: float(kv[0]))
    return " ".join("%s x%d" % (k, v) for k, v in items[:top]) + (" ..." if len(items) > top else "")


def feeds_by(g, name, band):
    S = g["S"]
    f = an.feat(g, name)
    c = collections.Counter()
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] == f:
            if (band == "L1" and S["L"][i] == 1) or (band == "ge2" and S["L"][i] >= 2):
                c["%.2f" % S["fd"][i]] += 1
    return c


def same_paths(ga, gb, names, layers=None, tol=1e-3):
    """are the extruding paths of `names` the same sequence of coordinates in both files?"""
    res = {}
    for name in names:
        fa, fb = an.feat(ga, name), an.feat(gb, name)
        if fa is None or fb is None:
            res[name] = "missing"
            continue
        A, B = ga["S"], gb["S"]
        ia = [i for i in range(len(A["k"])) if A["k"][i] == an.X and A["F"][i] == fa and (layers is None or A["L"][i] in layers)]
        ib = [i for i in range(len(B["k"])) if B["k"][i] == an.X and B["F"][i] == fb and (layers is None or B["L"][i] in layers)]
        if len(ia) != len(ib):
            res[name] = "moves %d vs %d (differ)" % (len(ia), len(ib))
            continue
        bad = 0
        mx = 0.0
        for p, q in zip(ia, ib):
            d = max(abs(A["x0"][p] - B["x0"][q]), abs(A["y0"][p] - B["y0"][q]), abs(A["x1"][p] - B["x1"][q]), abs(A["y1"][p] - B["y1"][q]))
            mx = max(mx, d)
            if d > tol:
                bad += 1
        res[name] = "%d moves, max dev %.4f, differing %d" % (len(ia), mx, bad)
    return res


# ---------------------------------------------------------------- #270
P("=" * 100, "\n#270 first-layer speeds  run c45355d9  base e9aa6f88")
r, b = gparse.load("c45355d9"), gparse.load("e9aa6f88")
for name in ("Outer wall", "Inner wall", "Bottom surface", "Brim", "Skirt"):
    if an.feat(r, name) is not None:
        P("  L1 %-15s run: %s | base: %s" % (name, hist(feeds_by(r, name, "L1"), 8), hist(feeds_by(b, name, "L1"), 8)))
P("  travel L1 run: %s | base: %s" % (hist(an.travel_hist(r, "first"), 8), hist(an.travel_hist(b, "first"), 8)))
P("  travel >=2 run: %s | base: %s" % (hist(an.travel_hist(r, "other"), 8), hist(an.travel_hist(b, "other"), 8)))
for name in r["feat_names"]:
    if an.feat(b, name) is not None and name not in ("Custom",):
        P("  >=2 %-20s same feed hist: %s | %s" % (name, feeds_by(r, name, "ge2") == feeds_by(b, name, "ge2"), same_paths(r, b, [name])[name]))
for k in ("initial_layer_speed", "initial_layer_infill_speed", "initial_layer_travel_speed", "filament_max_volumetric_speed",
          "filament_flow_ratio"):
    P("  config %-30s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))

# ---------------------------------------------------------------- #271
P("=" * 100, "\n#271 feature speeds  run 301dcb07  base 5994d5e6")
r, b = gparse.load("301dcb07"), gparse.load("5994d5e6")
for name in ("Outer wall", "Inner wall", "Sparse infill", "Top surface", "Internal solid infill", "Bridge", "Internal Bridge",
             "Gap infill", "Overhang wall", "Bottom surface"):
    P("  >=2 %-20s run: %s" % (name, hist(feeds_by(r, name, "ge2"), 14)))
    P("       %-20s base: %s" % ("", hist(feeds_by(b, name, "ge2"), 14)))
for k in ("outer_wall_speed", "inner_wall_speed", "sparse_infill_speed", "top_surface_speed", "small_perimeter_speed",
          "small_perimeter_threshold", "solid_infill_speed", "internal_solid_infill_speed", "filament_max_volumetric_speed",
          "filament_flow_ratio", "bridge_speed", "infill_direction", "top_surface_acceleration", "bridge_acceleration",
          "internal_bridge_acceleration", "internal_solid_infill_acceleration"):
    P("  config %-34s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
# volumetric rate implied by the top feeds
for name, epm in (("Outer wall", None), ("Sparse infill", None), ("Inner wall", None), ("Top surface", None)):
    pass
# small perimeters: loops < 10 mm
small_ok = small_bad = big_ok = big_bad = 0
bad_ex = []
small_feed = collections.Counter()
big_feed = collections.Counter()
for g, tag in ((r, "run"), (b, "base")):
    pass
for layer in range(2, len(r["layers"]) + 1):
    for name in ("Outer wall", "Inner wall"):
        for ch in an.chains(r, layer, name):
            L = an.chain_len(r, ch)
            f = r["S"]["fd"]
            feeds = collections.Counter("%.0f" % f[i] for i in ch)
            main = feeds.most_common(1)[0][0]
            if L < 10.0:
                small_feed[main] += 1
                if abs(float(main) - 3000) <= 60:
                    small_ok += 1
                else:
                    small_bad += 1
                    if len(bad_ex) < 12:
                        bad_ex.append((layer, name, round(L, 2), dict(feeds)))
            else:
                big_feed[main] += 1
                name_exp = "6000" if name == "Outer wall" else "9000"
                big_ok += feeds.get(name_exp, 0)
                big_bad += sum(v for k, v in feeds.items() if k != name_exp)
P("  loops with perimeter < 10 mm (layers>=2, outer+inner wall): %d; at F3000 +-60: %d; not: %d" % (
    small_ok + small_bad, small_ok, small_bad))
P("     main feed of small loops: %s" % dict(small_feed.most_common(12)))
P("     examples of small loops not at 3000: %s" % bad_ex)
P("  loops with perimeter >= 10 mm: moves at the set feed %d, moves at another feed %d; main feed %s" % (
    big_ok, big_bad, dict(big_feed.most_common(8))))
big_feed_b = collections.Counter()
for layer in range(2, len(b["layers"]) + 1):
    for name in ("Outer wall", "Inner wall"):
        for ch in an.chains(b, layer, name):
            feeds = collections.Counter("%.0f" % b["S"]["fd"][i] for i in ch)
            if an.chain_len(b, ch) < 10.0:
                big_feed_b[feeds.most_common(1)[0][0]] += 1
P("  (base) main feed of small loops < 10 mm: %s" % dict(big_feed_b.most_common(8)))
P("  paths: %s" % same_paths(r, b, ["Outer wall", "Inner wall", "Sparse infill", "Top surface", "Bottom surface"]))

# ---------------------------------------------------------------- #264 / #272
for row, rp in ((264, "cb8d8859"), (272, "94a82cda")):
    P("=" * 100, "\n#%d overhang speeds  run %s  base 0cccce4a" % (row, rp))
    r, b = gparse.load(rp), gparse.load("0cccce4a")
    for k in ("enable_overhang_speed", "detect_overhang_wall", "overhang_1_4_speed", "overhang_2_4_speed", "overhang_3_4_speed",
              "overhang_4_4_speed", "overhang_totally_speed", "bridge_speed", "outer_wall_speed", "inner_wall_speed",
              "slowdown_for_curled_perimeters", "filament_max_volumetric_speed"):
        P("  config %-28s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
    for name in ("Outer wall", "Overhang wall", "Bridge", "Inner wall", "Sparse infill", "Top surface", "Internal Bridge"):
        cr, cb = feeds_by(r, name, "ge2"), feeds_by(b, name, "ge2")
        P("  >=2 %-15s run n=%d: %s" % (name, sum(cr.values()), hist(cr, 400)))
        P("       %-15s base n=%d: %s" % ("", sum(cb.values()), hist(cb, 400)))
    # how many moves within 3% of each expected band feed
    cr = feeds_by(r, "Outer wall", "ge2")
    tot = sum(cr.values())
    for exp in (2400, 1800, 1200, 600, 300):
        n = sum(v for k, v in cr.items() if abs(float(k) - exp) <= 0.03 * exp)
        P("     outer wall moves within 3%% of F%d: %d of %d" % (exp, n, tot))
    vals = sorted(float(k) for k in cr)
    P("     outer wall feeds: min %.0f max %.0f; distinct %d" % (vals[0], vals[-1], len(vals)))
    P("  paths: %s" % same_paths(r, b, ["Outer wall", "Inner wall", "Bridge", "Sparse infill"]))

# ---------------------------------------------------------------- #273
P("=" * 100, "\n#273 travel speed  run d15b8c66  base cd540456")
r, b = gparse.load("d15b8c66"), gparse.load("cd540456")
for band in ("first", "other"):
    P("  travel %-5s run: %s" % (band, hist(an.travel_hist(r, band), 20)))
    P("  travel %-5s base: %s" % (band, hist(an.travel_hist(b, band), 20)))
for k in ("travel_speed", "travel_speed_z", "z_hop", "prime_tower_... ", "wipe_speed", "role_based_wipe_speed", "retract_speed",
          "wipe_retract_speed", "deretraction_speed", "filament_retract_speed", "filament_travel_speed", "travel_acceleration"):
    P("  config %-26s run %s | base %s" % (k.strip(), an.config(r, k.strip()), an.config(b, k.strip())))
# what are the non-F18000 travels on layers >= 2 ? classify by the feature they are in, E and neighbours
S = r["S"]
cls = collections.Counter()
ex = {}
for i in range(len(S["k"])):
    if S["k"][i] == an.T and S["L"][i] > 1 and abs(S["fd"][i] - 18000) > 1:
        name = r["feat_names"][S["F"][i]] if S["F"][i] is not None else "-"
        key = (name, "%.0f" % S["fd"][i], "wi" if S["wi"][i] else "")
        cls[key] += 1
        ex.setdefault(key, i)
P("  run travels on layers>=2 not at F18000 by (feature, feed, in-wipe): %s" % dict(cls))
for key, i in list(ex.items())[:8]:
    lines = []
    for j in range(max(0, i - 3), min(len(S["k"]), i + 3)):
        lines.append("L%d F%s k%d E%.4f (%.2f,%.2f)->(%.2f,%.2f) [%s] wi%d" % (
            S["L"][j], S["fd"][j], S["k"][j], S["e"][j], S["x0"][j] or 0, S["y0"][j] or 0, S["x1"][j] or 0, S["y1"][j] or 0,
            r["feat_names"][S["F"][j]] if S["F"][j] is not None else "-", S["wi"][j]))
    P("     %s ->" % (key,))
    for l in lines:
        P("         " + l)
Sb = b["S"]
clsb = collections.Counter()
for i in range(len(Sb["k"])):
    if Sb["k"][i] == an.T and Sb["L"][i] > 1:
        name = b["feat_names"][Sb["F"][i]] if Sb["F"][i] is not None else "-"
        clsb[(name, "%.0f" % Sb["fd"][i], "wi" if Sb["wi"][i] else "")] += 1
P("  base travels on layers>=2 by (feature, feed, in-wipe): %s" % dict(clsb))
# moves with XY and negative E on layers >= 2 by feed
neg = collections.Counter()
for i in range(len(S["k"])):
    if S["k"][i] == an.WIPERET and S["L"][i] > 1:
        neg["%.0f" % S["fd"][i]] += 1
negb = collections.Counter()
for i in range(len(Sb["k"])):
    if Sb["k"][i] == an.WIPERET and Sb["L"][i] > 1:
        negb["%.0f" % Sb["fd"][i]] += 1
P("  XY moves with negative E on layers>=2: run %s | base %s" % (dict(neg), dict(negb)))
P("  extruding feeds identical: %s" % all(feeds_by(r, n, "ge2") == feeds_by(b, n, "ge2") for n in r["feat_names"] if n != "Custom" and an.feat(b, n) is not None))
P("  paths: %s" % same_paths(r, b, ["Outer wall", "Inner wall", "Sparse infill", "Top surface", "Prime tower", "Internal solid infill"]))
P("  max feed of any XY move: run %.0f base %.0f" % (max(S["fd"][i] for i in range(len(S["k"])) if S["k"][i] in (an.X, an.T)),
                                                   max(Sb["fd"][i] for i in range(len(Sb["k"])) if Sb["k"][i] in (an.X, an.T))))

# ---------------------------------------------------------------- #276
P("=" * 100, "\n#276 speed limits  run 8902f8ae  base e9aa6f88")
r, b = gparse.load("8902f8ae"), gparse.load("e9aa6f88")
for k in ("outer_wall_speed", "layer_height", "outer_wall_line_width", "filament_max_volumetric_speed", "machine_max_speed_x",
          "machine_max_speed_y", "filament_flow_ratio", "slowdown_layer_time", "slowdown_layer_time_initial",
          "min_layer_time", "min_print_speed", "enable_overhang_speed"):
    P("  config %-28s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
for name in ("Outer wall", "Inner wall", "Sparse infill", "Top surface"):
    cr, cb = feeds_by(r, name, "ge2"), feeds_by(b, name, "ge2")
    P("  >=2 %-13s run: %s" % (name, hist(cr, 12)))
    P("       %-13s base: %s" % ("", hist(cb, 12)))
S = r["S"]
mx = max(S["fd"][i] for i in range(len(S["k"])) if S["k"][i] in (an.X, an.T))
P("  max feed of any XY move: run %.1f base %.1f" % (mx, max(b["S"]["fd"][i] for i in range(len(b["S"]["k"])) if b["S"]["k"][i] in (an.X, an.T))))
P("  files identical in motion+commands (events & feeds): %s" % (r["events"] == b["events"] and all(
    r["S"][k] == b["S"][k] for k in r["S"])))
P("  paths: %s" % same_paths(r, b, ["Outer wall", "Inner wall", "Sparse infill", "Top surface"]))
epm = 0.03073
for vol in (12.0, 15.0):
    P("  cap for w0.42 h0.2: %.1f mm3/s / (E/mm %.5f x 2.405 = %.5f mm3/mm) = %.1f mm/s = F%.0f; rectangular 15/(0.42x0.2) = %.1f mm/s" % (
        vol, epm, epm * 2.40528, vol / (epm * 2.40528), 60 * vol / (epm * 2.40528), 15 / 0.084))
out.close()
