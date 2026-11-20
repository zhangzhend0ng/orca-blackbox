from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from harness import host_guard


@pytest.mark.parametrize(("kvp", "firmware", "is_guest"), [
    (True, {}, True),
    (False, {"SystemManufacturer": "Microsoft Corporation", "SystemProductName": "Virtual Machine"}, True),
    (False, {"SystemManufacturer": "Microsoft Corporation", "SystemProductName": "Surface Laptop"}, False),
    (False, {"SystemManufacturer": "Other Vendor", "SystemProductName": "Virtual Machine"}, False),
    (False, {}, False),
])
def test_in_guest_with_or_without_data_exchange(monkeypatch, kvp, firmware, is_guest):
    registry = {host_guard._FIRMWARE_KEY: firmware}
    if kvp:
        registry[host_guard._GUEST_KEY] = {}

    def open_key(_hive, name):
        if name not in registry:
            raise FileNotFoundError(name)
        return nullcontext(registry[name])

    def query_value(key, name):
        if name not in key:
            raise FileNotFoundError(name)
        return key[name], 1

    monkeypatch.setattr(host_guard, "winreg", SimpleNamespace(
        HKEY_LOCAL_MACHINE=object(), OpenKey=open_key, QueryValueEx=query_value,
    ))
    assert host_guard.in_guest() is is_guest
