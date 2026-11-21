"""Shared machinery for the Feishu 常用工艺参数 supplement cases.

Each case = a values dict (config keys the case may change, with target
values) plus G-code expectations the existing analyzers can prove. This
library builds verify_business implementations from such specs and keeps
the change-scope registry the settings-preservation check admits."""
from decimal import Decimal

from .agent_layer_verify import analyze_gcode
from .agent_protocol import ProtocolError
from .agent_verify import _require
from .pilot_common import _register_param_change_scope, inspect_preserved_settings
from .project_3mf import _archive, _json


def make_verify(case_id, values, *, schedule=None, ironing=None, cancelled_guard=True):
    """Build verify_business(project, fixture, gcode) for a parameter case.

    schedule: dict(layer_count=..., last_z=...) when the case leaves object
    geometry unchanged (the standard cube keeps 68 x 0.4 / 27.2).
    ironing: dict(speed_comment=..., min_moves=...) to require ironing
    moves and the configured speed via analyze_gcode's ironing inspection.
    """
    _register_param_change_scope(values)

    def verify_business(project: bytes, fixture: bytes, gcode: bytes, *, cancelled=lambda: False) -> dict:
        actual, original = (_json(a["Metadata/project_settings.config"])
                            for a in (_archive(project, cancelled), _archive(fixture, cancelled)))
        inspect_preserved_settings(actual, original, allowed_changes=values, cancelled=cancelled)
        result = {"case_id": case_id, "other_settings_preserved": True}
        for key, want in values.items():
            got = actual.get(key)
            _require(Decimal(str(got)) == Decimal(str(want)) if _numeric(want) else got == want,
                     "param_value:" + key)
            result[key] = got
        if schedule or ironing:
            layers = analyze_gcode(gcode, layer_height=str(actual.get("layer_height", "0.4")),
                                   first_layer_height=str(actual.get("initial_layer_print_height", "0.4")),
                                   inspect_ironing=bool(ironing), cancelled=cancelled)
            if schedule:
                _require(layers["layer_count"] == schedule["layer_count"], "param_layer_count")
                _require(Decimal(layers["last_z"]) == Decimal(schedule["last_z"]), "param_last_z")
            if ironing:
                _require(layers.get("ironing_moves", 0) >= ironing["min_moves"], "param_ironing_moves")
            result["layer_count"] = layers["layer_count"]
            result["last_z"] = layers["last_z"]
            result["gcode_sha256"] = layers["sha256"]
        return result

    return verify_business


def _numeric(value):
    try:
        Decimal(str(value))
        return True
    except Exception:
        return False


# ---- baseline-side: declarative process-panel operations -------------------

def run_ops(ui, ops):
    """Execute a list of process-panel operations on the running app.

    op forms:
      {"tab": "Quality", ...} switches the parameter tab first;
      {"op": "float",   "label": ..., "value": ..., ["group": ...]}
      {"op": "checkbox","label": ..., "value": True, ["group": ...]}
      {"op": "combo",   "current": ..., "target": ..., ["group": ...]}
    """
    from . import process_panel as pp

    app = ui.app
    ui.main_input()
    # Without Advanced the parameter pages show summary rows only - no
    # individual float Edits (m5c precedent; runs d536b165/4fb3929a).
    pp.ensure_advanced(app, want=True)
    current_tab = None
    for op in ops:
        tab = op.get("tab") or current_tab
        if tab and tab != current_tab:
            ui.main_input()
            if not pp.click_tab(app, tab, op.get("tab_hint", "")):
                raise ProtocolError("param_tab:" + tab)
            current_tab = tab
            ui.pause(1.0)
        ui.main_input()
        kind = op["op"]
        if kind == "float":
            ok = pp.set_option_float(app, op["label"], op["value"], group_substr=op.get("group"))
            if not ok or (isinstance(ok, tuple) and not ok[0]):
                raise ProtocolError("param_float:" + op["label"])
            pp.neutralize_focus(app)
        elif kind == "checkbox":
            ok = pp.set_option_checkbox(app, op["label"], op["value"], group_substr=op.get("group"))
            if ok is not True and not (isinstance(ok, tuple) and ok[0] is True):
                raise ProtocolError("param_checkbox:" + op["label"])
        elif kind == "combo":
            ok = pp.set_combo_by_popup(app, op["current"], op["target"],
                                       group_substr=op.get("group"),
                                       log="[param case]")
            if not ok:
                raise ProtocolError("param_combo:" + op["target"])
        else:
            raise ProtocolError("param_op:" + str(kind))
        ui.pause(1.0)
    ui.pause(6)
    ui.main_input()
