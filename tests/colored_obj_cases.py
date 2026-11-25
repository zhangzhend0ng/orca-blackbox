#!/usr/bin/env python3
"""Fixture and GUI-step helpers for Feishu #228: an OBJ whose faces carry two materials.

The fixture is written by the case itself, in pure Python, into the run directory.
Nothing here judges the product; tests/colored_obj_oracle.py does.

What each form of the fixture makes the application do, read in the source of
the guest build (ref ``sync/softfever-20261010``, 813784a9d0):

* ``model.obj`` + ``model.mtl`` + ``texture.png``, the material ``red``
  carrying ``map_Kd texture.png`` and the faces carrying ``vt``: ``load_obj``
  sets ``has_uv_png`` and keeps the UVs (OBJ.cpp:173-190);
  ``Model::read_from_file`` hands the mesh and the materials to
  ``obj_to_textured_mesh`` and keeps the result as the model's ``texture_mesh``
  (Model.cpp:356-365); the GUI shows the modal ``Import Model`` dialog
  (Plater.cpp:24060, title at TextureImportDialog.cpp:1777) whose ``Confirm``
  button has the id wxID_OK (TextureImportDialog.cpp:2352-2353).
* ``model_kd.obj`` + ``model_kd.mtl``, no ``map_Kd`` and no ``vt``: the face
  colours become ``precomputed_face_colors`` (Model.cpp:398-415) and the same
  dialog follows (Plater.cpp:700-706 returns true for them).

The dialog is surveyed before anything is pressed: its class, title, every
child window with its class, text, control id and enabled state, and a
picture. Only then is the affirmative button pressed, by control id or by its
text, and the dialog is confirmed closed. Without such a button the survey
and the picture stay in the analysis and the case stops with an error.

On the tag ``sm-v2.4.0`` (b1831e5d) the same two forms take another way:
``Model::read_from_file`` calls ``objFn`` only when ``has_uv_png`` is false
(Model.cpp:282-296 there), which shows ``Obj file Import color``
(ObjColorDialog.cpp:143), and a textured OBJ is loaded as plain geometry.
"""
import ctypes
from hashlib import sha256
from pathlib import Path
import struct
import time
import zlib

import cv2

import m7_common as m7
from colored_obj_oracle import MATERIALS, material_triangles, mesh_geometry
from file_export_cases import capture_window, descendants, row_label
from harness import export_util, topbar_util, winutil
from m8_common import wait_arrival

TEXTURE = 'texture.png'
IMPORT_DIALOG = 'Import Model'
WXID_OK = 5104
AFFIRMATIVE = ('confirm', 'ok', 'import', 'yes', 'continue')
CHILD_LIMIT = 80


# --- the fixture ---------------------------------------------------------------

def _png(pixels):
    """An 8-bit RGB PNG (IHDR, IDAT, IEND, each with its CRC) from rows of (red, green, blue)."""
    raw = b''.join(b'\x00' + bytes(channel for pixel in row for channel in pixel) for row in pixels)

    def chunk(kind, data):
        body = kind + data
        return struct.pack('>I', len(data)) + body + struct.pack('>I', zlib.crc32(body) & 0xffffffff)

    header = struct.pack('>IIBBBBB', len(pixels[0]), len(pixels), 8, 2, 0, 0, 0)
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')


def _red_texture(side=16):
    """A uniform red square: with the material's Kd 1 0 0 the red material reads red either way."""
    return _png([[(255, 0, 0)] * side for _ in range(side)])


def _obj_text(stem, geometry, uv):
    """The OBJ text of a fixture geometry: the vertices once, the faces under their material's
    ``usemtl``. Lines end with a line feed only: after the last number of a ``Kd`` line the
    parser of the guest build accepts a space, a tab or the end of the line and nothing else
    (Format/objparser.cpp:546, 566)."""
    vertices, faces = mesh_geometry(geometry)
    lines = [f'mtllib {stem}.mtl', '# Feishu #228: a 20 mm cube, the left half red and the right half blue']
    lines += [f'v {x:g} {y:g} {z:g}' for x, y, z in vertices]
    if uv:
        lines += ['vt 0 0', 'vt 1 0', 'vt 1 1', 'vt 0 1']
    for material in MATERIALS:
        lines.append(f'usemtl {material}')
        for i, j, k, owner in faces:
            if owner == material:
                lines.append('f ' + ' '.join(f'{index + 1}/{index % 4 + 1}' if uv else str(index + 1)
                                             for index in (i, j, k)))
    return ('\n'.join(lines) + '\n').encode('ascii')


def _mtl_text(texture):
    """Two materials in the spelling the parser of the guest build reads with that casing
    (Format/objparser.cpp:495-512 for ``newmtl`` and ``map_Kd``, 532-573 for ``Ka`` and ``Kd``)."""
    lines = ['# Feishu #228: two materials', 'newmtl red', 'Ka 0 0 0', 'Kd 1 0 0']
    if texture:
        lines.append(f'map_Kd {TEXTURE}')
    lines += ['', 'newmtl blue', 'Ka 0 0 0', 'Kd 0 0 1', '']
    return ('\n'.join(lines)).encode('ascii')


