"""Feishu #268 (常用工艺参数, P0): sparse-infill combination.

density=20%, pattern=gyroid, direction=45, wall overlap=15%,
gap_fill_target=everywhere; object schedule unchanged."""
from .param_case_lib import make_verify

CASE_ID = "param_268_infill_combo"
GOAL = ("Set sparse infill density to 20%, pattern to gyroid, direction 45, infill wall overlap "
        "15% and gap fill target to everywhere. Preserve the cube geometry, its placement, "
        "material assignment and every other setting.")
# Key correction 2026-11-22 (run 74fe62e3 diff evidence): the overlap setting
# serializes as top_bottom_infill_wall_overlap; the Feishu table's
# "infill_wall_overlap" name never appears in the 3MF config.
VALUES = {"sparse_infill_density": "20%", "sparse_infill_pattern": "gyroid",
          "infill_direction": "45", "top_bottom_infill_wall_overlap": "15%",
          "gap_fill_target": "everywhere"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
