"""The #232 popup reading: a page the default OCR reads as dividers only is read again from the
inverted picture, and both readings are returned."""
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests'), str(ROOT / 'tests' / 'engine')]

import import_configs_cases as cases  # noqa: E402

DIVIDERS = [('------ Project-inside presets ------', 10, 5, 300, 14), ('------ User presets ------', 10, 40, 170, 14)]
BOXED_ROW = [('BB', 18, 60, 22, 14), ('Test', 44, 60, 28, 14), ('Printer', 76, 60, 56, 14)]
ROWS = [('Snapmaker', 18, 25, 80, 14), ('U1', 102, 25, 18, 14), ('BB', 18, 60, 22, 14)]


def page(monkeypatch, first, second):
    """capture_window gives a blank picture; the OCR call answers `first` for the default reading
    (scale 3, psm 6) and `second` for the second one, and records every call it had."""
    calls = []
    monkeypatch.setattr(cases.winutil, 'capture_window', lambda hwnd: (404, 168, np.zeros((168, 404, 4), np.uint8).tobytes()))
    monkeypatch.setattr(cases.winutil, 'screen_grab', lambda: pytest.fail('the window was captured; no screen crop is needed'))

    def ocr(image, scale, psm):
        calls.append((image.shape[:2], scale, psm, int(image[:, :, :3].max())))
        return list(first if psm == 6 else second)
    monkeypatch.setattr(cases.m7.mdu, 'ocr_words_img', ocr)
    return calls


def test_a_page_of_dividers_only_is_read_again_from_the_inverted_picture(monkeypatch):
    calls = page(monkeypatch, DIVIDERS, BOXED_ROW)
    _image, words = cases.popup_page((0, 0, 404, 168), 77)
    assert [text for text, _word in cases.row_lines(words)] == [
        '------ Project-inside presets ------', '------ User presets ------', 'BB Test Printer']
    assert [(scale, psm) for _shape, scale, psm, _bright in calls] == [(3, 6), (3, 4)]
    assert calls[1][3] == 255 and calls[0][3] == 0  # the second reading is of the inverted picture


def test_a_page_with_rows_is_read_once(monkeypatch):
    calls = page(monkeypatch, DIVIDERS[:1] + ROWS, BOXED_ROW)
    _image, words = cases.popup_page((0, 0, 404, 168), 77)
    assert [text for text, _word in cases.row_lines(words)] == ['------ Project-inside presets ------', 'Snapmaker U1', 'BB']
    assert [(scale, psm) for _shape, scale, psm, _bright in calls] == [(3, 6)]


def test_an_empty_reading_is_not_taken_for_dividers(monkeypatch):
    assert cases.dividers_only([]) is False
    assert cases.dividers_only([('------ User presets ------', 0, 0, 10, 10)]) is True
    assert cases.dividers_only([('------ User presets ------', 0, 0, 10, 10), ('BB Test Printer', 0, 20, 10, 10)]) is False


def test_a_screen_crop_is_read_the_same_way(monkeypatch):
    calls = page(monkeypatch, DIVIDERS, BOXED_ROW)
    monkeypatch.setattr(cases.winutil, 'capture_window', lambda hwnd: (_ for _ in ()).throw(OSError('not captured')))
    monkeypatch.setattr(cases.winutil, 'screen_grab',
                        lambda: (1920, 1080, np.zeros((1080, 1920, 4), np.uint8).tobytes()))
    image, words = cases.popup_page((100, 100, 504, 268), 77)
    assert image.shape[:2] == (168, 404) and len(calls) == 2 and len(words) == len(DIVIDERS) + len(BOXED_ROW)
