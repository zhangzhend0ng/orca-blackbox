"""Keys a harvested run's SAVED project config differs in from the FIXTURE it
opened, minus the serialisation migrations pilot_common already allows.

    python tools/diff_saved.py <repo-root> <run-id prefix>   (harvest looked up under <repo-root>, then under the cwd)

Read-only. Prints the keys outside the known migrations (before -> after) and
the manifest of both. <repo-root> supplies harness.pilot_common; run it with
the worktree whose rules you want applied."""
import glob
import hashlib
import io
import json
import os
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
root, prefix = sys.argv[1], sys.argv[2]
sys.path.insert(0, root)
from harness import pilot_common as pc  # noqa: E402

hit = [h for h in glob.glob(os.path.join(root, "artifacts", "windows_mcp_harvest", prefix + "*")) if os.path.isdir(h)]
if not hit:
    hit = [h for h in glob.glob(os.path.join("artifacts", "windows_mcp_harvest", prefix + "*")) if os.path.isdir(h)]
d = hit[0] + os.sep


def config(path):
    return json.loads(zipfile.ZipFile(path).read("Metadata/project_settings.config").decode("utf-8-sig"))


proof = glob.glob(d + "proof/*.3mf")
if not proof:
    print("no proof 3mf in", d)
    raise SystemExit(1)
saved, fixture = config(proof[0]), config(d + "input/fixture.3mf")
raw = open(d + "input/fixture.3mf", "rb").read()
print("run", os.path.basename(d.rstrip(os.sep))[:8], "fixture sha", hashlib.sha256(raw).hexdigest()[:12])
print("manifest fixture", fixture.get("different_settings_to_system"))
print("manifest saved  ", saved.get("different_settings_to_system"))
odd = []
for key in sorted(set(saved) | set(fixture)):
    before, after = fixture.get(key), saved.get(key)
    if before == after or key == "different_settings_to_system":
        continue
    if key in pc._ADDED_DEFAULTS and after == pc._ADDED_DEFAULTS[key]:
        continue
    if key in pc._VECTOR_MIGRATIONS and isinstance(before, str) and after == [before]:
        continue
    if key in ("printer_settings_id", "print_settings_id") and after == before + "(fixture.3mf)":
        continue
    if key == "filament_settings_id" and after == [v + "(fixture.3mf)" for v in before]:
        continue
    if key == "version" and before == "2.3.6" and after == "2.4.0":
        continue
    if key == "filament_ids" and before[0] == "GFSG99" and after == [""] + before[1:]:
        continue
    odd.append((key, before, after))
print("keys outside the known migrations:", len(odd))
for key, before, after in odd:
    print("   %-30s %s -> %s" % (key, json.dumps(before, ensure_ascii=False)[:70], json.dumps(after, ensure_ascii=False)[:70]))
