import importlib.util
from pathlib import Path
import json
import subprocess
import sys


SCRIPT = Path(__file__).parents[1] / "tools" / "feishu_vs_table.py"
spec = importlib.util.spec_from_file_location("feishu_vs_table", SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_status_distinguishes_missing_and_unplanned_rows():
    assert module.status_for("param_269", ["internal_bridge_support_thickness"]) == "missing"
    assert module.status_for("param_269", []) == "all_step_keys_listed"
    assert module.status_for(None, ["some_key"]) == "no_scenario"


def test_step_keys_preserves_every_key_from_setup_line():
    text = "1. 设置测试参数：alpha=1；beta=0.6mm; gamma=45"
    assert module.step_keys(text) == ["alpha", "beta", "gamma"]


def test_json_cli_stdout_is_one_parseable_document_for_selected_ids():
    root = SCRIPT.parents[1]
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(root), "--ids", "265,269,276,288", "--json"],
        capture_output=True, text=True, encoding="utf-8", check=True,
    )
    payload = json.loads(result.stdout)
    by_id = {str(row["case_id"]): row for row in payload["rows"]}
    assert set(by_id) == {"265", "269", "276", "288"}
    assert by_id["265"]["status"] == "missing"
    assert by_id["269"]["missing_keys"] == ["internal_bridge_support_thickness"]
    assert by_id["276"]["status"] == "missing"
    assert by_id["288"]["status"] == "no_scenario"
