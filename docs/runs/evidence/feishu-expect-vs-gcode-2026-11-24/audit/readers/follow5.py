"""Tower / skirt / brim / labels / jerk mapping / wall closure / NON_GREEN reasons.

    python -B follow5.py <out.txt>
"""
import collections
import io
import json
import math
import os
import re
import sys

import numpy as np
from shapely.geometry import Polygon, Point

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402

out = io.open(sys.argv[1], "w", encoding="utf-8")


def P(*a):
    out.write(" ".join(str(x) for x in a) + "\n")


def cfg(g, keys, b=None):
    for k in keys:
        P("  config %-30s %s | base %s" % (k, (an.config(g, k) or "")[:70], (an.config(b, k) or "")[:40] if b else ""))


def bbox(segs):
    if len(segs) == 0:
        return None
    return (min(segs[:, 0].min(), segs[:, 2].min()), max(segs[:, 0].max(), segs[:, 2].max()),
            min(segs[:, 1].min(), segs[:, 3].min()), max(segs[:, 1].max(), segs[:, 3].max()))


def comment_count(path):
    """comment lines after the first ;TYPE: (i.e. inside the printed part of the file)."""
    n = 0
    started = False
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if not started:
                if raw.startswith(";TYPE:") or raw.startswith("; EXECUTABLE_BLOCK_START"):
                    started = True
                continue
            if raw.startswith("; EXECUTABLE_BLOCK_END"):
                break
            if raw[0] == ";" and not raw.startswith((";TYPE:", ";LAYER_CHANGE", ";Z:", ";HEIGHT:", ";WIDTH:", ";WIPE_START", ";WIPE_END")):
                n += 1
    return n


# ---------------------------------------------------------------- #275 jerk mapping
P("=" * 80, "\n#275 jerk: SET_VELOCITY_LIMIT SQUARE_CORNER_VELOCITY by the move that follows it  run 9f47af1f")
r = gparse.load("9f47af1f")
sq = collections.defaultdict(collections.Counter)
cur = "Custom"
last = None
with open(r["path"], encoding="utf-8", errors="replace") as fh:
    lay = 0
    for raw in fh:
        if raw.startswith(";LAYER_CHANGE"):
            lay += 1
        elif raw.startswith(";TYPE:"):
            cur = raw[6:].strip()
        elif raw.startswith("SET_VELOCITY_LIMIT"):
            m = re.search(r"SQUARE_CORNER_VELOCITY=([0-9.]+)", raw)
            if m:
                last = "%g" % float(m.group(1))
            continue
        if raw[:3] in ("G0 ", "G1 ", "G2 ", "G3 "):
            if "X" not in raw and "Y" not in raw:
                continue
            if last is None:
                continue
            key = ("L1 " if lay <= 1 else "") + ("travel" if ("E" not in raw) else cur)
            sq[key][last] += 1
            last = None
for k, v in sq.items():
    P("  %-26s SQUARE_CORNER_VELOCITY x lines: %s" % (k, " ".join("%s x%d" % kv for kv in sorted(v.items(), key=lambda kv: -kv[1]))))
for k in ("default_jerk", "initial_layer_jerk", "outer_wall_jerk", "inner_wall_jerk", "infill_jerk", "travel_jerk", "top_surface_jerk", "solid_infill_jerk",
          "gap_fill_jerk", "bridge_jerk"):
    P("  config %-24s run %s | base %s" % (k, an.config(r, k), an.config(gparse.load("818ecfc6"), k)))

# ---------------------------------------------------------------- #266 wall closure across types
P("=" * 80, "\n#266 wall closure when overhang parts are counted as part of the wall")
r, b = gparse.load("1ffdefee"), gparse.load("5994d5e6")


def chains_multi(g, L, names):
    S = g["S"]
    fs = set(an.feat(g, n) for n in names if an.feat(g, n) is not None)
    ids = sorted(i for i in range(len(S["k"])) if S["L"][i] == L and S["F"][i] in fs and S["k"][i] == an.X)
    out, cur, last = [], [], None
    for i in ids:
        if last is None or abs(S["x0"][i] - last[0]) > 2e-3 or abs(S["y0"][i] - last[1]) > 2e-3:
            if cur:
                out.append(cur)
            cur = []
        cur.append(i)
        last = (S["x1"][i], S["y1"][i])
    if cur:
        out.append(cur)
    return out


