# Feishu #262 on the physical Mac

The Mac ran Snapmaker Orca 2.4.2 in the dedicated test account with `fixtures/feishu_std_boat.3mf` (SHA-256 `d550f8ac10adfbea6fcfc61be46d76f07515384e20225d425e42eb49d50b4d65`). The source uses the U1 0.4 mm nozzle, PLA, a 0.20 mm standard process and a 0.25 mm initial layer. Raw plate files and receipts are alongside this note.

| Mac CLI slice | Top / bottom / global flow | Slice wall time | Comparison with CLI baseline |
|---|---|---:|---|
| `cli-baseline.gcode` | 1 / 1 / 1 | 3.099 s | Unedited project |
| `cli-target.gcode` | 1.1 / 0.9 / 1 | 3.093 s | Passed `tools/verify_surface_flow_paths.py` |
| `cli-control.gcode` | 0.9 / 1.1 / 1 | 3.092 s | Rejected by the same verifier |

`cli-verified.json` records the binary hash, project and plate hashes, and the comparison for each variant. The target retained the extrusion path segments of each labelled feature. Top and bottom extrusion changed by the expected factors, and other features retained their extrusion. Total extrusion across all labelled features increased by 0.281%. Timings cover the slicer invocation and exclude project preparation and verification.

The CLI inputs can be reproduced from the fixture with Python's `zipfile`. Copy each member using its original `ZipInfo`. For `Metadata/project_settings.config` only, load the JSON, assign the three string values shown in the table to `top_solid_infill_flow_ratio`, `bottom_solid_infill_flow_ratio` and `print_flow_ratio`, then write `json.dumps(settings, ensure_ascii=False).encode()`. This reproduced both recorded input digests on the Windows controller.

## GUI attempts

- `cb5ac024` completed the project-copy workflow with result `SHADOW` in 7 min 18 s. Baseline, edit and reopen ran in three separate named project processes. Direct scrollbar navigation brought both labelled rows into view. Each edit required the parameter's exact key in its native AX editor. The top field took 61.23 s and the bottom field 9.58 s. The saved project retained the boat geometry, placement, U1/PLA process and all three intended flow multipliers.
- The default and independently reopened GUI plates each had 240 layers from Z 0.25 to 48.05. Top extrusion was 1.100001× the baseline over 1,014 matched segments and bottom extrusion was 0.900007× over 311. Other labelled extrusions and all feature paths matched. The global multiplier remained 1. Actual labelled object extrusion increased from 3,785.59731 to 3,796.23152 mm (+0.2809%). The run checks generated geometry and extrusion. Visual acceptance of Preview and strict conservation of total material remain outside the `SHADOW` result.
- `577365ce` timed out waiting for the named baseline AX window. The worker completed cleanup.
- `9aed995e` produced a genuine baseline plate (240 layers, first Z 0.25, last Z 48.05), then opened the editable project in a separate process. Finding the top surface flow row exceeded the 150 s single-operation budget. The baseline G-code digest matches `guest.slice_receipts.baseline.sha256` in `9aed995e-result.json`.
- `a3ab0571` reproduced the GUI baseline, then spent 287.8 s attempting to locate the first editable surface row under a 270 s operation budget. OCR still showed **Precision** after six scroll positions. The source settings and the editable copy stayed at their initial values.

Run `python tools/verify_surface_flow_paths.py --baseline <baseline.gcode> --target <target.gcode>` on two files from the same execution mode. Repeated GUI baselines `9aed995e` and `a3ab0571` have identical paths and extrusion totals for every labelled role. The GUI baseline and the CLI target have different top-surface segment counts (1014 and 1018), despite identical outer-wall paths.
