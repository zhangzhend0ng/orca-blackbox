#!/usr/bin/env python3
"""uia_probe.py — one-shot Orca accessibility (UIA) tree probe (GUEST).

Evaluation scaffolding for docs/STRUCTURING_PLAN.md phase-2 item #4 (UIA
hybrid locating): answers "is Orca's UIA tree good enough to locate controls
structurally" before any test framework commits to that route. NOT a
regression case — never registered in cases.py, writes nothing inside the
sandbox except artifacts/uia_probe_datadir (gitignored).

Launches the app exactly like the cases do (profile.seed_profile datadir
isolation + launcher.launch — v1 lesson: a bare exe start surfaces the boot
splash as the largest window and walks 27 Panes of nothing). Outputs:

  C:\\coil\\uia_probe_out.json       full structured dump (ASCII-escaped UTF-8)
  C:\\coil\\uia_probe_compact.json   everything except the deep main-tree dump
  C:\\coil\\uia_probe_report.txt     ASCII-only human summary (safe over GBK relay)

Runs under the INTERACTIVE scheduled task 'uia_probe' (PITFALLS_0901.md 18.7:
PS Direct cannot see the desktop; UIA needs the interactive session). Needs
pywinauto on the guest python — hv_uia_probe.ps1 installs it first.

Exit code: 0 = probe completed (individual findings may still be negative),
1 = probe crashed before finishing (traceback is in the report/steps).
"""

from __future__ import annotations

import ctypes
import datetime
import json
import sys
import time
import traceback
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parents[1]
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

ORCA_EXE_NAME = "snapmaker-orca.exe"
OUT_FULL = r"C:\coil\uia_probe_out.json"
OUT_COMPACT = r"C:\coil\uia_probe_compact.json"
OUT_REPORT = r"C:\coil\uia_probe_report.txt"

# Hard caps so a pathological tree can never hang the task (30 min limit):
# depth 12: mixing sidebar sections live at depth 6-9 and their parameter
# rows sit deeper (v2.2: 9 cut exactly those branches off).
MAX_DEPTH = 12         # main-window walk depth
MAX_CHILDREN = 60      # per node
MAX_NODES = 4000       # whole walk
WALK_BUDGET_S = 120.0  # wall clock per walk
MENU_KEYWORDS = ["mix", "multimat", "paint", "filament", "混色", "彩", "涂", "多材"]


def wait_idle_boot(session: Any, log: StepLog) -> None:
    """Block until the app passes its idle-boot anchor (tab bar settled) —
    v2 lesson: find_main_window returns a hwnd seconds before wx finishes
    building children, so an immediate walk undersamples (80 nodes, sidebar=5).
    Reuses the canonical anchors idle signal, then maximizes so the settings
    sidebar exposes its full visible set (case-calibrated geometry)."""
    import ctypes as _ctypes

    from harness import anchors

    score, _x, _y = anchors.wait_for(session, "tab_prepare_active", timeout_s=60.0)
    log.add("INFO", "idle_boot_anchor", f"score={score:.3f}")
    _ctypes.windll.user32.ShowWindow(int(session.hwnd), 3)  # SW_MAXIMIZE
    time.sleep(2.0)


def now_hms() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S")


class StepLog:
    """Structured step trace shared by all outputs (no PII/credentials)."""

    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def add(self, level: str, step: str, detail: str = "") -> None:
        entry = {"ts": now_hms(), "level": level, "step": step, "detail": detail}
        self.entries.append(entry)
        print(f"[{entry['ts']}] {level} {step} {detail}", flush=True)


@dataclass
class Node:
    control_type: str
    name: str
    automation_id: str
    class_name: str
    enabled: bool
    depth: int
    rect: list[int]
    path: str = ""
    error: str = ""
    children: list["Node"] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "control_type": self.control_type,
            "name": self.name,
            "automation_id": self.automation_id,
            "class_name": self.class_name,
            "enabled": self.enabled,
            "depth": self.depth,
            "rect": self.rect,
            "path": self.path,
        }
        if self.error:
            out["error"] = self.error
        if self.children:
            out["children"] = [child.to_dict() for child in self.children]
        return out


