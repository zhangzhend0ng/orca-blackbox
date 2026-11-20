"""Trusted, finite diagnostic approvals. Never an actor-selected fallback."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CanvasApproval:
    profile_id: str
    version: int
    mode: str
    window_class: str
    window_title: str
    diagnostic_run_id: str
    diagnostic_sha256: str
    sut_sha256: str


_OBSERVED = CanvasApproval(
    "observed-wxglcanvas-v1", 1, "observed_wxglcanvas", "wxGLCanvas", "GLCanvas",
    "bb64f8a261f74ed4b78fe2a8aed577aa",
    "ea1bea303abc1f675f2f8018fa9d1e241e4a65c224beec81fb5e20660746bd40",
    "5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf")


def validate_approval(value):
    if (type(value) is not CanvasApproval or type(value.version) is not int
            or any(type(getattr(value, key)) is not str for key in value.__dataclass_fields__ if key != "version")
            or value != _OBSERVED):
        raise ValueError("canvas_approval_not_registered")
    return value


def resolve_approval(profile_id, *, diagnostic_sha256, sut_sha256):
    """Trusted setup must establish these hashes from actual diagnostic/SUT bytes.

    Constants are provenance identifiers, not secrets or a signature. The actor
    tool schema must never expose this profile choice or a binding-file writer.
    """
    if (type(profile_id) is not str or type(diagnostic_sha256) is not str or type(sut_sha256) is not str
            or (profile_id, diagnostic_sha256, sut_sha256) !=
            (_OBSERVED.profile_id, _OBSERVED.diagnostic_sha256, _OBSERVED.sut_sha256)):
        raise ValueError("canvas_approval_provenance_mismatch")
    return _OBSERVED
