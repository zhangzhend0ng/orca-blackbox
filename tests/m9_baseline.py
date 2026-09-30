#!/usr/bin/env python3
# m9_baseline.py — LOCAL baseline gcode export for the cloud-slicing review
# (C:\coil\云切片专项审查). One project per process.
#
#   boot with the .3mf on the command line (hands-off auto-load) -> click
#   Slice -> wait for the done rendering -> export PLAIN .gcode (not
#   .gcode.3mf) -> verify the exported header against the settings the
#   PROJECT ITSELF carries (Metadata/project_settings.config).
#
# MULTI-PLATE projects take a different road: the old hover-click plate
# switch exported the SAME plate twice (byte-identical plate1/plate2,
# measured 09-17/18). Instead: Slice all mode (m3f) -> File > Export >
# 'Export all plate sliced file' -> one .gcode.3mf embedding every plate's
# Metadata/plate_N.gcode (the same shape the cloud engine emits) -> unpack
# to per-plate plain .gcode artifacts and verify each, asserting the
# plates DIFFER.
#
# NOT a regression case: a one-off artifact producer driven by
# tools/baseline_batch.py. No setting is ever written — the only app
# interactions are Slice and the export dialogs.
#
# Verification is post-hoc on the exported file, because that is the ground
# truth of what the slicer actually used AND the same basis the cloud review
# used (gcode '; key = value' echoes vs the input project config), keeping
# local and cloud outputs apples-to-apples.

import argparse
import json
import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent  # repo root (cases live in tests/)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, gcode_check, topbar_util, winutil  # noqa: E402
from m2_slice_chain import click_slice_start, wait_slicing_done  # noqa: E402
from m3_common import add_common_args, boot_session  # noqa: E402
from m3f_multi_plate import switch_to_slice_all  # noqa: E402

# The settings the review task names as must-match, plus the printer identity
# a silent substitution would change. These decide PASS/FAIL.
REQUIRED_KEYS = [
    "nozzle_volume_type",
    "filament_volume_type",
    "brim_width",
    "nozzle_diameter",
    "layer_height",
    "skirt_loops",
    "printer_model",
    "printer_variant",
]
# Preset DISPLAY names. Reported for the record but not fatal: Orca appends the
# project filename to a preset id when it treats the project's embedded preset
# as project-scoped ("Snapmaker U1 (0.4 nozzle)(proj.3mf)") — a naming artifact
# of preset resolution, NOT a substitution to another printer.
IDENTITY_KEYS = [
    "printer_settings_id",
    "print_settings_id",
    "filament_settings_id",
]
CHECK_KEYS = REQUIRED_KEYS + IDENTITY_KEYS


def project_config(model: Path) -> dict:
    """The project's OWN settings, read straight out of the input 3mf."""
    with zipfile.ZipFile(model) as z:
        return json.loads(z.read("Metadata/project_settings.config").decode("utf-8"))


def project_plates(model: Path) -> list[int]:
    """Plate numbers the project declares. Falls back to [1] — a project
    without Metadata/plate_N.json is still a single-plate project."""
    with zipfile.ZipFile(model) as z:
        names = z.namelist()
    got = sorted({int(m.group(1)) for n in names
                  for m in [re.fullmatch(r"Metadata/plate_(\d+)\.json", n)] if m})
    return got or [1]


def norm(v) -> str:
    """Comparable form for the two encodings of the same setting.

    The project config stores extruder-keyed values as JSON arrays; the gcode
    echo carries numeric vectors comma-joined and string vectors as
    ';'-separated quoted items ('"a";"b"'). Numbers normalize across float
    formatting (0.08 vs 0.080000)."""
    if v is None:
        return ""
    if isinstance(v, (list, tuple)):
        return ",".join(norm(x) for x in v)
    s = str(v).strip()
    if ";" in s:                      # ';'-separated quoted string vector
        return ",".join(norm(p) for p in s.split(";"))
    s = s.strip().strip('"')
    try:
        return f"{float(s):g}"
    except ValueError:
        return s


