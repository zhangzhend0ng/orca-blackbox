#!/usr/bin/env python3
# feishu_writeback.py — host-side closeout step: patch the Feishu Base table's
# 自动化状态 field for a batch's GREEN cases, in the SAME payload shape as
# the historical writebacks (artifacts/feishu_base/wb_*.json):
#   {"record_id_list": [...], "patch": {"自动化状态": "已自动化"}}
#
# Mapping source is a JSON file record_id -> {"case": ..., ...} (the shape of
# diag/feishu_0908/writeback_map.json). Case names come from argv — use the
# names the batch log printed (regress_progress.txt). A map entry matches a
# name when any "/"-separated token of its "case" value equals the name or is
# its prefix at a "_" boundary ("m7a" matches "m7a_boot_shutdown", "m2/m3a"
# matches "m3a_empty_slice").
#
# Safety:
#   - default is DRY-RUN: payload files + the exact lark-cli command printed,
#     nothing written to the Base;
#   - any requested case name with ZERO matching records aborts the whole
#     writeback (exit 2) — never patch a partial set silently;
#   - --apply executes lark-cli base +record-batch-update (host npm global;
#     the guest has no lark-cli and no credentials — writeback is host-side
#     by design), then reads every record back and checks the field value
#     before reporting success (read-back rule, 09-16 session);
#   - batches of >200 records are chunked (platform limit per call).
#
# Usage:
#   python tools/feishu_writeback.py m7a_boot_shutdown m7c_import_stl       # dry-run
#   python tools/feishu_writeback.py m7a_boot_shutdown --apply              # write + verify
#   python tools/feishu_writeback.py --map diag/feishu_0908/writeback_map.json m7d_import_corrupt
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DEFAULT_MAP = ROOT / "diag" / "feishu_0908" / "writeback_map.json"
# Current table: wiki node VtS3wy9WpiNKoRkFJJYcNvPSnZb -> base RJKPbW7fTaMkNnsPx3LcFQISnmd,
# table tbl2WmD8AtG9yH1i「基线用例」(107 records, resolved 2026-09-21). The old
# EDUAbY…/tblvh0eGrID9JQ02 pair and diag/feishu_0908/writeback_map.json belong to an
# earlier table instance whose record_ids no longer exist here — prefer
# --from-annotations, which rebuilds the map from the case headers + the live export.
DEFAULT_BASE = "RJKPbW7fTaMkNnsPx3LcFQISnmd"
DEFAULT_TABLE = "tbl2WmD8AtG9yH1i"
BATCH_LIMIT = 200  # platform limit for +record-batch-update (tools/feishu_u1_base.py:31)


def load_map(path: Path) -> dict[str, dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"map must be a JSON object: {path}")
    return raw


def map_from_annotations(export: Path | None = None) -> dict[str, dict]:
    """record_id -> {case, id, title} built from the case annotations.

    Source of truth: each case script declares `# feishu: baseline#<用例编号> ...`
    (cases.feishu_refs); the record_id for a number comes from the live-table
    export (--export, default artifacts/feishu_baseline_full.ndjson). This keeps
    the writeback keyed to the CURRENT table instead of a hand-kept map file.

    Pass --export when the target table is not the default one — the table the
    user tracks (NhqXbsLgPaJ4wvsGtjecsx83n3c/tblWFGvJ5KQGVInq) has its own
    record_ids, so an ids-from-the-other-table map would patch nothing.
    """
    nd = Path(export) if export else (ROOT / "artifacts" / "feishu_baseline_full.ndjson")
    if not nd.exists():
        sys.stderr.write(
            "missing " + str(nd) + " — export the live table first:\n"
            '  lark-cli base +record-list --base-token ' + DEFAULT_BASE +
            ' --table-id ' + DEFAULT_TABLE +
            ' --format ndjson --output ' + str(nd) + ' --limit 2000 --overwrite\n')
        sys.exit(2)
    by_num: dict[str, dict] = {}
    for ln in nd.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        r = json.loads(ln)
        num = r.get("用例编号")
        num = num[0] if isinstance(num, list) and num else num
        title = r.get("用例标题")
        title = title[0] if isinstance(title, list) and title else title
        if num:
            by_num[str(num)] = {"record_id": r["record_id"], "title": title or ""}
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    import cases as _cases  # noqa: PLC0415
    _ = _cases
    out: dict[str, dict] = {}
    for case in _cases.CASES:
        for ref in (_cases.feishu_refs(case) or []):
            if not ref.startswith("baseline#"):
                continue
            n = ref.split("#", 1)[1]
            entry = by_num.get(n)
            if not entry:
                continue
            rid = entry["record_id"]
            prev = out.get(rid)
            if prev is None:
                out[rid] = {"case": case, "id": n, "title": entry["title"]}
            elif case not in case_tokens(prev):
                # several cases can automate the same baseline row (m7t73 and
                # m7t74 both cover #152) — keep them all as "/"-separated tokens
                # (case_tokens/matches already read that shape). Overwriting made
                # every earlier name unresolvable and aborted the whole writeback.
                prev["case"] = prev["case"] + "/" + case
    return out


