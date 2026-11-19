"""Inventory config dependency evidence from immutable upstream Git blobs."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
from contextlib import ExitStack
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "contracts/config_dependencies.json"
SOURCE_ROOTS = ("src",)
PRESET_ROOTS = ("resources/profiles", "resources/profiles_template")
DEFINITIONS = "src/libslic3r/PrintConfig.cpp"
TOKEN = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
IDENT = re.compile(r"\b[a-z][a-z0-9_]*\b")
ENTRY = re.compile(r"\b(if|switch|while|toggle_line|toggle_field|set_key_value|set_visible|set_enabled)\s*\(")
CONFIG_READ = re.compile(
    r'\b(?:opt_[a-z_]+|opt|option|has|get_abs_value)\s*(?:<[^;<>\n]+>)?\s*\(\s*"([a-z0-9_]+)"'
    r'|\b(?:[a-z_]*config(?:\s*\(\))?)(?:\.|->)([a-z0-9_]+)'
)
PRESET_KEYS = ("inherits", "compatible_printers", "compatible_printers_condition",
               "compatible_prints", "compatible_prints_condition", "default_print_profile",
               "default_filament_profile", "printer_model", "printer_variant", "nozzle_diameter",
               "min_layer_height", "max_layer_height", "filament_type", "filament_is_support",
               "exclude", "excluded_printers", "version")


def git(upstream, *args):
    return subprocess.check_output(["git", "-C", str(upstream), *args])


def blob(process, oid):
    process.stdin.write(oid.encode() + b"\n")
    process.stdin.flush()
    header = process.stdout.readline().split()
    if len(header) != 3 or header[1] != b"blob":
        raise ValueError(f"Cannot read Git blob {oid}")
    content = process.stdout.read(int(header[2]))
    if process.stdout.read(1) != b"\n":
        raise ValueError(f"Truncated Git blob {oid}")
    return content.decode("utf-8-sig", errors="replace")


def mask(text):
    return TOKEN.sub(lambda match: re.sub(r"[^\n]", " ", match[0]), text)


def closing_token(source, start, opening, closing):
    depth = 1
    for index in range(start, len(source)):
        if source[index] == opening:
            depth += 1
        elif source[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


def record(kind, file, line, trigger, affected, scope, expected, evidence):
    token = json.dumps([kind, file, trigger, affected], ensure_ascii=False)
    return {"id": kind + "-" + hashlib.sha256(token.encode()).hexdigest()[:24],
            "kind": kind, "trigger": trigger, "affected": affected, "scope": scope,
            "expected": expected, "evidence": evidence, "source": [{"file": file, "line": line}]}


def source_records(file, text, settings, unresolved):
    clean = mask(text)
    newlines = [m.start() for m in re.finditer("\n", text)]
    for match in ENTRY.finditer(clean):
        end = closing_token(clean, match.end(), "(", ")")
        if end is None:
            unresolved.append({"file": file, "line": bisect_right(newlines, match.start()) + 1})
            continue
        call = match[1]
        expression = text[match.end():end].strip()
        keys = sorted(settings.intersection(IDENT.findall(expression)))
        if not keys and call in {"if", "switch", "while"}:
            continue
        line = bisect_right(newlines, match.start()) + 1
        start = end + 1
        start += len(clean[start:]) - len(clean[start:].lstrip())
        statement = ""
        if call in {"if", "switch", "while"}:
            stop = (closing_token(clean, start + 1, "{", "}") if clean[start:start + 1] == "{"
                    else clean.find(";", start))
            if stop is not None and stop >= start:
                statement = text[start:min(stop + 1, start + 900)].strip()
        row = record("source_candidate", file, line, expression, keys, call,
                     "Review branch effects, outer guards and data flow.", "inference_pending")
        row["statement"] = statement
        yield row
    for match in CONFIG_READ.finditer(text):
        key = match[1] or match[2]
        # Ignore comments and quoted snippets while retaining quoted option keys.
        if key in settings and clean[match.start():match.start() + 1].strip():
            line = bisect_right(newlines, match.start()) + 1
            lo = newlines[line - 2] + 1 if line > 1 else 0
            hi = newlines[line - 1] if line <= len(newlines) else len(text)
            yield record("config_read", file, line, text[lo:hi].strip(), [key], "C++ access site",
                         "Trace actual reader, override precedence and any guards.", "inference_pending")


def preset_records(file, text, unresolved, names, parent_refs):
    try:
        preset = json.loads(text)
    except ValueError:
        unresolved.append(file)
        return
    if not isinstance(preset, dict):
        return
    scope = {"name": preset.get("name"), "type": preset.get("type")}
    if isinstance(scope["name"], str) and isinstance(scope["type"], str):
        names[scope["type"], scope["name"]].append(file)
        if isinstance(preset.get("inherits"), str) and preset["inherits"]:
            parent_refs.append((file, scope["type"], preset["inherits"]))
    for key in PRESET_KEYS:
        value = preset.get(key)
        if not value:
            continue
        found = re.search(rf'^[ \t]*"{key}"\s*:', text, re.MULTILINE)
        row = record("preset_declaration", file, text.count("\n", 0, found.start()) + 1 if found else 1,
                     {key: value}, [key], scope,
                     "Declared preset input; inspect bundle loading and compatibility evaluation for effective values.",
                     "source_confirmed")
        yield row


def write_parent_diagnostics(output, names, refs):
    gaps, stats = [], Counter()
    for file, kind, parent in refs:
        candidates = sorted(names.get((kind, parent), []))
        status = "unique_name" if len(candidates) == 1 else "ambiguous_name" if candidates else "name_absent"
        stats[status] += 1
        if status != "unique_name":
            gaps.append({"file": file, "type": kind, "parent": parent, "name_matches": candidates, "status": status})
    # This is a name lookup across the snapshot. The real loader's manifest order,
    # loaded vendor set and fallback collection determine the effective parent.
    (output / "preset-parent-gaps.json").write_text(json.dumps(gaps, indent=2) + "\n", encoding="utf-8")
    return dict(stats)


def scan(upstream, revision, output):
    rev = git(upstream, "rev-parse", revision + "^{commit}").decode().strip()
    entries = {}
    paths = (*SOURCE_ROOTS, *PRESET_ROOTS)
    for item in git(upstream, "ls-tree", "-rz", rev, "--", *paths).split(b"\0"):
        if item:
            meta, path = item.split(b"\t", 1)
            if meta.split()[1] == b"blob":
                entries[path.decode()] = meta.split()[2].decode()
    submodule = "submodules/Profiles"
    linked = git(upstream, "ls-tree", rev, "--", submodule).decode().split()
    submodule_commit = linked[2] if linked and linked[1] == "commit" else None
    submodule_entries = {}
    if submodule_commit:
        profile_repo = upstream / submodule
        for item in git(profile_repo, "ls-tree", "-rz", submodule_commit).split(b"\0"):
            if item:
                meta, path = item.split(b"\t", 1)
                if meta.split()[1] == b"blob" and path.endswith(b".json"):
                    submodule_entries[f"{submodule}/{path.decode()}"] = meta.split()[2].decode()
    counts, files = Counter(), Counter()
    unresolved, unclosed, parent_refs = [], [], []
    names = defaultdict(list)
    output.mkdir(parents=True, exist_ok=True)
    with ExitStack() as stack:
        process = stack.enter_context(subprocess.Popen(["git", "-C", str(upstream), "cat-file", "--batch"],
                                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE))
        profile_process = None
        if submodule_entries:
            profile_process = stack.enter_context(subprocess.Popen(
                ["git", "-C", str(profile_repo), "cat-file", "--batch"],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE))
        stream = stack.enter_context((output / "inventory.ndjson.gz").open("wb"))
        archive = stack.enter_context(gzip.GzipFile(fileobj=stream, filename="", mode="wb", mtime=0))
        definition = blob(process, entries[DEFINITIONS])
        definitions = list(re.finditer(r'\bthis->add\("([a-z0-9_]+)"\s*,\s*(\w+)\)', definition))
        settings = {match[1] for match in definitions}
        for index, match in enumerate(definitions):
            end = definitions[index + 1].start() if index + 1 < len(definitions) else match.end()
            definition_fields = re.findall(
                r"def->(?:min|max|max_literal|mode|ratio_over|set_default_value|enum_values)[^;]*;",
                definition[match.end():end],
            )
            row = record("setting_definition", DEFINITIONS, definition.count("\n", 0, match.start()) + 1,
                         {"type": match[2], "fields": definition_fields}, [match[1]], "PrintConfig",
                         "Declared option type, bounds, UI mode, ratio, enum and default where present.",
                         "source_confirmed")
            archive.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
        counts["setting_definition"] = len(definitions)
        for file, oid in {**entries, **submodule_entries}.items():
            if file in submodule_entries:
                rows = preset_records(file, blob(profile_process, oid), unresolved, names, parent_refs)
                files["profile_submodule_json"] += 1
            elif file.startswith(tuple(root + "/" for root in PRESET_ROOTS)) and file.endswith(".json"):
                rows = preset_records(file, blob(process, oid), unresolved, names, parent_refs)
                files["preset_json"] += 1
            elif file.endswith((".cpp", ".hpp", ".h", ".cc", ".ipp")):
                rows = source_records(file, blob(process, oid), settings, unclosed)
                files["cxx"] += 1
            else:
                continue
            seen = Counter()
            for row in rows:
                row["source"][0]["revision"] = submodule_commit if file in submodule_entries else rev
                seen[row["id"]] += 1
                if seen[row["id"]] > 1:
                    row["id"] += f"-{seen[row['id']]}"
                archive.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
                counts[row["kind"]] += 1
        for child in filter(None, (process, profile_process)):
            child.stdin.close()
            if child.wait() != 0:
                raise RuntimeError("git cat-file failed")
    summary = {"upstream_commit": rev, "roots": paths, "files": dict(files), "counts": dict(counts),
               "upstream_preset_tree": git(upstream, "rev-parse", rev + ":resources/profiles").decode().strip(),
               "profile_submodule_commit": submodule_commit,
               "invalid_preset_json": unresolved,
               "unclosed_cpp_expressions": unclosed,
               "preset_parent_names": write_parent_diagnostics(output, names, parent_refs),
               "inventory_sha256": hashlib.sha256((output / "inventory.ndjson.gz").read_bytes()).hexdigest()}
    (output / "inventory-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def installed_vendor(root, vendor):
    manifest_path = root / f"{vendor}.json"
    paths = sorted([manifest_path, *(root / vendor).rglob("*.json")],
                   key=lambda path: path.relative_to(root).as_posix())
    files = {path.relative_to(root).as_posix(): path.read_bytes() for path in paths}
    manifest = json.loads(files[manifest_path.name].decode("utf-8-sig"))
    digest = hashlib.sha256()
    for ident, raw in files.items():
        digest.update(ident.encode() + b"\0" + hashlib.sha256(raw).digest())
    return files, {"version": manifest.get("version"), "json_files": len(files),
                   "json_tree_sha256": digest.hexdigest()}


def scan_installed(root, output):
    """Inventory only the two system vendors seeded by the native replay."""
    output.mkdir(parents=True, exist_ok=True)
    rows, unresolved, vendors, parent_refs = [], [], {}, []
    names = defaultdict(list)
    for vendor in ("Snapmaker", "BBL"):
        files, vendors[vendor] = installed_vendor(root, vendor)
        for ident, raw in files.items():
            rows.extend(preset_records(ident, raw.decode("utf-8-sig"), unresolved, names, parent_refs))
    with (output / "installed-presets.ndjson.gz").open("wb") as stream, gzip.GzipFile(
            fileobj=stream, filename="", mode="wb", mtime=0) as archive:
        for row in rows:
            archive.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
    summary = {"vendors": vendors, "declarations": len(rows), "invalid_json": unresolved,
               "preset_parent_names": write_parent_diagnostics(output, names, parent_refs),
               "inventory_sha256": hashlib.sha256((output / "installed-presets.ndjson.gz").read_bytes()).hexdigest()}
    (output / "installed-preset-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=REPO.parents[1])
    parser.add_argument("--revision", help="Scan a different comparison commit from the same upstream.")
    parser.add_argument("--installed-presets", type=Path, help="Read a deployed profiles directory.")
    parser.add_argument("--output", type=Path, default=REPO / "artifacts/config_dependencies")
    args = parser.parse_args()
    revision = args.revision or json.loads(CATALOG.read_text(encoding="utf-8"))["upstream_commit"]
    summary = (scan_installed(args.installed_presets, args.output) if args.installed_presets
               else scan(args.upstream, revision, args.output))
    print(json.dumps(summary, indent=2))
