#!/usr/bin/env python3
# feishu: baseline#241
"""Auto Rotate both tipped objects from the blank plate context menu."""
import time

from plate_layout_case import activate_on_blank_plate, record_checks, run_case, save_stage


def orient(session, work, before, analysis, log):
    from plate_layout_oracle import verify_orient

    started = time.monotonic()
    activate_on_blank_plate(session, 'Auto Rotate', log)
    time.sleep(8)
    after = save_stage(session, work, 'after')
    record_checks(analysis, verify_orient(before, after))
    analysis['phase_seconds']['auto_rotate_and_save'] = round(time.monotonic() - started, 3)


if __name__ == '__main__':
    raise SystemExit(run_case(241, orient))
