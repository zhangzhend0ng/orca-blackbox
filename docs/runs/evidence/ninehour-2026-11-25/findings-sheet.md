# ninehour_1125 — findings sheet (scratch; sources cited for the delivery)

T0 2026-11-25 01:29:12 Beijing. Three-machine start commit 636a733. Integration commit d5fc2fa (= engine e3bfdfe + receipts tool).
Everything below was measured tonight unless marked otherwise. Machine caps: win11-test = regression-evidence machine; fa706g3 = SHADOW at most (README rule 6); Mac = SHADOW at most.

## Feishu rows (snapshot docs/runs/evidence/feishu-tblKjIVV8KA53kUQ-2026-11-22/*.ndjson; base JB5jbAczEa7vZUsWFencTmNnnob, table tblKjIVV8KA53kUQ)
- #276 reczz28b6mRAyH5p 速度高级-流量与机器上限组合. Precondition: U1 0.4 nozzle, PLA, 0.20 mm standard preset; model 标准模型>立方体. Steps: outer_wall_speed=700; layer_height=0.20; outer_wall_line_width=0.42; filament_max_volumetric_speed=15; machine_max_speed_x=500; baseline slice saved; apply all at once and reslice; compare config, preview, G-code. Expected: (1) values written, G-code produced; (2) outer wall speed first limited by volumetric flow to about 178 mm/s; (3) not above X 500 mm/s, excess slowed, path unchanged.
- #264 reczz28b6mRB0mjp 悬垂-识别与分档速度组合. Precondition: same machine/preset; model 实用模型>欧特克FDM测试. Steps: detect_overhang_wall=1; enable_overhang_speed=1; overhang_1_4_speed=40; overhang_2_4_speed=30; overhang_3_4_speed=20; overhang_4_4_speed=10; overhang_totally_speed=5; baseline slice; apply and reslice; compare. Expected: (1) values written, G-code produced; (2) F of each overhang band about 2400/1800/1200/600/300; (3) F of non-overhang and BRIDGE areas unchanged.
- Feishu status: both rows are 待实现 (not among the 92 已自动化). Snapshot currency: identical to the 11-24 23:21 live export on the step/expected fields.
- Existing comparison full table (216 rows): artifacts/feishu216-audit/ (xlsx + combined.json, git-ignored), built 11-24 23:34 on f03e614. 已自动化 92 (完整 4 / 部分 63 / 未证实 25), 部分自动化 4, 空白 27, 不适用 49, 待实现 44.

## Source facts for #264 (app under test = Snapmaker Orca 2.4.0, source commit 56e82d53 in C:\coil\Projects\SnapmakerOrca)
- "Overhang speed" row has exactly four boxes: src/slic3r/GUI/Tab.cpp:2713-2722 (four append_option) for overhang_1_4_speed (10%-25%), overhang_2_4_speed ([25%,50%)), overhang_3_4_speed ([50%,75%)), overhang_4_4_speed ([75%,100%)); definitions src/libslic3r/PrintConfig.cpp:1270-1316. No get_field_count exists.
- overhang_totally_speed is not a parameter of 2.4.0: only in the legacy ignore set (PrintConfig.cpp:7613, dropped 7616-7619). The fifth option and the key were added by commit b070bcfaff on 2026-11-05, which is in 2.4.1 (PrintConfig.cpp:1365-1366, Tab.cpp:2867-2871), not in 56e82d53.
- Slicing: base speed of an overhang wall is bridge_speed (GCode.cpp:7568-7569); the lowest band runs at bridge_speed when slowdown_for_curled_perimeters is off (GCode.cpp:7681, 7720), else overhang_4_4_speed (7698-7700).
- Serialization: save writes every present key (Plater.cpp:20877/20982 -> bbs_3mf.cpp:7469-7475, Config.cpp:1539-1563); an injected overhang_totally_speed is dropped at load (handle_legacy).
- Historic run 50798c59 (the run a stale comment cited) wrote the "5" into the THIRD box under an older script; current ops fill four boxes.
- Decision tonight: the fifth value is NOT mapped onto bridge_speed - the row expects bridge F unchanged - so the gap stays for the test team (run on a build that has the parameter, or amend the row).

## Where the 27 s of checkbox "Detect overhang" went (fa run 76b85931: 26.99 s; guest 778bbfa2: 26.37 s)
- 96% was fixed sleep. scroll_group_into_view (harness/process_panel.py) sent ONE wheel notch per turn; a turn costs 0.75 s of sleeps (0.15 + 0.08 + 0.4 in real_wheel, 0.12 in the loop). The 'Overhangs' title is 26-27 notches below the page top: 19.50 s (fa, 26 notches) / 20.25 s (guest, 27 notches).
- Scan: about 1.03 s per wheeled iteration (one crop upscaled x3 + pytesseract, a notch, 0.4 s sleep); 2-3 OCR passes.
- Clicks: both boxes were already ticked in the default preset (0.88 -> 0.13 -> 0.86): each op toggled its box off and on, 4.40 s of sleep.
- 'Slow down' (Speed page, 4 notches down) therefore cost 8.03 s: 3.0 s of notches + 4.4 s of double toggle.
- Tab switch (9.6 s twice): 9.25 s fixed sleep on a single-poll path (click 1.0, 1.5, a 40-notch reset wheel 3.75, 3.0 settle); not changed tonight.
- Not changed on purpose: the double toggle (keeps the checkbox actually operated).