class WalkStats:
    def __init__(self) -> None:
        self.nodes = 0
        self.named = 0
        self.with_automation_id = 0
        self.max_depth_seen = 0
        self.cut_by_depth = 0
        self.cut_by_children = 0
        self.cut_by_budget = False
        self.cut_by_node_cap = False
        self.by_type: Counter[str] = Counter()

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodes": self.nodes,
            "named": self.named,
            "with_automation_id": self.with_automation_id,
            "max_depth_seen": self.max_depth_seen,
            "cut_by_depth": self.cut_by_depth,
            "cut_by_children": self.cut_by_children,
            "cut_by_budget": self.cut_by_budget,
            "cut_by_node_cap": self.cut_by_node_cap,
            "by_control_type": dict(self.by_type),
        }


# --- typed shims over the untyped pywinauto/element_info boundary ---


def element_field(info: Any, attr: str, default: Any) -> Any:
    """UIA elements vanish between queries; every attribute read is a boundary."""
    try:
        value = getattr(info, attr)
    except Exception as exc:  # COMError etc. — caller sees the default
        return f"<{type(exc).__name__}>" if default == "" else default
    return default if value is None else value


def element_children(info: Any) -> tuple[list[Any], str]:
    try:
        kids = info.children
        if callable(kids):  # property vs method varies across pywinauto versions
            kids = kids()
        return list(kids or []), ""
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


def info_rect(info: Any) -> list[int]:
    rect = element_field(info, "rectangle", None)
    return [
        int(getattr(rect, "left", 0) or 0),
        int(getattr(rect, "top", 0) or 0),
        int(getattr(rect, "right", 0) or 0),
        int(getattr(rect, "bottom", 0) or 0),
    ]


def node_from_info(info: Any, depth: int, parent_path: str) -> Node:
    name = str(element_field(info, "name", "") or "")
    automation_id = str(element_field(info, "automation_id", "") or "")
    control_type = str(element_field(info, "control_type", "") or "")
    label = name or automation_id or "?"
    return Node(
        control_type=control_type,
        name=name,
        automation_id=automation_id,
        class_name=str(element_field(info, "class_name", "") or ""),
        enabled=bool(element_field(info, "enabled", True)),
        depth=depth,
        rect=info_rect(info),
        path=f"{parent_path}/{control_type}:{label[:48]}",
    )


def walk_tree(
    info: Any,
    depth: int,
    parent_path: str,
    stats: WalkStats,
    log: StepLog,
    deadline: float,
    collected: list[tuple[Node, Any]],
) -> Node:
    node = node_from_info(info, depth, parent_path)
    stats.nodes += 1
    stats.max_depth_seen = max(stats.max_depth_seen, depth)
    stats.by_type[node.control_type or "<none>"] += 1
    if node.name:
        stats.named += 1
    if node.automation_id:
        stats.with_automation_id += 1
    collected.append((node, info))
    if depth >= MAX_DEPTH:
        stats.cut_by_depth += 1
        return node
    if stats.nodes >= MAX_NODES:
        stats.cut_by_node_cap = True
        return node
    if time.monotonic() > deadline:
        stats.cut_by_budget = True
        return node
    kids, err = element_children(info)
    if err:
        log.add("WARN", "children_query_failed", f"depth={depth} err={err[:120]}")
    if len(kids) > MAX_CHILDREN:
        stats.cut_by_children += len(kids) - MAX_CHILDREN
        kids = kids[:MAX_CHILDREN]
    for kid in kids:
        node.children.append(walk_tree(kid, depth + 1, node.path, stats, log, deadline, collected))
    return node


def flatten(nodes: list[Node]) -> list[Node]:
    out: list[Node] = []
    stack = list(nodes)
    while stack:
        node = stack.pop(0)
        out.append(node)
        stack.extend(node.children)
    return out


