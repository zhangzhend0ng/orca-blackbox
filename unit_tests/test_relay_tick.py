"""Regression for a real same-second background-launch receipt collision."""
from runner import relay_run


def test_same_second_header_waits_for_a_distinct_response_identity(monkeypatch):
    ticks = iter(["19:41:49", "19:41:49", "19:41:50"])
    waits = []
    monkeypatch.setattr(relay_run.time, "strftime", lambda _: next(ticks))
    monkeypatch.setattr(relay_run.time, "sleep", waits.append)
    relay_run._await_fresh_tick("=== RUN 19:41:49 ===")
    assert waits == [.05, .05]


def test_old_header_needs_no_delay(monkeypatch):
    monkeypatch.setattr(relay_run.time, "strftime", lambda _: "19:41:50")
    monkeypatch.setattr(relay_run.time, "sleep", lambda _: (_ for _ in ()).throw(AssertionError()))
    relay_run._await_fresh_tick("=== RUN 19:41:49 ===")
