"""The extruder popup read by position (harness.param_combo_row.extruder_row_point).

The words are the OCR of a real popup: fa706g3 / guest runs 1f8a4309 and
f7f796f6, 2026-11-24 - a fixture whose five filaments are all PLA. The popup
was (246, 795, 366, 975): 'Default' then '1 PLA' .. '5 PLA', six rows of
30 px; the '1 PLA' row itself was not read, the others lost or mangled their
digit."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.param_combo_row import _popup_lines, extruder_row_point

POPUP = (246, 795, 366, 975)
CAPTURE = [("Default", 27, 8, 58, 14), ("2)", 26, 65, 12, 14), ("PLA", 52, 69, 24, 14),
           ("By", 26, 95, 16, 14), ("PLA", 52, 99, 24, 14), ("4", 31, 129, 10, 14),
           ("PLA", 52, 129, 24, 14), ("PLA", 52, 159, 24, 14)]


def test_lines_are_grouped_by_y_and_read_left_to_right():
    with_noise = CAPTURE + [("~", 9, 12, 10, 14)]
    assert _popup_lines(with_noise) == [(17, "~ Default"), (74, "2) PLA"), (104, "By PLA"),
                                        (136, "4 PLA"), (166, "PLA")]


def test_first_extruder_is_the_second_row_of_a_six_row_list():
    x, y = extruder_row_point(CAPTURE, POPUP, "1 PLA")
    assert (x, y) == (60, 45)          # entry 1 of six: its row spans 30..60


def test_entry_number_selects_the_row():
    assert extruder_row_point(CAPTURE, POPUP, "3 PLA")[1] == 105
    assert extruder_row_point(CAPTURE, POPUP, "5 PLA")[1] == 165


def test_an_entry_the_list_does_not_have_is_refused():
    assert extruder_row_point(CAPTURE, POPUP, "6 PLA") is None
    assert extruder_row_point(CAPTURE, POPUP, "0 PLA") is None


def test_a_target_that_is_not_an_extruder_entry_is_refused():
    assert extruder_row_point(CAPTURE, POPUP, "By object") is None
    assert extruder_row_point(CAPTURE, POPUP, "PETG") is None
    assert extruder_row_point(CAPTURE, POPUP, "1 Snapmaker PLA") is None


def test_a_list_that_does_not_start_with_default_is_refused():
    default_last = CAPTURE[1:] + [("Default", 27, 199, 58, 14)]
    assert extruder_row_point(default_last, POPUP, "1 PLA") is None


def test_rows_of_another_type_are_refused():
    mixed = [("Default", 27, 8, 58, 14), ("PETG", 52, 39, 40, 14), ("PLA", 52, 69, 24, 14),
             ("PLA", 52, 99, 24, 14)]
    assert extruder_row_point(mixed, POPUP, "1 PLA") is None


def test_rows_off_the_grid_are_refused():
    off = CAPTURE + [("PLA", 52, 144, 24, 14)]                # a line 15 px off its seat
    assert extruder_row_point(off, POPUP, "1 PLA") is None


def test_the_popup_height_must_be_whole_rows_of_the_read_pitch():
    # 210 px: seven rows of 30 - a seventh row OCR did not read; still the list
    assert extruder_row_point(CAPTURE, (246, 795, 366, 1005), "1 PLA") == (60, 45)
    # 200 px read as seven rows would put the last read row a quarter row off
    # its seat
    assert extruder_row_point(CAPTURE, (246, 795, 366, 995), "1 PLA") is None


def test_too_few_read_rows_to_anchor_the_pitch_are_refused():
    thin = [CAPTURE[0], ("PLA", 52, 69, 24, 14)]
    assert extruder_row_point(thin, POPUP, "1 PLA") is None


def test_no_entry_beyond_the_last_row_ocr_saw():
    # rows read: Default, 1 PLA, 2 PLA - a third entry would be extrapolated
    # past what was seen; the two that were seen are taken
    short = [("Default", 27, 8, 58, 14), ("1", 31, 39, 10, 14), ("PLA", 52, 39, 24, 14),
             ("2", 31, 69, 10, 14), ("PLA", 52, 69, 24, 14)]
    assert extruder_row_point(short, POPUP, "3 PLA") is None
    assert extruder_row_point(short, POPUP, "2 PLA") == (60, 75)
    assert extruder_row_point(short, POPUP, "1 PLA") == (60, 45)
