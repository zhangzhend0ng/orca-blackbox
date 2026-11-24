"""E/mm and spacing rows: 255, 262, 259, 280, 268, 263, 281.

    python -B emm.py <out.txt>
"""
import collections
import io
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402

out = io.open(sys.argv[1], "w", encoding="utf-8")
out.maxlong = 0


def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n")


def epmm(g, name, layers=None):
    S = g["S"]
    f = an.feat(g, name)
    L = E = 0.0
    n = 0
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] == f and (layers is None or S["L"][i] in layers):
            L += an.seg_len(S, i)
            E += S["e"][i]
            n += 1
    return (E / L if L else float("nan")), L, E, n


def layers_ge(g, n):
    return set(range(n, len(g["layers"]) + 1))


def area_epm(w, h, flow=1.0, ratio=0.98):
    return (w * h - 0.858407 * (h / 2.0) ** 2) * flow * ratio / 2.40528


def spacing(g, layer, name, minlen=0.6):
    S4 = an.segs_of(g, layer, [name])
    # keep only straight-ish long segments
    if len(S4):
        d = S4[:, 2:] - S4[:, :2]
        L = np.hypot(d[:, 0], d[:, 1])
        S4 = S4[L >= minlen]
    sp = an.spacing_parallel(S4)
    return sp, len(S4)


def paths_equal(ga, gb, name, layers=None, tol=1e-3):
    A, B = ga["S"], gb["S"]
    fa, fb = an.feat(ga, name), an.feat(gb, name)
    ia = [i for i in range(len(A["k"])) if A["k"][i] == an.X and A["F"][i] == fa and (layers is None or A["L"][i] in layers)]
    ib = [i for i in range(len(B["k"])) if B["k"][i] == an.X and B["F"][i] == fb and (layers is None or B["L"][i] in layers)]
    if len(ia) != len(ib):
        return "moves %d vs %d" % (len(ia), len(ib))
    mx = max((max(abs(A["x0"][p] - B["x0"][q]), abs(A["y0"][p] - B["y0"][q]), abs(A["x1"][p] - B["x1"][q]), abs(A["y1"][p] - B["y1"][q]))
              for p, q in zip(ia, ib)), default=0.0)
    return "%d moves, max dev %.4f" % (len(ia), mx)


