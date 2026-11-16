"""Regression checks for m5 control flow, without importing Win32/GUI drivers.

Compile the production function definitions with fake collaborators. This
exercises the real function bodies while avoiding m5_common's GUI-heavy
imports and sys.path mutation. GUI integration still requires the guest rig.
"""

import ast
import itertools
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


RECT = (10, 20, 100, 200)
DELETE_ALL = [("Delete", 1, 2, 5, 10), ("All", 12, 2, 6, 10)]


@pytest.fixture
def driver():
    source = Path(os.environ.get(
        "M5_COMMON_SOURCE",
        str(Path(__file__).resolve().parents[1] / "tests" / "m5_common.py")))
    parsed = ast.parse(source.read_text(encoding="utf-8-sig"))
    names = {"_seq_point", "_delete_row_point", "menu_click",
             "delete_all_models", "boot_cube_session"}
    functions = [node for node in parsed.body
                 if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in functions} == names
    env = {
        "LOG": "[m5]", "sys": sys,
        "time": SimpleNamespace(sleep=Mock(), monotonic=Mock(
            side_effect=itertools.count())),
        "winutil": SimpleNamespace(
            user32=SimpleNamespace(SetCursorPos=Mock(), ShowWindow=Mock()),
            real_click_screen=Mock(), window_rect=Mock(
                return_value=(0, 0, 2000, 1080))),
        "mdu": SimpleNamespace(_send_keys=Mock()),
        "capture_bgr": Mock(return_value=object()),
        "has_colored_content": Mock(return_value=0.0),
        "open_plate_menu": Mock(return_value=(RECT, DELETE_ALL)),
        "pp": SimpleNamespace(relocate_wizard=Mock(return_value=True)),
        "add_shape": SimpleNamespace(add_primitive=Mock(return_value=True)),
        "wait_model_loaded": Mock(return_value=(True, 0.1)),
        "MIXED_3MF": Path("fixture.3mf"),
    }
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(source), "exec"), env)
    return env


@pytest.mark.parametrize("menu", [(None, None), (RECT, None), (RECT, [])],
                         ids=["no-menu", "no-ocr", "empty-ocr"])
def test_menu_click_unavailable_menu_never_clicks(driver, menu):
    driver["open_plate_menu"].return_value = menu
    assert driver["menu_click"](object(), ("Delete", "All")) is False
    driver["winutil"].real_click_screen.assert_not_called()


def test_menu_click_valid_row_uses_screen_coordinates(driver):
    assert driver["menu_click"](object(), ("Delete", "All")) is True
    driver["winutil"].real_click_screen.assert_called_once_with(11, 27)


def test_menu_click_no_ocr_dismisses_existing_menu_when_requested(driver):
    driver["open_plate_menu"].return_value = (RECT, None)
    assert driver["menu_click"](object(), ("Delete",)) is False
    assert driver["mdu"]._send_keys.call_count == 2


@pytest.mark.parametrize("menu", [(None, None), (RECT, None), (RECT, [])],
                         ids=["no-menu", "no-ocr", "empty-ocr"])
def test_delete_missing_menu_has_bounded_retries_and_cannot_pass_on_blank_frame(
        driver, menu):
    driver["open_plate_menu"].return_value = menu
    assert driver["delete_all_models"](object()) is False
    assert driver["open_plate_menu"].call_count == 3
    driver["winutil"].real_click_screen.assert_not_called()


def test_delete_does_not_substitute_select_all_for_delete(driver):
    driver["open_plate_menu"].return_value = (
        RECT, [("Select", 1, 2, 5, 10), ("All", 12, 2, 6, 10)])
    assert driver["delete_all_models"](object()) is False
    driver["winutil"].real_click_screen.assert_not_called()


def test_delete_clicked_row_then_observed_empty_plate_passes(driver):
    assert driver["delete_all_models"](object()) is True
    driver["winutil"].real_click_screen.assert_called_once_with(11, 27)
    assert driver["open_plate_menu"].call_count == 1


def test_delete_nonempty_plate_after_all_attempts_fails(driver):
    driver["has_colored_content"].return_value = 0.1
    assert driver["delete_all_models"](object(), timeout_s=1) is False
    assert driver["open_plate_menu"].call_count == 3


@pytest.fixture
def boot_driver(driver):
    session = SimpleNamespace(hwnd=123, close=Mock())
    driver["boot_session"] = Mock(return_value=session)
    driver["delete_all_models"] = Mock(return_value=True)
    return driver, session


@pytest.mark.parametrize("stage", ["relocate", "wait", "delete", "add", "rect"])
def test_boot_setup_exception_closes_owned_session_and_propagates(boot_driver, stage):
    env, session = boot_driver
    original = RuntimeError("setup stage failed")
    stages = {
        "relocate": env["pp"].relocate_wizard,
        "wait": env["wait_model_loaded"],
        "delete": env["delete_all_models"],
        "add": env["add_shape"].add_primitive,
        "rect": env["winutil"].window_rect,
    }
    stages[stage].side_effect = original
    with pytest.raises(RuntimeError, match="setup stage failed") as caught:
        env["boot_cube_session"](object())
    assert caught.value is original
    session.close.assert_called_once_with()


def test_boot_cleanup_error_is_reported_without_masking_original(boot_driver, capsys):
    env, session = boot_driver
    original = ValueError("bad setup")
    env["delete_all_models"].side_effect = original
    session.close.side_effect = RuntimeError("close failed")
    with pytest.raises(ValueError, match="bad setup") as caught:
        env["boot_cube_session"](object())
    assert caught.value is original
    assert "setup cleanup failed" in capsys.readouterr().err
    session.close.assert_called_once_with()


def test_boot_unloaded_model_closes_and_never_deletes(boot_driver):
    env, session = boot_driver
    env["wait_model_loaded"].return_value = (False, 0.0)
    assert env["boot_cube_session"](object()) == (session, False)
    env["delete_all_models"].assert_not_called()
    session.close.assert_called_once_with()


def test_boot_normal_failure_does_not_retry_failed_close(boot_driver):
    env, session = boot_driver
    env["delete_all_models"].return_value = False
    session.close.side_effect = RuntimeError("close failed")
    with pytest.raises(RuntimeError, match="close failed"):
        env["boot_cube_session"](object())
    session.close.assert_called_once_with()


def test_boot_success_transfers_live_session_to_case(boot_driver):
    env, session = boot_driver
    assert env["boot_cube_session"](object()) == (session, True)
    session.close.assert_not_called()
    env["add_shape"].add_primitive.assert_called_once_with(session, "Cube")
