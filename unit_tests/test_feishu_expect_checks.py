import hashlib
import importlib.util
import json
import sys
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
spec = importlib.util.spec_from_file_location("feishu_expect_checks", ROOT / "tools" / "feishu_expect_checks.py")
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class ExpectCheckTests(unittest.TestCase):
    def test_four_rows_reject_noop_or_deviation(self):
        rows = {
            258: ({"arcs": {"extruding": 0}}, {"arcs": {"extruding": 0}}),
            262: ({"features": {"Top surface": {"e_per_mm": 1}, "Bottom surface": {"e_per_mm": 1}}},
                  {"features": {"Top surface": {"e_per_mm": 1}, "Bottom surface": {"e_per_mm": 1}}}),
            273: ({"travel_feeds": {"other": [["30000", 5]]}},
                  {"travel_feeds": {"other": [["30000", 5]]}}),
            277: ({"features": {"Support": {"moves": 0}, "Support interface": {"moves": 0}}},
                  {"features": {"Support": {"moves": 0}, "Support interface": {"moves": 0}}}),
        }
        for number, (before, after) in rows.items():
            with self.subTest(number=number):
                self.assertFalse(checks.measured_check(number, before, after)[0])

    def test_missing_measurements_return_none(self):
        self.assertIsNone(checks.measured_check(273, {"travel_feeds": {"other": []}},
                                                {"travel_feeds": {"other": []}})[0])
        data = {"features": {"Top surface": {"e_per_mm": 1}, "Bottom surface": {"e_per_mm": 1}}}
        self.assertIsNone(checks.measured_check(262, data, {"features": {}})[0])

    def make_export(self, root, run_id, sut, gcode):
        run = root / run_id
        (run / "input").mkdir(parents=True)
        (run / "exports").mkdir()
        fixture = b"synthetic fixture"
        (run / "input" / "fixture.3mf").write_bytes(fixture)
        (run / "exports" / "out.gcode").write_text(gcode)
        digest = hashlib.sha256((run / "exports" / "out.gcode").read_bytes()).hexdigest()
        (run / "proof.json").write_text(json.dumps({"run_id": run_id, "sut_sha256": sut, "gcode_sha256": digest}))
        (run / "result.json").write_text(json.dumps({"release_verdict": "SHADOW"}))
        return run, hashlib.sha256(fixture).hexdigest()

    def test_compare_rejects_changed_export_hash_and_different_sut(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base, sha = self.make_export(root, "base", "build-a", ";LAYER_CHANGE\n;TYPE:External perimeter\nG1 X1 Y1 E1 F100\n")
            case, _ = self.make_export(root, "case", "build-a", ";LAYER_CHANGE\n;TYPE:External perimeter\nG1 X1 Y1 E1 F100\n")
            (case / "exports" / "out.gcode").write_text("tampered")
            self.assertIsNone(checks.compare(258, base, case, sha)[0])
            case2, _ = self.make_export(root, "case2", "build-b", ";LAYER_CHANGE\n;TYPE:External perimeter\nG1 X1 Y1 E1 F100\n")
            self.assertIsNone(checks.compare(258, base, case2, sha)[0])


if __name__ == "__main__":
    unittest.main()
