#!/usr/bin/env python3
# m7x_254_gcode_tmp_probe.py — Record how the plate's temporary G-code grows, and whether a low-memory dialog is what leaves it half written.
# feishu: none  (#254 follow-up probe: a record, never a verdict, so it claims no baseline row)
"""Feishu #254 follow-up: slice the standard sphere once and watch, once a
second, until the plate file is complete or has stopped growing:

  (a) a native dialog titled "Memory Usage Warning". Its texts, a picture and
      the memory reading beside it are kept, then the button whose text is
      exactly "Yes, Continue" is clicked by its rectangle with the dialog as
      the root window. Nothing else is ever activated: no Enter, no default
      button ("No, Stop"), no fallback. Two attempts that leave it open end
      the watch with a failure.
  (b) whether File > Export > "Export G-code..." is enabled, read from the
      open menu (nothing is dispatched). The row needs a valid slice result,
      which the app grants only after the plate file was written and renamed,
      so it is the completion signal. Sampled every --menu-s seconds.
  (c) the names and sizes of this process's plate files in a private
      temporary directory, plus the enabled flags of the top-bar buttons.

The app writes "<.pid.n.gcode>.tmp" while it exports and renames it to
".pid.n.gcode" at the end (GCode::do_export), so a ".tmp" that stops growing
means the export thread is not running. The 2.4.0 build asks the user what to
do when min(available RAM, available commit) stays below 512 MB for a second,
and it asks from inside the export thread (PrintBase::check_memory_guard).
While it waits, the "Slice plate" button is greyed exactly as after a
finished slice, which is what the slice_button_done template matches.

--hog-mb holds that much memory in a helper process from the slice click on,
so the question comes up on every run; without an argument the size is read
from C:\\coil\\diag_hog_mb.txt, as diag_slice_export_probe.py does. The helper
exits by itself after ten minutes if this script is killed.

Outputs, flat in the run directory: analysis.json, probe.log, warning-NN.png,
final.png, and the plate file as plate.gcode or the stalled part as
partial.gcode.tmp.gcode. The banner is RED by construction: a probe records
and certifies nothing.
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from unittest.mock import patch

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]
import m7_common as m7
from harness import export_util, topbar_util, winutil
from harness.agent_protocol import MODEL_FIXTURES
from m2_slice_chain import click_slice_start, wait_slicing_done
from m7x_249_add_part import capture, stage
from plate_reserve_case import case_main

FIXTURE = HERE / 'fixtures' / 'feishu_std_sphere.3mf'
WARNING = 'Memory Usage Warning'
CONTINUE = 'Yes, Continue'
UNANSWERED = 'Memory Usage Warning could not be answered with "Yes, Continue"'
MARKER = Path(r'C:\coil\diag_hog_mb.txt')
POLL_S, RENAMED_QUIET_S, FAILURES = 1.0, 30.0, 2
HOG = '\n'.join([
    'import sys, time',
    'block = bytearray(int(sys.argv[1]) << 20)',
    'block[::4096] = bytes(len(block[::4096]))',
    'sys.stdout.write("ready" + chr(10))',
    'sys.stdout.flush()',
    'time.sleep(600)',
])
STATE = {}


class _Status(ctypes.Structure):
    _fields_ = [('dwLength', wt.DWORD), ('dwMemoryLoad', wt.DWORD)] + [
        (name, ctypes.c_ulonglong) for name in ('ullTotalPhys', 'ullAvailPhys', 'ullTotalPageFile',
                                                'ullAvailPageFile', 'ullTotalVirtual', 'ullAvailVirtual',
                                                'ullAvailExtendedVirtual')]


class _Performance(ctypes.Structure):
    # PERFORMANCE_INFORMATION whole: GetPerformanceInfo rejects a short cb with ERROR_BAD_LENGTH
    _fields_ = [('cb', wt.DWORD)] + [(name, ctypes.c_size_t) for name in (
        'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal', 'PhysicalAvailable', 'SystemCache',
        'KernelTotal', 'KernelPaged', 'KernelNonpaged', 'PageSize')] + [
        (name, wt.DWORD) for name in ('HandleCount', 'ProcessCount', 'ThreadCount')]


_KERNEL32 = ctypes.WinDLL('kernel32', use_last_error=True)
_KERNEL32.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(_Status)]
_PSAPI = ctypes.WinDLL('psapi', use_last_error=True)
_PSAPI.GetPerformanceInfo.argtypes = [ctypes.POINTER(_Performance), wt.DWORD]


def memory():
    """The two inputs of the app's memory guard in MB (libslic3r/utils.cpp uses the smaller one)."""
    try:
        status = _Status()
        status.dwLength = ctypes.sizeof(status)
        phys = status.ullAvailPhys if _KERNEL32.GlobalMemoryStatusEx(ctypes.byref(status)) else 0
        performance = _Performance()
        performance.cb = ctypes.sizeof(performance)
        commit = 0
        if _PSAPI.GetPerformanceInfo(ctypes.byref(performance), performance.cb) and performance.PageSize:
            commit = max(0, performance.CommitLimit - performance.CommitTotal) * performance.PageSize
    except (OSError, AttributeError) as error:
        return {'error': f'{type(error).__name__}: {error}'}
    return {'total_mb': status.ullTotalPhys >> 20, 'avail_phys_mb': round(phys / 2 ** 20, 1),
            'commit_avail_mb': round(commit / 2 ** 20, 1)}


