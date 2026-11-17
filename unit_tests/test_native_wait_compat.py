"""Observed Windows-MCP 0.8.9 Wait schema is required integer duration.

Regression evidence: 701b3ee5340f47eebe1e4ad0065288b6, server int_from_float.
"""
import pytest

from harness.native_save_policy import NATIVE_TOOLS, scoped_tool_schemas, validate_input


@pytest.mark.parametrize("args", [{"duration": 1.5}, {}, {"duration": True}, {"duration": 6}])
def test_advertised_wait_schema_rejects_unusable_or_unbounded_calls(args):
    jsonschema = pytest.importorskip("jsonschema")
    tools = [{"name": n, "inputSchema": {}} for n in NATIVE_TOOLS]
    schema = next(t["inputSchema"] for t in scoped_tool_schemas(tools, "C:\\owned\\0001.3mf") if t["name"] == "Wait")
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(args, schema)
    with pytest.raises(ValueError):
        validate_input("Wait", args, "C:\\owned\\0001.3mf")


@pytest.mark.parametrize("duration", [0, 1, 5, 1.0])
def test_wait_integer_json_values_remain_compatible(duration):
    jsonschema = pytest.importorskip("jsonschema")
    tools = [{"name": n, "inputSchema": {}} for n in NATIVE_TOOLS]
    schema = next(t["inputSchema"] for t in scoped_tool_schemas(tools, "C:\\owned\\0001.3mf") if t["name"] == "Wait")
    jsonschema.validate({"duration": duration}, schema)
    validate_input("Wait", {"duration": duration}, "C:\\owned\\0001.3mf")


def test_new_upstream_required_parameter_blocks_admission():
    tools = [{"name": n, "inputSchema": {"required": ["new_field"] if n == "Wait" else []}}
             for n in NATIVE_TOOLS]
    with pytest.raises(ValueError, match="upstream_required"):
        scoped_tool_schemas(tools, "C:\\owned\\0001.3mf")