for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    cl = op = 0
    gaps = []
    for L in range(2, len(g["layers"]) + 1):
        for ch in chains_multi(g, L, ("Outer wall", "Overhang wall")):
            ln = sum(an.seg_len(S, i) for i in ch)
            if ln < 3.0:
                continue
            gap = math.hypot(S["x1"][ch[-1]] - S["x0"][ch[0]], S["y1"][ch[-1]] - S["y0"][ch[0]])
            if gap <= 0.12:
                cl += 1
            else:
                op += 1
                gaps.append(round(gap, 2))
    gaps.sort()
    P("  [%s] outer-wall chains (with overhang parts), layers>=2: closed %d, open %d; open gaps: %s" % (tag, cl, op, gaps[:10] + (["..."] if len(gaps) > 10 else [])))

# ---------------------------------------------------------------- tower rows 283 / 286
for row, rp in ((283, "9bc92f73"), (286, "9dbad28b")):
    P("=" * 80, "\n#%d  run %s  base 0c80c4a0" % (row, rp))
    r, b = gparse.load(rp), gparse.load("0c80c4a0")
    cfg(r, ["enable_prime_tower", "prime_tower_width", "prime_volume", "prime_tower_brim_width", "wipe_tower_wall_type", "wipe_tower_no_sparse_layers",
            "wipe_tower_cone_angle", "wipe_tower_filament", "flush_into_infill", "flush_into_objects", "flush_into_support", "flush_multiplier",
            "flush_volumes_matrix", "wiping_volumes_extruders", "wipe_tower_x", "wipe_tower_y", "wipe_tower_bridging", "wipe_tower_rib_width",
            "wipe_tower_wall_gap", "enable_support", "wipe_tower_retain"], b)
    for tag, g in (("run", r), ("base", b)):
        S = g["S"]
        ft = an.feat(g, "Prime tower")
        print_ = []
        for L in (2, 61, 121, 181, 240):
            seg = an.segs_of(g, L, ["Prime tower"])
            bb = bbox(seg)
            tot = sum(S["e"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == ft)
            len_ = sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == ft)
            print_.append((L, "w %.2f h %.2f" % (bb[1] - bb[0], bb[3] - bb[2]) if bb else "-", "len %.0f E %.1f" % (len_, tot)))
        P("  [%s] tower per layer (layer, extent, length/E): %s" % (tag, print_))
        b1 = bbox(an.segs_of(g, 1, ["Prime tower"]))
        br = an.segs_of(g, 1, ["Brim"])
        bb_b = bbox(br)
        tow1 = an.segs_of(g, 1, ["Prime tower"])
        allb1 = bbox(np.vstack([tow1, br])) if len(br) else b1
        P("       layer 1: tower bbox %s ; Brim block bbox %s ; brim moves %d" % (
            tuple(round(x, 2) for x in b1) if b1 else None, tuple(round(x, 2) for x in bb_b) if bb_b else None, len(br)))
        # tower E between tool changes
        seq = []
        cur_tool = None
        acc = collections.defaultdict(float)
        cnt = collections.defaultdict(int)
        order = []
        for i in range(len(S["k"])):
            t = S["T"][i]
            if t != cur_tool:
                if cur_tool is not None:
                    seq.append((cur_tool, t, round(acc[cur_tool], 2), round(acc.get(-1, 0), 2)))
                cur_tool = t
            if S["k"][i] == an.X and S["F"][i] == ft:
                acc[cur_tool] += S["e"][i]
        P("       tower E summed by the tool that extruded it (mm of filament): %s" % {k: round(v, 1) for k, v in acc.items() if k != -1})
        # per tool-change tower usage: walk through and split at T changes
        segs = []
        acc = 0.0
        t0 = S["T"][0]
        for i in range(len(S["k"])):
            if S["T"][i] != t0 and S["k"][i] == an.X and S["F"][i] == ft:
                pass
        tools = [(i, S["T"][i]) for i in range(0, len(S["k"])) if S["T"][i] is not None and (i == 0 or S["T"][i] != S["T"][i - 1])]
        P("       tool changes: %d; order of tools over time (first 9): %s" % (len(tools), [t for _, t in tools[:9]]))
        # tower E in each tool's segment
        seg_e = collections.Counter()
        seg_n = collections.Counter()
        for a, (ib, tb) in enumerate(tools):
            ie = tools[a + 1][0] if a + 1 < len(tools) else len(S["k"])
            e = sum(S["e"][i] for i in range(ib, ie) if S["k"][i] == an.X and S["F"][i] == ft)
            seg_e[(S["T"][tools[a - 1][0]] if a else None, tb)] += e
            seg_n[(S["T"][tools[a - 1][0]] if a else None, tb)] += 1
        P("       tower E per tool-change segment (from, to) -> mean E per segment (mm, and mm3 at 2.405): %s" % {
            "%s->%s" % k: "%.2f mm = %.1f mm3 (n=%d)" % (v / seg_n[k], v / seg_n[k] * 2.40528, seg_n[k]) for k, v in seg_e.items()})
        # distance tower <-> model
        ds = []
        for L in (3, 50, 100, 150, 200, 239):
            t_ = an.segs_of(g, L, ["Prime tower"])
            m_ = an.segs_of(g, L, ["Outer wall", "Overhang wall", "Brim", "Skirt"])
            if len(t_) and len(m_):
                ds.append(round(an.seg_seg_min_dist(t_, m_), 2))
        P("       min distance tower <-> model walls per sampled layer: %s" % ds)
        P("       sparse-infill blocks/moves/length: %d / %d / %.0f ; internal solid infill moves %d" % (
            g["types"].get("Sparse infill", 0), sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(g, "Sparse infill")),
            sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(g, "Sparse infill")),
            sum(1 for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(g, "Internal solid infill"))))
        P("       tower feeds: %s" % dict(collections.Counter("%.0f" % S["fd"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == ft).most_common(3)))
    # model geometry equal
    def segset(g, name):
        S = g["S"]
        f = an.feat(g, name)
        c = collections.Counter()
        for i in range(len(S["k"])):
            if S["k"][i] == an.X and S["F"][i] == f:
                a = (round(S["x0"][i], 3), round(S["y0"][i], 3))
                bb = (round(S["x1"][i], 3), round(S["y1"][i], 3))
                c[(S["L"][i],) + min(a, bb) + max(a, bb)] += 1
        return c
    P("  model geometry run vs base (segments only in run / only in base): %s" % {
        n: "%d/%d" % (sum((segset(r, n) - segset(b, n)).values()), sum((segset(b, n) - segset(r, n)).values()))
        for n in ("Outer wall", "Inner wall", "Sparse infill", "Internal solid infill", "Top surface", "Bottom surface")})

# ---------------------------------------------------------------- #290 skirt
P("=" * 80, "\n#290 skirt / draft shield  run c2b32dd2  base 5994d5e6")
r, b = gparse.load("c2b32dd2"), gparse.load("5994d5e6")
cfg(r, ["skirt_loops", "skirt_height", "skirt_distance", "draft_shield", "skirt_speed", "brim_type", "brim_width"], b)
S = r["S"]
f = an.feat(r, "Skirt")
lays = sorted(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f))
P("  Skirt on layers %d..%d (%d layers of %d); skirt speed %s mm/min" % (
    lays[0], lays[-1], len(lays), len(r["layers"]), sorted(set("%.0f" % S["fd"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f))[:3]))
for L in (1, 2, 3, 4, 5, 100, 239, 240):
    ch = an.chains(r, L, "Skirt")
    model = an.segs_of(r, L, ["Outer wall", "Overhang wall", "Brim"])
    if ch:
        lens = [round(an.chain_len(r, c), 1) for c in ch]
        closed = [an.chain_closed(r, c, 0.2) for c in ch]
        d = an.seg_seg_min_dist(an.segs_of(r, L, ["Skirt"]), model) if len(model) else float("nan")
        P("  layer %d: skirt loops %d (closed %s) lengths %s ; min distance skirt to model walls %.3f" % (L, len(ch), closed, lens, d))
P("  layers with skirt and without: first 3 layers %s ; top layers %s" % ([L in lays for L in (1, 2, 3)], [L in lays for L in (238, 239, 240)]))
def segset(g, name):
    S = g["S"]
    f = an.feat(g, name)
    c = collections.Counter()
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] == f:
            a = (round(S["x0"][i], 3), round(S["y0"][i], 3))
            bb = (round(S["x1"][i], 3), round(S["y1"][i], 3))
            c[(S["L"][i],) + min(a, bb) + max(a, bb)] += 1
    return c
