# profile.py — seed an ISOLATED app data dir ("sandbox profile") for a
# black-box vision test run.
#
# Why not ORCA_GUI_TEST_MODE: that env var HIDES the main window
# (GUI_App.cpp: mainframe->Show(true) is skipped when gui_test_mode()) — a
# vision driver has nothing to screenshot. Instead we pre-seed the datadir so
# a NORMAL, VISIBLE startup skips every modal side path:
#
#   wizard     : needs conf to exist AND printers to be non-default AND
#                privacy flag non-empty (GUI_App::config_wizard_startup).
#                -> we install repo presets + write a clean conf with
#                   privacy_policy_isagree=true and firstguide.finish=true.
#   splash     : app.show_splash_screen = false
#   language   : app.language = "en_US" (template byte-stability; NOT the OS
#                locale, which a fresh dir would otherwise pick and persist)
#   start page : app.default_page = "1" (3D editor; "0" is the WebView2 Home)
#   restore    : app.backup_switch = false + no last_backup_path (Plater would
#                otherwise pop the modal "restore previous project?" dialog)
#   geometry   : no window_mainframe key -> default size (a saved position on
#                the GameViewer virtual display would put every sandbox
#                window on a throttled, non-interactive screen)
#
# DATA SOURCES (2026-08-28): everything comes from the REPO RESOURCES (with
# the exe-side resources/ as fallback) — never from the user's %APPDATA%:
#   system/   <- resources/profiles/{Snapmaker,BBL} (+ vendor json). This is
#                the packed-install form the app's own Orca Updater stages
#                into datadir/system; the user's installed system/ is merely
#                a copy of it. Only the vendors the sandbox exercises are
#                copied (58 vendors = 80MB would bloat every fresh seed).
#   printers/ <- resources/printers/ (vendor machines: BL-P001 Bambu Lab,
#                N1/N2S, ...). Without them every third-party project loses
#                its printer preset (silent replacement) and startup logs
#                "staging validation failed (printers)".
#   conf      <- a minimal hand-written template. Copying the user's conf
#                leaks personal state (recent files, window geometry, login/
#                device identity) and makes the sandbox non-reproducible.
#
# Config format (this fork, USE_JSON_CONFIG): a single JSON object followed by
# "\n# MD5 checksum <32 hex>\n". The MD5 is only an informational check on
# load (a mismatch logs an info line); the JSON must simply parse.

import hashlib
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent  # <repo>/harness
SANDBOX = HERE.parent  # <repo> (standalone checkout root)
REPO_RESOURCES = SANDBOX / "resources"  # vendored preset subset (profiles/{Snapmaker,BBL} + printers)

# Minimal conf: everything the startup gate needs and nothing personal.
# Keys are typed like the real conf (bool vs string) so the app's typed
# getters (get vs get_bool) keep working.
MINIMAL_CONF = {
    "app": {
        "language": "en_US",
        "show_splash_screen": False,
        "single_instance": False,
        "default_page": "1",             # "1" = 3D editor (Prepare)
        "privacy_policy_isagree": True,
        "backup_switch": False,          # kill the restore-project modal
    },
    "firstguide": {"finish": True},      # exactly as the wizard persists it
}

# Vendors installed into datadir/system (whitelist keeps fresh seeds fast;
# the app only needs ANY non-default printer to skip the wizard).
_VENDORS = ["Snapmaker", "BBL"]


def default_presets_dir() -> Path:
    """System-preset vendors source: repo resources/profiles when a dev
    checkout vendors them, else the exe-side resources/profiles the app
    ships for Orca Updater staging. The git clone does NOT carry the ~80MB
    vendor set, so without this fallback datadir/system stays empty and the
    first-run Setup Wizard comes BACK on empty boots (measured 09-03
    boot_probe phase a: #32770 'Setup Wizard' at t=2s over the window
    centre, despite the seeded conf — the wizard gate needs non-default
    printers, which only system vendors provide)."""
    from . import launcher
    for cand in (REPO_RESOURCES / "profiles",
                 launcher.default_exe().resolve().parent
                 / "resources" / "profiles"):
        if cand.exists():
            return cand
    return REPO_RESOURCES / "profiles"  # caller prints the visible WARN


