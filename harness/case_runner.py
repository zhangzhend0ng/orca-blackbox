"""harness/case_runner.py — shared post-run analysis of a case log.

Extracted verbatim from mcp_server.py tool_run_case's verdict-parsing logic
so batch entries (run_regression.sh via emit_junit, hv_go guest suite) and
the MCP tool agree on ONE convention:

- verdict block: lines between "=== verdict ===" and the next "[...]" line,
  each "key: value" becomes a dimension;
- GREEN/RED marker anywhere in the log wins;
- no marker -> m0/m1/m2 convention: the exit code IS the verdict.
"""

from __future__ import annotations


def parse_case_result(text: str, rc: int, timed_out: bool = False) -> dict:
    """Return {green, verdict} for a finished case run's log text."""
    green = None  # explicit GREEN/RED marker if the case prints one
    verdict: dict[str, str] = {}
    in_block = False
    for line in text.splitlines():
        if "=== verdict ===" in line:
            in_block = True
            continue
        if in_block:
            s = line.strip()
            if s.startswith("["):
                in_block = False
            elif ":" in s:
                k, _, v = s.partition(":")
                verdict[k.strip()] = v.strip()
        if "GREEN" in line:
            green = True
        elif "RED" in line:
            green = False
    if green is None:
        # m0/m1/m2 convention: the exit code IS the verdict (no GREEN marker)
        green = (rc == 0) and not timed_out
    return {"green": green, "verdict": verdict or None}
