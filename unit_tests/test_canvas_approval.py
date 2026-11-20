"""Finite observed approval provenance, never a GL or GUI success proof."""
from dataclasses import FrozenInstanceError, replace

import pytest

from harness.canvas_approval import resolve_approval, validate_approval

PROFILE = "observed-wxglcanvas-v1"
DIAG = "ea1bea303abc1f675f2f8018fa9d1e241e4a65c224beec81fb5e20660746bd40"
SUT = "5c48644d7da18b50636ceeee4ef9fd2eaf6d4e8ac05bd88752f40e3717fc47bf"


def approved():
    return resolve_approval(PROFILE, diagnostic_sha256=DIAG, sut_sha256=SUT)


def test_explicit_reviewed_profile_is_immutable_and_exact():
    a = approved()
    assert a.mode == "observed_wxglcanvas" and a.window_class == "wxGLCanvas" and a.window_title == "GLCanvas"
    assert validate_approval(a) is a
    with pytest.raises(FrozenInstanceError): a.mode = "pfd"


@pytest.mark.parametrize("field,value", [("profile_id", "any"), ("diagnostic_sha256", "0"*64),
    ("sut_sha256", "0"*64), ("version", True), ("window_class", "AnyCanvas"),
    ("window_title", "Other"), ("mode", "fallback"), ("diagnostic_run_id", "a"*32)])
def test_forged_profile_values_are_not_approvals(field, value):
    with pytest.raises(ValueError): validate_approval(replace(approved(), **{field:value}))


@pytest.mark.parametrize("profile,diag,sut", [("unknown", DIAG, SUT), (PROFILE, "0"*64, SUT),
    (PROFILE, DIAG, "0"*64), (True, DIAG, SUT)])
def test_profile_selection_and_source_hashes_must_match(profile, diag, sut):
    with pytest.raises(ValueError): resolve_approval(profile, diagnostic_sha256=diag, sut_sha256=sut)
