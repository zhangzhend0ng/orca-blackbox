import copy

import pytest

from harness.native_authority_probe import verify_responses


def responses():
    return [{"result": {"isError": True, "structuredContent": {"authority": {
        "protocol": "native-authority-1", "run_id": "a"*32, "seq": seq, "tool": "Click",
        "decision": "fatal", "dispatched": False, "error_code": code}}}}
        for seq, code in enumerate(("native_target_not_owned", "native_authority_already_revoked"), 1)]


@pytest.mark.parametrize("fault", [None, "run_id", "seq", "decision", "dispatched", "isError", "first", "count", "unrelated_second_fatal"])
def test_real_probe_cannot_claim_stopped_from_incomplete_or_dispatched_results(fault):
    data = copy.deepcopy(responses())
    if fault == "isError":
        data[1]["result"]["isError"] = False
    elif fault == "first":
        data[0]["result"]["structuredContent"]["authority"]["error_code"] = "other"
    elif fault == "count":
        data.pop()
    elif fault == "unrelated_second_fatal":
        data[1]["result"]["structuredContent"]["authority"]["error_code"] = "native_foreground_not_owned"
    elif fault:
        data[1]["result"]["structuredContent"]["authority"][fault] = True if fault == "dispatched" else "wrong"
    if fault:
        with pytest.raises(ValueError):
            verify_responses(data, "a"*32)
    else:
        assert verify_responses(data, "a"*32)["subsequent_input_dispatched"] is False
