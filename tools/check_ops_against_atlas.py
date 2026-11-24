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

# What the 2.4.0 pages really paint, line by line (census b0a7f3a0, stitched
# by tools/rows_from_census.py). This is the primary source for labels: the
# atlas is a different tree than the build.
_PAGE_ROWS_FILE = Path(__file__).resolve().parent / "param_ui_rows_2.4.0.json"
PAGE_ROWS = (json.loads(_PAGE_ROWS_FILE.read_text(encoding="utf-8"))["tabs"]
        if _PAGE_ROWS_FILE.exists() else {})

# Rows and groups the fixture page does not paint. PAGE_ROWS is ONE picture
# of each tab with the fixture preset, so a row that an earlier op of the
# same scenario brings onto the page is missing there by construction (and
# the census OCR garbled one or two others). Every entry names its proof;
# an op that is not listed and does not match is a problem, as before.
# Keyed by the op's FIRST label candidate (a group, by its name) and not by
# op index: ops get inserted (raft gained Enable + Type in r5.6) and an
# index key silently stops matching.
CONDITIONAL = {
    ("uia_param_raft", "Raft contact Z distance"): "appears after Raft layers > 0 "
    "(VM run be0664ae: 'Raft contact Z distance 0.2 mm' once layers was 3)",
    ("uia_param_prime_tower", "Stabilization cone apex angle"): "exists only while Wall type is "
    "Cone (ConfigManipulation.cpp:858; VM run aa451776 without it; #283 closed on fa706g3, "
    "run 2bacb634)",
    ("uia_param_tree_support", "Tree support branch angle"): "the 'Tree supports' group appears "
    "after Style leaves Default (VM run 1f23038c band; ConfigManipulation.cpp:755-763; #282 "
    "closed on fa706g3, run e946ad14)",
    ("uia_param_tree_support", "Tree supports"): "the group title exists only after Style leaves "
    "Default (same proof as the branch angle row)",
    ("uia_param_tree_support", "Max bridge length"): "needs support enabled "
    "(ConfigManipulation.cpp:771)",
    ("uia_param_support_ironing", "Support Ironing linespacing"): "appears after support ironing "
    "is on (#280 closed on fa706g3, run 51380cfe)",
    ("uia_param_ironing_top", "roning"): "appears after ironing is on",
    ("uia_param_wall_generator", "Wall distribution count"): "appears with the Arachne generator "
    "(#260 closed, run 7e59e22a)",
    ("uia_param_single_wall_avoid", "Max detour length"): "appears with Make overhang printable "
    "on (#261 closed, run 3727296c)",
    ("uia_param_surface_flow", "Top surface flow ratio"): "on the page; the census OCR read it "
    "'Tan cirface flaw ratio' (#262 closed, run a7504d39)",
    ("uia_param_gcode_output", "number"): "develop mode only (case open: user_mode)",
    ("uia_param_overhang_bridge", "External"): "the label painted beside the bridge_speed box "
    "under the overhang stack (Tab.cpp: Line{L(\"Bridge\")} with bridge_speed and "
    "internal_bridge_speed; the atlas gives bridge_speed the label 'External'); the page census "
    "stops above it - guest screenshot 94a82cda shows '50 mm/s  External' under the fourth "
    "overhang box",
}
# Popup targets no census has listed yet: (scenario, op index) -> (target,
# proof pending). The run that opens the popup is the proof; drop the entry
# once the popup census (tools/param_ui_popups_2.4.0.json) has the row -
# as 'Wall type' did after fa706g3 run 2bacb634 (Rectangle / Cone / Rib).
PENDING_TARGET = {}
# Scenarios whose control the fixture machine does not offer: checked
# nowhere, reported once. The row stays in the case table (it is valid for
# a machine with a camera) and the case is recorded N/A in the run ledger.
NOT_APPLICABLE = {
    "uia_param_timelapse": "only BBL printers get the Timelapse row "
    "(ConfigManipulation.cpp:932 toggle_line(\"timelapse_type\", is_BBL_Printer)); the row census "
    "of Others / Special mode on the U1 machine: Slicing Mode / Print sequence / Intra-layer "
    "order / Spiral vase",
}


