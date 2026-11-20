"""Single-writer run evidence; not an ACL or a hostile-process sandbox.

The trusted scheduler must own the root and deny executor writes to it. Only
sanitized identifiers and evidence references belong here, never raw tool input,
credentials, screenshots or user text. The public API cannot reopen/overwrite runs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import threading
import time
from typing import Any
import uuid

from .run_contract import CaseContract, validate_contract

_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_METADATA = {"repository_commit", "sut_sha256", "environment_id", "executor_version",
             "model_version", "prompt_version", "checker_version"}
_SENSITIVE = {"password", "passwd", "token", "accesstoken", "refreshtoken", "apikey",
              "secret", "authorization", "cookie", "email", "phone"}


def _json(value: Any) -> bytes:
    def check(item: Any, depth: int = 0) -> None:
        if depth > 20:
            raise ValueError("evidence: nesting exceeds limit")
        if type(item) is dict:
            for key, val in item.items():
                if type(key) is not str:
                    raise ValueError("evidence: keys must be strings")
                if re.sub(r"[^a-z]", "", key.lower()) in _SENSITIVE:
                    raise ValueError("evidence: sensitive field rejected")
                check(val, depth + 1)
        elif type(item) is list:
            for val in item:
                check(val, depth + 1)
        elif item is not None and type(item) not in (str, int, float, bool):
            raise ValueError("evidence: non-JSON value")
    check(value)
    raw = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True,
                     separators=(",", ":")).encode("utf-8")
    if len(raw) > 65536:
        raise ValueError("evidence: record exceeds size limit")
    return raw


def _id(value: Any) -> str:
    if type(value) is not str or not _ID.fullmatch(value) or value in {".", ".."}:
        raise ValueError("evidence: invalid identifier")
    return value


class RunEvidence:
    """Create once, append structured events, finalize once; exceptions propagate.

    Use create(), then a context manager or close(). Durability uses flush/fsync;
    event hashes detect accidental edits when a trusted verifier checks the chain.
    """

    @classmethod
    def create(cls, root: str | Path, contract: CaseContract | dict, *,
               run_id: str | None = None, metadata: dict | None = None) -> RunEvidence:
        validated = validate_contract(contract.to_dict() if isinstance(contract, CaseContract) else contract)
        frozen = _json(validated.to_dict())
        md = {} if metadata is None else metadata
        if type(md) is not dict or not set(md) <= _METADATA:
            raise ValueError("metadata: unknown fields")
        for value in md.values():
            if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_.:/+ -]{1,256}", value):
                raise ValueError("metadata: invalid identifier value")
        ident = _id(run_id if run_id is not None else uuid.uuid4().hex)
        parent = Path(root).resolve(strict=True)
        if not parent.is_dir():
            raise ValueError("evidence: root must be a directory")
        target = parent / ident
        target.mkdir(mode=0o700)  # Exclusive allocation, including concurrent creators.
        if target.resolve() != target or target.is_symlink():
            raise ValueError("evidence: invalid run directory")
        now = time.time_ns()
        manifest = {"schema_version": 1, "run_id": ident, "case_id": validated.case_id,
                    "executor": validated.executor,
                    "started_at": datetime.fromtimestamp(now / 1e9, timezone.utc).isoformat(),
                    "started_at_ns": now, "contract_sha256": hashlib.sha256(frozen + b"\n").hexdigest(),
                    "metadata": dict(md)}
        self = cls.__new__(cls)
        self.run_id, self.run_dir, self.manifest = ident, target, manifest
        self._lock = threading.Lock()
        self._previous, self._sequence, self._closed, self._finalized = "", 0, False, False
        self._write_once("contract.json", frozen)
        self._write_once("manifest.json", _json(manifest))
        self._events = (target / "events.ndjson").open("xb")
        return self

    def _write_once(self, name: str, raw: bytes) -> Path:
        import os
        path = self.run_dir / name
        with path.open("xb") as stream:
            stream.write(raw + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        return path

    def append_event(self, event_type: str, *, step_id: str | None = None,
                     status: str | None = None, evidence: str | None = None) -> None:
        """Append bounded identifiers; evidence is a relative in-run file reference."""
        import os
        _id(event_type)
        if step_id is not None:
            _id(step_id)
        if status is not None:
            _id(status)
        if evidence is not None:
            if (type(evidence) is not str or not 1 <= len(evidence) <= 512
                    or "\\" in evidence or ":" in evidence or any(ord(ch) < 32 for ch in evidence)):
                raise ValueError("evidence: invalid relative reference")
            rel = PurePosixPath(evidence)
            if rel.is_absolute() or any(x in {"", ".", ".."} for x in evidence.split("/")):
                raise ValueError("evidence: reference escapes run")
            candidate = (self.run_dir / evidence).resolve()
            if not candidate.is_relative_to(self.run_dir):
                raise ValueError("evidence: reference escapes run")
        with self._lock:
            if self._closed or self._finalized:
                raise ValueError("evidence: run is closed or finalized")
            event = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": "INFO",
                     "message": event_type, "context": {"run_id": self.run_id,
                     "step_id": step_id, "status": status, "evidence": evidence},
                     "sequence": self._sequence, "previous_sha256": self._previous}
            raw = _json(event)
            self._events.write(raw + b"\n")
            self._events.flush()
            os.fsync(self._events.fileno())
            self._previous = hashlib.sha256(raw).hexdigest()
            self._sequence += 1

    def finalize(self, result: dict) -> Path:
        """Persist a trusted checker result once; this writer does not decide GREEN."""
        if type(result) is not dict:
            raise ValueError("result: expected object")
        raw = _json(result)
        with self._lock:
            if self._closed or self._finalized:
                raise ValueError("evidence: run is closed or finalized")
            path = self._write_once("result.json", raw)
            self._finalized = True
            return path

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._events.close()
                self._closed = True

    def __enter__(self) -> RunEvidence:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()
