"""Feishu #264 (常用工艺参数, P0): overhang detection + tiered overhang speeds."""
import hashlib

from .agent_protocol import FIXTURE_SUFFIXES
from .agent_verify import _require
from .param_case_lib import make_verify
from .param_comparison import _export

CASE_ID = "param_264_overhang_speeds"
GOAL = ("Enable detect overhang wall and slow down for overhang, then set the five overhang "
        "degree-band speeds to 40/30/20/10/5. Preserve the cube geometry, its placement, "
        "material and every other setting.")
# Stored booleans as "1" per the #266 wall_thin precedent (run 05dd9020).
# Enum-free: overhang_* are coFloatsOrPercents written as plain numbers.
VALUES = {"detect_overhang_wall": "1", "enable_overhang_speed": "1",
          "overhang_1_4_speed": "40", "overhang_2_4_speed": "30",
          "overhang_3_4_speed": "20", "overhang_4_4_speed": "10"}
# Recorded deviation (2026-11-23): the Feishu row asks for five band speeds,
# but 2.4.0 has no fifth "Overhang speed" box and no overhang_totally_speed
# key (both arrived with 2.4.1; run 50798c59's saved file showed the key
# absent), so the fifth value (5) has no control and is not asserted.
_verify_settings = make_verify(CASE_ID, VALUES)
_verify_other_fixtures = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
_FDM_FIXTURE_SHA256 = FIXTURE_SUFFIXES["_fdmt"][1]

# Default-parameter FDM exports 0cccce4a (fa706g3) and 032905f0 (win11-test)
# agree on these paths. Pin the overhang geometry to identify the original
# model, and compare its body to the default by role and modal feed. Sort the
# paths because print order can vary, and exclude internal solid infill, whose
# segmentation changed between runs with identical settings.
_FDM_OVERHANG_GEOMETRY = "b4c3e69b4798bf78aa38ff2c74ba5a31f70c33cd716ed4ac4cb05e65d3ea76d3"
_FDM_DEFAULT_OVERHANG = "b7acb73cfba01672d35b89c39a92d39fa381bdb715c4df8defdc17d16bf50e79"
_FDM_DEFAULT_BRIDGE = "6d0a9654b9b7558dab496aedf0b8f95af4f26509d35247c8c656ef7be9fc0c92"
_FDM_DEFAULT_TOP_GEOMETRY = "7a7328af0f61b94cfe05c9f4d5cbd5710c527128d22681354252793009da1eeb"
_FDM_DEFAULT_TOP = "efdff8db01e7eca4453b2cbbdb29b017e7655461bebfc9fd908a57919602b752"
_FDM_DEFAULT_BRIDGE_FEEDS_MM_MIN = {960, 3000}
_EXPECTED_FEEDS_MM_MIN = (2400, 1800, 1200, 600, 300)


def _path_signature(paths, *, include_feed):
    rows = []
    for location, feed in paths:
        row = ",".join(str(value) for value in (location[0], *location[2:]))
        rows.append(f"{row},{feed:g}" if include_feed else row)
    return hashlib.sha256("\n".join(sorted(rows)).encode("ascii")).hexdigest()


def verify_business(project, fixture, gcode, *, cancelled=lambda: False):
    if hashlib.sha256(fixture).hexdigest() != _FDM_FIXTURE_SHA256:
        return _verify_other_fixtures(project, fixture, gcode, cancelled=cancelled)

    result = _verify_settings(project, fixture, gcode, cancelled=cancelled)
    layers, moves = _export(gcode, {key: str(result[key]) for key in VALUES}, cancelled)
    expected_layers = [(25 + 20 * index) / 100 for index in range(460)]
    _require(layers == expected_layers, "param_264_fdm_layer_grid")

    paths = {role: [] for role in ("Overhang wall", "Bridge", "Top surface")}
    for location, speed, _, _ in moves:
        if location[1] in paths:
            paths[location[1]].append((location, round(speed * 60, 6)))
    overhang = paths["Overhang wall"]
    _require(_path_signature(overhang, include_feed=False) == _FDM_OVERHANG_GEOMETRY,
             "param_264_fdm_overhang_geometry")
    _require(paths["Bridge"] and paths["Top surface"], "param_264_fdm_deposition")
    overhang_changed = _path_signature(overhang, include_feed=True) != _FDM_DEFAULT_OVERHANG
    bridge = paths["Bridge"]
    bridge_signature_changed = _path_signature(bridge, include_feed=True) != _FDM_DEFAULT_BRIDGE
    _require(overhang_changed or bridge_signature_changed, "param_264_fdm_default_export_body")

    bridge_feeds = {feed for _, feed in bridge}
    bridge_feeds_changed = bridge_feeds != _FDM_DEFAULT_BRIDGE_FEEDS_MM_MIN
    top = paths["Top surface"]
    top_shape_matches = _path_signature(top, include_feed=False) == _FDM_DEFAULT_TOP_GEOMETRY
    top_feeds_changed = top_shape_matches and _path_signature(top, include_feed=True) != _FDM_DEFAULT_TOP
    feeds = {feed for _, feed in overhang}
    missing = [want for want in _EXPECTED_FEEDS_MM_MIN
               if not any(abs(feed - want) <= want * 0.01 for feed in feeds)]
    unmet = ["overhang_totally_speed"]
    if missing:
        unmet.append("overhang_band_feeds")
    if bridge_feeds_changed:
        unmet.append("bridge_feeds_unchanged")
    if top_feeds_changed:
        unmet.append("non_overhang_feeds_unchanged")
    result.update(
        layer_count=len(layers), first_z=str(layers[0]), last_z=str(layers[-1]),
        schedule_asserted=True, gcode_sha256=hashlib.sha256(gcode).hexdigest(),
        fdm_original_model_export_checked=True,
        overhang_feed_count=len(feeds), overhang_feeds_mm_min=sorted(feeds)[:20],
        missing_overhang_feeds_mm_min=missing,
        bridge_feed_count=len(bridge_feeds), bridge_feeds_mm_min=sorted(bridge_feeds)[:20],
        bridge_feed_set_changed=bridge_feeds_changed,
        top_surface_paths_match_default=top_shape_matches,
        top_surface_feeds_changed=top_feeds_changed if top_shape_matches else None,
        unmet_expectations=unmet,
    )
    return result
