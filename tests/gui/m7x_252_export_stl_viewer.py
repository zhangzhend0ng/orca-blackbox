#!/usr/bin/env python3
"""#252 Export a selected object's complete STL and open it independently in F3D."""
# feishu: baseline#252
from hashlib import sha256
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(HERE), str(HERE / 'tests')]

from harness import export_util, winutil
import m7_common as m7
from m7x_247_split_shells import prepare_fixture
from model_context_cases import open_model_menu
from plate_reserve_case import activate, case_main, save_snapshot
from plate_reserve_oracle import verify_f3d_image, verify_stl


DEFAULT_VIEWER = Path('C:/coil/Tools/orca-bb-f3d/bin/f3d-console.exe')


def export_stl(session, target):
    activate(session, open_model_menu(session, 'Export as one STL'), '[m7x252]')
    dialog = m7.wait_dialog(session.pid, timeout_s=15, title_substr='Export STL file')
    edit = export_util.find_edit(dialog[3]) if dialog else None
    if edit is None or winutil._window_pid(edit) != session.pid:
        raise ValueError('owned Export STL file chooser did not open')
    winutil.select_all(edit)
    winutil.msg_text(edit, str(target))
    if winutil.edit_text(edit, size=260) != str(target):
        raise ValueError('STL output path was not accepted by the native chooser')
    winutil._send_msg(dialog[3], 0x0111, 1, 0)  # WM_COMMAND / IDOK.
    if not export_util.wait_file(target, timeout_s=35):
        raise ValueError('no nonempty STL at the chosen output path')
    deadline = time.monotonic() + 10
    while winutil.user32.IsWindowVisible(dialog[3]) and time.monotonic() < deadline:
        time.sleep(0.2)
    if not session.alive() or m7.wait_dialog(session.pid, timeout_s=0.75):
        raise ValueError('STL export left the editor in an unexpected dialog or exit state')


def run_viewer(exe, args, work, name):
    command = [str(exe), *map(str, args)]
    with (work / (name + '.log')).open('wb') as log:
        return subprocess.run(command, cwd=work, stdin=subprocess.DEVNULL, stdout=log,
                              stderr=subprocess.STDOUT, timeout=45, check=False).returncode


def open_in_viewer(args, exported, work, analysis):
    configured = args.viewer or os.environ.get('ORCA_BB_F3D')
    detected = configured or (DEFAULT_VIEWER if DEFAULT_VIEWER.is_file() else shutil.which('f3d'))
    if detected is None or not (exe := Path(detected).resolve()).is_file():
        raise ValueError('third-party F3D executable unavailable, export geometry retained')
    version_rc = run_viewer(exe, ['--version'], work, 'f3d-version')
    version = (work / 'f3d-version.log').read_text(encoding='utf-8', errors='replace')
    if version_rc or 'f3d' not in version.casefold():
        raise ValueError('external executable did not identify itself as F3D')
    receipt = analysis['viewer'] = {'path': str(exe), 'version': version.strip(), 'version_rc': version_rc,
                                    'source_sha256': sha256(exported.read_bytes()).hexdigest()}
    options = ['--no-cache', '--no-background', '--resolution=800,600']
    rendered = work / 'f3d-view.png'
    receipt['positive_rc'] = run_viewer(exe, [exported, f'--output={rendered}', *options], work, 'f3d-view')
    if receipt['positive_rc']:
        raise ValueError('F3D failed to open the exact exported STL')
    receipt['image'] = verify_f3d_image(rendered)
    receipt['output_sha256'] = sha256(rendered.read_bytes()).hexdigest()
    corrupt = work / 'invalid.stl'
    corrupt.write_bytes(b'not an STL mesh\n')
    negative = work / 'f3d-invalid.png'
    receipt['negative_rc'] = run_viewer(exe, [corrupt, f'--output={negative}', *options], work, 'f3d-invalid')
    if negative.is_file():
        try:
            verify_f3d_image(negative)
        except (OSError, ValueError):
            pass
        else:
            raise ValueError('F3D output check accepted an invalid STL')
    receipt['negative_rejected'] = True


def steps(session, work, analysis, args):
    before = save_snapshot(session, work, 'before')
    target = work / 'selected-object.stl'
    export_stl(session, target)
    analysis['export_geometry'] = verify_stl(before, target)
    analysis['results']['native menu exported all triangles of the selected object to the chosen STL path'] = 'PASS'
    open_in_viewer(args, target, work, analysis)
    analysis['results']['third-party F3D opened and rendered the exact STL, rejecting the malformed control'] = 'PASS'


if __name__ == '__main__':
    raise SystemExit(case_main(252, HERE / 'fixtures/feishu_std_cube.3mf', prepare_fixture, steps,
                               lambda parser: parser.add_argument('--viewer', type=Path)))
