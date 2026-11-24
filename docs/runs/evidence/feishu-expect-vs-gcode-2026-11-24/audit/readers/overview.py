"""Per-row overview for the audit: config keys that changed baseline -> run, the
line-width summary comments, and a per-feature table (moves, length, E/mm on layers >= 2,
feeds) for both exports.

    python -B overview.py <out.txt> [prefix pairs: row=run:base ...]
"""
import collections
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gparse  # noqa: E402

# row -> (run prefix, baseline prefix)
PAIRS = {
    295: ("d3191da6", "71c5f8fc"), 255: ("cd9a4f6a", "e9aa6f88"), 259: ("fcfb01eb", "e9aa6f88"),
    267: ("728e77c7", "e9aa6f88"), 268: ("d08d1fe8", "e9aa6f88"), 270: ("c45355d9", "e9aa6f88"),
    276: ("8902f8ae", "e9aa6f88"), 256: ("fd0abb31", "818ecfc6"), 275: ("9f47af1f", "818ecfc6"),
    293: ("4efcad2b", "818ecfc6"), 257: ("3f239cab", "0d6777e0"), 258: ("dc0f42c3", "0d6777e0"),
    260: ("433b83c4", "78f01bb0"), 261: ("bdf3dd93", "5994d5e6"), 262: ("2779be8f", "5994d5e6"),
    266: ("1ffdefee", "5994d5e6"), 271: ("301dcb07", "5994d5e6"), 274: ("0b0d9c99", "5994d5e6"),
    278: ("0c5eda6b", "5994d5e6"), 290: ("c2b32dd2", "5994d5e6"), 291: ("ae7fc220", "5994d5e6"),
    263: ("4dc30e72", "0cccce4a"), 264: ("cb8d8859", "0cccce4a"), 265: ("4b8da518", "0cccce4a"),
    269: ("3c6a8dc5", "0cccce4a"), 277: ("06c69298", "0cccce4a"), 280: ("f366c4c9", "0cccce4a"),
    281: ("99f34ea9", "0cccce4a"), 273: ("d15b8c66", "cd540456"), 296: ("a3160612", "cd540456"),
    297: ("24f867a0", "cd540456"), 282: ("c4eb7a29", "bfada110"), 283: ("9bc92f73", "0c80c4a0"),
    286: ("9dbad28b", "0c80c4a0"), 285: ("46fcf33b", "02793334"),
    # not SHADOW but with a G-code
    272: ("94a82cda", "0cccce4a"), 294: ("150834d4", "5994d5e6"),
}


def num(v):
    return "%.6g" % v if isinstance(v, float) else str(v)


def feature_table(g):
    S = g["S"]
    per = collections.OrderedDict()
    for i, k in enumerate(S["k"]):
        f = S["F"][i]
        if f is None or S["L"][i] == 0:
            continue
        d = per.setdefault(f, {"blocks": 0, "moves": 0, "len": 0.0, "e": 0.0, "len1": 0.0, "e1": 0.0,
                               "m1": 0, "feeds": collections.Counter(), "feeds1": collections.Counter(),
                               "ret": 0, "prime": 0, "trav": collections.Counter(), "arc": 0,
                               "layers": set(), "tools": collections.Counter(), "widths": collections.Counter()})
        if k == gparse.EXTRUDE:
            import math
            d["moves"] += 1
            d["arc"] += S["arc"][i]
            if S["arc"][i]:
                # chord length as a lower bound of the arc
                L = math.hypot(S["x1"][i] - S["x0"][i], S["y1"][i] - S["y0"][i])
            else:
                L = math.hypot(S["x1"][i] - S["x0"][i], S["y1"][i] - S["y0"][i])
            if S["L"][i] == 1:
                d["len1"] += L; d["e1"] += S["e"][i]; d["m1"] += 1
                d["feeds1"][num(S["fd"][i])] += 1
            else:
                d["len"] += L; d["e"] += S["e"][i]
                d["feeds"][num(S["fd"][i])] += 1
            d["layers"].add(S["L"][i])
            d["tools"][S["T"][i]] += 1
            d["widths"][num(S["w"][i]) if S["w"][i] else "nom"] += 1
        elif k == gparse.EONLY:
            if S["e"][i] > 0:
                d["prime"] += 1
            else:
                d["ret"] += 1
        elif k == gparse.TRAVEL:
            d["trav"][num(S["fd"][i])] += 1
    for b in g["blocks"]:
        if b[1] in per:
            per[b[1]]["blocks"] += 1
    return per


def show(out, label, g):
    out.write("  [%s] run %s  lines %d  moves %d  layers %d  numbered %d\n" % (
        label, g["run"][:8], g["nlines"], len(g["S"]["k"]), len(g["layers"]), g["numbered"]))
    out.write("     summary: %s\n" % " | ".join(s[2:] for s in g["summary"]))
    per = feature_table(g)
    out.write("     %-24s %5s %6s %9s %9s %8s %8s %8s %5s %5s %5s\n" % (
        "feature", "blocks", "moves", "len>=2", "E>=2", "E/mm>=2", "E/mm L1", "len L1", "ret", "prim", "arc"))
    for f, d in per.items():
        out.write("     %-24s %5d %6d %9.1f %9.3f %8s %8s %8.1f %5d %5d %5d  feeds>=2: %s\n" % (
            g["feat_names"][f], d["blocks"], d["moves"], d["len"], d["e"],
            "%.5f" % (d["e"] / d["len"]) if d["len"] else "-",
            "%.5f" % (d["e1"] / d["len1"]) if d["len1"] else "-", d["len1"], d["ret"], d["prime"], d["arc"],
            " ".join("%s x%d" % kv for kv in d["feeds"].most_common(9))))
        if d["feeds1"]:
            out.write("     %-24s       feeds L1: %s | widths %s | tools %s | layers %d\n" % (
                "", " ".join("%s x%d" % kv for kv in d["feeds1"].most_common(5)),
                " ".join("%s x%d" % kv for kv in sorted(d["widths"].items(), key=lambda kv: -kv[1])[:8]),
                dict(d["tools"]), len(d["layers"])))


def main():
    out_path = sys.argv[1]
    wanted = [int(a) for a in sys.argv[2:]] if len(sys.argv) > 2 else sorted(PAIRS)
    out = io.open(out_path, "w", encoding="utf-8")
    for row in wanted:
        run, base = PAIRS[row]
        out.write("=" * 110 + "\n#%d  run %s  baseline %s\n" % (row, run, base))
        gr, gb = gparse.load(run), gparse.load(base)
        cr, cb = gr["config"], gb["config"]
        changed = [k for k in sorted(set(cr) | set(cb)) if cr.get(k) != cb.get(k)]
        out.write("  config changed (%d): %s\n" % (len(changed), ", ".join(changed)))
        for k in changed:
            out.write("     %-44s %s  ->  %s\n" % (k, cb.get(k), cr.get(k)))
        out.write("  baseline:\n")
        show(out, "base", gb)
        out.write("  run:\n")
        show(out, "run", gr)
    out.close()


if __name__ == "__main__":
    main()
