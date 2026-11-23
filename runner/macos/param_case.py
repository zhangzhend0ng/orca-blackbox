"""One case of param_cases.json on macOS Orca 2.4.1, through the proven operations of param_ops.

  param_case.py --case <scenario> [--fuse N]

The case's ops run in order, each through its param_ops operation:
  (an op that carries `tab` switches to it first: switch_tab)
  float      -> find_row over its label candidates (the first that locates the row, with its
                group), then set_float on that label
  checkbox   -> find_row the same way, then the cell click of set_checkbox's check turn
                (the uncheck turn and its saves are not wanted inside a case)
  rowcombo   -> pick_combo on its row label

`unsupported op` - the case is marked so and does not run, nothing is guessed: a combo op
(located by the value it paints), a field / below box (a vertical stack of boxes), an op that
must answer a dialog, a checkbox that must end unchecked (the box's painted state has no
reader), or a row op before any tab op. A case whose app_conf is not empty is `needs develop
mode` and does not run either.

When every op is done: File > Save Project, then each key of the case's `values` is read from
the saved 3mf's Metadata/project_settings.config and judged pass / mismatch - a one-element
list by its first element, numbers as Decimal. An op that raises stops the case where it is and
nothing is saved; an op whose own readback refuses is recorded and the saved values decide.

From an ordinary shell the command only supervises; the GUI work runs in the test login's Aqua
session through param_ops' one-shot LaunchAgent. Results go to results.json under `cases`.
"""
import argparse
from decimal import Decimal, InvalidOperation
import hashlib
import json
import shutil
import sys
import time

import param_ops as po

TABLE = po.WORK / "param_cases.json"
SOURCE_COMMIT = "2733ef6"  # origin codex/glm-dev-20261124, tools/param_cases_export.json
# The keys each op may carry besides `op` (tab / tab_hint: switch to that page first); any
# other key is a form this version does not run.
ROW_KEYS = {"tab", "tab_hint", "label", "group"}
RUNNABLE = {"float": ROW_KEYS | {"value"}, "checkbox": ROW_KEYS | {"value"},
            "rowcombo": ROW_KEYS | {"target"}}


class AnchorMiss(Exception):
    """An anchored label ('^...') matched a row that does not start with it."""


def load_case(scenario):
    """The case table entry, with the table's identity; `po.require` (not a bare exit) keeps the
    worker's error shape."""
    raw = TABLE.read_bytes()
    table = json.loads(raw)
    po.require(table.get("meta"), f"{TABLE} is not the exported case table")
    hit = [c for c in table["cases"] if c["scenario"] == scenario]
    po.require(len(hit) == 1, f"{len(hit)} cases named {scenario!r} in {TABLE}")
    return {**hit[0], "_table": {"path": "runner/macos/param_cases.json", "source_commit": SOURCE_COMMIT,
                                 "sha256": hashlib.sha256(raw).hexdigest()}}


def unsupported(case):
    """The first op this version cannot run and why (None when it can run them all)."""
    tab = None
    for index, op in enumerate(case["ops"]):
        allowed = RUNNABLE.get(op.get("op"))
        why = None
        if allowed is None:
            why = f"unsupported op {op.get('op')!r}"
        elif set(op) - allowed - {"op"}:
            why = "unsupported op: " + ", ".join(sorted(set(op) - allowed - {"op"}))
        elif op.get("tab"):
            tab = op["tab"]
        elif tab is None:
            why = "unsupported op: a row op before any tab op"
        elif op["op"] == "checkbox" and op.get("value") is not True:
            why = "unsupported op: a checkbox that must end unchecked (no reader for its painted state)"
        if why:
            return {"index": index, "op": op, "reason": why}
    return None


def scalar(value):
    """A saved setting as one string: a one-element list by its first element, a bool as 1 / 0."""
    if isinstance(value, list) and len(value) == 1:
        value = value[0]
    if isinstance(value, bool):
        return "1" if value else "0"
    return None if value is None else str(value)


def same(saved, expected):
    """(equal?, how): numbers as Decimal, anything else as the exact string."""
    try:
        return Decimal(saved) == Decimal(expected), "decimal"
    except InvalidOperation:
        return saved == expected, "string"


def judge(before, saved, values):
    """pass / mismatch for each key of `values`, read from the saved settings."""
    keys = {}
    for key, expected in values.items():
        item = {"expected": expected, "before": scalar(before.get(key)) if key in before else None}
        if key not in saved:
            item.update(status="mismatch", saved=None, why="key absent from the saved project_settings.config")
        else:
            equal, how = same(scalar(saved[key]), str(expected))
            item.update(status="pass" if equal else "mismatch", saved=scalar(saved[key]), compared=how)
        keys[key] = item
    return keys