## Measured facts from harvested artifacts (recompute agent; scripts and JSON in ninehour_1125\recompute)
- #276 (ec032d7c, eebdf238, 5359abca): saved outer wall 200->700, slot-1 max volumetric 12->15; layer 0.2, width 0.42 and X 500 already had the step values; echo equals saved for every present key; 135 layers; peak outer wall 202.956 mm/s = F12177.366 on 28 of 536 outer-wall moves (default slice 162.365); volumetric peak 15.000 mm3/s.
  - Expected 2 as worded ("about 178") is not met: 178.57 = 15/(0.20*0.42) assumes a rectangular section; the slicer uses 0.073908 mm2 (0.2*(0.42-0.2*(1-pi/4))*0.98) -> 202.956. near_feishu_178_mm_s = false.
  - Expected 3 is not exercised: the X-axis component peaks at 202.956 mm/s, the 500 limit never acts. "Path unchanged" holds for both Quality runs (6123 moves identical to baseline e9aa6f88); it FAILS for the Strength run (6093 moves; internal solid infill 2.02 mm shorter in 5 cells) although the saved project equals Quality's except the source_file path.
- #264 cube runs (7484bd43 guest; 19d61032, 8e207463 fa): 0->40, 50->30, 25->20, 5->10; detect/enable already 1; no totally key; 68 layers; no Overhang wall section on a cube. fa and guest saved identical settings (586 keys), identical echo (574 keys) and identical G-code bodies (only timestamp, thumbnail and object-id lines differ).
- #264 fdmt (b697f7c2 guest, Feishu row's own model): 0->40, 50->30, 30->20, 4/4 already 10; 460 layers. 146 Overhang wall sections use only F3000 (1524.8 mm) and F1980 (77.0 mm), identical to the default slice; none of 2400/1800/1200/600/300 appears there (2.4.0 interpolates per point: 270 distinct wall feeds). F1200 elsewhere is the layer-cooling floor and is present equally in the default slice.
  - Versus the default slice 0cccce4a (made on fa706g3 on 11-24 12:05; a guest default baseline was added tonight: run 032905f0 uia_param_fdmt_save_only): same paths extruded in all 1494 (type, layer) cells; bridge feeds CHANGED on 431.5 mm of 7898 mm (off F3000 to F660-F1980) because 2.4.0 applies the band table to bridges too; non-overhang feeds changed on 151 of 258 layers through slow_down_for_layer_cooling.
- Every export and proof matched the sha256 in proof.json; keys differing input->saved are targets plus 2.3.6->2.4.0 migrations, 0 unrelated.

## Negative controls of the judges (offline, on copies) - holes, in bold in the delivery
1. The #264 judge asserts nothing about the G-code of the Feishu row's own run: the business judge AND the full verify_saved accepted the default-parameter export, the cube's export, a 2000-byte truncation, an export whose config block carries default values, and default moves behind the edited config block. checks.business: pass rests on saved settings only (detail carries schedule_error: gcode_fixture_height_mismatch).
2. The #264 judge never compares the export's config block with the saved project.
3. #276: the in-run check (no baseline) accepts default moves behind an edited config block (pair_status: baseline_required); only the host-side paired judge rejects it, and that judge can never answer PASS because x_limit_effect is a constant (harness/param_comparison.py:132, 208).
4. The full verifier ignores manifest.json case_id, executor, contract_sha256 and metadata.
- Rejected as they should be (both rows): one step off, target left at default or unset, targets right plus one unrelated setting, the input fixture presented as result, a dirty list with an unrelated key.

## Native model actor (ZCode provider new-provider / Snapmaker, model glm-5.4, gateway ai-gateway.s.com), guest, engine eae2376, Quality start
- #265 run eefe9d78: RuntimeError zcode_actor_failed:agent_deadline; host 672.703 s; 20 tool calls (Snapshot 10, Click 7, Wait 2, Screenshot 1); 11 model requests.
- #276 run 2053992c: zcode_actor_failed:native_action_budget; host 437.125 s; 41 tool calls (Snapshot 20, Click 16, Shortcut 2, Type 2, Screenshot 1); 42 model requests.
- Both NON_GREEN, cleanup confirmed; no verified GUI result, so no pairing. Same signatures as the 11-24 round.

## Mac line (blocked)
- coil's console session locked at 2026-11-24 19:25:27 (CGSSessionScreenLockedTime 1795519527); still locked at every check through 03:42.
- Test instance launches, renders and loads the project (screenshot), but every app in the coilwin session (Finder, Safari, iTerm2, UURemote, the test Orca) answers AXWindows with an AXApplication-titled self-referential placeholder; AXEnhancedUserInterface set returns -25208. Worker gate needs an AXStandardWindow with the project title -> "Named project window did not open" at baseline.launch.
- Runs: 5bb1a766 (first run, NON_GREEN, 01:35), probes 01:42-02:21 (scratch copies of the worker only). Last successful Mac GUI runs were before 11-24 16:20, console unlocked.
- Recovery condition: the console session is unlocked by its user. Not attempted: unlocking, switching the console, or touching coil's own Orca process.
- Evidence: ninehour_1125\mac\ (ledger.txt, probe*.log, console_sessions_*.json), screenshots mac_probe2_baseline.png / mac_probe6_baseline2.png.