def search_matches(pairs: list[tuple[Node, Any]], keywords: list[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for node, _raw in pairs:
        hay = f"{node.name} {node.automation_id}".lower()
        hit = next((kw for kw in keywords if kw.lower() in hay), None)
        if hit:
            hits.append(
                {
                    "matched_keyword": hit,
                    "control_type": node.control_type,
                    "name": node.name,
                    "automation_id": node.automation_id,
                    "class_name": node.class_name,
                    "enabled": node.enabled,
                    "depth": node.depth,
                    "rect": node.rect,
                    "path": node.path,
                }
            )
    return hits


def screen_size() -> dict[str, int]:
    user32 = ctypes.WinDLL("user32")
    return {"w": int(user32.GetSystemMetrics(0)), "h": int(user32.GetSystemMetrics(1))}


def process_exe_name(pid: int) -> str:
    """Exe basename for a pid via QueryFullProcessImageNameW (stdlib only)."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.QueryFullProcessImageNameW.restype = ctypes.c_int
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
        ctypes.POINTER(ctypes.c_ulong),
    ]
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, 0, int(pid))
    if not handle:
        return ""
    try:
        size = ctypes.c_ulong(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value.replace("\\", "/").rsplit("/", 1)[-1].lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def ascii_safe(text: str) -> str:
    return text.encode("ascii", "backslashreplace").decode("ascii")


def top_level_infos(desktop: Any) -> list[tuple[Any, str]]:
    out: list[tuple[Any, str]] = []
    for wrapper in desktop.windows():
        try:
            info = wrapper.element_info
        except Exception:
            continue
        out.append((info, process_exe_name(int(element_field(info, "process_id", 0) or 0))))
    return out


def info_rect_area(info: Any) -> int:
    l, t, r, b = info_rect(info)
    return max(0, r - l) * max(0, b - t)


def launch_app(log: StepLog) -> Any:
    """Seed an isolated datadir and launch via the case-standard launcher.

    v1 lesson: a bare exe start resurfaces the boot splash as the
    largest-area window 5s in; launcher.launch -> winutil.find_main_window
    waits out the boot chain for the REAL frame (90s budget).
    """
    from harness import launcher, profile

    datadir = HERE / "artifacts" / "uia_probe_datadir"
    profile.seed_profile(datadir)
    session = launcher.launch(datadir=datadir)
    log.add("INFO", "app_launched", f"pid={session.pid} hwnd=0x{session.hwnd:x}")
    return session


def scan_extra_windows(desktop: Any, main_hwnd: int, log: StepLog) -> list[dict[str, Any]]:
    """Other visible top-level windows of the app process (update prompts,
    wizards...): name + class + first-level button names. This quantifies
    whether UIA can SEE a boot blocker well enough to auto-dismiss it."""
    extras: list[dict[str, Any]] = []
    for info, exe in top_level_infos(desktop):
        if exe != ORCA_EXE_NAME:
            continue
        handle = int(element_field(info, "handle", 0) or 0)
        if handle == main_hwnd or handle == 0:
            continue
        if not element_field(info, "visible", True):
            continue
        buttons: list[str] = []
        kids, _err = element_children(info)
        for kid in kids[:40]:
            ctype = str(element_field(kid, "control_type", "") or "")
            if ctype in ("Button", "Hyperlink", "CheckBox"):
                label = str(element_field(kid, "name", "") or "")
                if label:
                    buttons.append(label)
        extras.append(
            {
                "name": str(element_field(info, "name", "") or "")[:120],
                "class_name": str(element_field(info, "class_name", "") or ""),
                "control_type": str(element_field(info, "control_type", "") or ""),
                "rect": info_rect(info),
                "buttons": buttons[:12],
            }
        )
    if extras:
        log.add("INFO", "extra_windows", f"count={len(extras)}")
    return extras


def try_menu_expand(pairs: list[tuple[Node, Any]], log: StepLog) -> dict[str, Any]:
    """Expand the first menu item and dump the popup menu tree (win32 '#32768')."""
    result: dict[str, Any] = {"attempted": False, "popup_found": False}
    menubar_children = [
        (node, raw)
        for node, raw in pairs
        if node.control_type == "MenuItem" and node.depth <= 2 and node.name
    ]
    if not menubar_children:
        result["error"] = "no named MenuItem at menubar level"
        return result
    first_node, first_raw = menubar_children[0]
    result["attempted"] = True
    result["menu_item"] = first_node.name
    from pywinauto import Desktop
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto.keyboard import send_keys

    desktop = Desktop(backend="uia")
    before = {int(element_field(info, "handle", 0) or 0) for info, _ in top_level_infos(desktop)}
    try:
        UIAWrapper(first_raw).invoke()
        time.sleep(1.2)
    except Exception as exc:
        result["error"] = f"invoke failed: {type(exc).__name__}: {exc}"[:200]
        send_keys("{ESC}")
        return result
    for info, _exe in top_level_infos(desktop):
        # NOTE: no exe filter here — the popup menu belongs to the Orca
        # process itself; only the before-handle set excludes old windows.
        handle = int(element_field(info, "handle", 0) or 0)
        if handle in before:
            continue
        if str(element_field(info, "control_type", "")) != "Menu":
            continue
        result["popup_found"] = True
        stats = WalkStats()
        collected: list[tuple[Node, Any]] = []
        root = walk_tree(info, 0, "", stats, log, time.monotonic() + 30, collected)
        result["popup_stats"] = stats.as_dict()
        result["popup_items"] = [
            {"name": n.name, "automation_id": n.automation_id, "enabled": n.enabled, "depth": n.depth}
            for n in flatten([root])
            if n.control_type == "MenuItem"
        ][:150]
        break
    send_keys("{ESC}")  # close the popup; do not act on any item
    time.sleep(0.5)
    return result


def try_mixing_invoke(
    matches: list[dict[str, Any]],
    pairs: list[tuple[Node, Any]],
    desktop: Any,
    log: StepLog,
) -> dict[str, Any]:
    """Invoke up to 3 enabled mixing-related controls; dump any new window."""
    result: dict[str, Any] = {"attempts": [], "dialog_dump": None}
    by_path = {node.path: (node, raw) for node, raw in pairs}
    candidates = [
        m
        for m in matches
        if m["enabled"] and m["control_type"] in ("Button", "MenuItem", "TabItem", "ListItem", "TreeItem", "DataItem", "Hyperlink")
    ][:3]
    from pywinauto.controls.uiawrapper import UIAWrapper
    from pywinauto.keyboard import send_keys

    for cand in candidates:
        pair = by_path.get(cand["path"])
        if not pair:
            continue
        _node, raw = pair
        attempt: dict[str, Any] = {"path": cand["path"], "name": cand["name"]}
        before = {int(element_field(info, "handle", 0) or 0) for info, _ in top_level_infos(desktop)}
        try:
            UIAWrapper(raw).invoke()
            time.sleep(2.5)
            attempt["invoked"] = True
        except Exception as exc:
            attempt["invoked"] = False
            attempt["error"] = f"{type(exc).__name__}: {exc}"[:200]
            result["attempts"].append(attempt)
            continue
        new_windows = [
            info
            for info, _exe in top_level_infos(desktop)
            if int(element_field(info, "handle", 0) or 0) not in before
        ]
        attempt["new_windows"] = len(new_windows)
        if new_windows:
            dialog = new_windows[0]
            stats = WalkStats()
            collected: list[tuple[Node, Any]] = []
            root = walk_tree(dialog, 0, "", stats, log, time.monotonic() + 45, collected)
            attempt["dialog_title"] = str(element_field(dialog, "name", ""))
            attempt["dialog_class"] = str(element_field(dialog, "class_name", ""))
            result["dialog_dump"] = {
                "stats": stats.as_dict(),
                "tree": root.to_dict(),
            }
            send_keys("{ESC}")
            time.sleep(1.0)
        else:
            send_keys("{ESC}")  # in-main-window state change; undo conservatively
            time.sleep(0.8)
        result["attempts"].append(attempt)
    return result


def sidebar_sample(nodes: list[Node], main_rect: list[int]) -> dict[str, Any]:
    """Spatial sample: nodes in the right 45% of the main window (settings panel)."""
    left_edge = main_rect[0] + 0.55 * max(1, main_rect[2] - main_rect[0])
    sample = [
        node
        for node in nodes
        if node.rect[0] >= left_edge and node.rect[2] > node.rect[0]
    ][:300]
    stats = WalkStats()
    for node in sample:
        stats.nodes += 1
        stats.by_type[node.control_type or "<none>"] += 1
        if node.name:
            stats.named += 1
        if node.automation_id:
            stats.with_automation_id += 1
        stats.max_depth_seen = max(stats.max_depth_seen, node.depth)
    lines = [
        {
            "control_type": n.control_type,
            "name": n.name[:80],
            "automation_id": n.automation_id,
            "enabled": n.enabled,
            "depth": n.depth,
        }
        for n in sample[:120]
    ]
    return {"stats": stats.as_dict(), "nodes": lines}


def build_report(result: dict[str, Any]) -> str:
    # crash-safe: every section is optional so a mid-probe crash still gets
    # a readable report instead of a KeyError inside the finally block
    lines: list[str] = []
    add = lines.append
    meta = result["meta"]
    add(f"UIA PROBE REPORT  {meta['finished']}")
    add(f"screen={meta['screen']['w']}x{meta['screen']['h']}  pywinauto={meta.get('pywinauto_version', '?')}")
    main_window = result.get("main_window", {})
    add(f"app: class={main_window.get('class_name', '?')} framework={main_window.get('framework_id', '?')}")
    stats = main_window.get(
        "stats",
        {
            "nodes": 0, "named": 0, "with_automation_id": 0, "max_depth_seen": 0,
            "cut_by_depth": 0, "cut_by_children": 0, "cut_by_budget": False, "cut_by_node_cap": False,
        },
    )
    named_pct = 100.0 * stats["named"] / max(1, stats["nodes"])
    aid_pct = 100.0 * stats["with_automation_id"] / max(1, stats["nodes"])
    add(
        f"main tree: nodes={stats['nodes']} named={named_pct:.0f}% automationId={aid_pct:.0f}% "
        f"maxDepth={stats['max_depth_seen']} cuts(d/c/budget/cap)="
        f"{stats['cut_by_depth']}/{stats['cut_by_children']}/{int(stats['cut_by_budget'])}/{int(stats['cut_by_node_cap'])}"
    )
    add(f"top control types: {sorted(stats.get('by_control_type', {}).items(), key=lambda kv: -kv[1])[:8]}")
    menubar = main_window.get("menu_bar", [])
    add(f"menu bar ({len(menubar)}): {ascii_safe(' | '.join(menubar))[:300]}")
    menu_exp = result.get("menu_expand", {})
    add(f"menu popup: attempted={menu_exp.get('attempted')} popup_found={menu_exp.get('popup_found')} items={len(menu_exp.get('popup_items', []))}")
    sb = result.get("settings_sidebar_sample", {}).get("stats", {})
    if sb:
        sb_named = 100.0 * sb["named"] / max(1, sb["nodes"])
        sb_aid = 100.0 * sb["with_automation_id"] / max(1, sb["nodes"])
        add(f"settings sidebar sample: nodes={sb['nodes']} named={sb_named:.0f}% automationId={sb_aid:.0f}% maxDepth={sb['max_depth_seen']}")
    extras = result.get("extra_windows", [])
    add(f"extra app windows (blockers/prompts): {len(extras)}")
    for extra in extras[:4]:
        add(f"  [{ascii_safe(extra['name'])[:70]}] class={extra['class_name']} buttons={ascii_safe('|'.join(extra['buttons']))[:90]}")
    mixing = result.get("mixing_search", {})
    add(f"mixing search: {len(mixing.get('matches', []))} matches (keywords={ascii_safe(str(mixing.get('keywords')))}[:110])")
    for attempt in mixing.get("invoke_attempts", []):
        add(
            f"  invoke: invoked={attempt.get('invoked')} new_windows={attempt.get('new_windows')} "
            f"name={ascii_safe(attempt.get('name', ''))[:60]} err={ascii_safe(attempt.get('error', ''))[:80]}"
        )
    dump = mixing.get("dialog_dump")
    if dump:
        dstats = dump["stats"]
        d_named = 100.0 * dstats["named"] / max(1, dstats["nodes"])
        add(f"mixing dialog tree: nodes={dstats['nodes']} named={d_named:.0f}% automationId={100.0 * dstats['with_automation_id'] / max(1, dstats['nodes']):.0f}%")
    errors = [e for e in result.get("steps", []) if e["level"] in ("WARN", "ERROR")]
    add(f"steps WARN/ERROR: {len(errors)}")
    for entry in errors[:15]:
        add(f"  [{entry['ts']}] {entry['level']} {entry['step']} {ascii_safe(entry['detail'])[:120]}")
    return "\n".join(lines) + "\n"


def main() -> int:
    log = StepLog()
    log.add("INFO", "probe_start", "")
    result: dict[str, Any] = {
        "meta": {"started": now_hms(), "screen": screen_size(), "exe_name": ORCA_EXE_NAME},
        "steps": log.entries,
    }
    completed = False
    session = None
    desktop = None
    try:
        import pywinauto

        result["meta"]["pywinauto_version"] = getattr(pywinauto, "__version__", "?")
        from pywinauto import Desktop

        desktop = Desktop(backend="uia")
        session = launch_app(log)
        wait_idle_boot(session, log)
        main_spec = desktop.window(handle=session.hwnd)
        main_info = main_spec.wrapper_object().element_info

        # main window tree
        stats = WalkStats()
        collected: list[tuple[Node, Any]] = []
        root = walk_tree(main_info, 0, "", stats, log, time.monotonic() + WALK_BUDGET_S, collected)
        nodes = flatten([root])
        result["main_window"] = {
            "class_name": str(element_field(main_info, "class_name", "")),
            "framework_id": str(element_field(main_info, "framework_id", "")),
            "name": str(element_field(main_info, "name", "")),
            "rect": root.rect,
            "stats": stats.as_dict(),
            "tree": root.to_dict(),
        }
        log.add("INFO", "main_tree_done", f"nodes={stats.nodes} named={stats.named} aid={stats.with_automation_id}")

        # menu bar (always-visible level)
        menubar = next((n for n in nodes if n.control_type == "MenuBar"), None)
        result["main_window"]["menu_bar"] = [c.name for c in menubar.children if c.name] if menubar else []
        result["menu_expand"] = try_menu_expand(collected, log)

        # settings sidebar spatial sample
        result["settings_sidebar_sample"] = sidebar_sample(nodes, root.rect)

        # boot blockers / prompts: other visible windows of the app process
        main_hwnd = int(session.hwnd)
        result["extra_windows"] = scan_extra_windows(desktop, main_hwnd, log)

        # mixing entry search + invoke probe
        matches = search_matches(collected, MENU_KEYWORDS)
        log.add("INFO", "mixing_matches", f"count={len(matches)}")
        result["mixing_search"] = {
            "keywords": MENU_KEYWORDS,
            "matches": matches[:40],
        }
        result["mixing_search"]["invoke_attempts"] = []
        if matches:
            inv = try_mixing_invoke(result["mixing_search"]["matches"], collected, desktop, log)
            result["mixing_search"]["invoke_attempts"] = inv["attempts"]
            result["mixing_search"]["dialog_dump"] = inv["dialog_dump"]

        result["toplevel_windows"] = [
            {
                "name": str(element_field(info, "name", ""))[:80],
                "class_name": str(element_field(info, "class_name", "")),
                "control_type": str(element_field(info, "control_type", "")),
                "pid": int(element_field(info, "process_id", 0) or 0),
                "exe": exe,
                "rect": info_rect(info),
            }
            for info, exe in top_level_infos(desktop)
        ]
        completed = True
    except Exception:
        log.add("ERROR", "probe_crashed", traceback.format_exc(limit=8))
    finally:
        if session is not None:
            try:
                session.close()
                log.add("INFO", "app_closed", f"pid={session.pid}")
            except Exception as exc:
                log.add("WARN", "app_close_failed", f"{type(exc).__name__}: {exc}"[:160])
        result["meta"]["finished"] = now_hms()
        result["meta"]["completed"] = completed
        result["steps"] = log.entries
        compact = {k: v for k, v in result.items() if k != "main_window"}
        if "main_window" in result:
            compact["main_window"] = {
                k: v for k, v in result["main_window"].items() if k != "tree"
            }
        for path, payload in ((OUT_FULL, result), (OUT_COMPACT, compact)):
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=True, separators=(",", ":"))
        with open(OUT_REPORT, "w", encoding="utf-8") as handle:
            handle.write(build_report(result))
        log.add("INFO", "probe_end", f"completed={completed}")
    return 0 if completed else 1


if __name__ == "__main__":
    raise SystemExit(main())
