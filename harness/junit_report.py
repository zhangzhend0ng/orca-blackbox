"""harness/junit_report.py — JUnit XML emitter for batch entries (stdlib only).

Consumed by run_regression.sh after each case finishes: read the case log,
parse the verdict via case_runner.parse_case_result, accumulate into one
<testsuite>, write artifacts/junit.xml. Single-case direct runs pay nothing —
emission happens only at the batch layer, and the verdict output format of
m3_common.verdict() is untouched.
"""

from __future__ import annotations

import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

# allow "python harness/junit_report.py ..." from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.case_runner import parse_case_result  # noqa: E402


def add_result(suite: ET.Element, case: str, rc: int, log_path: Path,
               duration_s: float, timed_out: bool = False) -> ET.Element:
    """Append one <testcase> from a finished case's log; returns the element."""
    # utf-8-sig: guest logs are Out-File utf8 (PS 5.1 adds a BOM)
    text = log_path.read_text(encoding="utf-8-sig", errors="replace") if log_path.exists() else ""
    parsed = parse_case_result(text, rc, timed_out)
    tc = ET.SubElement(suite, "testcase", {
        "name": case,
        "classname": f"blackbox.{case.rsplit('_', 1)[0] if '_' in case else case}",
        "time": f"{max(duration_s, 0.0):.1f}",
    })
    verdict = parsed["verdict"] or {}
    props = ET.SubElement(tc, "properties")
    ET.SubElement(props, "property", {"name": "log", "value": str(log_path)})
    for k, v in verdict.items():
        ET.SubElement(props, "property", {"name": f"dim:{k}", "value": v[:200]})
    if timed_out:
        ET.SubElement(tc, "error", {"type": "Timeout"}).text = \
            "case driver killed after timeout (app swept via WM_CLOSE)"
    elif not parsed["green"]:
        fail = ET.SubElement(tc, "failure", {
            "type": "RED" if verdict else f"exit-{rc}",
            "message": "; ".join(f"{k}: {v}" for k, v in verdict.items()
                                 if not v.startswith("PASS")) or f"exit code {rc}",
        })
        fail.text = "\n".join(text.splitlines()[-30:]) or ""
    else:
        so = ET.SubElement(tc, "system-out")
        so.text = "\n".join(text.splitlines()[-10:])
    return tc


def new_suite(name: str = "orca-blackbox") -> ET.Element:
    return ET.Element("testsuite", {"name": name, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})


def write(suite: ET.Element, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    root = ET.Element("testsuites")
    suite.set("tests", str(len(suite.findall("testcase"))))
    suite.set("failures", str(len(suite.findall("testcase/failure"))))
    suite.set("errors", str(len(suite.findall("testcase/error"))))
    root.append(suite)
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(out_path, encoding="utf-8", xml_declaration=True)
    return out_path


def main(argv: list[str]) -> int:
    """CLI with two modes (stdlib only, consumed by run_regression.sh):

    single: python harness/junit_report.py <case> <rc> <log_path> [out_path]
    batch:  python harness/junit_report.py --batch <out_path> <case>|<rc>|<log_path> ...
            (durations unknown at batch time -> 0; logs carry timestamps)
    """
    if len(argv) >= 4 and argv[1] == "--batch":
        out = Path(argv[2])
        suite = new_suite()
        for spec in argv[3:]:
            case, rc, log = spec.split("|", 2)
            add_result(suite, case, int(rc), Path(log), 0.0)
        print(write(suite, out))
        return 0
    if len(argv) < 4:
        print(__doc__)
        return 2
    case, rc, log = argv[1], int(argv[2]), Path(argv[3])
    out = Path(argv[4]) if len(argv) > 4 else log.parent / "junit.xml"
    suite = new_suite()
    add_result(suite, case, rc, log, 0.0)
    print(write(suite, out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