P("  model paths run vs base: %s" % {n: "%d/%d" % (sum((segset(r, n) - segset(b, n)).values()), sum((segset(b, n) - segset(r, n)).values()))
                                   for n in ("Outer wall", "Inner wall", "Sparse infill", "Internal solid infill", "Top surface", "Bottom surface", "Brim")})

# ---------------------------------------------------------------- #291 brim
P("=" * 80, "\n#291 brim  run ae7fc220  base 5994d5e6")
r, b = gparse.load("ae7fc220"), gparse.load("5994d5e6")
cfg(r, ["brim_width", "brim_type", "brim_object_gap", "brim_ears_detection_radius", "brim_ears_max_angle", "brim_ears_detection_length"], b)
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    br = an.segs_of(g, 1, ["Brim"])
    ow = an.segs_of(g, 1, ["Outer wall"])
    bb_b, bb_o = bbox(br), bbox(ow)
    P("  [%s] layer 1: Brim moves %d, chains %d (closed %d), length %.0f; brim bbox %s ; outer-wall bbox %s" % (
        tag, len(br), len(an.chains(g, 1, "Brim")), sum(1 for c in an.chains(g, 1, "Brim") if an.chain_closed(g, c, 0.2)),
        sum(an.seg_len(S, i) for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == an.feat(g, "Brim")),
        tuple(round(x, 2) for x in bb_b), tuple(round(x, 2) for x in bb_o)))
    ends = np.vstack([br[:, :2], br[:, 2:]])
    d = an.point_seg_dist(ends, ow)
    uniq = sorted(set(np.round(d, 2).tolist()))
    pitch = [round(b - a, 2) for a, b2 in zip(uniq, uniq[1:]) for b in [b2]][:14]
    P("       brim line ends to the outer-wall centreline: min %.3f p5 %.3f median %.3f max %.3f ; successive distances %s" % (
        d.min(), float(np.percentile(d, 5)), float(np.median(d)), d.max(), uniq[:12]))
    P("       brim width per side (brim bbox - wall bbox)/2: x %.2f / %.2f, y %.2f / %.2f" % (
        bb_o[0] - bb_b[0], bb_b[1] - bb_o[1], bb_o[2] - bb_b[2], bb_b[3] - bb_o[3]))
    polys = []
    for c in an.chains(g, 1, "Outer wall"):
        if an.chain_len(g, c) >= 2.0 and an.chain_closed(g, c, 0.12):
            try:
                p = Polygon(an.pts(g, c))
                if p.is_valid and p.area > 0.5:
                    polys.append(p)
            except Exception:
                pass
    polys.sort(key=lambda p: -p.area)
    inside_small = 0
    inside_big = 0
    for q in ends[::5]:
        pt = Point(q)
        hits = [k for k, p in enumerate(polys) if p.contains(pt)]
        if hits:
            # inside a loop: if it is inside the largest loop and also outside all others -> it's inside the model footprint (not allowed)
            if 0 in hits and len(hits) == 1:
                inside_big += 1
            else:
                inside_small += 1
    P("       brim points inside the outer-wall footprint (inside the largest loop only): %d ; inside an inner loop only: %d ; of %d sampled" % (
        inside_big, inside_small, len(ends[::5])))

