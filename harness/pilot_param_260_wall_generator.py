"""Feishu #260 (常用工艺参数, P0): Arachne wall generator combination.

Snapshot row: .../tblKjIVV8KA53kUQ_20261122_024056_171.ndjson line 179.
Five of the seven targets already equal the fixture config values
(min_bead_width=85%, min_feature_size=25%, wall_transition_angle=10,
wall_transition_length=100%, wall_transition_filter_deviation=25% -
measured in fixtures/agent_layer_cube.3mf; the Feishu names match the
config keys exactly). Only the generator combo (classic->arachne) and
wall_distribution_count (1->3) move. Arachne rewrites wall paths, not
the layer grid: the schedule stays 68 x 0.4 / 27.2."""
from .param_case_lib import make_verify

CASE_ID = "param_260_wall_generator"
GOAL = ("Switch the wall generator to Arachne and set wall distribution count "
        "to 3, keeping minimum wall width 85%, minimum feature size 25%, wall "
        "transitioning threshold angle 10 deg, transition length 100% and "
        "transitioning filter margin 25%. Preserve the cube geometry, its "
        "placement, material assignment and every other setting.")
VALUES = {"wall_generator": "arachne", "min_bead_width": "85%",
          "min_feature_size": "25%", "wall_distribution_count": "3",
          "wall_transition_angle": "10", "wall_transition_length": "100%",
          "wall_transition_filter_deviation": "25%"}
verify_business = make_verify(CASE_ID, VALUES, schedule={"layer_count": 68, "last_z": "27.2"})