def case_tokens(entry: dict) -> set[str]:
    value = entry.get("case", "")
    return {t.strip() for t in str(value).split("/") if t.strip()}


def matches(name: str, entry: dict) -> bool:
    return any(name == t or name.startswith(t + "_") for t in case_tokens(entry))


def resolve(map: dict[str, dict], cases: list[str]) -> tuple[list[str], list[str]]:
    """Return (record_ids, unmatched_case_names)."""
    found: list[str] = []
    for name in cases:
        hits = [rid for rid, entry in map.items() if matches(name, entry)]
        if not hits:
            return [], [name]  # abort on the FIRST gap; caller reports all later
        found.extend(hits)
    # preserve map order, drop duplicates
    seen: set[str] = set()
    ordered = [rid for rid in found if not (rid in seen or seen.add(rid))]
    return ordered, []


def chunked(ids: list[str], limit: int = BATCH_LIMIT) -> list[list[str]]:
    return [ids[i:i + limit] for i in range(0, len(ids), limit)]


def write_payloads(chunks: list[list[str]], field: str, value: str,
                   out_dir: Path, stem: str) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for i, chunk in enumerate(chunks, start=1):
        payload = {"record_id_list": chunk, "patch": {field: value}}
        base = stem if len(chunks) == 1 else f"{stem}_{i}"
        path = out_dir / f"{base}.json"
        n = 2
        while path.exists():  # never silently overwrite an earlier batch's payload
            path = out_dir / f"{base}_{n}.json"
            n += 1
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
        paths.append(path)
    return paths


def lark_cmd(*args: str) -> list[str]:
    exe = shutil.which("lark-cli")
    if not exe:
        sys.stderr.write("lark-cli not found on PATH — install it on the HOST (npm global);\n"
                         "the guest has no lark-cli and no credentials: writeback is host-side.\n")
        sys.exit(3)
    return [exe, *args]


def run_lark(args: list[str]) -> dict | None:
    """Run lark-cli; return parsed JSON, or None when stdout is not JSON."""
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120)
    if proc.returncode != 0:
        sys.stderr.write(f"lark-cli failed rc={proc.returncode}\n{proc.stderr[-2000:]}\n")
        sys.exit(3)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def update_records(payload_paths: list[Path], base: str, table: str) -> None:
    for path in payload_paths:
        print(f"[writeback] applying {path} ...")
        run_lark(lark_cmd("base", "+record-batch-update",
                          "--base-token", base, "--table-id", table,
                          "--json", f"@{path}"))


def cell_value(row: object) -> object:
    """Single-select cells arrive as a list of strings in record-get output."""
    if isinstance(row, list) and row and isinstance(row[0], list) and row[0]:
        return row[0][0]
    return row


def _record_get(ids: list[str], base: str, table: str, field: str) -> dict | None:
    return run_lark(lark_cmd("base", "+record-get",
                             "--base-token", base, "--table-id", table,
                             "--field-id", field, "--format", "json",
                             "--json", json.dumps({"record_id_list": ids})))


def _extract_values(resp: dict | None) -> dict:
    """{record_id: cell value} from a +record-get response (shape-tolerant)."""
    if not resp or not isinstance(resp.get("data"), dict):
        return {}
    rows = resp["data"].get("data", [])
    rid_list = resp["data"].get("record_id_list") or []
    got = {}
    if rid_list and len(rid_list) == len(rows):
        # current shape: each row carries ONLY the requested cells; the ids come
        # back in a parallel record_id_list (verified against the live table 09-21)
        for rid, row in zip(rid_list, rows):
            got[str(rid)] = cell_value(row)
    else:
        for row in rows:  # legacy shape: [record_id, value]
            if isinstance(row, list) and len(row) >= 2:
                got[str(row[0])] = cell_value(row[1])
    return got


