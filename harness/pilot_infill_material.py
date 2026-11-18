"""Combined infill and material proof on the same saved and resliced cube."""
from .pilot_common import require_gcode_settings
from .pilot_infill import _sparse_extrusion_moves
from .pilot_material3 import _verify_logical_slot

CASE_ID = "general_infill30_material3"
GOAL = ("Set Sparse infill density to 30%, keeping the existing Grid pattern, and assign "
        "the whole cube to existing filament slot 3. Preserve all other settings, geometry "
        "and placement. Keep global material and nozzle mappings unchanged.")


def verify_business(project, fixture, gcode, *, cancelled=lambda: False):
    summary = _verify_logical_slot(project, fixture, gcode, slot=3, cancelled=cancelled,
                                  allowed_changes={"sparse_infill_density": "30%"})
    require_gcode_settings(gcode, {"sparse_infill_density": "30%", "sparse_infill_pattern": "grid",
                                  "wall_loops": "2"}, "combo_gcode_setting")
    return dict(summary, sparse_infill_density="30%",
                sparse_positive_xy_e_moves=_sparse_extrusion_moves(gcode, cancelled),
                physical_density_ratio_verified=False)
