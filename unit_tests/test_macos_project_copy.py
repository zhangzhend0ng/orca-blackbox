from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from runner.macos import project_copy


def test_strength_tab_rechecks_merged_label_from_the_same_frame(monkeypatch):
    frame = object()
    capture = Mock(return_value=frame)
    ocr = Mock(side_effect=[
        [{"x": 376, "y": 764, "w": 132, "h": 18, "text": "Quality Strength"}],
        [{"x": 448, "y": 764, "w": 60, "h": 18, "text": "Strength"}],
    ])
    monkeypatch.setattr(project_copy, "screen_capture", capture)
    monkeypatch.setattr(project_copy, "screen_ocr", ocr)
    monkeypatch.setattr(project_copy.time, "sleep", Mock())
    desktop = Mock()

    project_copy.go_strength(desktop, 42, "root", "window", SimpleNamespace(x=360, y=280), "copy")

    capture.assert_called_once_with("strength-tab")
    assert [call.kwargs["png"] for call in ocr.call_args_list] == [frame, frame]
    desktop.click_point.assert_called_once_with(42, "root", "window", "copy", 118, 493)


@pytest.mark.parametrize("tokens,actual", [
    (["3"], "3"),
    (["4"], "4"),
    (["5÷3"], None),
    (["3", "4"], None),
    ([], None),
])
def test_reopen_reads_only_unambiguous_numeric_value_from_same_frame(monkeypatch, tokens, actual):
    frame = object()
    capture = Mock(return_value=frame)
    ocr = Mock(side_effect=[
        [{"x": 388, "y": 830, "w": 70, "h": 18, "text": "Wall loops"},
         {"x": 590, "y": 828, "w": 48, "h": 20, "text": "5÷3"}],
        [{"text": value} for value in tokens],
    ])
    monkeypatch.setattr(project_copy, "screen_capture", capture)
    monkeypatch.setattr(project_copy, "screen_ocr", ocr)

    observed = project_copy.reopen_wall_value(SimpleNamespace(x=360, y=80))

    assert observed == actual
    capture.assert_called_once_with("reopen-strength")
    ocr.assert_called_with("reopen-strength", (624, 825, 36, 25), png=frame)
    assert [call.kwargs["png"] for call in ocr.call_args_list] == [frame, frame]
