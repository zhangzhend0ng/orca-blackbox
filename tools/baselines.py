"""Latest harvested run of every save-only baseline: run id, machine, verdict,
error - and, on demand, what the save changed outside the known migrations.

    python tools/baselines.py <repo-root> [--diff]

The harvest is looked up under ORCA_BB_HARVEST, else under
<repo-root>/artifacts/windows_mcp_harvest (the code may live in another
worktree than the runs). Every fixture behind the suffix rule has its own
save-only baseline (harness/agent_protocol.BASELINES); on 2026-11-24 all
fourteen - the cube's control and the thirteen fixtures - came back SHADOW
with nothing outside the migrations.
"""
import glob
import hashlib
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
root = sys.argv[1]
sys.path.insert(0, root)
from harness.agent_protocol import BASELINES, FIXTURE_SUFFIXES, LAYER_FIXTURE_SHA256  # noqa: E402
from harness.pilot_common import _ADDED_DEFAULTS, _VECTOR_MIGRATIONS  # noqa: E402
import zipfile  # noqa: E402

HARVEST = os.environ.get("ORCA_BB_HARVEST") or os.path.join(root, "artifacts", "windows_mcp_harvest")


def settings(raw):
    return json.loads(zipfile.ZipFile(io.BytesIO(raw)).read("Metadata/project_settings.config").decode("utf-8-sig"))


def outside(saved, fixture):
    odd = []
    for key in sorted(set(saved) | set(fixture)):
        before, after = fixture.get(key), saved.get(key)
        if before == after or key == "different_settings_to_system":
            continue
        if key in _ADDED_DEFAULTS and after == _ADDED_DEFAULTS[key]:
            continue
        if key in _VECTOR_MIGRATIONS and isinstance(before, str) and after == [before]:
            continue
        if key in ("printer_settings_id", "print_settings_id") and after == before + "(fixture.3mf)":
            continue
        if key == "filament_settings_id" and after == [v + "(fixture.3mf)" for v in before]:
            continue
        if key == "version" and before == "2.3.6" and after == "2.4.0":
            continue
        if key == "filament_ids" and before[0] == "GFSG99" and after == [""] + before[1:]:
            continue
        odd.append(key)
    return odd


shas = {sha: suffix for suffix, (_path, sha) in FIXTURE_SUFFIXES.items()}
shas[LAYER_FIXTURE_SHA256] = "(cube)"
for name in ["uia_param_save_only"] + [b for b, _c in BASELINES.values()]:
    best = None
    for d in glob.glob(os.path.join(HARVEST, "*") + os.sep):
        try:
            scope = json.load(open(d + "scope.json", encoding="utf-8-sig"))
            proc = json.load(open(d + "process.json", encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        if scope.get("scenario") == name and proc.get("started_at_ns"):
            if best is None or proc["started_at_ns"] > best[0]:
                best = (proc["started_at_ns"], d)
    if not best:
        print("%-30s NOT RUN" % name)
        continue
    d = best[1]
    result = json.load(open(d + "result.json", encoding="utf-8-sig"))
    worker = json.load(open(d + "native_worker.json", encoding="utf-8-sig"))
    log = open(d + "native_worker.log", "rb").read()
    sha = hashlib.sha256(open(d + "input/fixture.3mf", "rb").read()).hexdigest()
    line = "%-30s %s %-4s %-9s %s" % (name, os.path.basename(d.rstrip(os.sep))[:8], "fa" if b"ORCA_BB_ALLOW_TESTBOX" in log else "vm",
                                      result.get("release_verdict"), (worker.get("error") or "")[:60])
    if "--diff" in sys.argv and result.get("release_verdict") == "SHADOW":
        proof = glob.glob(d + "proof/*.3mf")
        if proof:
            line += " | outside migrations: %s" % (outside(settings(open(proof[0], "rb").read()),
                                                       settings(open(d + "input/fixture.3mf", "rb").read())) or "none")
    print(line + "  [%s]" % shas.get(sha, sha[:8]))