def verify(gcode: bytes, expected: dict) -> dict:
    """Per-key comparison of the exported header against the project config.

    Each entry carries `ok` (value matches) and `required` (whether a
    mismatch should fail the artifact)."""
    out = {}
    for k in CHECK_KEYS:
        if k not in expected:
            continue
        got = gcode_check.config_value(gcode, k)
        exp = norm(expected.get(k))
        out[k] = {"expected": exp, "actual": got,
                  "ok": got is not None and norm(got) == exp,
                  "required": k in REQUIRED_KEYS}
    return out


def total_layers(gcode: bytes) -> int | None:
    m = re.search(rb";\s*total layer number:\s*(\d+)", gcode)
    return int(m.group(1)) if m else None


def is_plain_gcode(path: Path) -> tuple[bool, str]:
    """A .gcode that is really a zip is a .gcode.3mf wearing the wrong name."""
    try:
        head = path.open("rb").read(2)
    except OSError as e:
        return False, f"unreadable: {e}"
    if head == b"PK":
        return False, "exported artifact is a ZIP (gcode.3mf), not plain gcode"
    return True, ""


def app_toplevels(session) -> list[tuple[int, str, str]]:
    """(hwnd, class, title) for the app's visible top-level windows other than
    the main frame."""
    out = []
    for hwnd, pid in winutil.enum_windows():
        if pid != session.pid or hwnd == session.hwnd:
            continue
        if not winutil.user32.IsWindowVisible(hwnd):
            continue
        out.append((hwnd, winutil.window_class(hwnd), winutil.window_title(hwnd)))
    return out