def write_fixture(work, stem='model', texture=True, uv=True, geometry='two-boxes'):
    """Write ``<stem>.obj``, ``<stem>.mtl`` and (unless it is already there) ``texture.png`` into
    `work`; returns what was written, with the byte count and SHA-256 of each file. ``geometry``
    names a geometry of colored_obj_oracle.GEOMETRIES."""
    work = Path(work)
    files = {f'{stem}.obj': _obj_text(stem, geometry, uv), f'{stem}.mtl': _mtl_text(texture)}
    if texture or not (work / TEXTURE).is_file():
        files[TEXTURE] = _red_texture()
    for name, raw in files.items():
        if not name.endswith('.png') and b'\r' in raw:  # the text files end their lines with a line feed only
            raise ValueError(f'{name} was about to be written with a carriage return')
        (work / name).write_bytes(raw)
    return {'obj': f'{stem}.obj', 'mtl': f'{stem}.mtl', 'geometry': geometry,
            'texture_referenced': texture, 'obj_has_uv': uv,
            'faces': {name: len(faces) for name, faces in material_triangles(geometry).items()},
            'files': {name: {'bytes': len(raw), 'sha256': sha256(raw).hexdigest()} for name, raw in files.items()}}


# --- the application's own dialogs ---------------------------------------------

def app_dialogs(session, title=''):
    """[(class, title, rect, hwnd)] of the application's visible dialog windows (#32770) and of
    any visible top-level window of it whose title contains `title`."""
    found = []

    def visit(hwnd, _lp):
        if winutil._window_pid(hwnd) != session.pid or not winutil.user32.IsWindowVisible(hwnd):
            return True
        cls, text = winutil.window_class(hwnd), winutil.window_title(hwnd)
        if cls == '#32770' or (title and title.casefold() in text.casefold()):
            found.append((cls, text, winutil.window_rect(hwnd), hwnd))
        return True

    winutil.user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(visit), 0)
    return found


def survey_dialog(work, hwnd, stem):
    """What a dialog shows: class, title, its children (class, text, control id, state, place)
    and a picture kept as `<stem>.png`."""
    children = []
    for cls, text, child in descendants(hwnd):
        if len(children) >= CHILD_LIMIT:
            break
        if text or winutil.user32.IsWindowVisible(child):
            children.append({'class': cls, 'text': text, 'hwnd': child, 'id': winutil.user32.GetDlgCtrlID(child),
                             'enabled': bool(winutil.user32.IsWindowEnabled(child)),
                             'visible': bool(winutil.user32.IsWindowVisible(child)),
                             'rect': list(winutil.window_rect(child))})
    record = {'class': winutil.window_class(hwnd), 'title': winutil.window_title(hwnd),
              'rect': list(winutil.window_rect(hwnd)), 'children': children, 'image': f'{stem}.png'}
    try:
        capture_window(hwnd, Path(work) / record['image'])
    except (OSError, RuntimeError, ValueError, cv2.error) as exc:
        record['image'] = f'unavailable ({exc})'
    return record


def affirmative(children):
    """The child that accepts the dialog: the one with the control id wxID_OK, else the one
    enabled and visible child named like an affirmative; None when there is not exactly one."""
    by_id = [child for child in children if child['id'] == WXID_OK]
    if len(by_id) == 1:
        return by_id[0]
    named = [child for child in children
             if child['text'].strip().casefold() in AFFIRMATIVE and child['enabled'] and child['visible']]
    return named[0] if len(named) == 1 else None


def press_child(session, dialog, child):
    """Click one child of a dialog until the dialog closes; returns what was tried."""
    left, top, right, bottom = child['rect']
    x, y = (left + right) // 2, (top + bottom) // 2
    tiers = []
    winutil.msg_click_screen(x, y, dialog)  # resolved inside the dialog's own window tree
    time.sleep(1.5)
    tiers.append({'how': 'message click inside dialog', 'at': [x, y],
                  'closed': not winutil.user32.IsWindowVisible(dialog)})
    if (not tiers[-1]['closed'] and winutil.user32.IsWindow(dialog)
            and winutil._window_pid(winutil.window_from_screen_point(x, y)) == session.pid):
        # A real click goes through the OS input queue: only onto a window of the application under test.
        winutil.user32.SetCursorPos(x, y)
        time.sleep(0.2)
        winutil.real_click_screen(x, y)
        time.sleep(1.5)
        tiers.append({'how': 'real click', 'at': [x, y],
                      'closed': not winutil.user32.IsWindowVisible(dialog)})
    return tiers


