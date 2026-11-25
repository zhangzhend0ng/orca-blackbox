"""Read a named harvested artifact only when its recorded size and digest match."""
import hashlib
from pathlib import Path


def verified_part(directory: Path, prefix: str, manifest: list[dict], name: str) -> Path:
    entries = [entry for entry in manifest if entry["part"] == name]
    if len(entries) != 1:
        raise ValueError(f"{name}: expected one manifest entry, found {len(entries)}")
    entry = entries[0]
    path = directory / f"{prefix}-{name}"
    if path.stat().st_size != entry["bytes"]:
        raise ValueError(f"{name}: size differs from manifest")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != entry["sha256"].lower():
        raise ValueError(f"{name}: SHA-256 differs from manifest")
    return path