def start_hog(mb):
    """A helper process that holds `mb` MB until killed."""
    hog = subprocess.Popen([sys.executable, '-c', HOG, str(mb)], stdout=subprocess.PIPE, text=True)
    hog.stdout.readline()
    time.sleep(3)
    return hog


def _title(hwnd):
    text = ctypes.create_unicode_buffer(256)
    winutil.user32.GetWindowTextW(hwnd, text, 256)
    return text.value


def dialog_titles(pid):
    """Titles of every visible native dialog (#32770) of the process."""
    found = []

    def visit(hwnd, _):
        owner = wt.DWORD()
        winutil.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and winutil.user32.IsWindowVisible(hwnd) and winutil.window_class(hwnd) == '#32770':
            found.append(_title(hwnd))
        return True

    winutil.user32.EnumWindows(export_util.WNDENUMPROC(visit), 0)
    return found


def toolbar(session):
    """Enabled flags of the top-bar buttons and of the main window (one enumeration, no input)."""
    states = {'main window': bool(winutil.user32.IsWindowEnabled(session.hwnd))}
    for text, _rect, hwnd in export_util.topbar_buttons(session.hwnd):
        if text in ('Slice plate', 'Print', 'Export G-code file'):
            states[text] = bool(winutil.user32.IsWindowEnabled(hwnd))
    return states


def export_row(session):
    """State of File > Export > "Export G-code...", read from the open menu. row_enabled is None
    when the File menu did not open, so a missed read is not mistaken for a disabled row."""
    opened = []
    open_menu = topbar_util.open_file_menu

    def spy(current):
        menu = open_menu(current)
        opened.append(menu is not None)
        return menu

    with patch.object(topbar_util, 'open_file_menu', spy):
        enabled, _dialog = m7.file_menu_dispatch(session, 'Export G-code', via='Export', inspect_enabled=True)
    row = {'menu_opened': bool(opened and opened[0]), 'row_enabled': enabled if opened and opened[0] else None}
    row['menus_left_open'] = len(topbar_util._enum_menu_windows(session.pid))
    return row


def plate_files(private_temp, pid):
    """[name, size, mtime_ns] of this process's plate files (PartPlate::get_tmp_gcode_path)."""
    pattern = f'snapmaker_orca_model/*/*#{pid}#*/Metadata/.{pid}.*.gcode*'
    files = []
    for path in sorted(private_temp.glob(pattern)):
        try:
            info = path.stat()
        except OSError:            # renamed or removed between listing and stat
            continue
        files.append([path.name, info.st_size, info.st_mtime_ns])
    return files


