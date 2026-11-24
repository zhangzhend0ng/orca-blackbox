"""Offline proof that a rebuilt fixture is what the app itself saves: compare the
fixture's config with the config the app SAVED from the previous build of it
(a harvested save-only run), minus the serialisation migrations pilot_common
allows. Zero keys outside the migrations = a plain save of the new fixture will
pass the preserved-settings rule as far as the app's own writing can tell.

    python tools/fixture_vs_saved.py <repo-root> <fixture.3mf> <run-id prefix>
"""
import glob
import io
import json
import os
import sys
import zipfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
root, fixture_path, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, root)
from harness import pilot_common as pc  # noqa: E402


def config(path):
    return json.loads(zipfile.ZipFile(path).read("Metadata/project_settings.config").decode("utf-8-sig"))


hit = [h for h in glob.glob(os.path.join("artifacts", "windows_mcp_harvest", prefix + "*")) if os.path.isdir(h)][0] + os.sep
saved, fixture = config(glob.glob(hit + "proof/*.3mf")[0]), config(fixture_path)
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
print("keys outside the known migrations (new fixture vs the app's saved config):", len(odd))
for key, before, after in odd:
    print("   %-30s %s -> %s" % (key, json.dumps(before, ensure_ascii=False)[:70], json.dumps(after, ensure_ascii=False)[:70]))
print("manifest equal:", fixture.get("different_settings_to_system") == saved.get("different_settings_to_system"))
