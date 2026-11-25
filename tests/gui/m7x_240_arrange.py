#!/usr/bin/env python3
# feishu: baseline#240
"""Arrange three intersecting instances from the blank plate context menu."""
import time

from plate_layout_case import activate_on_blank_plate, record_checks, run_case, save_stage


def arrange(session, work, before, analysis, log):
    from plate_layout_oracle import verify_arrange

    initial = verify_arrange(before, before)
    if not initial['checks']['every_pair_overlapped_before']:
        raise ValueError('all three input pairs must overlap before Arrange')
    analysis['results']['loaded objects pairwise overlap'] = 'PASS'
    started = time.monotonic()
    activate_on_blank_plate(session, 'Arrange', log)
    time.sleep(5)
    after = save_stage(session, work, 'after')
    record_checks(analysis, verify_arrange(before, after))
    analysis['phase_seconds']['arrange_and_save'] = round(time.monotonic() - started, 3)


if __name__ == '__main__':
    raise SystemExit(run_case(240, arrange))