def default_resources_dir() -> Path:
    """Repo resources/ first (development), then packaged-layout resources/
    (<runner>/resources), then exe-side resources/ (installed builds)."""
    if REPO_RESOURCES.exists():
        return REPO_RESOURCES
    runner_dir = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
                  else SANDBOX)
    data_dir = runner_dir / "_internal" if (runner_dir / "_internal").exists() else runner_dir
    for alt in (data_dir / "resources",
                runner_dir / "resources",
                Path(r"C:\coil\Projects\SnapmakerOrca_dev\build\src\Release\resources")):
        if alt.exists():
            return alt
    raise FileNotFoundError("no resources dir (repo/packaged/exe-side) found")


def load_conf(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    left = raw[: raw.rfind("}") + 1]  # strip the trailing checksum comment
    return json.loads(left)


def write_conf(path: Path, conf: dict) -> None:
    body = json.dumps(conf, indent=4, ensure_ascii=False)
    digest = hashlib.md5((body + "\n").encode("utf-8")).hexdigest().upper()
    path.write_text(body + "\n# MD5 checksum " + digest + "\n", encoding="utf-8")


def _kill_lingering_app() -> None:
    """A previous case's app can outlive its driver (graceful-close race)
    and hold <datadir>\\log open, which makes the fresh seed's rmtree blow
    up with PermissionError (measured 09-01). Kill it before seeding."""
    import subprocess
    subprocess.run(["taskkill", "/IM", "snapmaker-orca.exe", "/F"],
                   capture_output=True)


def seed_profile(dest: Path,
                 source_conf: Path | None = None,
                 source_presets: Path | None = None,
                 source_printers: Path | None = None,
                 fresh: bool = False,
                 conf_extra: dict | None = None) -> Path:
    """Create/refresh `dest` as a runnable sandbox datadir; returns it.

    All sources default to the repo/exe resources; explicit overrides are
    accepted for CI setups that vendor their own assets.

    `conf_extra` merges extra keys over MINIMAL_CONF (top-level keys land in
    the conf's default section; dict values deep-merge one level so e.g.
    {"app": {"skip_version": "..."}} works). This is the isolation knob:
    boot_probe phases and future "updater UX" cases use it to pin/unpin the
    upgrade-feed URLs the app fetches at post_init.
    """
    dest = Path(dest)
    resources = default_resources_dir()
    source_presets = Path(source_presets) if source_presets else default_presets_dir()
    source_printers = Path(source_printers) if source_printers else resources / "printers"

    if fresh and dest.exists():
        _kill_lingering_app()
        for attempt in range(3):
            try:
                shutil.rmtree(dest)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(3.0)
    dest.mkdir(parents=True, exist_ok=True)

    # 1) system presets: makes printers.only_default_printers() false so the
    #    startup wizard does not run. Whitelisted vendors in packed-install
    #    form (vendor dir + vendor.json), the same layout the app's Orca
    #    Updater stages into datadir/system.
    print(f"[profile] system presets source: {source_presets}")
    dst_system = dest / "system"
    if not dst_system.exists():
        missing = []
        for vendor in _VENDORS:
            vdir = source_presets / vendor
            if not vdir.exists():
                missing.append(vendor)
                continue
            shutil.copytree(vdir, dst_system / vendor)
            vjson = source_presets / f"{vendor}.json"
            if vjson.exists():
                shutil.copy2(vjson, dst_system / f"{vendor}.json")
        if missing:
            print(f"[profile] WARN vendor dir(s) missing under {source_presets}: "
                  f"{', '.join(missing)} — datadir/system stays incomplete and "
                  f"the first-run Setup Wizard can reappear on empty boots "
                  f"(see profile.default_presets_dir)")

    # 2) vendor printer presets: the app's Orca Updater stages these into
    #    <datadir>/printers at startup; without them third-party projects
    #    lose their printer preset and startup logs "staging validation
    #    failed (printers)".
    dst_printers = dest / "printers"
    if not dst_printers.exists():
        if not source_printers.exists():
            print(f"[profile] WARN printers source missing: {source_printers}")
        else:
            shutil.copytree(source_printers, dst_printers)

    # 3) app conf: minimal hand-written template — reproducible and free of
    #    user state (recent files, window geometry, device identity).
    conf = json.loads(json.dumps(MINIMAL_CONF))
    for key, value in (conf_extra or {}).items():
        if isinstance(value, dict) and isinstance(conf.get(key), dict):
            conf[key].update(value)          # one-level deep merge
        else:
            conf[key] = value                # top-level key (default section)
    write_conf(dest / "Snapmaker_Orca.conf", conf)
    print(f"[profile] seeded {dest} (resources: {resources})")
    print(f"[profile] conf: {json.dumps(conf)}")
    return dest


if __name__ == "__main__":
    import sys
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("vision_profile")
    seed_profile(dest)