def labels(label):
    return [label] if isinstance(label, str) else list(label)


def anchor(panel, label):
    """find_row matches a substring; '^' in the table anchors the label at the start of the row.
    AnchorMiss is not a RuntimeError, so locate_row's fallback chain does not run for it."""
    if not label.startswith("^"):
        return
    plain, wanted = panel.find_row, po.norm(label[1:])

    def find(rows, group, wanted_label):
        row = plain(rows, group, wanted_label[1:])
        if not po.norm(row["text"]).startswith(wanted):
            raise AnchorMiss(f"Row {wanted_label!r} is anchored; it matched {row['text']!r}, "
                             "which does not start with it")
        return row
    panel.find_row = find


def locate(panel, op, tab):
    """find_row over the label candidates: (the label that located the row, its result, every
    candidate that did not - with the page rows it saw)."""
    tried = []
    for label in labels(op["label"]):
        anchor(panel, label)
        try:
            found = po.op_find_row(panel, {"tab": tab, "group": op.get("group"), "label": label})
        except (RuntimeError, TimeoutError, AnchorMiss) as error:
            tried.append({"label": label, "error": po.brief(error, 2500)})
            continue
        return label, found, tried
    po.require(False, f"Row not found for any label candidate in tab {tab!r}, group "
                      f"{op.get('group')!r}: {json.dumps(tried, ensure_ascii=False)[-3000:]}")


def tick(panel, op, tab, label):
    """The cell click of tick_checkbox (set_checkbox's check turn), without its save."""
    rows, row, note, tag = panel.locate_row(tab, op.get("group"), label, "check")
    base = po.checkbox_strip(panel, row, tag)
    gx, gy = panel.geometry()[0].x + po.VALUE_X, row["y"] + row["h"] / 2
    panel.click(gx, gy)
    time.sleep(0.9)
    panel.shot("check-checked")
    changed = po.pixel_diff(po.checkbox_strip(panel, row, "check-checked"), base)
    po.require(panel.dirty and changed > 8,
               f"The cell click did not tick the box: dirty={panel.dirty}, pixels changed={changed}")
    return {"ok": True,
            "readback": {"tab": tab, "label": row["text"], "click": [round(gx), round(gy)],
                         "pixels_changed_vs_before": changed},
            "evidence": {"notes": note, "page_text": panel.page_text(rows)[:60],
                         "screenshots": {"before": tag + ".png", "after": "check-checked.png"}}}


def prefixed(index, done):
    """The operation's evidence, its fixed shot names brought under this op's prefix."""
    evidence = dict(done.get("evidence") or {})
    shots = evidence.get("screenshots")
    if isinstance(shots, dict):
        evidence["screenshots"] = {k: f"op{index}-{v}" if v else v for k, v in shots.items()}
    return evidence


