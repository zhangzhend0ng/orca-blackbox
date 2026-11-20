"""Regression for host completion uncertainty being hidden by guest success."""
from tools.zcode_matrix import grade
from unit_tests.test_native_matrix import receipts


def business_receipts():
    host, result, process, teardown, trace = receipts()
    result.update(verified_pass=True, execution_status="completed", release_verdict="SHADOW")
    host["error"] = None
    return host, result, process, teardown, trace


def test_guest_success_does_not_hide_host_completion_uncertainty():
    args = business_receipts()
    args[0]["error"] = "zcode_completion_unconfirmed:TimeoutError"
    assert not grade("pilot_material", *args, coordinator_exit=0)


def test_business_requires_successful_coordinator_exit():
    args = business_receipts()
    assert not grade("pilot_material", *args, coordinator_exit=1)


def test_business_with_known_completed_host_and_coordinator_is_accepted():
    assert grade("pilot_material", *business_receipts(), coordinator_exit=0)


def test_missing_coordinator_receipt_is_unknown_not_an_implicit_zero_exit():
    assert not grade("pilot_material", *business_receipts())
