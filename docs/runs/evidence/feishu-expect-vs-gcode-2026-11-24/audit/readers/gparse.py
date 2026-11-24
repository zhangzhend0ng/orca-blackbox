"""Independent G-code reader for the audit (scratch only; belongs to neither repository).

    import gparse; g = gparse.load(run_prefix)        # cached pickle in ./cache

What load() returns (dict):
  path, run       file and its run id
  config          {key: value} from the trailing "; key = value" block
  summary         the "; ... = ...mm" lines before the executable block (line widths)
  feat_names      feature names (after ;TYPE:) in order of first appearance
  types           Counter of ;TYPE: blocks per feature name
  layers          [{n, z, height, feats}]  one per ;LAYER_CHANGE (z from ;Z:, height ;HEIGHT:)
  blocks          [layer, feat, i0, i1]    a ;TYPE: block = move range [i0, i1)
  S               parallel lists, one entry per G0/G1/G2/G3 line that carries X, Y, Z, E or F
  events          [(layer, z, feat, text)] every other non-comment command line
  markers         Counter of comment markers (first word after ';')
  nlines, numbered, motion_lines
Keys of S (index i in every list):
  L layer, Z machine Z after the move, H layer height (;HEIGHT:), F feature index (None before
  the first ;TYPE:), T tool, fd feed (mm/min, modal at that line), x0 y0 x1 y1,
  e filament mm of the move (negative = retract), k kind, w width from the last ;WIDTH:,
  arc (0 / 1 G2 / 2 G3), cx cy arc centre, wi 1 between ;WIPE_START and ;WIPE_END, ln file line
k: 1 extruding move with XY, 2 travel with XY (no E), 3 XY move with negative E, 4 Z only,
   5 E only (prime > 0 / retract < 0), 6 F only.
E is relative unless the file says M82 (use_relative_e_distances = 1 in these exports).
"""
import collections
import glob
import math
import os
import pickle
import re
import sys

HARVEST = os.environ.get("ORCA_BB_HARVEST") or (
    r"C:\coil\Projects\SnapmakerOrca\external\orca-blackbox\.worktrees\glm\artifacts\windows_mcp_harvest")
HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
KEYS = ("L", "Z", "H", "F", "T", "fd", "x0", "y0", "x1", "y1", "e", "k", "w", "arc", "cx", "cy", "wi", "ln")
EXTRUDE, TRAVEL, WIPERET, ZONLY, EONLY, FONLY = 1, 2, 3, 4, 5, 6
N_RE = re.compile(r"^N\d+\s+")


def gcode_of(prefix):
    hits = glob.glob(os.path.join(HARVEST, prefix + "*"))
    if not hits:
        raise SystemExit("no run with prefix " + prefix)
    files = glob.glob(os.path.join(hits[0], "exports", "*.gcode"))
    if not files:
        raise SystemExit("run %s has no G-code" % prefix)
    return files[0]


def run_dir(prefix):
    hits = glob.glob(os.path.join(HARVEST, prefix + "*"))
    if not hits:
        raise SystemExit("no run with prefix " + prefix)
    return hits[0]


def _f(text):
    try:
        return float(text)
    except ValueError:
        return None