def op_case(panel, ns):
    """The `case` operation of param_ops: every op of the case, Save Project, the keys judged."""
    case = ns["_case"]
    blocked = unsupported(case)
    po.require(blocked is None, f"unsupported op: {json.dumps(blocked, ensure_ascii=False)[:400]}")
    started, before, saved = time.time(), po.settings_of(po.PROJECT), None
    steps, stopped, tab = [], None, None
    for index, op in enumerate(case["ops"]):
        step = {"index": index, "op": op["op"], "label": op.get("label"), "group": op.get("group"),
                "value": op.get("value"), "at": round(time.time() - started, 1)}
        steps.append(step)
        # The operations name their shots fixed ('float-after'); keep one set per op.
        panel.read = lambda tag, _index=index, **kw: po.Panel.read(panel, f"op{_index}-{tag}", **kw)
        panel.shot = lambda tag, _index=index: po.Panel.shot(panel, f"op{_index}-{tag}")
        try:
            tab_evidence = None
            if op.get("tab"):  # the op names a tab when the case changes page
                tab = op["tab"]
                switched = po.op_switch_tab(panel, {"tabs": tab})
                step["tab"] = {"name": tab, "hint": op.get("tab_hint"), "readback": switched["readback"]}
                po.require(switched["ok"], f"Tab {tab!r} did not open: {json.dumps(switched['readback'])[:300]}")
                tab_evidence = switched["evidence"]
            if op["op"] == "rowcombo":
                done = po.op_pick_combo(panel, {"tab": tab, "group": op.get("group"), "label": op["label"],
                                                "target": op["target"]})
                step.update(readback=done["readback"])
                po.require(done["ok"], f"pick_combo did not take: {json.dumps(done['readback'])[:300]}")
            else:
                label, found, tried = locate(panel, op, tab)
                step.update(label=label, row=found["readback"], label_candidates=labels(op["label"]),
                            candidates_not_found=tried, notes=found["evidence"]["notes"],
                            page_text=found["evidence"]["page_text"][:60])
                if op["op"] == "float":
                    done = po.op_set_float(panel, {"tab": tab, "group": op.get("group"), "label": label,
                                                   "value": str(op["value"])})
                else:
                    done = tick(panel, op, tab, label)
                step.update(readback=done["readback"], readback_ok=done["ok"])
            step["evidence"] = {**prefixed(index, done), "tab": tab_evidence}
        except Exception as error:
            step["error"] = po.brief(error, 2500)
            try:  # what the page showed where the op stopped
                step["page_text_at_error"] = panel.page_text(po.Panel.read(panel, f"op{index}-error"))[:60]
            except RuntimeError as failure:
                step["page_text_at_error"] = f"<not read: {po.brief(failure, 200)}>"
            stopped = step
        finally:
            for name in ("read", "shot", "find_row"):  # back to the Panel's own methods
                panel.__dict__.pop(name, None)
        step["seconds"] = round(time.time() - started, 1) - step["at"]
        if stopped:
            break
    result = {"status": "not passed", "scenario": case["scenario"], "case_id": case["case_id"],
              "table": case["_table"]}
    if stopped:
        result["reason"] = (f"stopped at op {stopped['index']} ({stopped['op']} {stopped.get('label')}): "
                            f"{stopped['error'][:600]}")
    else:
        try:
            saved = po.save_settings(panel)
        except Exception as error:
            result["reason"] = f"Save Project failed: {po.brief(error, 400)}"
        else:
            keys = judge(before, saved, case["values"])
            missed = [k for k in keys if keys[k]["status"] != "pass"]
            result.update(keys=keys, title_after_save=panel.title,
                          status="not passed" if missed else "pass",
                          ops_whose_readback_refused=[s["index"] for s in steps if s.get("readback_ok") is False])
            if missed:
                result["reason"] = "mismatch: " + ", ".join(missed)
    # Review material, not judged: settings other than the case's keys that the save changed.
    others = [] if saved is None else sorted(
        k for k in set(before) | set(saved) if k not in case["values"]
        and scalar(before.get(k)) != scalar(saved.get(k)))
    return {"ok": result["status"] == "pass", "status": result["status"],
            "readback": result,
            "evidence": {"steps": steps, "notes": panel.last_notes,
                         "other_changed_keys": {"count": len(others), "keys": others[:80]}}}


# param_ops' supervisor runs whatever op its OPS table holds, stages the worker under
# WORKER_SCRIPT and files the result through record(): this module adds its own of each.
po.WORKER_SCRIPT, po.OPS["case"] = "param_case.py", op_case

_staged = po.stage


def stage(work):
    """param_ops' stage plus this runner and the case table the worker reads."""
    _staged(work)
    for name in ("param_case.py", "param_cases.json"):
        shutil.copy2(po.WORK / name, work / name)


def record(result, stamp):
    """File the run under results.json `cases`; the record it replaces is kept in `cases_history`."""
    path = po.EVIDENCE / "results.json"
    data = json.loads(path.read_text())
    key = ":".join(filter(None, (result["op"], result.get("name"))))
    cases = data.setdefault("cases", {})
    if key in cases:
        data.setdefault("cases_history", []).append(cases[key])
    cases[key] = result
    data.setdefault("attempts", []).append({"op": key, "stamp": stamp, "ok": result["ok"]})
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


po.stage, po.record = stage, record


def finish(result):
    """Record a case that does not run (no worker, no shots)."""
    record(result, time.strftime("%H%M%S"))
    print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
    return 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--worker"]:
        return po.worker_main(json.loads(argv[1]))
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", required=True, metavar="SCENARIO", help="a scenario of param_cases.json")
    parser.add_argument("--fuse", type=int, help="seconds before the supervisor gives up "
                        "(default 120 + 80 per op: one op may need the whole fallback chain)")
    ns = parser.parse_args(argv)
    case = load_case(ns.case)
    ns.op, ns.name = "case", ns.case
    ns.fuse = ns.fuse or 120 + 80 * len(case["ops"])
    result = {"op": "case", "name": case["scenario"], "case_id": case["case_id"], "ok": False,
              "table": case["_table"]}
    if case.get("app_conf"):
        return finish({**result, "status": "needs develop mode", "app_conf": case["app_conf"]})
    blocked = unsupported(case)
    if blocked:
        return finish({**result, "status": "unsupported op", "blocked": blocked})
    ns._case = {k: v for k, v in case.items()}
    return po.supervise(ns)


if __name__ == "__main__":
    sys.exit(main())
