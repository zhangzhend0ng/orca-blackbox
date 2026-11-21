"""Feishu #259 (常用工艺参数, P0): top-surface ironing combination.

ironing_type=topmost, ironing_flow=10%, ironing_spacing=0.15,
ironing_speed=60 on the standard cube; the G-code must carry ironing
moves on the top surface (analyze_gcode's ironing inspection) with the
object schedule otherwise unchanged."""
from .param_case_lib import make_verify

CASE_ID = "param_259_ironing_top"
GOAL = ("Enable topmost-surface ironing with flow 10%, spacing 0.15 mm and speed 60 mm/s. "
        "Preserve the cube geometry, its placement, material assignment and every other setting.")
VALUES = {"ironing_type": "topmost", "ironing_flow": "10%", "ironing_spacing": "0.15",
          "ironing_speed": "60"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"},
                              ironing={"min_moves": 8})