def describe_warning(session, hwnd, work, serial, sample, hold):
    """Keep the warning's texts, picture and memory reading. Unless `hold`, click the one button whose
    text is exactly "Yes, Continue"; with any other count of such buttons nothing is clicked."""
    children = export_util._children_texts(hwnd)
    event = {'title': _title(hwnd), 'texts': [text for text, _rect, _h in children if text],
             'seen_at_s': sample['t_s'], 'size_bytes': _total(sample), 'memory': sample['memory']}
    try:
        width, height, pixels = winutil.capture_window(hwnd)
        name = f'warning-{serial:02d}.png'
        frame = cv2.cvtColor(np.frombuffer(pixels, np.uint8).reshape(height, width, 4), cv2.COLOR_BGRA2BGR)
        event['screenshot'] = name if cv2.imwrite(str(work / name), frame) else 'not written'
    except Exception as error:    # the picture is evidence, not a precondition for answering
        event['screenshot'] = f'{type(error).__name__}: {error}'
    if hold:
        event['clicked'] = 'not clicked: --hold-warning'
        return event
    exact = [rect for text, rect, _h in children if text.strip() == CONTINUE]
    if len(exact) != 1:
        event['clicked'] = f'not clicked: {len(exact)} buttons read exactly "Yes, Continue"'
        return event
    left, top, right, bottom = exact[0]
    center = (left + right) // 2, (top + bottom) // 2
    target = winutil.msg_click_screen(*center, hwnd)   # the dialog is the root: without it the click misses
    event['clicked'] = {'center': list(center), 'target_class': winutil.window_class(target)}
    return event