# ---------------------------------------------------------------- #255
P("=" * 90, "\n#255 line widths  run cd9a4f6a  base e9aa6f88")
r, b = gparse.load("cd9a4f6a"), gparse.load("e9aa6f88")
ge2 = layers_ge(r, 2)
for k in ("line_width", "initial_layer_line_width", "outer_wall_line_width", "inner_wall_line_width", "top_surface_line_width",
          "sparse_infill_line_width", "support_line_width", "filament_flow_ratio", "print_flow_ratio", "layer_height", "first_layer_height"):
    P("  config %-26s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
P("  summary run:", " | ".join(s[2:] for s in r["summary"]))
for name, w in (("Outer wall", 0.42), ("Inner wall", 0.45), ("Sparse infill", 0.45), ("Top surface", 0.40), ("Internal solid infill", 0.42),
                ("Bottom surface", 0.50), ("Internal Bridge", 0.42)):
    e2, L2, E2, n2 = epmm(r, name, ge2)
    e1, L1, E1, n1 = epmm(r, name, {1})
    eb2 = epmm(b, name, ge2)[0]
    eb1 = epmm(b, name, {1})[0]
    P("  %-20s E/mm L>=2 %.5f (base %.5f; formula w=%.2f,h=.2,0.98: %.5f; ratio to formula %.4f; ratio to w*h/2.405 %.4f) | L1 %.5f (base %.5f; formula w=.5,h=.25: %.5f)" % (
        name, e2, eb2, w, area_epm(w, 0.2), e2 / area_epm(w, 0.2), e2 * 2.40528 / (w * 0.2), e1, eb1, area_epm(0.5, 0.25)))
for name in ("Outer wall", "Inner wall", "Sparse infill", "Internal solid infill", "Internal Bridge", "Bottom surface"):
    P("  paths %-20s run vs base: %s" % (name, paths_equal(r, b, name)))
P("  Top surface len: run %.1f base %.1f ; moves %d vs %d" % (epmm(r, "Top surface")[1], epmm(b, "Top surface")[1], epmm(r, "Top surface")[3], epmm(b, "Top surface")[3]))

# ---------------------------------------------------------------- #262
P("=" * 90, "\n#262 surface flow  run 2779be8f  base 5994d5e6")
r, b = gparse.load("2779be8f"), gparse.load("5994d5e6")
ge2 = layers_ge(r, 2)
for name in ("Top surface", "Bottom surface", "Internal solid infill", "Outer wall", "Inner wall", "Sparse infill", "Bridge", "Internal Bridge"):
    er, Lr, Er, nr = epmm(r, name)
    eb, Lb, Eb, nb = epmm(b, name)
    P("  %-20s E/mm run %.5f base %.5f ratio %.4f | len %.1f/%.1f moves %d/%d" % (name, er, eb, er / eb if eb else float("nan"), Lr, Lb, nr, nb))
P("  bottom-surface layers in run: %s" % sorted(set(r["S"]["L"][i] for i in range(len(r["S"]["k"])) if r["S"]["k"][i] == an.X and r["S"]["F"][i] == an.feat(r, "Bottom surface"))))
P("  top-surface layers in run: %s" % sorted(set(r["S"]["L"][i] for i in range(len(r["S"]["k"])) if r["S"]["k"][i] == an.X and r["S"]["F"][i] == an.feat(r, "Top surface"))))
for name in ("Top surface", "Bottom surface", "Outer wall", "Inner wall", "Sparse infill", "Internal solid infill", "Bridge", "Internal Bridge", "Gap infill", "Overhang wall"):
    P("  paths %-20s run vs base: %s" % (name, paths_equal(r, b, name)))
tr = collections.Counter("%.1f" % r["S"]["fd"][i] for i in range(len(r["S"]["k"])) if r["S"]["k"][i] == an.X and r["S"]["F"][i] == an.feat(r, "Top surface"))
P("  top-surface feeds run: %s" % dict(tr.most_common(4)))

# ---------------------------------------------------------------- #259 / #280 ironing
for row, rp, bp, sup in ((259, "fcfb01eb", "e9aa6f88", False), (280, "f366c4c9", "0cccce4a", True)):
    P("=" * 90, "\n#%d ironing  run %s  base %s" % (row, rp, bp))
    r, b = gparse.load(rp), gparse.load(bp)
    for k in ("ironing_type", "ironing_flow", "ironing_spacing", "ironing_speed", "ironing_pattern", "ironing_direction", "ironing_angle",
              "support_ironing", "support_ironing_flow", "support_ironing_spacing", "support_ironing_pattern", "support_line_width",
              "top_surface_line_width", "line_width", "layer_height", "filament_flow_ratio"):
        P("  config %-26s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
    S = r["S"]
    f = an.feat(r, "Ironing")
    lays = sorted(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f))
    e, L, E, n = epmm(r, "Ironing")
    feeds = collections.Counter("%.0f" % S["fd"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f)
    P("  Ironing: %d blocks on %d layers %s..%s; moves %d; len %.1f; E %.3f; E/mm %.5f; feeds %s" % (
        r["types"].get("Ironing", 0), len(lays), lays[0], lays[-1], n, L, E, e, dict(feeds.most_common(4))))
    ref_name = "Support" if sup else "Top surface"
    ref = epmm(r, ref_name, None if sup else ge2)[0]
    P("  reference E/mm of %s = %.5f -> ironing/ref = %.3f ; 10%% of it would be %.5f; ironing mm3/mm = %.5f" % (
        ref_name, ref, e / ref, 0.1 * ref, e * 2.40528))
    if sup:
        fi = an.feat(r, "Support interface")
        lay_i = set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi)
        fs = an.feat(r, "Support")
        lay_s = set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fs)
        P("  layers with Support interface: %d; with Ironing: %d; ironing layers that also have support interface: %d; without: %d" % (
            len(lay_i), len(lays), len(set(lays) & lay_i), len(set(lays) - lay_i)))
        P("  ironing layers without support interface (first 10): %s" % sorted(set(lays) - lay_i)[:10])
        # is ironing adjacent to a support-interface block? check previous block type for each Ironing block
        blocks = r["blocks"]
        prev = collections.Counter(r["feat_names"][blocks[k - 1][1]] for k in range(1, len(blocks)) if blocks[k][1] == f)
        P("  block type preceding each Ironing block: %s" % dict(prev))
        # does the model top layer (last) have ironing?
        P("  last model layer %d has ironing: %s" % (len(r["layers"]), len(r["layers"]) in lays))
    else:
        sp, nseg = spacing(r, lays[-1], "Ironing", 1.0)
        if sp:
            P("  ironing line spacing (layer %d, %d long segments): median %.3f min %.3f max %.3f (n=%d)" % (
                lays[-1], nseg, float(np.median(sp)), min(sp), max(sp), len(sp)))
        lens = sorted(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f)
        P("  ironing move lengths: min %.3f median %.3f max %.3f" % (lens[0], lens[len(lens) // 2], lens[-1]))
    # raw sample
    lines = open(r["path"], encoding="utf-8", errors="replace").read().split("\n")
    start = next(i for i, l in enumerate(lines) if l.startswith(";TYPE:Ironing"))
    P("  raw sample:")
    for l in lines[start:start + 14]:
        P("     " + l[:90])
    for name in (["Support", "Support interface", "Outer wall", "Top surface", "Internal solid infill"] if sup else ["Top surface", "Outer wall", "Inner wall", "Sparse infill", "Internal solid infill"]):
        P("  paths %-20s run vs base: %s" % (name, paths_equal(r, b, name)))

# ---------------------------------------------------------------- #268
P("=" * 90, "\n#268 infill combo  run d08d1fe8  base e9aa6f88")
r, b = gparse.load("d08d1fe8"), gparse.load("e9aa6f88")
for k in ("sparse_infill_density", "sparse_infill_pattern", "infill_direction", "infill_wall_overlap", "top_bottom_infill_wall_overlap",
          "sparse_infill_line_width", "gap_fill_target", "gap_fill_enabled", "infill_combination", "wall_loops", "line_width"):
    P("  config %-28s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
S = r["S"]
fs = an.feat(r, "Sparse infill")
fi = an.feat(r, "Inner wall")
mid = list(range(20, 120))
per_r = collections.Counter()
per_b = collections.Counter()
for i in range(len(S["k"])):
    if S["k"][i] == an.X and S["F"][i] == fs and S["L"][i] in mid:
        per_r[S["L"][i]] += an.seg_len(S, i)
Sb = b["S"]
fsb = an.feat(b, "Sparse infill")
for i in range(len(Sb["k"])):
    if Sb["k"][i] == an.X and Sb["F"][i] == fsb and Sb["L"][i] in mid:
        per_b[Sb["L"][i]] += an.seg_len(Sb, i)
Lr = sum(per_r.values()) / len(mid)
Lb = sum(per_b.values()) / len(mid)
P("  sparse-infill length per mid layer (layers 20..119): run %.1f mm base %.1f mm ratio %.4f" % (Lr, Lb, Lr / Lb))
P("  line length ratio -> density: run/base %.4f vs 20%%/15%% = %.4f" % (Lr / Lb, 20 / 15.0))
ang_r = collections.Counter()
ang_b = collections.Counter()
for g, f, c in ((r, fs, ang_r), (b, fsb, ang_b)):
    SS = g["S"]
    for i in range(len(SS["k"])):
        if SS["k"][i] == an.X and SS["F"][i] == f and 20 <= SS["L"][i] <= 119:
            a = int(round((math.degrees(math.atan2(SS["y1"][i] - SS["y0"][i], SS["x1"][i] - SS["x0"][i])) % 180.0) / 5.0)) * 5 % 180
            c[a] += 1
tot = sum(ang_r.values())
P("  direction histogram of sparse infill (5-deg buckets, %% of moves) run: %s" % " ".join(
    "%d:%.0f%%" % (a, 100.0 * n / tot) for a, n in sorted(ang_r.items())))
tot = sum(ang_b.values())
P("  direction histogram base: %s" % " ".join("%d:%.0f%%" % (a, 100.0 * n / tot) for a, n in sorted(ang_b.items())))
seg_r = sorted(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fs and 20 <= S["L"][i] <= 119)
P("  run sparse-infill move lengths: n=%d median %.3f p90 %.3f max %.3f" % (len(seg_r), seg_r[len(seg_r) // 2], seg_r[int(len(seg_r) * .9)], seg_r[-1]))
for lay in (60,):
    spr, nr = spacing(r, lay, "Sparse infill", 0.5)
    spb, nb = spacing(b, lay, "Sparse infill", 0.5)
    P("  layer %d spacing: run median %.3f (n=%d, segs %d) | base median %.3f (n=%d, segs %d)" % (
        lay, float(np.median(spr)) if spr else float("nan"), len(spr), nr, float(np.median(spb)) if spb else float("nan"), len(spb), nb))
# distance from sparse-infill segment ends to the inner-wall centreline
for g, tag, f_ in ((r, "run", fs), (b, "base", fsb)):
    SS = g["S"]
    ends = []
    for layer in range(20, 120):
        ids = [i for i in an.idx(g).get((layer, f_), []) if SS["k"][i] == an.X]
        if not ids:
            continue
        walls = an.segs_of(g, layer, ["Inner wall"])
        pts_ = np.array([(SS["x0"][i], SS["y0"][i]) for i in ids] + [(SS["x1"][i], SS["y1"][i]) for i in ids])
        d = an.point_seg_dist(pts_, walls)
        ends.append(d)
    d = np.concatenate(ends)
    P("  [%s] distance from sparse-infill line ends to inner-wall centreline: min %.4f, 5%% %.4f, median %.4f" % (
        tag, d.min(), float(np.percentile(d, 5)), float(np.median(d))))
P("  gap infill blocks/moves: run %s/%s base %s/%s" % (r["types"].get("Gap infill", 0), sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(r, "Gap infill")) if an.feat(r, "Gap infill") is not None else 0,
  b["types"].get("Gap infill", 0), 0))
for name in ("Outer wall", "Inner wall", "Top surface", "Internal solid infill"):
    P("  paths %-20s run vs base: %s" % (name, paths_equal(r, b, name)))

# ---------------------------------------------------------------- #263
P("=" * 90, "\n#263 bridge  run 4dc30e72  base 0cccce4a")
r, b = gparse.load("4dc30e72"), gparse.load("0cccce4a")
for k in ("bridge_flow", "bridge_density", "thick_bridges", "bridge_angle", "max_bridge_length", "bridge_line_width", "bridge_speed",
          "enable_support", "support_type", "internal_bridge_flow", "thick_internal_bridges", "bridge_acceleration"):
    P("  config %-24s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    f = an.feat(g, "Bridge")
    ids = [i for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f]
    L = sum(an.seg_len(S, i) for i in ids)
    E = sum(S["e"][i] for i in ids)
    ang = collections.Counter()
    for i in ids:
        a = int(round((math.degrees(math.atan2(S["y1"][i] - S["y0"][i], S["x1"][i] - S["x0"][i])) % 180.0)))
        ang["%d" % (5 * int(round(a / 5.0)) % 180)] += an.seg_len(S, i)
    tot = sum(ang.values())
    lens = sorted(an.seg_len(S, i) for i in ids)
    lays = sorted(set(S["L"][i] for i in ids))
    P("  [%s] Bridge: blocks %d on %d layers %s; moves %d; len %.1f; E %.1f; E/mm %.5f; direction (by length) %s" % (
        tag, g["types"].get("Bridge", 0), len(lays), lays, len(ids), L, E, E / L, " ".join("%s:%.0f%%" % (a, 100.0 * n / tot) for a, n in ang.most_common(4))))
    P("       move lengths: median %.3f max %.3f; longest %s" % (lens[len(lens) // 2], lens[-1], [round(x, 1) for x in lens[-5:]]))
    # spacing on a bridge layer
    for lay in lays[:3] + lays[-2:]:
        sp, nseg = spacing(g, lay, "Bridge", 1.0)
        P("       layer %d: %d bridge moves, %d long segments, spacing median %.3f min %.3f max %.3f (n=%d)" % (
            lay, sum(1 for i in ids if S["L"][i] == lay), nseg, float(np.median(sp)) if sp else float("nan"), min(sp) if sp else float("nan"),
            max(sp) if sp else float("nan"), len(sp)))
    for name in ("Overhang wall", "Internal Bridge"):
        P("       %s E/mm %.5f moves %d" % (name, epmm(g, name)[0], epmm(g, name)[3]))
    P("       Support types present: %s" % [t for t in g["types"] if "Support" in t])

# ---------------------------------------------------------------- #281
P("=" * 90, "\n#281 support interface  run 99f34ea9  base 0cccce4a")
r, b = gparse.load("99f34ea9"), gparse.load("0cccce4a")
for k in ("support_top_z_distance", "support_bottom_z_distance", "support_object_xy_distance", "support_interface_top_layers",
          "support_interface_bottom_layers", "support_interface_spacing", "support_interface_pattern", "support_line_width",
          "support_interface_speed", "enable_support", "support_type", "support_interface_not_for_body", "support_base_pattern",
          "support_pattern", "support_spacing", "support_object_first_layer_gap"):
    P("  config %-30s run %s | base %s" % (k, an.config(r, k), an.config(b, k)))
S = r["S"]
fi = an.feat(r, "Support interface")
fs = an.feat(r, "Support")
lay_i = collections.Counter(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi)
lay_s = collections.Counter(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fs)
lans = sorted(lay_i)
P("  Support interface on %d layers: %s .. %s" % (len(lans), lans[0], lans[-1]))
P("  Support on %d layers: %d .. %d" % (len(lay_s), min(lay_s), max(lay_s)))
# interface spacing on a few layers
sps = []
for lay in lans[::max(1, len(lans) // 12)]:
    sp, nseg = spacing(r, lay, "Support interface", 0.8)
    if sp:
        sps.append((lay, nseg, float(np.median(sp)), min(sp), max(sp)))
P("  interface line spacing per sampled layer (layer, long segs, median, min, max): %s" % [(a, b_, round(c, 3), round(d, 3), round(e, 3)) for a, b_, c, d, e in sps])
seg = sorted(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == fi)
P("  interface move lengths: median %.3f p90 %.3f max %.3f; E/mm %.5f" % (seg[len(seg) // 2], seg[int(len(seg) * .9)], seg[-1], epmm(r, "Support interface")[0]))
# consecutive-interface-layer runs = interface layers at the top of each support column
runs = []
cur = 0
for L in range(1, len(r["layers"]) + 1):
    if lay_i.get(L):
        cur += 1
    elif cur:
        runs.append(cur)
        cur = 0
if cur:
    runs.append(cur)
P("  runs of consecutive layers with interface: %s (count per run length: %s)" % (
    runs[:40], dict(collections.Counter(runs))))
# Z gap: top interface layer Z vs first model layer above it (model = anything not Support / Support interface)
model_lay = collections.defaultdict(float)
for L, info in enumerate(r["layers"], 1):
    pass
mod = set()
for i in range(len(S["k"])):
    if S["k"][i] == an.X and S["F"][i] not in (fi, fs):
        mod.add(S["L"][i])
# per column approximated per layer: for each layer with interface but no interface above, the next model layer
gaps = collections.Counter()
for n in runs:
    pass
tops = [L for L in lans if (L + 1) not in lay_i]
for L in tops:
    m = min((m for m in mod if m > L), default=None)
    if m:
        zi = r["layers"][L - 1]["z"]
        hm = r["layers"][m - 1]["height"]
        zm = r["layers"][m - 1]["z"]
        gaps["%.2f" % (zm - hm - zi)] += 1
P("  vertical gap between top interface layer and the first model layer above (per top-interface layer): %s" % dict(gaps))
# XY distance support (interface+body) to model walls on the same layer
mins = []
detail = []
for L in lans[::max(1, len(lans) // 25)]:
    sup = an.segs_of(r, L, ["Support", "Support interface"])
    wal = an.segs_of(r, L, ["Outer wall", "Overhang wall"])
    if len(sup) and len(wal):
        d = an.seg_seg_min_dist(sup, wal)
        mins.append(d)
        detail.append((L, round(d, 3)))
P("  min XY distance support <-> outer wall centreline per sampled layer: min %.3f median %.3f max %.3f; %s" % (
    min(mins), float(np.median(mins)), max(mins), detail[:12]))
out.close()