def verify_records(ids: list[str], base: str, table: str, field: str, value: str,
                   attempts: int = 5, delay_s: float = 3.0) -> None:
    """Read the field back and require every id to carry `value`.

    The Base is eventually consistent right after a batch update: the first read
    following a successful write still returned the OLD value (measured 09-28:
    11 records all stale; 09-29: #123 read '待实现' while the update had already
    been accepted). Retry before reporting — only a value that stays wrong after
    the attempts is a real mismatch."""
    print(f"[writeback] read-back verify: {len(ids)} record(s), field '{field}' == '{value}' ...")
    for attempt in range(1, attempts + 1):
        got = _extract_values(_record_get(ids, base, table, field))
        bad = {rid: got.get(rid) for rid in ids if got.get(rid) != value}
        if not bad:
            print(f"[writeback] verified: {len(ids)} record(s) == '{value}'")
            return
        if attempt < attempts:
            print(f"[writeback] read-back attempt {attempt}/{attempts}: "
                  f"{len(bad)} stale — retrying in {delay_s:.0f}s")
            time.sleep(delay_s)
    sample = ", ".join(f"{rid}={v!r}" for rid, v in list(bad.items())[:5])
    sys.stderr.write(f"read-back MISMATCH on {len(bad)} record(s): {sample}\n")
    sys.exit(3)


def main() -> int:
    ap = argparse.ArgumentParser(description="Feishu 自动化状态 writeback (host-side closeout)")
    ap.add_argument("cases", nargs="*", help="GREEN case names from the batch log (regress_progress.txt)")
    ap.add_argument("--ids-file", type=Path,
                    help="write by explicit record ids instead of case names: JSON list or "
                         '{"record_id_list": [...]} (e.g. a category from tools/feishu_status_plan.py)')
    ap.add_argument("--ids-key", default="", help="when --ids-file holds a plan, pick this category")
    ap.add_argument("--map", type=Path, default=DEFAULT_MAP, help="record_id -> {case,...} JSON")
    ap.add_argument("--from-annotations", action="store_true",
                    help="rebuild the map from the case `# feishu:` annotations + the live export")
    ap.add_argument("--export", type=Path, default=None,
                    help="record-list ndjson backing --from-annotations (default: "
                         "artifacts/feishu_baseline_full.ndjson; must be an export of the "
                         "table named by --base-token/--table-id)")
    ap.add_argument("--base-token", default=DEFAULT_BASE)
    ap.add_argument("--table-id", default=DEFAULT_TABLE)
    ap.add_argument("--field", default="自动化状态")
    ap.add_argument("--value", default="已自动化")
    ap.add_argument("--apply", action="store_true", help="execute the update (default: dry-run)")
    ap.add_argument("--no-verify", action="store_true", help="skip read-back check (with --apply)")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "artifacts" / "feishu_base")
    args = ap.parse_args()

    if args.from_annotations:
        mapping = map_from_annotations(args.export)
        print(f"[writeback] map from annotations: {len(mapping)} record(s)")
    else:
        if not args.map.exists():
            sys.stderr.write(f"map not found: {args.map} (pass --map <json> or --from-annotations)\n")
            return 2
        mapping = load_map(args.map)

    if args.ids_file:
        raw = json.loads(args.ids_file.read_text(encoding="utf-8"))
        if args.ids_key:
            raw = (raw.get("plan") or {}).get(args.ids_key, [])
        if isinstance(raw, dict):
            raw = raw.get("record_id_list", [])
        ids = [str(x) for x in raw]
        print(f"[writeback] ids from {args.ids_file}"
              + (f" [{args.ids_key}]" if args.ids_key else "") + f": {len(ids)} record(s)")
        unmatched = []
    else:
        ids, unmatched = resolve(mapping, args.cases)
    if unmatched:
        sys.stderr.write(f"aborted: no map entry for: {', '.join(unmatched)} "
                         f"(map has {len(mapping)} records)\n")
        return 2
    if not ids:
        sys.stderr.write("aborted: zero records resolved\n")
        return 2

    stem = f"wb_green_{time.strftime('%Y%m%d_%H%M%S')}"
    payloads = write_payloads(chunked(ids), args.field, args.value, args.out_dir, stem)
    for p in payloads:
        print(f"[writeback] payload: {p} ({json.loads(p.read_text(encoding='utf-8'))['record_id_list'].__len__()} records)")

    if args.apply:
        update_records(payloads, args.base_token, args.table_id)
        if not args.no_verify:
            verify_records(ids, args.base_token, args.table_id, args.field, args.value)
        print("[writeback] DONE (applied + verified)" if not args.no_verify
              else "[writeback] DONE (applied, read-back skipped)")
        return 0

    for p in payloads:
        print("  dry-run command:")
        print("    lark-cli base +record-batch-update "
              f"--base-token {args.base_token} --table-id {args.table_id} --json @{p}")
    print("[writeback] DRY-RUN complete — re-run with --apply to write + verify")
    return 0


if __name__ == "__main__":
    sys.exit(main())