def wait_closed(hwnd, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and winutil.user32.IsWindow(hwnd) and winutil.user32.IsWindowVisible(hwnd):
        time.sleep(0.1)
    return not (winutil.user32.IsWindow(hwnd) and winutil.user32.IsWindowVisible(hwnd))


def handle_warning(session, hwnd, work, warnings, sample, started, hold):
    """Record the warning and try to answer it. True once it closed, False when nothing closed it."""
    event = describe_warning(session, hwnd, work, len(warnings), sample, hold)
    if isinstance(event['clicked'], dict):
        event['closed'] = wait_closed(hwnd)
    event['settled_at_s'] = round(time.monotonic() - started, 2)
    warnings.append(event)
    print(f"[m7x254p] warning: {json.dumps(event, default=str)}", flush=True)
    return bool(event.get('closed'))


def plate_facts(raw):
    """What the file holds: both end blocks, the layer markers against the declared count, the last commands."""
    text = raw.decode('utf-8', 'replace')
    declared = re.search(r'^; total layer number: (\d+)', text, re.M)
    numbered = [int(n) for n in re.findall(r'^;LAYER:(\d+)\s*$', text, re.M)]
    commands = [line for line in text.split('; EXECUTABLE_BLOCK_END')[0].splitlines()
                if line[:1] in 'GM' and line[1:2].isdigit()]
    return {
        'bytes': len(raw),
        'executable_block_closed': '; EXECUTABLE_BLOCK_END' in text,
        'config_block_complete': '; CONFIG_BLOCK_START' in text and '; CONFIG_BLOCK_END' in text,
        'declared_layers': int(declared[1]) if declared else None,
        'layer_change_markers': len(re.findall(r'^;LAYER_CHANGE', text, re.M)),
        'numbered_layer_markers': len(numbered),
        'numbered_layers_consecutive_from_zero': numbered == list(range(len(numbered))),
        'last_commands': commands[-8:],
    }


def _total(sample):
    return sum(size for _name, size, _mtime in sample['files'])


def _is_final(sample):
    return any(name.endswith('.gcode') for name, _size, _mtime in sample['files'])


def _guard_input(sample):
    readings = sample['memory']
    return min(readings.get('avail_phys_mb', float('inf')), readings.get('commit_avail_mb', float('inf')))


def timeline(samples, warnings):
    """When the plate file appeared, grew, was renamed and became exportable, around the warning."""
    changes = [b['t_s'] for a, b in zip(samples, samples[1:])
               if _total(a) != _total(b) or [f[0] for f in a['files']] != [f[0] for f in b['files']]]
    open_samples = [sample for sample in samples if sample.get('warning_open')]
    answered = [event for event in warnings if isinstance(event['clicked'], dict)]

    def first(test):
        return next((sample['t_s'] for sample in samples if test(sample)), None)

    settled = answered[0]['settled_at_s'] if answered else None
    resumed = [t for t in changes if settled is not None and t >= settled]
    return {
        'slice_button_disabled_at_s': first(lambda s: s['toolbar'].get('Slice plate') is False),
        'first_plate_file_at_s': first(lambda s: s['files']),
        'first_growth_at_s': changes[0] if changes else None,
        'last_growth_at_s': changes[-1] if changes else None,
        'renamed_to_gcode_at_s': first(_is_final),
        'export_row_enabled_at_s': first(lambda s: (s.get('export_gcode_row') or {}).get('row_enabled') is True),
        'print_button_enabled_at_s': first(lambda s: s['toolbar'].get('Print') or s['toolbar'].get('Export G-code file')),
        'warning_open_at_s': open_samples[0]['t_s'] if open_samples else None,
        'warning_open_samples': len(open_samples),
        'sizes_while_warning_open': sorted({_total(sample) for sample in open_samples}),
        'warning_answered_at_s': settled,
        'growth_resumed_at_s': resumed[0] if resumed else None,
        'smallest_guard_input_mb': min(map(_guard_input, samples), default=None),
        'samples_below_512_mb': sum(_guard_input(sample) < 512 for sample in samples),
        'complete_plate_file_at_stop': bool(samples) and _is_final(samples[-1]),
    }


def watch(session, private_temp, work, analysis, started, args):
    """One sample per second until the export row is enabled, the plate file has stalled, or the limit.
    Returns why it stopped."""
    samples, warnings = analysis['samples'], analysis['warnings'] = [], []
    attempts, failures, last_key, last_change, last_menu, renamed_at = {}, 0, None, None, None, None
    reason = 'time limit'
    with (work / 'probe.log').open('w', encoding='utf-8') as log:
        while True:
            now = time.monotonic()
            at = round(now - started, 2)
            sample = {'t_s': at, 'files': plate_files(private_temp, session.pid), 'memory': memory(),
                      'toolbar': toolbar(session), 'dialogs': dialog_titles(session.pid)}
            warning = m7.wait_dialog(session.pid, timeout_s=0.2, title_substr=WARNING)
            if warning is not None:
                sample['warning_open'] = True
                if attempts.get(warning[3], 0) < (1 if args.hold_warning else FAILURES):
                    attempts[warning[3]] = attempts.get(warning[3], 0) + 1
                    closed = handle_warning(session, warning[3], work, warnings, sample, started, args.hold_warning)
                    if closed and not args.hold_warning:
                        last_change = time.monotonic()
                    elif not args.hold_warning:
                        failures += 1
            key = tuple((name, size) for name, size, _mtime in sample['files'])
            if sample['files'] and key != last_key:
                last_key, last_change = key, now
            if not sample['files']:
                last_key = None
            if _is_final(sample) and renamed_at is None:
                renamed_at = at
            row = None
            if warning is None and (last_menu is None or now - last_menu >= args.menu_s):
                last_menu = now
                row = sample['export_gcode_row'] = export_row(session)
            names = ', '.join(f'{name}:{size}' for name, size, _mtime in sample['files']) or '-'
            line = (f"t={at:7.2f}s files=[{names}] phys={sample['memory'].get('avail_phys_mb')}MB "
                    f"commit={sample['memory'].get('commit_avail_mb')}MB toolbar={sample['toolbar']} "
                    f"dialogs={sample['dialogs']}"
                    + (' warning_open' if warning is not None else '')
                    + (f" export_row={row['row_enabled']}" if row is not None else ''))
            samples.append(sample)
            print(f'[m7x254p] {line}', flush=True)
            log.write(line + '\n')
            log.flush()
            answered = any(isinstance(event['clicked'], dict) for event in warnings)
            stalled = (sample['files'] and renamed_at is None and (warning is None or args.hold_warning)
                       and now - last_change >= (3 * args.quiet_s if answered else args.quiet_s))
            if row is not None and row['row_enabled']:
                reason = 'File > Export > Export G-code is enabled'
            elif failures >= FAILURES:
                reason = UNANSWERED
            elif not session.alive():
                reason = 'app exited'
            elif renamed_at is not None and at - renamed_at >= RENAMED_QUIET_S:
                reason = 'plate file renamed but the export row stayed disabled'
            elif stalled:
                reason = f"plate file unchanged for {3 * args.quiet_s if answered else args.quiet_s:.0f} s"
            if reason != 'time limit' or at >= args.limit_s:
                break
            time.sleep(max(0.0, POLL_S - (time.monotonic() - now)))
    if not any((sample.get('export_gcode_row') or {}).get('row_enabled') for sample in samples):
        # one reading at the stop, also under an open warning, which the loop does not disturb
        analysis['export_row_at_stop'] = export_row(session)
    analysis['stop'] = {'reason': reason, 'at_s': round(time.monotonic() - started, 2), 'attempts': attempts,
                        'failed_attempts': failures}
    analysis['timeline'] = timeline(samples, warnings)
    return reason


def retain(private_temp, work, analysis, pid):
    """Copy the plate file, or the stalled part, into the run directory and describe its end."""
    analysis['retained'] = []
    for path in sorted(private_temp.glob(f'snapmaker_orca_model/*/*#{pid}#*/Metadata/.{pid}.*.gcode*')):
        target = work / ('plate.gcode' if path.name.endswith('.gcode') else 'partial.gcode.tmp.gcode')
        try:
            raw = path.read_bytes()
        except OSError as error:
            analysis['retained'].append({'name': path.name, 'error': f'{type(error).__name__}: {error}'})
            continue
        target.write_bytes(raw)
        analysis['retained'].append({'name': path.name, 'as': target.name, **plate_facts(raw)})


def steps(session, work, analysis, args):
    analysis['timings'] = {}
    analysis['pid'] = session.pid
    analysis['settings'] = {'hold_warning': args.hold_warning, 'menu_every_s': args.menu_s,
                            'limit_s': args.limit_s, 'quiet_s': args.quiet_s}
    mb = args.hog_mb or (int(MARKER.read_text().strip() or 0) if MARKER.is_file() else 0)
    if mb:
        STATE['hog'] = start_hog(mb)
        analysis['memory_hog'] = {'mb': mb, 'pid': STATE['hog'].pid, 'after_start': memory()}
        print(f"[m7x254p] memory hog: {analysis['memory_hog']}", flush=True)
    if not m7.wait_slice_button_ready(session):
        raise ValueError('slice button neither idle nor done before the click')
    private_temp = Path(os.environ['TMP'])
    reason = None
    with stage(analysis, 'slice_and_watch'):
        if not click_slice_start(session):
            raise ValueError('slice click did not take')
        started = time.monotonic()        # the click is confirmed within 3 s of its dispatch
        done, score = wait_slicing_done(session, timeout_s=3)
        analysis['slice_button_done_template'] = {'at_s': round(time.monotonic() - started, 2),
                                                   'done': done, 'score': score}
        reason = watch(session, private_temp, work, analysis, started, args)
        retain(private_temp, work, analysis, session.pid)
    capture(session, work / 'final.png')
    analysis['results']['record (not a verdict)'] = f'RECORDED: {reason}'
    if reason == UNANSWERED:
        raise ValueError(reason)


def prepare_fixture(model, work):
    """The sphere under its canonical name, and a private temporary directory for the app's plate files."""
    original = Path(model).read_bytes()
    if hashlib.sha256(original).hexdigest() != MODEL_FIXTURES['_sphere'][1]:
        raise ValueError('not the standard sphere fixture')
    fixture = work / 'fixture.3mf'
    fixture.write_bytes(original)
    private_temp = work / 'probe-temp'
    private_temp.mkdir()
    for name in ('TMP', 'TEMP'):          # launcher.py hands os.environ to the app
        STATE[name] = os.environ.get(name)
        os.environ[name] = str(private_temp)
    return fixture


def extra_args(parser):
    parser.add_argument('--hog-mb', type=int, default=0,
                        help='hold this much memory in a helper process from the slice click on (0 = read '
                             f'{MARKER}, else none)')
    parser.add_argument('--hold-warning', action='store_true',
                        help='record the warning but never answer it (the control run)')
    parser.add_argument('--menu-s', type=float, default=5.0, help='seconds between reads of the export row')
    parser.add_argument('--limit-s', type=float, default=300.0, help='longest watch after the click')
    parser.add_argument('--quiet-s', type=float, default=15.0,
                        help='unchanged seconds that mean a stalled file (three times as long after an answer)')


def main():
    try:
        return case_main(254, FIXTURE, prepare_fixture, steps, extra_args)
    finally:
        if 'hog' in STATE:
            STATE['hog'].kill()
            STATE['hog'].wait()
        for name in ('TMP', 'TEMP'):
            if name in STATE:
                if STATE[name] is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = STATE[name]


if __name__ == '__main__':
    raise SystemExit(main())
