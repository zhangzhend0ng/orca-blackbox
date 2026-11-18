"""Scoped UIA readback and drawn input for the verified Add Mix surfaces."""
import time

from .agent_verify import _require
from .native_mix_badges import ROW_HEIGHT, popup_slots, selected_slot
from .native_save_policy import MIX_CHOICES, MIX_DIALOG, validate_uia_selector
from .native_uia_hybrid import OBSERVATION_LIMIT_NS, within

OPEN_MIX = {"control_type": "ButtonControl", "automation_id": "-31825", "name": ""}
DRAWN = {"ratio": "Ratio", "gradient": "Gradient", "confirm": "OK"}
DESKTOP = [0, 0, 1920, 1080]


def choice_near_combo(box, combo):
    return (within(DESKTOP, box) and abs(box[0] - combo[0]) <= 4 and abs(box[2] - combo[2]) <= 4
            and 100 <= box[3] - box[1] <= 140
            and min(abs(box[1] - combo[3]), abs(box[3] - combo[1])) <= 14)


def legacy_action(item):
    query = getattr(item, "GetLegacyIAccessiblePattern", None)
    pattern = query() if query is not None else None
    if pattern is None or not callable(getattr(pattern, "DoDefaultAction", None)):
        return None
    value = getattr(pattern, "DefaultAction", "")
    return pattern if type(value) is str and value.strip() else None


