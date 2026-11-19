"""Inventory config dependency evidence from immutable upstream Git blobs."""
import argparse
from bisect import bisect_right
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess

REPO = Path(__file__).resolve().parents[1]
CATALOG = REPO / "contracts/config_dependencies.json"
SOURCE_ROOTS = ("src/libslic3r", "src/slic3r/GUI", "src/slic3r/Utils")
PRESET_ROOT = "resources/profiles/"
DEFINITIONS = "src/libslic3r/PrintConfig.cpp"
TOKEN = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
IDENT = re.compile(r"\b[a-z][a-z0-9_]*\b")
ENTRY = re.compile(r"\b(if|switch|while|toggle_line|toggle_field|set_key_value|set_visible|set_enabled)\s*\(")
PRESET_KEYS = ("inherits", "compatible_printers", "compatible_printers_condition",
               "compatible_prints", "compatible_prints_condition", "default_print_profile",
               "default_filament_profile", "printer_model", "nozzle_diameter")


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


def closing_paren(source, start):
    depth = 1
    for index in range(start, len(source)):
        if source[index] == "(":
            depth += 1
        elif source[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def record(kind, file, line, trigger, affected, scope, expected, evidence):
    token = json.dumps([kind, file, trigger, affected], ensure_ascii=False)
    return {"id": kind + "-" + hashlib.sha256(token.encode()).hexdigest()[:24],
            "kind": kind, "trigger": trigger, "affected": affected, "scope": scope,
            "expected": expected, "evidence": evidence, "source": [{"file": file, "line": line}]}


def source_records(file, text, settings):
    clean = mask(text)
    newlines = [m.start() for m in re.finditer("\n", text)]
    for match in ENTRY.finditer(clean):
        end = closing_paren(clean, match.end())
        if end is None:
            continue
        call = match[1]
        expression = text[match.end():end].strip()
        keys = sorted(settings.intersection(IDENT.findall(expression)))
        if not keys and call in {"if", "switch", "while"}:
            continue
        line = bisect_right(newlines, match.start()) + 1
        after = clean[end + 1:].lstrip()
        statement = ""
        if call in {"if", "switch", "while"} and not after.startswith("{"):
            start = end + 1
            stop = clean.find(";", start)
            if 0 <= stop - start <= 500:
                statement = text[start:stop + 1].strip()
        row = record("source_candidate", file, line, expression, keys, call,
                     "Review branch effects, outer guards and data flow.", "inference_pending")
        row["statement"] = statement
        yield row


def preset_records(file, text, unresolved):
    try:
        preset = json.loads(text)
    except ValueError:
        unresolved.append(file)
        return
    if not isinstance(preset, dict):
        return
    for key in PRESET_KEYS:
        value = preset.get(key)
        if not value:
            continue
        found = re.search(rf'^\s*"{key}"\s*:', text, re.MULTILINE)
        row = record("preset_declaration", file, text.count("\n", 0, found.start()) + 1 if found else 1,
                     {key: value}, [key], {"name": preset.get("name"), "type": preset.get("type")},
                     "Declared preset input; inspect bundle loading and compatibility evaluation for effective values.",
                     "source_confirmed")
        yield row


def scan(upstream, catalog, output):
    rev = catalog["upstream_commit"]
    entries = {}
    paths = (*SOURCE_ROOTS, PRESET_ROOT.rstrip("/"))
    for item in git(upstream, "ls-tree", "-rz", rev, "--", *paths).split(b"\0"):
        if item:
            meta, path = item.split(b"\t", 1)
            if meta.split()[1] == b"blob":
                entries[path.decode()] = meta.split()[2].decode()
    counts, files = Counter(), Counter()
    unresolved = []
    output.mkdir(parents=True, exist_ok=True)
    with subprocess.Popen(["git", "-C", str(upstream), "cat-file", "--batch"],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process, (
            output / "inventory.ndjson.gz").open("wb") as stream, gzip.GzipFile(
                fileobj=stream, filename="", mode="wb", mtime=0) as archive:
        definition = blob(process, entries[DEFINITIONS])
        definitions = list(re.finditer(r'\bthis->add\("([a-z0-9_]+)"\s*,\s*(\w+)\)', definition))
        settings = {match[1] for match in definitions}
        for match in definitions:
            row = record("setting_definition", DEFINITIONS, definition.count("\n", 0, match.start()) + 1,
                         {"type": match[2]}, [match[1]], "PrintConfig", "Declared setting and option type.",
                         "source_confirmed")
            archive.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
        counts["setting_definition"] = len(definitions)
        for file, oid in entries.items():
            if file.startswith(PRESET_ROOT) and file.endswith(".json"):
                rows = preset_records(file, blob(process, oid), unresolved)
                files["preset_json"] += 1
            elif file.endswith((".cpp", ".hpp", ".h", ".cc", ".ipp")):
                rows = source_records(file, blob(process, oid), settings)
                files["cxx"] += 1
            else:
                continue
            seen = Counter()
            for row in rows:
                seen[row["id"]] += 1
                if seen[row["id"]] > 1:
                    row["id"] += f"-{seen[row['id']]}"
                archive.write((json.dumps(row, ensure_ascii=False) + "\n").encode())
                counts[row["kind"]] += 1
        process.stdin.close()
        if process.wait() != 0:
            raise RuntimeError("git cat-file failed")
    summary = {"upstream_commit": rev, "roots": paths, "files": dict(files), "counts": dict(counts),
               "upstream_preset_tree": git(upstream, "rev-parse", rev + ":resources/profiles").decode().strip(),
               "invalid_preset_json": unresolved,
               "inventory_sha256": hashlib.sha256((output / "inventory.ndjson.gz").read_bytes()).hexdigest()}
    (output / "inventory-summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=REPO.parents[1])
    parser.add_argument("--output", type=Path, default=REPO / "artifacts/config_dependencies")
    args = parser.parse_args()
    print(json.dumps(scan(args.upstream, json.loads(CATALOG.read_text(encoding="utf-8")), args.output), indent=2))