# ---------------------------------------------------------------- #296 / #297 labels
P("=" * 80, "\n#296 gcode output  run a3160612 | #297 exclude objects  run 24f867a0 | #273 run d15b8c66 | base cd540456")
rb = gparse.load("cd540456")
for row, rp in ((296, "a3160612"), (297, "24f867a0"), (273, "d15b8c66")):
    r = gparse.load(rp)
    P("  #%d run %s" % (row, rp))
    cfg(r, ["gcode_comments", "gcode_add_line_number", "gcode_label_objects", "exclude_object", "filename_format", "reduce_infill_retraction",
            "gcode_flavor", "gcode_filename_initial_placeholder" if False else "time_lapse_gcode", "timelapse_type"], rb)
    ev = [e[3] for e in r["events"]]
    P("     N-numbered lines: %d ; EXCLUDE_OBJECT lines: %d (%s) ; comment lines inside the executable block: run %d base %d" % (
        r["numbered"], sum(1 for e in ev if "EXCLUDE_OBJECT" in e), sorted(set(e.split(" ")[0] for e in ev if "EXCLUDE_OBJECT" in e)),
        comment_count(r["path"]), comment_count(rb["path"])))
    # motion lines comparison
    def motion(path):
        return [l.split(";", 1)[0].strip() for l in open(path, encoding="utf-8", errors="replace") if l.split(";", 1)[0].strip()]
    mr, mb = motion(r["path"]), motion(rb["path"])
    first = next((k for k, (x, y) in enumerate(zip(mr, mb)) if x != y), None)
    P("     non-comment lines run %d base %d, identical %s ; first difference at %s: %s | %s" % (
        len(mr), len(mb), mr == mb, first, (mr[first][:60] if first is not None else ""), (mb[first][:60] if first is not None else "")))
    d = gparse.run_dir(rp)
    names = sorted(os.listdir(d))
    P("     run dir: %s ; exports: %s ; projects: %s" % (names[:14], os.listdir(os.path.join(d, "exports")), os.listdir(os.path.join(d, "projects"))[:4]))
    for fn in ("contract.json", "manifest.json", "setup.json", "scope.json"):
        try:
            txt = open(os.path.join(d, fn), encoding="utf-8-sig").read()
        except OSError:
            continue
        hits = sorted(set(re.findall(r"[A-Za-z0-9_\-{}\\\[\]():.]+\.(?:gcode|3mf)", txt)))[:6]
        if hits:
            P("     file names in %s: %s" % (fn, hits))

