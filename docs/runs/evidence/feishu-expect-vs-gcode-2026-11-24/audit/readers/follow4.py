"""Follow-up checks 4: 269 sparse infill per layer, 274 accel by next move, 275 event diff, 285 extra M104,
257 mesh cross-section at layer heights, 282 new-branch line lengths, 266 open wall chains.

    python -B follow4.py
"""
import collections
import math
import os
import re
import sys
import zipfile

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import an  # noqa: E402
import gparse  # noqa: E402


def feat_layers(g, name):
    S = g["S"]
    f = an.feat(g, name)
    return sorted(set(S["L"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["F"][i] == f))


print("#269 sparse infill per layer")
r, b = gparse.load("3c6a8dc5"), gparse.load("0cccce4a")
lay_r, lay_b = feat_layers(r, "Sparse infill"), feat_layers(b, "Sparse infill")
print("  layers with sparse infill: run %d base %d (of %d)" % (len(lay_r), len(lay_b), len(r["layers"])))
for tag, g in (("run", r), ("base", b)):
    S = g["S"]
    f = an.feat(g, "Sparse infill")
    per = collections.Counter()
    em = collections.defaultdict(float)
    ee = collections.defaultdict(float)
    for i in range(len(S["k"])):
        if S["k"][i] == an.X and S["F"][i] == f:
            per[S["L"][i]] += an.seg_len(S, i)
            ee[S["L"][i]] += S["e"][i]
    L0 = min(per)
    print("  [%s] per-layer sparse-infill length for layers %d..%d+14: %s" % (tag, L0, L0, [int(per.get(L, 0)) for L in range(L0, L0 + 15)]))
    print("       E/mm per layer: %s" % [round(ee[L] / per[L], 4) if per.get(L) else 0 for L in range(L0, L0 + 15)])
    both = [L for L in per if per[L] > 0]
    print("       layers with infill %d; mean length on layers with infill %.0f; empty layers between %d..%d: %d of %d" % (
        len(both), sum(per[L] for L in both) / len(both), both[0], both[-1], (both[-1] - both[0] + 1) - len(both), both[-1] - both[0] + 1))
for name in ("Internal Bridge", "Bridge", "Gap infill", "Internal solid infill"):
    print("  %-20s layers run %d base %d ; blocks run %d base %d" % (name, len(feat_layers(r, name)), len(feat_layers(b, name)), r["types"].get(name, 0), b["types"].get(name, 0)))

print("\n#274 acceleration by the move that follows it")
r, b = gparse.load("0b0d9c99"), gparse.load("5994d5e6")
for tag, g in (("run", r), ("base", b)):
    acc = collections.defaultdict(collections.Counter)
    cur = "Custom"
    last = None
    with open(g["path"], encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            if raw.startswith(";TYPE:"):
                cur = raw[6:].strip()
                continue
            if raw.startswith("SET_VELOCITY_LIMIT"):
                m = re.search(r"ACCEL=([0-9.]+)", raw)
                if m:
                    last = "%g" % float(m.group(1))
                continue
            if raw[:3] in ("G0 ", "G1 ", "G2 ", "G3 "):
                if "X" not in raw and "Y" not in raw:
                    continue
                if last is None:
                    continue
                acc["travel" if ("E" not in raw) else cur][last] += 1
                last = None
    print("  [%s] %s" % (tag, " | ".join("%s: %s" % (k, " ".join("%s x%d" % kv for kv in sorted(v.items(), key=lambda kv: -kv[1])[:3]))
                                         for k, v in acc.items())))

print("\n#275 event difference")
r, b = gparse.load("9f47af1f"), gparse.load("818ecfc6")
cr = collections.Counter(e[3] for e in r["events"])
cb = collections.Counter(e[3] for e in b["events"])
print("  command lines only (or more) in run: %s" % dict((cr - cb).most_common(6)))
print("  command lines only (or more) in base: %s" % dict((cb - cr).most_common(6)))
seq_r = [e[3] for e in r["events"]]
seq_b = [e[3] for e in b["events"]]
print("  SET_VELOCITY_LIMIT lines run %d base %d; distinct: run %s base %s" % (
    sum(v for k, v in cr.items() if k.startswith("SET_VELOCITY")), sum(v for k, v in cb.items() if k.startswith("SET_VELOCITY")),
    sorted(set(k for k in cr if k.startswith("SET_VELOCITY")))[:6], sorted(set(k for k in cb if k.startswith("SET_VELOCITY")))[:6]))
print("  motion coordinates/feeds identical: %s" % all(r["S"][k] == b["S"][k] for k in r["S"] if k != "ln"))

print("\n#285 extra M104")
r, b = gparse.load("46fcf33b"), gparse.load("02793334")
er = [(e[0], e[3]) for e in r["events"] if e[3].startswith("M104 S220 T0")]
print("  'M104 S220 T0' in run at (layer, z?) %s ; index among events %s" % (er[:4], [k for k, e in enumerate(r["events"]) if e[3] == "M104 S220 T0"][:4]))
idx = [k for k, e in enumerate(r["events"]) if e[3] == "M104 S220 T0"][0]
print("  neighbours: %s" % [e[3][:40] for e in r["events"][idx - 3: idx + 3]])
eb = [(e[0], e[3]) for e in b["events"] if e[3].startswith(("M109 S220", "M104 S220"))]
print("  base: %s" % eb)

print("\n#257 mesh cross-section bbox at layer mid-heights")
d = gparse.run_dir("3f239cab")
z = zipfile.ZipFile(os.path.join(d, "input", "fixture.3mf"))
xml = z.read("3D/Objects/OrcaToleranceTest_1.model").decode("utf-8", errors="replace")
vs = re.findall(r"<vertex\s+([^>]*)/?>", xml)
V = np.array([[float(re.search(r'\b%s="([-0-9.eE]+)"' % a, v).group(1)) for a in "xyz"] for v in vs])
ts = re.findall(r"<triangle\s+([^>]*)/?>", xml)
T = np.array([[int(re.search(r'\b%s="(\d+)"' % a, t).group(1)) for a in ("v1", "v2", "v3")] for t in ts])
tr = re.findall(r"<build>.*?</build>", xml, re.S)
print("  mesh: %d vertices %d triangles; bbox x %.3f..%.3f y %.3f..%.3f z %.3f..%.3f ; build item transform: %s" % (
    len(V), len(T), V[:, 0].min(), V[:, 0].max(), V[:, 1].min(), V[:, 1].max(), V[:, 2].min(), V[:, 2].max(),
    re.findall(r'transform="([^"]+)"', xml)[:1]))
P = V[T]
for zc in (0.125, 0.35, 0.55, 1.05):
    pts = []
    for tri in P:
        zz = tri[:, 2]
        if zz.min() - 1e-9 <= zc <= zz.max() + 1e-9 and (zz.max() - zz.min()) > 1e-9:
            for a, bb in ((0, 1), (1, 2), (2, 0)):
                if (zz[a] - zc) * (zz[bb] - zc) < 0:
                    t = (zc - zz[a]) / (zz[bb] - zz[a])
                    pts.append(tri[a, :2] + t * (tri[bb, :2] - tri[a, :2]))
    pts = np.array(pts)
    if len(pts):
        print("  section at z=%.3f: %d edge crossings; bbox x %.3f..%.3f y %.3f..%.3f" % (zc, len(pts), pts[:, 0].min(), pts[:, 0].max(), pts[:, 1].min(), pts[:, 1].max()))
    else:
        print("  section at z=%.3f: no triangle edges cross (flat top/bottom at this height?)" % zc)
print("  vertices with z==0: %d ; with 0<z<6.4: %d ; z==6.4: %d" % (int((V[:, 2] <= 1e-9).sum()), int(((V[:, 2] > 1e-9) & (V[:, 2] < 6.4 - 1e-9)).sum()), int((V[:, 2] >= 6.4 - 1e-9).sum())))
for tag, g in (("run", r), ("base", b)):
    pass
g = gparse.load("0d6777e0")
S = g["S"]
f = an.feat(g, "Outer wall")
for L in (1, 2):
    xs = [S["x0"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f] + [S["x1"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f]
    ys = [S["y0"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f] + [S["y1"][i] for i in range(len(S["k"])) if S["k"][i] == an.X and S["L"][i] == L and S["F"][i] == f]
    print("  baseline outer-wall centreline bbox layer %d: x %.3f..%.3f y %.3f..%.3f" % (L, min(xs), max(xs), min(ys), max(ys)))

print("\n#282 new-branch line lengths (tree support)")
r = gparse.load("c4eb7a29")
S = r["S"]
fs, fi = an.feat(r, "Support"), an.feat(r, "Support interface")
tip = []
for L in range(3, 500, 2):
    seg = an.segs_of(r, L, ["Support"])
    below = an.segs_of(r, L - 1, ["Support", "Support interface"])
    if len(seg) == 0 or len(below) == 0:
        continue
    mids = (seg[:, :2] + seg[:, 2:]) / 2.0
    dd = an.point_seg_dist(mids, below)
    new = seg[dd > 0.6]
    for row in new:
        tip.append(math.hypot(row[2] - row[0], row[3] - row[1]))
tip = np.array(tip)
print("  support lines starting a new branch (no support within 0.6 mm below): n=%d; length median %.2f p10 %.2f p90 %.2f max %.2f" % (
    len(tip), float(np.median(tip)), float(np.percentile(tip, 10)), float(np.percentile(tip, 90)), tip.max()) if len(tip) else "  none")
for L, info in enumerate(r["layers"], 1):
    if abs((info["height"] or 0) - 0.4) < 1e-6 or abs((info["height"] or 0) - 0.25) > 1e-6 and abs((info["height"] or 0) - 0.2) > 1e-6 and L > 1:
        print("  layer %d has z %s height %s" % (L, info["z"], info["height"]))
b = gparse.load("bfada110")
print("  baseline layer heights: %s ; last z %s | run last z %s" % (dict(collections.Counter("%.3g" % (l["height"] or 0) for l in b["layers"])), b["layers"][-1]["z"], r["layers"][-1]["z"]))

print("\n#266 open wall chains (run 1ffdefee)")
r = gparse.load("1ffdefee")
S = r["S"]
shown = 0
for L in range(2, len(r["layers"]) + 1):
    for name in ("Outer wall", "Inner wall"):
        for ch in an.chains(r, L, name):
            ln = an.chain_len(r, ch)
            gap = math.hypot(S["x1"][ch[-1]] - S["x0"][ch[0]], S["y1"][ch[-1]] - S["y0"][ch[0]])
            if ln > 2.0 and gap > 0.5 and shown < 6:
                i = ch[-1]
                nxt = ch[-1] + 1
                print("  L%d %s len %.1f gap %.2f ; end (%.2f,%.2f) ; after it: k%d (%.2f,%.2f)->(%.2f,%.2f) E%.4f F%.0f ; then k%d" % (
                    L, name, ln, gap, S["x1"][i], S["y1"][i], S["k"][nxt], S["x0"][nxt] or 0, S["y0"][nxt] or 0, S["x1"][nxt] or 0, S["y1"][nxt] or 0,
                    S["e"][nxt], S["fd"][nxt], S["k"][nxt + 1]))
                shown += 1
    if shown >= 6:
        break
