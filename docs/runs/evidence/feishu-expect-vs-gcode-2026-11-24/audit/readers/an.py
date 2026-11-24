"""Analysis helpers for the audit (scratch only)."""
import collections
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gparse  # noqa: E402

X, T, EONLY = gparse.EXTRUDE, gparse.TRAVEL, gparse.EONLY
WIPERET = gparse.WIPERET
TRAVEL, EXTRUDE, ZONLY, FONLY = gparse.TRAVEL, gparse.EXTRUDE, gparse.ZONLY, gparse.FONLY


def feat(g, name):
    return g["feat_names"].index(name) if name in g["feat_names"] else None


def idx(g):
    """{(layer, feat): [move indices in file order]} (cached on the dict)."""
    if "_idx" not in g:
        d = collections.defaultdict(list)
        S = g["S"]
        for i in range(len(S["k"])):
            d[(S["L"][i], S["F"][i])].append(i)
        g["_idx"] = d
    return g["_idx"]


def seg_len(S, i):
    return math.hypot(S["x1"][i] - S["x0"][i], S["y1"][i] - S["y0"][i])


def chains(g, layer, name, with_feed=False):
    """Extruding moves of one feature on one layer split into polylines: a new
    polyline starts where the previous extruding move did not end. Returns a list
    of lists of move indices."""
    S = g["S"]
    f = feat(g, name)
    out, cur = [], []
    last = None
    for i in idx(g).get((layer, f), []):
        if S["k"][i] != X:
            continue
        if last is None or abs(S["x0"][i] - last[0]) > 2e-3 or abs(S["y0"][i] - last[1]) > 2e-3:
            if cur:
                out.append(cur)
            cur = []
        cur.append(i)
        last = (S["x1"][i], S["y1"][i])
    if cur:
        out.append(cur)
    return out


def chain_len(g, ch):
    return sum(seg_len(g["S"], i) for i in ch)


def chain_closed(g, ch, tol=0.05):
    S = g["S"]
    a, b = ch[0], ch[-1]
    return math.hypot(S["x1"][b] - S["x0"][a], S["y1"][b] - S["y0"][a]) <= tol


def pts(g, ch):
    S = g["S"]
    p = [(S["x0"][i], S["y0"][i]) for i in ch]
    p.append((S["x1"][ch[-1]], S["y1"][ch[-1]]))
    return p


def segs_of(g, layer, names):
    """numpy segments (M,4) of the extruding moves of `names` (list) on `layer`."""
    S = g["S"]
    rows = []
    for name in names:
        f = feat(g, name)
        if f is None:
            continue
        for i in idx(g).get((layer, f), []):
            if S["k"][i] == X:
                rows.append((S["x0"][i], S["y0"][i], S["x1"][i], S["y1"][i]))
    return np.array(rows, dtype=float) if rows else np.zeros((0, 4))


def point_seg_dist(P, S4):
    """P (N,2) points, S4 (M,4) segments -> (N,) min distance from each point to any segment."""
    if len(S4) == 0 or len(P) == 0:
        return np.full(len(P), np.inf)
    A = S4[:, :2]
    B = S4[:, 2:]
    AB = B - A
    L2 = (AB ** 2).sum(axis=1)
    L2[L2 == 0] = 1e-12
    out = np.empty(len(P))
    chunk = 400
    for s in range(0, len(P), chunk):
        p = P[s:s + chunk]
        ap = p[:, None, :] - A[None, :, :]
        t = np.clip((ap * AB[None, :, :]).sum(axis=2) / L2[None, :], 0.0, 1.0)
        proj = A[None, :, :] + t[:, :, None] * AB[None, :, :]
        d = np.sqrt(((p[:, None, :] - proj) ** 2).sum(axis=2))
        out[s:s + chunk] = d.min(axis=1)
    return out


def seg_seg_min_dist(Sa, Sb):
    """min distance between two segment sets (no crossing assumed; uses endpoint-to-segment)."""
    if len(Sa) == 0 or len(Sb) == 0:
        return float("inf")
    ends = np.vstack([Sa[:, :2], Sa[:, 2:]])
    d1 = point_seg_dist(ends, Sb).min()
    ends_b = np.vstack([Sb[:, :2], Sb[:, 2:]])
    d2 = point_seg_dist(ends_b, Sa).min()
    return float(min(d1, d2))


def spacing_parallel(S4, tol=0.02):
    """Line spacing of a set of (mostly parallel) straight extrusion segments:
    for each segment, the perpendicular distance from its midpoint to the nearest
    other, non-collinear segment that is long enough. Returns list of distances."""
    if len(S4) < 2:
        return []
    A = S4[:, :2]
    B = S4[:, 2:]
    mid = (A + B) / 2.0
    d = B - A
    L = np.hypot(d[:, 0], d[:, 1])
    keep = L > 0.6
    if keep.sum() < 2:
        return []
    A, B, mid, d, L = A[keep], B[keep], mid[keep], d[keep], L[keep]
    u = d / L[:, None]
    out = []
    for i in range(len(mid)):
        # vector from i's midpoint to others' midpoints
        v = mid - mid[i]
        proj = np.abs(v[:, 0] * u[i, 0] + v[:, 1] * u[i, 1])           # along i
        perp = np.abs(-v[:, 0] * u[i, 1] + v[:, 1] * u[i, 0])          # across i
        cross = np.abs(u[:, 0] * u[i, 1] - u[:, 1] * u[i, 0])          # sin of angle
        ok = (perp > 0.01) & (proj < min(L[i], 0.9 * 1e9) * 0.75 + 0.0) & (cross < 0.25)
        if ok.any():
            out.append(float(perp[ok].min()))
    return out


def feed_hist(g, name, layers=None, top=40):
    S = g["S"]
    f = feat(g, name)
    c = collections.Counter()
    c_len = collections.Counter()
    for i in idx(g).get(None, []) if False else []:
        pass
    for (layer, ff), ids in idx(g).items():
        if ff != f:
            continue
        if layers is not None and layer not in layers:
            continue
        for i in ids:
            if S["k"][i] == X and S["L"][i] >= 1:
                c["%.1f" % S["fd"][i]] += 1
                c_len["%.1f" % S["fd"][i]] += seg_len(S, i)
    return c, c_len


def travel_hist(g, band):
    S = g["S"]
    c = collections.Counter()
    for i in range(len(S["k"])):
        if S["k"][i] == T:
            if (band == "first" and S["L"][i] == 1) or (band == "other" and S["L"][i] > 1):
                c["%.1f" % S["fd"][i]] += 1
    return c


def config(g, key, default=None):
    return g["config"].get(key, default)


def layers_z(g):
    return [(l["n"], l["z"], l["height"]) for l in g["layers"]]


def layer_feats(g, n):
    l = g["layers"][n - 1]
    return [(g["feat_names"][f], z["z"]) for f in l["feats"]], l["z"], l["height"]