def parse(path):
    out = {"path": path, "run": os.path.basename(os.path.dirname(os.path.dirname(path)))}
    config, summary = {}, []
    feat_names, feat_idx, types = [], {}, collections.Counter()
    layers, blocks, events = [], [], []
    S = {k: [] for k in KEYS}
    markers = collections.Counter()
    in_cfg = in_exec = False
    layer, z, x, y, zc, hgt = 0, 0.0, None, None, None, None
    width, kind, feed, tool = 0.0, None, None, None
    wiping = False
    block = None
    nlines = numbered = 0
    with open(path, encoding="utf-8", errors="replace") as fh:
        for ln, raw in enumerate(fh, 1):
            nlines = ln
            if raw[0] == ";":
                word = raw[1:].split(" ", 1)[0].split(":", 1)[0].strip()
                markers[word] += 1
                if raw.startswith(";LAYER_CHANGE"):
                    layer += 1
                    layers.append({"n": layer, "z": None, "height": None, "feats": []})
                elif raw.startswith(";Z:"):
                    zc = _f(raw[3:].strip())
                    if layer:
                        layers[-1]["z"] = zc
                elif raw.startswith(";HEIGHT:"):
                    hgt = _f(raw[8:].strip())
                    if layer:
                        layers[-1]["height"] = hgt
                elif raw.startswith(";WIDTH:"):
                    width = _f(raw[7:].strip()) or 0.0
                elif raw.startswith(";WIPE_START"):
                    wiping = True
                elif raw.startswith(";WIPE_END"):
                    wiping = False
                elif raw.startswith(";TYPE:"):
                    name = raw[6:].strip()
                    types[name] += 1
                    kind = feat_idx.get(name)
                    if kind is None:
                        kind = len(feat_names)
                        feat_idx[name] = kind
                        feat_names.append(name)
                    if block is not None:
                        block[3] = len(S["L"])
                    block = [layer, kind, len(S["L"]), None]
                    blocks.append(block)
                    if layer:
                        layers[-1]["feats"].append(kind)
                elif raw.startswith("; CONFIG_BLOCK_START"):
                    in_cfg = True
                elif raw.startswith("; CONFIG_BLOCK_END"):
                    in_cfg = False
                elif in_cfg and " = " in raw:
                    key, val = raw[1:].split(" = ", 1)
                    config[key.strip()] = val.strip()
                elif not in_exec and " = " in raw and raw.rstrip().endswith("mm"):
                    summary.append(raw.strip())
                continue
            line = raw.split(";", 1)[0].strip()
            if not line:
                continue
            if line[:1] == "N" and line[1:2].isdigit():
                numbered += 1
                line = N_RE.sub("", line, count=1)
                if not line:
                    continue
            w3 = line[:3]
            if w3 in ("G0 ", "G1 ", "G2 ", "G3 ") or line in ("G0", "G1"):
                px = py = pz = pe = None
                arc = 1 if w3[1] == "2" else (2 if w3[1] == "3" else 0)
                cx = cy = 0.0
                for t in line[3:].split() if len(line) > 3 else []:
                    a, v = t[:1], t[1:]
                    try:
                        if a == "X":
                            px = float(v)
                        elif a == "Y":
                            py = float(v)
                        elif a == "Z":
                            pz = float(v)
                        elif a == "E":
                            pe = float(v)
                        elif a == "F":
                            feed = float(v)
                        elif a == "I" and arc:
                            cx = (x or 0.0) + float(v)
                        elif a == "J" and arc:
                            cy = (y or 0.0) + float(v)
                        elif a == "R" and arc and x is not None and y is not None:
                            r = float(v)
                            nx_, ny_ = (px if px is not None else x), (py if py is not None else y)
                            dx, dy = nx_ - x, ny_ - y
                            d = math.hypot(dx, dy) or 1e-9
                            h2 = math.sqrt(max(r * r - d * d / 4.0, 0.0))
                            sgn = 1.0 if arc == 1 else -1.0
                            if r < 0:
                                sgn = -sgn
                            cx, cy = (x + nx_) / 2.0 - sgn * dy * h2 / d, (y + ny_) / 2.0 + sgn * dx * h2 / d
                    except ValueError:
                        continue
                moving = px is not None or py is not None
                nx = px if px is not None else x
                ny = py if py is not None else y
                e_val = pe if pe is not None else 0.0
                if moving:
                    k = EXTRUDE if e_val > 0 else (WIPERET if e_val < 0 else TRAVEL)
                elif pe is not None:
                    k = EONLY
                elif pz is not None:
                    k = ZONLY
                else:
                    k = FONLY
                if pz is not None:
                    z = pz
                S["L"].append(layer); S["Z"].append(z); S["H"].append(hgt); S["F"].append(kind)
                S["T"].append(tool); S["fd"].append(feed); S["x0"].append(x); S["y0"].append(y)
                S["x1"].append(nx if moving else x); S["y1"].append(ny if moving else y)
                S["e"].append(e_val); S["k"].append(k); S["w"].append(width if k == EXTRUDE else 0.0)
                S["arc"].append(arc if k in (EXTRUDE, TRAVEL, WIPERET) else 0)
                S["cx"].append(cx if arc else 0.0); S["cy"].append(cy if arc else 0.0)
                S["wi"].append(1 if wiping else 0); S["ln"].append(ln)
                if moving:
                    x, y = nx, ny
                continue
            if line[:1] == "T" and line[1:2].isdigit():
                m = re.match(r"T(\d+)", line)
                if m:
                    tool = int(m.group(1))
            elif line.startswith("M82"):
                pass
            events.append((layer, zc, kind, line))
    if block is not None:
        block[3] = len(S["L"])
    out.update(config=config, summary=summary, feat_names=feat_names, types=types, layers=layers,
               blocks=blocks, S=S, events=events, markers=markers, nlines=nlines, numbered=numbered,
               motion_lines=sum(1 for k in S["k"] if k in (EXTRUDE, TRAVEL, WIPERET, ZONLY, EONLY)))
    return out


def load(prefix):
    """Parsed export of a run, cached. `prefix` = first characters of the run id."""
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)
    path = gcode_of(prefix)
    st = os.stat(path)
    key = "%s_%d_%d" % (os.path.basename(os.path.dirname(os.path.dirname(path))), st.st_size, int(st.st_mtime))
    cpath = os.path.join(CACHE, key + ".pkl")
    if os.path.exists(cpath):
        with open(cpath, "rb") as fh:
            return pickle.load(fh)
    g = parse(path)
    with open(cpath, "wb") as fh:
        pickle.dump(g, fh, protocol=pickle.HIGHEST_PROTOCOL)
    return g


if __name__ == "__main__":
    # smoke: python -B gparse.py <prefix> [...]
    for p in sys.argv[1:]:
        g = load(p)
        print(p, "lines", g["nlines"], "numbered", g["numbered"], "moves", len(g["S"]["k"]),
              "layers", len(g["layers"]), "blocks", len(g["blocks"]), "config keys", len(g["config"]))
        print("   types:", dict(g["types"]))
        print("   summary:", g["summary"])