class MixSurface:
    def __init__(self, guard):
        self.guard = guard
        self.opened = None
        self.dialog = None
        self.combo = None
        self.observed = {}
        self.choices = None
        self.selected = False

    def opened_from_sidebar(self):
        self.opened = time.monotonic_ns()

    def surface(self, wu, hwnd):
        from win32gui import GetAncestor, GetWindow, IsWindowVisible

        main, pid = self.guard.scope["hwnd"], self.guard.scope["app_pid"]
        if hwnd == main:
            self.dialog = self.combo = None
            self.choices = None
            self.selected = False
            return None
        if wu._window_pid(hwnd) != pid or not IsWindowVisible(hwnd) or GetAncestor(hwnd, 3) != main:
            return None
        owner = GetWindow(hwnd, 4)
        kind, title, box = wu.window_class(hwnd), wu.window_title(hwnd), list(wu.window_rect(hwnd))
        if not within(DESKTOP, box):
            return None
        if kind == "#32770" and title == "Add Mix" and owner == main:
            if self.dialog is None and self.opened is not None and time.monotonic_ns() - self.opened <= OBSERVATION_LIMIT_NS:
                self.dialog = hwnd
                self.opened = None
            if self.dialog != hwnd or not (350 <= box[2] - box[0] <= 450 and 600 <= box[3] - box[1] <= 800):
                return None
            role = MIX_DIALOG
        elif (kind == "wxWindowNR" and title == "panel" and owner == self.dialog and self.combo
              and IsWindowVisible(owner) and wu._window_pid(owner) == pid and wu.window_title(owner) == "Add Mix"
              and choice_near_combo(box, self.combo) and within(list(wu.window_rect(owner)), self.combo)):
            role = MIX_CHOICES
        else:
            return None
        return dict(role=role, hwnd=hwnd, owner=owner, root_owner=main, dialog=self.dialog, bounds=box,
                    kind=kind, title=title, combo=self.combo if role == MIX_CHOICES else None)

    def controls(self, wu, proof):
        from win32gui import IsChild

        if proof["role"] != MIX_DIALOG:
            return {}, []
        hwnd = proof["hwnd"]
        controls, duplicates, status, panes = {}, set(), [], []
        labels = {}
        for item in self.guard._elements(hwnd):
            handle, name = item.NativeWindowHandle, item.Name or ""
            if (not handle or not IsChild(hwnd, handle) or wu._window_pid(handle) != self.guard.scope["app_pid"]
                    or not item.IsEnabled or item.IsOffscreen):
                continue
            rect = item.BoundingRectangle
            bounds = [rect.left, rect.top, rect.right, rect.bottom]
            if not within(proof["bounds"], bounds):
                continue
            if item.ControlTypeName == "TextControl":
                if name in {"Filament 1", "Filament 2"}:
                    labels[name] = bounds
                elif name == "50%" or "cannot be mixed" in name:
                    status.append(name)
            elif item.ControlTypeName == "PaneControl" and name:
                # These named panes were measured without an actionable pattern.
                target = dict(name=name, automation_id=item.AutomationId or "", control_type="PaneControl")
                validate_uia_selector(target, "PaneControl")
                record = dict(target=target, hwnd=handle, bounds=bounds,
                              backend="LegacyDefaultAction" if legacy_action(item) is not None else "UiaBoundsClick")
                for role, expected in DRAWN.items():
                    if name == expected:
                        if role in controls:
                            duplicates.add(role)
                        controls[role] = record
                if 180 <= bounds[2] - bounds[0] <= 280 and 24 <= bounds[3] - bounds[1] <= 38:
                    panes.append(record)
        for label, filament in labels.items():
            row = [rec for rec in panes if rec["bounds"][0] >= filament[2]
                   and rec["bounds"][1] <= filament[1] < filament[3] <= rec["bounds"][3]]
            if len(row) == 1:
                controls["filament" + label[-1]] = row[0]
        return {key: value for key, value in controls.items() if key not in duplicates}, status

    def check(self, wu, hwnd, name, args):
        from win32gui import IsChild

        proof = self.surface(wu, hwnd)
        if proof is None:
            return None
        guard = self.guard
        guard.needs_main_snapshot = True
        role, box = proof["role"], proof["bounds"]
        window = dict(mix_surface=proof, app_pid=guard.scope["app_pid"], foreground_hwnd=hwnd,
                      foreground_pid=guard.scope["app_pid"], route="mix_tree")
        if name == "Snapshot":
            return window
        if name != "Click":
            raise ValueError("native_mix_requires_click")
        if role == MIX_DIALOG:
            key, control = self.resolve(wu, proof, args)
            if key == "confirm" and not self.selected:
                raise ValueError("native_mix_choice_readback_required")
            guard._clear_visual()
            return dict(window, route="mix_property", mix_control=dict(control, role=key),
                        target_hwnd=control["hwnd"], target_pid=guard.scope["app_pid"])
        if (args != {"mix_role": "filament3"} or self.choices is None or self.choices[0] != proof
                or 3 not in self.choices[1] or time.monotonic_ns() - self.choices[2] > OBSERVATION_LIMIT_NS):
            raise ValueError("native_mix_choice_not_observed")
        return dict(window, route="mix_badge", target_hwnd=hwnd, target_pid=guard.scope["app_pid"])

    def resolve(self, wu, proof, args):
        hits = [(key, rec) for key, rec in self.controls(wu, proof)[0].items()
                if key != "filament2" and rec == self.observed.get(key)
                and (args.get("mix_role") == key or args.get("target") == rec["target"])]
        if len(hits) != 1:
            raise ValueError("native_mix_uia_target_not_observed")
        return hits[0]

    def perform_click(self, wu, proof, arguments, window):
        from win32gui import IsChild

        key, control = self.resolve(wu, proof, arguments)
        if dict(control, role=key) != window["mix_control"]:
            raise ValueError("native_mix_uia_target_changed")
        handle = control["hwnd"]
        rect = control["bounds"]
        point = ((rect[0] + rect[2]) // 2, (rect[1] + rect[3]) // 2)
        self.guard.check_revocation()
        if control["backend"] == "LegacyDefaultAction":
            element = self.guard.control_from_handle(handle)
            action = legacy_action(element)
            if action is None:
                raise ValueError("native_mix_legacy_action_changed")
            action.DoDefaultAction()
        else:
            hit = wu.window_from_screen_point(*point)
            if hit != handle and (not hit or not IsChild(handle, hit)):
                raise ValueError("native_mix_property_click_occluded")
            if wu.real_click_screen(*point) != 2:
                raise ValueError("native_mix_property_click_failed")
        self.combo = control["bounds"] if key == "filament1" else None
        self.selected = False
        self.choices = None
        self.observed = {}
        return dict(target=control["target"], role=key, backend=control["backend"])

    def observed_slots(self, proof):
        from PIL import ImageGrab

        with ImageGrab.grab(bbox=tuple(proof["bounds"])) as image:
            return popup_slots(image)

    def select_filament(self, wu, proof, window):
        from PIL import ImageGrab

        slots = self.observed_slots(proof)
        if self.choices is None or slots != self.choices[1]:
            raise ValueError("native_mix_choice_changed")
        left, top, right, _ = proof["bounds"]
        point = [(left + right) // 2, top + ROW_HEIGHT * slots.index(3) + ROW_HEIGHT // 2]
        self.guard.check_revocation()
        if self.surface(wu, wu.user32.GetForegroundWindow()) != proof or wu.window_from_screen_point(*point) != proof["hwnd"]:
            raise ValueError("native_mix_choice_owner")
        if wu.real_click_screen(*point) != 2:
            raise ValueError("native_mix_choice_click_failed")
        self.choices = None
        self.combo = None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            self.guard.check_revocation()
            hwnd = wu.user32.GetForegroundWindow()
            if hwnd != proof["dialog"]:
                time.sleep(.05)
                continue
            dialog = self.surface(wu, hwnd)
            controls, _ = self.controls(wu, dialog) if dialog else ({}, [])
            if not {"filament1", "filament2", "confirm"} <= controls.keys():
                time.sleep(.05)
                continue
            try:
                selected = [selected_slot(controls[role]["bounds"], ImageGrab.grab) for role in ("filament1", "filament2")]
            except ValueError:
                time.sleep(.05)
                continue
            if selected == [3, 2]:
                window.update(mix_choices=slots, mix_point=point, mix_readback=selected)
                self.selected = True
                return {"selected_filaments": selected, "backend": "LocalBadgeTemplate"}
            time.sleep(.05)
        raise ValueError("native_mix_choice_readback")

    def describe(self, wu, proof, window):
        if proof["role"] == MIX_CHOICES:
            slots = self.observed_slots(proof)
            self.choices = (proof, slots, time.monotonic_ns())
            window["mix_choices"] = slots
            return {"window": proof["title"], "filament_slots": slots,
                    "state": "Use Click with mix_role=filament3 to choose F3 and read back both slots."}
        controls, status = self.controls(wu, proof)
        self.observed = controls
        window["mix_controls"] = controls
        return {"window": proof["title"],
                "controls": [{"role": role, **control} for role, control in controls.items()],
                "status": status, "state": "Click an observed control by mix_role or exact target. Snapshot after every click."}


class MixTrace:
    """Verify the two owned-dialog lifecycles independently of live handles."""
    def __init__(self, run_id, pid, main):
        self.run_id, self.pid, self.main = run_id, pid, main
        self.opened = None
        self.dialog = None
        self.combo = None
        self.choices = None
        self.controls = None
        self.selected = False
        self.property_actions = 0
        self.badge_actions = 0
        self.modes = []
        self.mode = None
        self.confirmed = False

    def record(self, row, counts):
        tool, args, window = row["tool"], row["arguments"], row["window"]
        route = window.get("route")
        if route not in {"mix_tree", "mix_property", "mix_badge"}:
            if tool == "Snapshot" and window.get("foreground_hwnd") == self.main and self.dialog is not None:
                _require(self.confirmed, "native_mix_unconfirmed_dialog_exit")
                self.dialog = self.combo = self.choices = self.controls = None
                self.confirmed = False
                self.selected = False
            if tool == "Click" and args.get("target") == OPEN_MIX:
                _require(route == "uia_action" and self.dialog is None and self.opened is None,
                         "native_mix_opening_receipt")
                self.opened = row["finished_at_ns"]
            return False
        proof = window["mix_surface"]
        role, box = proof["role"], proof["bounds"]
        _require(row["run_id"] == self.run_id and not self.confirmed and within(DESKTOP, box)
                 and window["foreground_pid"] == window["app_pid"] == self.pid
                 and window["foreground_hwnd"] == proof["hwnd"] and proof["root_owner"] == self.main,
                 "native_mix_surface_receipt")
        if role == MIX_DIALOG:
            _require(proof["kind"] == "#32770" and proof["title"] == "Add Mix"
                     and proof["owner"] == self.main and proof["dialog"] == proof["hwnd"], "native_mix_dialog_receipt")
            if self.dialog is None:
                _require(self.opened is not None and 0 <= row["started_at_ns"] - self.opened <= OBSERVATION_LIMIT_NS,
                         "native_mix_opening_receipt")
                self.opened = None
                self.dialog, self.mode = proof["hwnd"], "ratio"
            _require(self.dialog == proof["hwnd"], "native_mix_dialog_receipt")
        else:
            _require(role == MIX_CHOICES and self.dialog == proof["dialog"] == proof["owner"]
                     and proof["kind"] == "wxWindowNR" and proof["title"] == "panel"
                     and self.combo is not None and proof["combo"] == self.combo and choice_near_combo(box, self.combo),
                     "native_mix_choices_receipt")
        if route == "mix_tree":
            _require(tool == "Snapshot" and not args, "native_mix_tree_receipt")
            if role == MIX_CHOICES:
                slots = window["mix_choices"]
                _require(len(slots) == len(set(slots)) and 3 in slots and all(type(s) is int and s in range(1, 6) for s in slots),
                         "native_mix_choice_observation")
                self.choices = (proof, slots, row["finished_at_ns"])
                counts["cropped_visual_calls"] += 1
            else:
                self.controls = window["mix_controls"]
                counts["uia_tree_calls"] += 1
            return True
        _require(tool == "Click" and window["target_pid"] == self.pid,
                 "native_mix_click_receipt")
        if route == "mix_badge":
            slots = window["mix_choices"]
            _require(role == MIX_CHOICES and self.choices is not None and self.choices[:2] == (proof, slots)
                     and 0 <= row["started_at_ns"] - self.choices[2] <= OBSERVATION_LIMIT_NS
                     and args == {"mix_role": "filament3"} and window["target_hwnd"] == proof["hwnd"]
                     and window["mix_readback"] == [3, 2]
                     and window["mix_point"] == [(box[0] + box[2]) // 2, box[1] + ROW_HEIGHT * slots.index(3) + ROW_HEIGHT // 2],
                     "native_mix_choice_receipt")
            self.choices = None
            self.combo = None
            self.selected = True
            self.badge_actions += 1
            counts["visual_inputs"] += 1
        else:
            control = dict(window["mix_control"])
            kind = control.pop("role")
            bounds = control["bounds"]
            _require(role == MIX_DIALOG and self.controls is not None and self.controls.get(kind) == control
                     and (kind == "filament1" or kind in DRAWN and DRAWN[kind] == control["target"]["name"])
                     and (args == {"mix_role": kind} or args == {"target": control["target"]})
                     and within(box, bounds) and window["target_hwnd"] == control["hwnd"], "native_mix_control_receipt")
            self.controls = None
            self.combo = bounds if kind == "filament1" else None
            self.property_actions += 1
            if kind in {"ratio", "gradient"}:
                self.mode = kind
                self.selected = False
            if kind == "filament1":
                self.selected = False
            if kind == "confirm":
                _require(self.selected, "native_mix_confirm_without_material_readback")
                self.confirmed = True
                self.modes.append(self.mode)
        return True

    def summary(self):
        _require(self.dialog is None and self.opened is None and sorted(self.modes) == ["gradient", "ratio"],
                 "native_mix_two_dialogs_required")
        return {"mix_dialogs_confirmed": self.modes, "mix_property_actions": self.property_actions,
                "mix_badge_actions": self.badge_actions}