def is_title_line(tab, page_y):
    return any(abs(g["page_y"] - page_y) <= 10 for g in PAGE_ROWS[tab]["groups"])


def row_group(tab, page_y):
    """Title of the group a page line belongs to ('' above the first title)."""
    title = ""
    for g in PAGE_ROWS[tab]["groups"]:
        if g["page_y"] - 8 <= page_y:
            title = g["title"]
    return title


def label_in_rows(tab, labels, group=None):
    """(candidate, line) for the first candidate that matches a real ROW line
    of `tab` inside `group`; (None, reason) when none does. A match on a
    group TITLE line does not count - the engine skips title lines, and
    'First layer speed' is the title of the group whose first row reads
    'First layer' (that op passed for two days on the title plus 'below')."""
    if tab not in PAGE_ROWS:
        return None, "no row census for %r" % tab
    groups = [g["title"] for g in PAGE_ROWS[tab]["groups"]]
    if group and not any(group.lower() in t.lower() for t in groups):
        return None, "group %r is not a title on %s (%s)" % (group, tab, groups)
    only_title = []
    for cand in labels:
        for line in PAGE_ROWS[tab]["lines"]:
            if group and group.lower() not in row_group(tab, line["page_y"]).lower():
                continue
            if label_matches(cand, line["text"]):
                if is_title_line(tab, line["page_y"]):
                    only_title.append(cand)
                    continue
                return cand, line["text"]
    if only_title:
        return None, "label %r matches only the group TITLE line on %s" % (only_title[0], tab)
    return None, "no candidate matches a row line of %s in group %r" % (tab, group)


def value_in_rows(tab, value, group=None):
    text = " ".join(value) if isinstance(value, (tuple, list)) else str(value)
    for line in PAGE_ROWS[tab]["lines"]:
        if group and group.lower() not in row_group(tab, line["page_y"]).lower():
            continue
        if text.lower() in line["text"].lower():
            return True
    return False


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
        if scenario in NOT_APPLICABLE:
            notes.append(f"{scenario}: N/A on this machine - {NOT_APPLICABLE[scenario]}")
            continue
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
                if tab in PAGE_ROWS:
                    # The build's own page lines decide (see label_in_rows).
                    cand, why = label_in_rows(tab, labels, op.get("group"))
                    if cand is not None:
                        pass
                    elif (scenario, labels[0]) in CONDITIONAL:
                        why_cond = CONDITIONAL[(scenario, labels[0])]
                        notes.append(f"{scenario} op[{i}] label {labels!r}: CONDITIONAL row - "
                                     f"{why_cond}")
                    else:
                        problems.append(f"{scenario} op[{i}] label {labels!r}: {why}")
                else:
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
            if op.get("op") == "combo" and op.get("current") is not None and cur_tab in PAGE_ROWS:
                if not value_in_rows(cur_tab, op["current"], op.get("group")):
                    problems.append(f"{scenario} op[{i}] combo current {op['current']!r}: not painted on "
                                    f"{cur_tab} in group {op.get('group')!r} (row census)")
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
                        if cur_tab in PAGE_ROWS and value_in_rows(cur_tab, op["target"], op.get("group")):
                            notes.append(f"{scenario} op[{i}] combo TARGET {op['target']!r}: painted on "
                                         f"{cur_tab} (row census), popup itself not censused")
                        elif (PENDING_TARGET.get((scenario, i)) or (None,))[0] == op["target"]:
                            notes.append(f"{scenario} op[{i}] combo TARGET {op['target']!r}: PENDING run "
                                         f"proof - {PENDING_TARGET[(scenario, i)][1]}")
                        else:
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
        if scenario in NOT_APPLICABLE:
            continue
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
                    if (scenario, group) in CONDITIONAL:
                        notes.append(f"{scenario} op[{i}] group {group!r}: CONDITIONAL title on "
                                     f"{tab!r} - {CONDITIONAL[(scenario, group)]}")
                    else:
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