def _import_dialog(session, work, record_list, stem):
    """Survey the application's material dialog, press its affirmative button and confirm it closed."""
    _cls, _title, _rect, hwnd = next(dialog for dialog in app_dialogs(session, IMPORT_DIALOG)
                                     if IMPORT_DIALOG.casefold() in dialog[1].casefold())
    record = survey_dialog(work, hwnd, stem)
    record_list.append(record)
    print(f'[m7x228] {record["title"]!r}: {[child["text"] for child in record["children"] if child["text"]][:40]!r}',
          flush=True)
    button = affirmative(record['children'])
    if button is None:
        raise ValueError(f'{record["title"]!r} has no single affirmative button to press: '
                         f'{[(child["text"], child["id"], child["enabled"]) for child in record["children"]][:40]!r}')
    record['pressed'] = {'text': button['text'], 'id': button['id']}
    record['tiers'] = press_child(session, hwnd, button)
    record['closed'] = not winutil.user32.IsWindowVisible(hwnd)
    if not record['closed']:
        raise ValueError(f'{record["title"]!r} stayed open after {button["text"]!r} was pressed')
    return record


def wait_import(session, work, analysis, key='import_dialogs', stem='import-dialog', timeout_s=120):
    """After the chooser took the OBJ: answer every dialog the application shows and wait for
    the model. Each dialog met is written to `analysis[key]` with a picture; an error dialog
    stops the case after its survey is kept. Returns (arrived, coloured fraction)."""
    deadline = time.monotonic() + timeout_s
    met = analysis.setdefault(key, [])
    seen, quiet = set(), 0
    while time.monotonic() < deadline:
        import_dialogs = [dialog for dialog in app_dialogs(session, IMPORT_DIALOG)
                          if IMPORT_DIALOG.casefold() in dialog[1].casefold()]
        if import_dialogs:
            _import_dialog(session, work, met, f'{stem}-{len(met)}')
            quiet = 0
            continue
        arrived, fraction = wait_arrival(session, timeout_s=2, min_frac=0.001)
        for cls, title, _rect, hwnd in app_dialogs(session):
            if hwnd in seen or title.casefold().startswith('loading'):
                continue
            seen.add(hwnd)
            record = survey_dialog(work, hwnd, f'{stem}-{len(met)}')
            met.append(record)
            print(f'[m7x228] dialog {title!r}: {[child["text"] for child in record["children"] if child["text"]][:24]!r}',
                  flush=True)
            if 'error' in title.casefold():
                raise ValueError(f'the application showed {title!r}: '
                                 f'{[child["text"] for child in record["children"] if child["text"]][:12]!r}')
        quiet = quiet + 1 if arrived and not app_dialogs(session) else 0
        if quiet >= 2:
            return arrived, fraction
        time.sleep(0.5)
    raise ValueError(f'the OBJ did not appear on the plate within {timeout_s}s; dialogs met '
                     f'{[record.get("title") for record in met]!r}')


def hand_file_to_import(session, source, work, analysis, key, image):
    """File > Import > the one row that names the model formats: keep what the chooser showed,
    then give it `source` (the same steps as #227's import_stl, under other names)."""
    source, work = Path(source), Path(work)
    menu = topbar_util.open_file_menu(session)
    if not menu:
        raise ValueError('topbar File menu did not open')
    _rect, _hwnd, hmenu = menu
    index = topbar_util.find_item(hmenu, 'Import')
    rows = [] if index is None else [
        {'label': text, 'enabled': not flags & 3}
        for _i, text, flags in topbar_util.menu_items(topbar_util.item_info(hmenu, index)[1])]
    topbar_util.close_menu_windows(session.pid)
    hits = [row for row in rows if 'obj' in row_label(row['label']).casefold()]
    if len(hits) != 1 or not hits[0]['enabled']:
        raise ValueError(f'File > Import does not offer exactly one enabled row naming OBJ: {rows!r}')
    dispatched, dialog = m7.file_menu_dispatch(session, hits[0]['label'], expect_dialog=True, via='Import', timeout_s=10)
    if not dispatched or not dialog:
        raise ValueError(f'File > Import > {hits[0]["label"]!r} opened no chooser (dispatched={dispatched!r}, dialog={dialog!r})')
    _cls, title, _rect, hwnd = dialog
    children = descendants(hwnd)
    edit = export_util.find_edit(hwnd)
    if edit is None or winutil._window_pid(edit) != session.pid:
        winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 2, 0)
        raise ValueError(f'{title!r} has no owned file name box')
    entry = analysis[key] = {'row': hits[0]['label'], 'title': title,
                             'labels': [text for _cls, text, child in children
                                        if text and winutil.user32.IsWindowVisible(child)],
                             'image': capture_window(hwnd, work / image)}
    winutil.select_all(edit)
    winutil.msg_text(edit, str(source))
    entry['entered'] = winutil.edit_text(edit, size=1024)
    if entry['entered'] != str(source):
        winutil._send_msg(hwnd, m7.WM_COMMAND_MSG, 2, 0)
        raise ValueError(f'the chooser did not keep the path {source!r}: {entry["entered"]!r}')
    winutil._send_msg(hwnd, 0x0111, 1, 0)  # IDOK
    deadline = time.monotonic() + 15
    while winutil.user32.IsWindowVisible(hwnd) and time.monotonic() < deadline:
        time.sleep(0.2)
    entry['dialog_closed'] = not winutil.user32.IsWindowVisible(hwnd)
    if not entry['dialog_closed']:
        raise ValueError(f'{title!r} stayed open after {source.name} was given to it')
    return entry
