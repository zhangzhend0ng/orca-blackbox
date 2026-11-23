"""Probe, not a test case (2026-11-24): does THIS build offer any control for
the mixed-filament project settings of Feishu #288 / #289?

The two cases set mixed_filament_component_bias_enabled, mixed_color_
layer_height_a/b, mixed_filament_gradient_mode, mixed_filament_pointillism_
pixel_size / _line_gap, mixed_filament_region_collapse and mixed_filament_
surface_indentation. None of them has a row on the process pages (the
param censuses, default and develop mode). Two source trees say the only
editable key is mixed_filament_definitions (the Add Mix dialog); the rest
are written back from the project config, never from a control:

  - 2.3.5 (fa706g3 agent, Plater.cpp:6677-6698 / :6770-6778, the row editor
    with the bias spin hidden at :6824-6835)
  - 2.4.1 (host tree: update_mixed_filament_panel reads the keys at
    Plater.cpp:7387-7390 and writes the same values back at :7463-7470)

The 2.4.0 guest build has no source on either machine, so this probe
reads the build itself: the sidebar's Color Mixing panel, the four tabs
of the Add Mix dialog and the Options menu of an existing mixing entry -
every Static text, Button text, Edit value and OCR word, with the
keywords marked. Ends with param_census_done before the save phase.
"""
import json
import time

from .agent_protocol import ProtocolError

KEY_WORDS = ("bias", "gradient", "pointillism", "indent", "collapse", "layer height",
             "component", "local-z", "surface")
SIDEBAR = "Color Mixing"


def census_mix_dialog(ui):
    from harness import mix_dialog_util as mdu
    from . import process_panel as pp

    app = ui.app
    report = {"sidebar": {}, "add_mix": {}, "entry_menu": None, "keywords": list(KEY_WORDS)}

    def say(text):
        print("[mix census] " + text, flush=True)

    def dump(tag):
        """Texts the dialog shows, by four readings; keywords among them."""
        import cv2
        from harness import mixing_util
        rect = mdu.dialog_rect(app.pid, dlg)
        statics = [(t, r, vis) for t, r, _h, vis in mdu.static_texts(dlg)]
        buttons = [(t, r) for t, c, r, h in mixing_util.children(dlg)
                   if c in ("Button", "wxWindowNR") and t.strip()]
        edits = []
        for _r, h in mdu.edit_boxes(dlg):
            try:
                edits.append((h, mdu.edit_value(h)))
            except Exception as exc:  # noqa: BLE001
                edits.append((h, "unreadable: %s" % type(exc).__name__))
        words = mdu.ocr_words(dlg, scale=2)
        shot = ui.artifacts / ("mix_census_%s.png" % tag)
        try:
            cv2.imwrite(str(shot), mdu.hwnd_pixels(dlg))
        except Exception as exc:  # noqa: BLE001
            say("%s: screenshot not taken: %s" % (tag, exc))
        text = " ".join([t for t, _r, _v in statics] + [t for t, _r in buttons]
                        + [w[0] for w in words] + [str(v) for _h, v in edits]).lower()
        hits = sorted({k for k in KEY_WORDS if k in text})
        say("%s rect=%r keywords=%r statics=%r buttons=%r edits=%r ocr=%r" % (
            tag, rect, hits, [t for t, _r, _v in statics][:40],
            [t for t, _r in buttons][:30], [v for _h, v in edits][:10],
            [w[0] for w in words][:90]))
        return {"rect": rect, "statics": statics, "buttons": buttons, "edits": edits,
                "words": words, "keywords": hits, "shot": shot.name if shot.exists() else None}

    ui.main_input()
    entries = mdu.mix_entry_labels(app)
    report["sidebar"]["entries"] = [e[0] for e in entries]
    say("sidebar mixing entries: %r" % (report["sidebar"]["entries"],))
    row = mdu._sidebar_title_row(app, SIDEBAR)
    report["sidebar"]["title_row"] = bool(row)
    say("sidebar %r title row found: %s" % (SIDEBAR, bool(row)))
    img = pp.capture_bgr(app)
    side = pp.mdu.ocr_words_img(img[420:1040, 0:420], scale=2, psm=6)
    report["sidebar"]["ocr"] = [w[0] for w in side]
    side_text = " ".join(w[0] for w in side).lower()
    report["sidebar"]["keywords"] = sorted({k for k in KEY_WORDS if k in side_text})
    say("sidebar OCR keywords=%r words=%r" % (report["sidebar"]["keywords"], report["sidebar"]["ocr"][:70]))

    dlg = mdu.open_add_mix_dialog(app)
    if not dlg:
        raise ProtocolError("mix_census_dialog")
    say("Add Mix dialog hwnd=%r rect=%r" % (dlg, mdu.dialog_rect(app.pid, dlg)))
    for tab in mdu.TAB_LABELS:
        clicked = mdu.click_tab(app, dlg, tab)
        time.sleep(1.2)
        report["add_mix"][tab] = dump("add_%s" % tab.lower())
        report["add_mix"][tab]["clicked"] = bool(clicked)
    mdu.click_button(app, dlg, "Cancel")
    time.sleep(1.2)
    say("Add Mix cancelled: dialog gone=%s" % (not mdu.find_mix_dialog(app.pid, timeout_s=0.5),))

    entries = mdu.mix_entry_labels(app)
    if entries:
        menu = mdu.entry_options_menu(app, entries[0][1])
        if menu:
            report["entry_menu"] = {"entry": entries[0][0], "items": list(menu[3])}
            say("entry %r options menu: %r" % (entries[0][0], list(menu[3])))
            mdu.close_entry_menu(app)
        else:
            say("entry %r: options menu not read" % (entries[0][0],))
    else:
        say("no mixing entry in the sidebar: options menu not probed")

    found = sorted({k for tab in report["add_mix"].values() for k in tab["keywords"]}
                   | set(report["sidebar"]["keywords"]))
    report["keywords_found"] = found
    say("keywords found anywhere: %r" % (found,))
    (ui.artifacts / "mix_census.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    raise ProtocolError("param_census_done")