# ---------------------------------------------------------------- #297 retracts per feature
P("-" * 80, "\n#297 retracts by feature  run 24f867a0  base cd540456")
r = gparse.load("24f867a0")
for tag, g in (("run", r), ("base", rb)):
    S = g["S"]
    c = collections.Counter()
    tot = collections.Counter()
    for i in range(len(S["k"])):
        if S["k"][i] == an.EONLY and S["e"][i] < 0:
            c[g["feat_names"][S["F"][i]] if S["F"][i] is not None else "-"] += 1
        if S["k"][i] == an.X:
            tot[g["feat_names"][S["F"][i]] if S["F"][i] is not None else "-"] += 1
    P("  [%s] retracts by feature: %s" % (tag, dict(c)))
    P("       retracts per 1000 extruding moves, sparse infill %.1f, walls %.1f" % (
        1000.0 * c.get("Sparse infill", 0) / max(tot.get("Sparse infill", 0), 1), 1000.0 * (c.get("Outer wall", 0) + c.get("Inner wall", 0)) / max(tot.get("Outer wall", 0) + tot.get("Inner wall", 0), 1)))

# ---------------------------------------------------------------- NON_GREEN reasons
P("=" * 80, "\nNON_GREEN rows: result.json")
for row, pref in ((254, "5be898f5"), (272, "94a82cda"), (279, "1f8a4309"), (284, "2866a2bb"), (287, "d391a92e"), (292, "875f6c33"), (294, "150834d4")):
    d = gparse.run_dir(pref)
    try:
        res = json.load(open(os.path.join(d, "result.json"), encoding="utf-8-sig"))
        wr = json.load(open(os.path.join(d, "native_worker.json"), encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        P("  #%d %s: cannot read (%s)" % (row, pref, e))
        continue
    biz = ((res.get("checks") or {}).get("business") or {})
    P("  #%d %s verdict %s status %s verified_pass %s | business: %s | worker error: %s" % (
        row, pref, res.get("release_verdict"), res.get("execution_status"), res.get("verified_pass"),
        (str(biz.get("status") or "") + " " + str(biz.get("detail") or ""))[:330].replace("\n", " "), (wr.get("error") or "")[:200]))
    P("       reasons: %s" % (json.dumps(res.get("reasons"), ensure_ascii=False)[:300]))
out.close()
