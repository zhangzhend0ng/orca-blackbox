"""check_ops_against_atlas.py - offline ops-label validation.

Every PARAM_OPS label variant is checked against the source-mined
param_label_atlas.json (version-exact from the SUT's own C++ source):
  1. does the variant match SOME row on the op's claimed tab, using the
     engine's own matching semantics (single word: substring containment;
     multi-word: first word prefix + phrase prefix on the joined tail)?
  2. is the scenario's pilot VALUES key actually placed on a page (tab) at
     all, and does it agree with the ops' tab routing?

This turns label calibration from "one GUI run per guess" into an offline
table check (the census/atlas play, 2026-11-23).
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.native_script_baseline import PARAM_OPS  # noqa: E402

ATLAS = json.loads((Path(__file__).resolve().parent.parent
                    / "harness/param_label_atlas.json").read_text(encoding="utf-8"))
ROWS = ATLAS["rows"]
# What the 2.4.0 build really paints as group titles (census run c101c0f4).
# The atlas comes from the host's source tree and is NOT the build: it lists
# 'Initial layer speed' where the page says 'First layer speed', and a
# 'Tree supports' group the Support page does not have - both passed the
# atlas check and both failed in the GUI (queue18, 2026-11-23).
CENSUS = json.loads((Path(__file__).resolve().parent.parent
                     / "harness/param_ui_titles_2.4.0.json").read_text(encoding="utf-8"))
# What the build's option popups really list (census 67690ed4 / c814315c).
POPUPS = json.loads((Path(__file__).resolve().parent
                     / "param_ui_popups_2.4.0.json").read_text(encoding="utf-8"))["popups"]


def popup_for(tab, op):
    """The censused popup a combo op opens, or None: a rowcombo by its first
    label (without '^'), a combo by the value it currently paints."""
    if not tab:
        return None
    if op["op"] == "rowcombo":
        lab = op.get("label")
        row = (lab[0] if isinstance(lab, (tuple, list)) else str(lab)).lstrip("^")
    else:
        cur = op.get("current")
        row = " ".join(cur) if isinstance(cur, (tuple, list)) else str(cur)
    for pop in POPUPS:
        if pop["tab"] == tab and row.lower() in pop["row"].lower():
            return pop
    return None


def scenario_values():
    """scenario name -> its pilot's VALUES (the keys and values the case
    expects in the saved project)."""
    import importlib
    from harness import native_pilots
    out = {}
    for scenario, module in native_pilots.TRIALS.items():
        try:
            out[scenario] = importlib.import_module("harness." + module).VALUES
        except Exception:
            out[scenario] = {}
    return out


SCENARIO_VALUES = scenario_values()


def label_matches(variant, label):
    """Engine semantics: single word -> substring; multi-word -> the label's
    word sequence must have some word starting the variant's first word and
    the joined tail must start with the variant."""
    # A leading '^' anchors the label to the start of its row (engine
    # semantics, _find_phrase_row): only the row's first word may start it.
    anchored = variant.startswith("^")
    want = variant.lstrip("^").lower().split()
    words = label.lower().split()
    if len(want) == 1:
        return (want[0] in words[0]) if anchored else any(want[0] in w for w in words)
    for i in ((0,) if anchored else range(len(words))):
        # An unanchored variant may start at any word of the row. Until
        # 2026-11-23 this read range(len(words), len(words)) - empty - so an
        # unanchored MULTI-word variant never matched anything: 60 of the 62
        # "UNCERTAIN" lines the checker printed were that bug (Mac audit).
        if words[i].startswith(want[0]):
            if " ".join(words[i:i + len(want)]).startswith(" ".join(want)):
                return True
    return False


def tab_rows(tab):
    out = []
    for row in ROWS.values():
        if tab in row.get("tabs", []) and (row.get("label") or row.get("line_label")):
            r = dict(row)
            if r.get("line_label"):
                r["label"] = r["line_label"]  # the painted multi-field row label
            out.append(r)
    return out


def import_pilot_values():
    """scenario -> VALUES dict, from every pilot module on disk."""
    import importlib
    import glob
    import re
    from harness import native_pilots
    mapping = getattr(native_pilots, "SCENARIO_PILOTS", None) or {}
    # native_pilots exposes scenario -> module name differently per revision;
    # discover by filename convention instead.
    out = {}
    for path in glob.glob(str(Path(__file__).resolve().parent.parent
                              / "harness/pilot_param_*.py")):
        name = Path(path).stem
        try:
            mod = importlib.import_module("harness." + name)
        except Exception:
            continue
        vals = getattr(mod, "VALUES", None)
        cid = getattr(mod, "CASE_ID", name)
        if isinstance(vals, dict):
            out[cid] = vals
    return out


def main():
    problems = []
    notes = []
    cur_tab = None   # ops inherit the tab of the last op that named one
    for scenario, ops in sorted(PARAM_OPS.items()):
        cur_tab = None
        for i, op in enumerate(ops):
            # Ops inherit the tab of the last op that named one. Until
            # 2026-11-23 an op without 'tab' was checked against every page
            # (83 labels), which cannot fail (Mac audit).
            tab = op.get("tab") or cur_tab
            cur_tab = tab
            labels = op.get("label")
            labels = [labels] if isinstance(labels, str) else labels
            if op.get("op") in ("float", "checkbox", "rowcombo", "combo") and labels:
                rows = tab_rows(tab) if tab else []
                # The engine needs ONE of the label candidates to match, not
                # all of them: a scenario typically carries an OCR-spelled
                # first candidate ('Top lnterface layers') and a plain one.
                variant = next((v for v in labels
                                if any(label_matches(v, r["label"]) for r in rows)), None)
                if variant is None:
                    variant = labels[0]
                    # Where does the atlas know this label at all? Downgrade
                    # to a note only when every such row is a path-override
                    # row (rendered through the webui i18n, allowed to
                    # differ). Until 2026-11-23 ANY path row on the page (37
                    # to 84 per page) downgraded every miss: the hard branch
                    # was dead code and the checker was permanently red.
                    best = [(k, r) for k, r in ROWS.items()
                            if (r.get("line_label") or r.get("label"))
                            and label_matches(variant, r.get("line_label") or r.get("label"))]
                    where = [f"{r.get('line_label') or r.get('label')}@{r.get('tab')}"
                             for _k, r in best]
                    if best and all(r.get("label_path") for _k, r in best):
                        notes.append(f"{scenario} op[{i}] label {variant!r}: UNCERTAIN (path row) "
                                     f"on tab {tab!r} (atlas: {where[:3]})")
                    else:
                        problems.append(
                            f"{scenario} op[{i}] label {labels!r}: NO match on tab "
                            f"{tab!r}" + (f" (atlas elsewhere: {where[:3]})" if where else
                                          " (nowhere in atlas)"))
            if op.get("op") == "float" and "value" in op:
                # The typed value must be one the case expects. Run b1103170
                # typed 50 into a 'mm/s or %' field where the case wants 50%
                # and died at verification; the checker never compared the two.
                # Compared as numbers: a '%' field stores 100 for a typed 100
                # (bridge density), so the unit alone is not a mismatch.
                def _num(text):
                    digits = "".join(ch for ch in str(text) if ch.isdigit() or ch in ".-")
                    return float(digits) if digits not in ("", "-", ".", "-.") else None
                try:
                    want = {_num(v) for v in SCENARIO_VALUES.get(scenario, {}).values()}
                except ValueError:
                    want = set()
                if want and _num(op["value"]) not in want:
                    problems.append(f"{scenario} op[{i}] value {op['value']!r} is not among the "
                                    f"pilot's expected values "
                                    f"{sorted(SCENARIO_VALUES.get(scenario, {}).values())}")
            if op.get("op") in ("combo", "rowcombo") and op.get("target"):
                tgt = op["target"].lower()
                pop = popup_for(cur_tab, op)
                if pop:
                    # What the build's popup really offers (census) decides.
                    if not any(tgt in it.lower() for it in pop["items"]):
                        problems.append(
                            f"{scenario} op[{i}] TARGET {op['target']!r}: not among the rows the "
                            f"{cur_tab} {pop['row']!r} popup really offers (census): {pop['items']}")
                else:
                    # no census of that popup: the source atlas is all there is
                    found = any(tgt in (lbl or "").lower()
                                for r in ROWS.values()
                                for lbl in (r.get("enum_labels") or []))
                    if not found:
                        problems.append(f"{scenario} op[{i}] combo TARGET {op['target']!r}: "
                                        f"not found in any enum_labels (and not in the popup census)")
    # pilot VALUES keys must exist as config defs at all
    for cid, values in sorted(import_pilot_values().items()):
        for key in values:
            if key not in ROWS:
                problems.append(f"pilot {cid}: VALUES key {key!r} NOT a config def "
                                f"(key-name error, precedent infill_wall_overlap)")
    # op 'group' must be a real group title on that page: a missing title
    # made scroll_group_into_view wheel until its 420s timeout (#263 'Bridge'
    # vs 'Bridging', #276 'Advanced' on Quality). A combo 'current' given as
    # a multi-word STRING can never be inside one OCR word - it must be a
    # word-sequence tuple.
    for scenario, ops in sorted(PARAM_OPS.items()):
        tab = None
        for i, op in enumerate(ops):
            tab = op.get("tab") or tab
            group = op.get("group")
            if group and tab:
                # The painted titles of the build decide; the source atlas
                # is only the fallback for a tab the census did not cover.
                titles = [r["title"] for r in CENSUS["tabs"].get(tab, [])] or \
                    [g.get("title") for g in ATLAS["pages"].get(tab, [])]
                if titles and not any(group.lower() in (t or "").lower() for t in titles):
                    problems.append(f"{scenario} op[{i}] group {group!r}: no such group title on "
                                    f"tab {tab!r} (titles: {titles})")
            current = op.get("current")
            if op.get("op") == "combo" and isinstance(current, str) and " " in current.strip():
                problems.append(f"{scenario} op[{i}] combo current {current!r}: a multi-word string "
                                f"never matches one OCR word - use a tuple")
    print(f"checked {len(PARAM_OPS)} scenarios")
    for p in notes:
        print("  ? " + p)
    if problems:
        print(f"{len(problems)} problems ({len(notes)} notes):")
        for p in problems:
            print("  -", p)
    else:
        print(f"all ops validate ({len(notes)} notes)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