def confirm_nozzle_dialog(session, max_rounds: int = 12) -> int:
    """Answer every stacked NOZZLE-ASSIGNMENT GATE; returns how many.

    A project whose filaments do not share ONE nozzle_volume_type (the 组合
    nozzle-mixing cases: high_flow on 1-2, standard on 3-4) makes the app open
    a modal #32770 titled 'Custom Filament Grouping' when Slice is clicked:

        "Slicing will follow the nozzle assignment below:
         Standard Nozzle: 3,4  <->  High Flow Nozzle: 1,2  [Cancel][Confirm]"

    It CONFIRMS the assignment the project already carries — not a preset
    substitution and not a normalization — so confirming is what reproduces
    the project faithfully; Cancel would abort the slice. Until it is answered
    it swallows every later click, which is why those projects failed with
    "Slice click never took" while the single-nozzle-type 基准 projects sailed
    through.

    The instances STACK — each swallowed Slice click raises another, and
    click_slice_start retries internally — so this loops until none remain
    instead of answering just the first.
    """
    answered = 0
    for _ in range(max_rounds):
        target = None
        for hwnd, cls, _title in app_toplevels(session):
            if cls != "#32770":
                continue
            for text, crect, _ch in export_util._children_texts(hwnd):
                if text.strip().lower() == "confirm":
                    target = (hwnd, crect)
                    break
            if target:
                break
        if not target:
            break
        # Resolve the button INSIDE the dialog's own tree (deepest_child_at
        # from the dialog). Without a root hwnd the click would be aimed with
        # WindowFromPoint, and the driver demotes the app to the bottom of the
        # z-order — so the click would land on whatever is actually on top.
        hwnd, crect = target
        winutil.msg_click_screen((crect[0] + crect[2]) // 2,
                                 (crect[1] + crect[3]) // 2, hwnd)
        time.sleep(0.8)
        answered += 1
    if answered:
        print(f"[m9]   nozzle-assignment gate answered x{answered}", flush=True)
    return answered


def await_slicing_done(session, timeout_s: float) -> tuple[bool, float]:
    """wait_slicing_done, but answering the nozzle gate whenever it pops."""
    deadline = time.monotonic() + timeout_s
    score = 0.0
    while time.monotonic() < deadline:
        done, score = wait_slicing_done(session, timeout_s=8.0)
        if done:
            return True, score
        if confirm_nozzle_dialog(session):
            continue
    return False, score


def ensure_sliced(session, timeout_s: float) -> tuple[bool, str]:
    """Slicing finished. Cheap when a previous attempt already succeeded —
    wait_slicing_done is asked first, so a retry after a failed EXPORT does
    not needlessly re-slice."""
    confirm_nozzle_dialog(session)
    done, _score = wait_slicing_done(session, timeout_s=8.0)
    if done:
        return True, ""
    started = click_slice_start(session)
    # the gate is raised by that very click and then swallows the button state
    confirm_nozzle_dialog(session)
    done, score = await_slicing_done(session, timeout_s)
    if not done:
        return False, (f"slicing never completed (best score {score:.3f})"
                       if started else
                       "Slice click never took (button stayed idle)")
    return True, ""


def slice_and_export(session, out_path: Path, timeout_s: float,
                     attempts: int = 4) -> tuple[bool, str]:
    """Slice then export, retrying the whole step.

    The retry is required, not defensive: export_util sends the save dialog's
    IDOK through SendMessageTimeout, so a briefly busy app LOSES the click and
    wait_file reports no artifact — the failure mode its own header documents
    as "bounded, resolvable on the next run". A VM guest (software GL, slower
    disk) trips it often enough that one-shot export is not viable there."""
    why = "no attempt made"
    for a in range(1, attempts + 1):
        ok, why = ensure_sliced(session, timeout_s)
        if not ok:
            print(f"[m9]   attempt {a}: {why}", flush=True)
            time.sleep(5.0)
            continue
        time.sleep(2.0)  # let the done rendering settle before the toolbar click
        confirm_nozzle_dialog(session)
        if export_util.export_gcode(session, out_path, timeout_s=120.0):
            return True, ""
        why = "export gcode dialog/file did not land"
        print(f"[m9]   attempt {a}: {why}", flush=True)
        confirm_nozzle_dialog(session)
        time.sleep(5.0)
    return False, why


def slice_all_mode(session) -> bool:
    """Switch the Slice button into 'Slice all' mode and click it.

    Mode switch is m3f's (dropdown rows 'Slice all' / 'Slice plate'); the
    main button is then located by enumeration because the 'Slice all'
    label breaks the idle template m2's click_slice_start matches
    (m3f measured 0.64)."""
    if not switch_to_slice_all(session):
        return False
    _opt, main = export_util.find_slice_buttons(session.hwnd)
    if not main:
        return False
    winutil.msg_click_screen((main[1][0] + main[1][2]) // 2,
                             (main[1][1] + main[1][3]) // 2, session.hwnd)
    return True


def export_all_sliced(session, out_path: Path, timeout_s: float = 180.0) -> bool:
    """File > Export > 'Export all plate sliced file' -> save dialog -> path.

    The row is the export_menu entry wired to EVT_GLTOOLBAR_EXPORT_ALL_
    SLICED_FILE (Mainframe.cpp:2621) -> Plater::export_gcode_3mf(true):
    one .gcode.3mf embedding Metadata/plate_N.gcode for EVERY plate. The
    gate (can_export_all_gcode) demands all slice results ready, so this
    only runs after a Slice all. Activation sends the row's WM_COMMAND id
    straight to the frame — an artifact producer does not need real-click
    geometry probing. The save dialog is the same native dialog the
    per-plate export drives: path into the Edit, WM_COMMAND IDOK on the
    dialog."""
    if out_path.exists():
        out_path.unlink()  # wxFD_OVERWRITE_PROMPT would stack a second dialog
    menu = topbar_util.open_file_menu(session)
    if not menu:
        print("[m9]   File menu did not open", flush=True)
        return False
    rect, hwnd, hmenu = menu
    exp_idx = topbar_util.find_item(hmenu, "Export")
    if exp_idx is None:
        topbar_util.close_menu_windows(session.pid)
        print("[m9]   Export submenu row not found", flush=True)
        return False
    topbar_util.hover_row(rect, len(topbar_util.menu_items(hmenu)), exp_idx)
    sub = topbar_util.wait_submenu(session.pid, {hwnd}, timeout_s=5.0)
    if not sub:
        topbar_util.close_menu_windows(session.pid)
        print("[m9]   Export submenu did not open", flush=True)
        return False
    _srect, _shwnd, shmenu = sub
    row_idx = topbar_util.find_item(shmenu, "Export all plate sliced file")
    if row_idx is None:
        rows = [t for t, _r, _h in topbar_util.menu_items(shmenu)]
        topbar_util.close_menu_windows(session.pid)
        print(f"[m9]   'Export all plate sliced file' not in submenu: {rows}",
              flush=True)
        return False
    topbar_util.activate_menu_item(session, shmenu, row_idx)
    dlg = export_util.wait_save_dialog(session.pid, timeout_s=15.0)
    if not dlg:
        print("[m9]   save dialog did not appear", flush=True)
        topbar_util.close_menu_windows(session.pid)
        return False
    edit = export_util.find_edit(dlg[3])
    if edit is None:
        print("[m9]   save dialog has no filename edit", flush=True)
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(out_path))
    winutil._send_msg(dlg[3], 0x0111, 1, 0)  # WM_COMMAND, IDOK = 1
    return export_util.wait_file(out_path, timeout_s=timeout_s)


def extract_plates(out3mf: Path, outdir: Path, stem: str,
                   expected: dict) -> list[dict]:
    """Unpack Metadata/plate_N.gcode out of the export-all .gcode.3mf into
    the per-plate plain-gcode artifacts the batch expects, then run the
    same per-key checks as the single-plate path. Consecutive plates must
    DIFFER: two identical files mean the container carries one plate twice
    — the silent failure mode of the old hover-click plate switch."""
    datas: dict[int, bytes] = {}
    with zipfile.ZipFile(out3mf) as z:
        for n in z.namelist():
            m = re.fullmatch(r"Metadata/plate_(\d+)\.gcode", n)
            if m:
                datas[int(m.group(1))] = z.read(n)
    entries: list[dict] = []
    if not datas:
        return [{"plate": 0, "path": str(out3mf), "ok": False,
                 "error": "no Metadata/plate_N.gcode inside the export-all 3mf"}]
    last: tuple[int, bytes] | None = None
    for plate in sorted(datas):
        data = datas[plate]
        out = outdir / f"{stem}-plate{plate}-baseline.gcode"
        out.write_bytes(data)
        entry: dict = {"plate": plate, "path": str(out), "size": len(data),
                       "plain_gcode": True,
                       "bytes_note": f"extracted from {out3mf.name}",
                       "layers": total_layers(data),
                       "checks": verify(data, expected)}
        bad = [f"{k}={c['actual']!r}(want {c['expected']!r})"
               for k, c in entry["checks"].items()
               if not c["ok"] and c["required"]]
        entry["identity_notes"] = [
            f"{k}: {c['actual']!r} vs input {c['expected']!r}"
            for k, c in entry["checks"].items()
            if not c["ok"] and not c["required"]]
        if last is not None and data == last[1]:
            bad.append(f"identical to plate {last[0]} — one plate exported twice")
        entry["ok"] = not bad
        entry["error"] = "" if not bad else ("verification failed: " + ", ".join(bad))
        entries.append(entry)
        last = (plate, data)
    return entries


def run_multi_plate(session, outdir: Path, stem: str, expected: dict,
                    plates: list[int], timeout_s: float,
                    attempts: int = 3) -> list[dict]:
    """Slice ALL plates once, export them in one .gcode.3mf, unpack.

    Replaces the old hover-click plate switch: that exported the SAME
    plate twice on 09-17/18 (byte-identical plate1/plate2 files) because
    the canvas switch silently never took. Slice all (m3f-proven) +
    'Export all plate sliced file' involve no canvas interaction at all."""
    out3mf = outdir / f"{stem}-baseline.gcode.3mf"
    why = "no attempt made"
    for a in range(1, attempts + 1):
        confirm_nozzle_dialog(session)
        if not slice_all_mode(session):
            why = "Slice all mode/button not found"
            print(f"[m9]   attempt {a}: {why}", flush=True)
            time.sleep(5.0)
            continue
        done, score = await_slicing_done(session, timeout_s)
        if not done:
            why = f"slice-all never completed (best score {score:.3f})"
            print(f"[m9]   attempt {a}: {why}", flush=True)
            confirm_nozzle_dialog(session)
            time.sleep(5.0)
            continue
        time.sleep(2.0)
        confirm_nozzle_dialog(session)
        if export_all_sliced(session, out3mf):
            entries = extract_plates(out3mf, outdir, stem, expected)
            for e in entries:
                print(f"[m9] plate {e['plate']}: ok={e['ok']} {e['error']}",
                      flush=True)
            return entries
        why = "export-all save dialog/file did not land"
        print(f"[m9]   attempt {a}: {why}", flush=True)
        confirm_nozzle_dialog(session)
        time.sleep(5.0)
    return [{"plate": p, "path": str(outdir / f"{stem}-plate{p}-baseline.gcode"),
             "ok": False, "error": f"multi-plate export failed: {why}"}
            for p in plates]


def hover_click_client(session, cx: int, cy: int) -> None:
    """Move the cursor over a CLIENT point (posted WM_MOUSEMOVE) and click it.

    The 3D canvas only selects a plate when m_hover_plate_idxs is already
    populated, and that happens on mouse MOVE (GLCanvas3D.cpp:8138 —
    SceneRaycaster Bed hit): a bare click is not enough. A physical
    SetCursorPos cannot be used either, because the driver demotes the app to
    the bottom of the z-order and real motion lands on the window on top.
    """
    x, y = winutil.client_to_screen(session.hwnd, cx, cy)
    child = winutil.deepest_child_at(session.hwnd, x, y) or session.hwnd
    lparam = ((cy & 0xFFFF) << 16) | (cx & 0xFFFF)
    for _ in range(3):
        winutil._send_msg(child, 0x0200, 0, lparam)  # WM_MOUSEMOVE
        time.sleep(0.15)
    winutil.msg_click_screen(x, y, session.hwnd)


def select_plate(session, plate: int) -> bool:
    """Best-effort switch of the active plate on a multi-plate project.

    Plates sit side by side in the 3D scene and the canvas switches active
    plate on a hovered-then-clicked plate, so the target is a calibrated spot
    on the right half of the canvas (only one input project is multi-plate and
    its camera is fixed by the project). Whether the switch actually took is
    decided by the CALLER from the artifact: two plates that export identical
    gcode mean it did not.
    """
    w = session.rect()[2] - session.rect()[0]
    h = session.rect()[3] - session.rect()[1]
    hover_click_client(session, int(w * 0.85), int(h * 0.53))
    time.sleep(2.5)
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    add_common_args(ap, default_model=None)
    ap.add_argument("--outdir", type=Path, required=True)
    ap.add_argument("--suffix", default="-baseline.gcode")
    ap.add_argument("--timeout", type=float, default=2400.0)
    ap.add_argument("--no-shots", action="store_true",
                    help="skip the screenshot archiver. It captures a "
                         "full-screen frame every 0.5s and encodes an mp4, "
                         "which is pure overhead here and the largest memory "
                         "consumer in the run — the Hyper-V guest ran cv2 out "
                         "of commit for a 45 MB allocation with it on.")
    args = ap.parse_args()

    if args.no_shots:
        # patch BEFORE boot_session pulls it in (it does `from harness import
        # shot_archive` and calls through the module, so the attributes bind)
        import threading
        from harness import shot_archive
        shot_archive.start_archiver = lambda *a, **k: threading.Event()
        shot_archive.hook_stdout_tee = lambda *a, **k: None

    model = Path(args.model)
    stem = model.stem
    if not args.no_shots:
        # The batch runs this worker once per PROJECT, so sys.argv[0] is the
        # same "m9_baseline" for all of them and the default archive root
        # (artifacts/shots/m9_baseline/) made every project overwrite the same
        # mp4 — measured 09-18: one 1.3 MB fragment survived a 6-hour run.
        # Each project gets its own directory (and its own mp4) instead.
        from harness import shot_archive
        _orig_start = shot_archive.start_archiver

        def _start_archiver(session, name, **kw):
            return _orig_start(session, f"m9_{stem}",
                               out_root=HERE / "artifacts" / "shots" / f"m9_{stem}",
                               **kw)

        shot_archive.start_archiver = _start_archiver
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    result: dict = {"model": str(model), "stem": stem, "outputs": [], "error": None}
    try:
        expected = project_config(model)
        plates = project_plates(model)
    except Exception as e:  # noqa: BLE001 — report, never abort the batch
        result["error"] = f"cannot read project: {e!r}"
        print("BASELINE_RESULT " + json.dumps(result, ensure_ascii=False))
        return 1
    result["plates"] = plates

    session = None
    try:
        session = boot_session(args, model=model, fresh=True)
        # NOTE: wait_model_loaded is deliberately NOT a gate here — it is a
        # chromatic-pixel heuristic and a low-saturation model (README
        # pitfall #8) can slip under it. Model arrival is instead PROVEN
        # downstream: an empty bed cannot slice.

        if len(plates) > 1:
            # Slice all + export-all + unpack — the plate-switch route
            # proved unreliable (see run_multi_plate).
            result["outputs"] = run_multi_plate(session, outdir, stem,
                                                expected, plates, args.timeout)
        else:
            last_artifact = None
            for i, plate in enumerate(plates):
                if i and not select_plate(session, plate):
                    result["error"] = f"could not switch to plate {plate}"
                    break
                out = outdir / (f"{stem}-plate{plate}{args.suffix}" if len(plates) > 1
                                else f"{stem}{args.suffix}")
                ok, why = slice_and_export(session, out, args.timeout)
                entry: dict = {"plate": plate, "path": str(out), "ok": ok, "error": why}
                if ok:
                    data = out.read_bytes()
                    plain, plain_why = is_plain_gcode(out)
                    entry.update(size=len(data), plain_gcode=plain, bytes_note=plain_why,
                                 layers=total_layers(data),
                                 checks=verify(data, expected))
                    bad = [f"{k}={c['actual']!r}(want {c['expected']!r})"
                           for k, c in entry["checks"].items()
                           if not c["ok"] and c["required"]]
                    entry["identity_notes"] = [
                        f"{k}: {c['actual']!r} vs input {c['expected']!r}"
                        for k, c in entry["checks"].items()
                        if not c["ok"] and not c["required"]]
                    if i and data == last_artifact:
                        bad.append("identical to plate %d — plate switch never took"
                                   % plates[i - 1])
                    entry["ok"] = plain and not bad
                    if not entry["ok"]:
                        entry["error"] = plain_why or ("verification failed: " + ", ".join(bad))
                    last_artifact = data
                result["outputs"].append(entry)
                print(f"[m9] plate {plate}: ok={entry['ok']} {entry.get('error') or ''}", flush=True)
    except Exception as e:  # noqa: BLE001 — one bad project must not stop the batch
        result["error"] = f"{type(e).__name__}: {e}"
        import traceback
        result["traceback"] = traceback.format_exc()[-2500:]
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass

    if not result["outputs"]:
        result["error"] = result["error"] or "no plate produced an artifact"
    print("BASELINE_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["outputs"] and all(o["ok"] for o in result["outputs"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
