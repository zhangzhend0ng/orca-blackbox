"""One case of param_cases.json on macOS Orca 2.4.1, through the proven operations of param_ops.

  param_case.py --case <scenario> [--fuse N]

The case's ops run in order, each through its param_ops operation:
  (an op that carries `tab` switches to it first: switch_tab)
  float      -> find_row over all its label candidates at once (one reading of the page judges
                each of them; the one that hit names the row), then set_float on that label
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
SOURCE_COMMIT = "f371b47"  # origin codex/glm-dev-20261124, tools/param_cases_export.json (step 13: 270 / 271 in mm/s)
# The keys each op may carry besides `op` (tab / tab_hint: switch to that page first); any
# other key is a form this version does not run.
ROW_KEYS = {"tab", "tab_hint", "label", "group"}
CASE_FUSE = 420  # seconds for the whole case from the supervisor's start: launch, ops, save
OP_FUSE = 150  # seconds one op may take from its entry; surface_flow's op0 needs about 135 (060903)
SAVE = 40  # kept after the last op for Save Project and the keys read from the saved project
PROGRESS = po.WORK / "progress.json"  # the ops finished so far, put down after each one
RUNNABLE = {"float": ROW_KEYS | {"value"}, "checkbox": ROW_KEYS | {"value"},
            "rowcombo": ROW_KEYS | {"target"}}


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
    if isinstance(value, list):  # more than one extruder: shown as JSON, compared as that text
        return json.dumps(value)
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


def locate(panel, op, tab):
    """find_row over all the label candidates of the op at once: one reading of the page judges
    every candidate (r4 on Windows; run 043416 spent a whole locate chain on each of the two
    candidates that cannot match). (the candidate that located the row, its result, what each
    candidate matched on that page)"""
    candidates = labels(op["label"])
    try:
        found = po.op_find_row(panel, {"tab": tab, "group": op.get("group"),
                                       "label": op["label"] if len(candidates) > 1 else candidates[0]})
    except (RuntimeError, TimeoutError) as error:
        po.require(False, f"Row not found for any label candidate {candidates} in tab {tab!r}, group "
                          f"{op.get('group')!r}: {po.brief(error, 2500)}")
    return found["readback"]["label_candidate"], found, found["readback"]["match"]["candidates"]


def per_op_shots(panel, index):
    """The operations name their shots fixed ('float-after'); keep one set per op. Every capture
    goes through shot (read calls it), so the prefix goes there once: a tag handed to shot is
    never prefixed already."""
    panel.shot_prefix = f"op{index}"
    panel.shot = lambda tag: po.Panel.shot(panel, f"{panel.shot_prefix}-{tag}")


def on_disk(panel, tag):
    """The name shot `tag` has on disk. locate_row hands back the bare tag (check-page), while
    per_op_shots stored that capture as op1-check-page.png; the bare name is not a file in out/
    (run 034725 cut from the bare names and stopped right after its cell click)."""
    name = f"{panel.shot_prefix}-{tag}"
    po.require((po.OUT / f"{name}.png").is_file(), f"Shot {name!r} is not a file in {po.OUT}")
    return name


def tick(panel, op, tab, label):
    """The cell click of tick_checkbox (set_checkbox's check turn), without its save."""
    rows, row, note, tag = panel.locate_row(tab, op.get("group"), label, "check")
    base = po.checkbox_strip(panel, row, on_disk(panel, tag))  # refused here, before any click
    gx, gy = panel.geometry()[0].x + po.VALUE_X, row["y"] + row["h"] / 2
    panel.click(gx, gy)
    time.sleep(0.9)
    panel.shot("check-checked")
    changed = po.pixel_diff(po.checkbox_strip(panel, row, on_disk(panel, "check-checked")), base)
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


def op_limit(case_end, now=None):
    """Seconds the op that starts now may take: OP_FUSE, or less when the case's end is nearer
    than that and the save's SAVE seconds (the supervisor gives the whole case CASE_FUSE)."""
    left = case_end - SAVE - (time.time() if now is None else now)
    return round(min(OP_FUSE, left), 1)


def fuse_of(error):
    """Whether an op stopped on its own fuse: the OpFuse itself, or the error raised while it
    was being handled (locate and scroll_to wrap a chain's error in their own)."""
    seen = set()
    while error is not None and id(error) not in seen:
        if isinstance(error, po.OpFuse):
            return True
        seen.add(id(error))
        error = error.__context__ or error.__cause__
    return False


def op_case(panel, ns):
    """The `case` operation of param_ops: every op of the case, Save Project, the keys judged."""
    case = ns["_case"]
    blocked = unsupported(case)
    po.require(blocked is None, f"unsupported op: {json.dumps(blocked, ensure_ascii=False)[:400]}")
    started, before, saved = time.time(), po.settings_of(po.PROJECT), None
    steps, stopped, tab = [], None, None
    case_end = ns.get("case_end")  # wall-clock; po.supervise hands its own fuse's end over
    limits = {"per_op": OP_FUSE, "case": ns.get("fuse"), "ops": {}}
    head = {"scenario": case["scenario"], "case_id": case["case_id"], "table": case["_table"],
            "limits": limits}

    def put_down(state, reason=None):
        """The record so far, after each op: a supervisor kill (the case's fuse, a launch
        fault) takes result.json with it, and with it every op before the one it hit (run
        050914: op0's cell click). Written through a neighbour and renamed, never half."""
        record = {**head, "status": "not passed", "state": state, "steps": steps}
        if reason:
            record["reason"] = reason
        neighbour = PROGRESS.with_suffix(".tmp")
        neighbour.write_text(json.dumps(record, ensure_ascii=False))
        neighbour.replace(PROGRESS)

    for index, op in enumerate(case["ops"]):
        step = {"index": index, "op": op["op"], "label": op.get("label"), "group": op.get("group"),
                "value": op.get("value"), "at": round(time.time() - started, 1)}
        steps.append(step)
        per_op_shots(panel, index)
        # Each op has its own limit, checked by Panel.read: an op that runs out is this op's own
        # error (recorded, nothing saved), not a supervisor kill in the middle of a later op
        # that takes every op's result with it (runs 050552 / 050914 / 051203).
        op_fuse = op_limit(case_end) if case_end else OP_FUSE  # min(OP_FUSE, the case's time left)
        limits["ops"][f"op{index}"] = op_fuse
        panel.deadline = time.monotonic() + max(op_fuse, 0)
        try:
            po.require(op_fuse > 0, f"case fuse: less than the save's {SAVE} s left before the "
                                    f"case's end for this op")
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
            panel.deadline = None  # the error shot below is not this op's to pay for
            step["error"] = po.brief(error, 2500)
            step["op_fuse"] = fuse_of(error)
            if step["op_fuse"]:
                step["error"] = f"op fuse ({op_fuse} s): {step['error']}"
            try:  # what the page showed where the op stopped
                step["page_text_at_error"] = panel.page_text(panel.read("error"))[:60]
            except RuntimeError as failure:
                step["page_text_at_error"] = f"<not read: {po.brief(failure, 200)}>"
            stopped = step
        finally:
            for name in ("shot", "shot_prefix"):  # back to the Panel's own methods
                panel.__dict__.pop(name, None)
            panel.deadline = None
        step["seconds"] = round(time.time() - started, 1) - step["at"]
        reason = None
        if stopped:
            reason = (f"stopped at op {stopped['index']} ({stopped['op']} {stopped.get('label')}): "
                      f"{stopped['error'][:600]}")
        put_down("stopped" if stopped else "ops running", reason)
        if stopped:
            break
    result = {"status": "not passed", "scenario": case["scenario"], "case_id": case["case_id"],
              "table": case["_table"], "limits": limits}
    if stopped:
        result["reason"] = reason
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

_staged, _recorded = po.stage, po.record


def stage(work):
    """param_ops' stage plus this runner and the case table the worker reads."""
    _staged(work)
    for name in ("param_case.py", "param_cases.json"):
        shutil.copy2(po.WORK / name, work / name)


def record(result, stamp):
    """File a case under results.json `cases` (the record it replaces is kept in `cases_history`);
    any other result goes through param_ops' own record."""
    if result.get("op") != "case":
        return _recorded(result, stamp)
    path = po.EVIDENCE / "results.json"
    data = json.loads(path.read_text())
    if result.get("op") == "case" and not result.get("name"):
        result["name"] = SCENARIO
    key = ":".join(filter(None, (result["op"], result.get("name"))))
    cases = data.setdefault("cases", {})
    if key in cases:
        data.setdefault("cases_history", []).append(cases[key])
    if result.get("supervisor_error") and "status" not in result:
        result.update(status="not passed", reason="supervisor error (its fuse fired, or the launch failed): "
                      "no worker result - see supervisor_error")
    cases[key] = result
    data.setdefault("attempts", []).append({"op": key, "stamp": stamp, "ok": result["ok"]})
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")


po.stage, po.record = stage, record
SCENARIO = None  # the supervisor's own result (a timeout, a launch failure) carries no case name


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
    parser.add_argument("--fuse", type=int, help="seconds before the supervisor gives up on the "
                        "whole case (launch, ops, save); at most %d" % CASE_FUSE)
    ns = parser.parse_args(argv)
    case = load_case(ns.case)
    ns.op, ns.name = "case", ns.case
    ns.fuse = min(ns.fuse or CASE_FUSE, CASE_FUSE)
    ns.case_end = time.time() + ns.fuse  # the worker sizes each op's limit against it
    result = {"op": "case", "name": case["scenario"], "case_id": case["case_id"], "ok": False,
              "table": case["_table"], "limits": {"per_op": OP_FUSE, "case": ns.fuse}}
    if case.get("app_conf"):
        return finish({**result, "status": "needs develop mode", "app_conf": case["app_conf"]})
    blocked = unsupported(case)
    if blocked:
        return finish({**result, "status": "unsupported op", "blocked": blocked})
    ns._case = {k: v for k, v in case.items()}
    global SCENARIO
    SCENARIO = ns.case
    return po.supervise(ns)


if __name__ == "__main__":
    sys.exit(main())
