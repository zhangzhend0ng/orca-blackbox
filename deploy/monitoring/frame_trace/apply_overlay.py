"""Instrument a separate, archived Orca source snapshot. Do not run in a checkout."""

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
STAMP = ".orca-frame-trace-build.json"


def apply(source):
    source = source.resolve(strict=True)
    stamp = source / STAMP
    if any((root / ".git").exists() for root in (source, *source.parents)) or not stamp.is_file():
        raise ValueError("Use an isolated archived source with its build identity stamp")
    manifest = json.loads(stamp.read_text(encoding="utf-8"))
    if not manifest.get("source_commit") or "profiles_commit" not in manifest:
        raise ValueError("Missing source provenance")
    gui = source / "src" / "slic3r" / "GUI"
    f = gui / "GLCanvas3D.cpp"
    header = gui / "OrcaFrameTrace.hpp"
    if header.exists():
        raise ValueError("Frame trace is already installed")
    original = f.read_bytes()
    newline = b"\r\n" if b"\r\n" in original else b"\n"
    normalized = original.replace(b"\r\n", b"\n")
    if b"void GLCanvas3D::render(bool only_init, bool overlayOnly)" in normalized:
        overlay_only = b"!fullSceneRefresh"
    elif b"void GLCanvas3D::render(bool only_init)" in normalized:
        overlay_only = b"false"
    else:
        raise ValueError("Unsupported GLCanvas3D::render signature")
    edits = [
        (b'#include "GLCanvas3D.hpp"',
         b'#include "GLCanvas3D.hpp"\n#if defined(_WIN32)\n#include "OrcaFrameTrace.hpp"\n#endif'),
        (b"    if (only_init)\n        return;\n",
         b"    if (only_init)\n        return;\n\n"
         b"#if defined(_WIN32)\n"
         b"    auto* frame_trace = OrcaBlackbox::FrameTrace::current();\n"
         b"    const auto render_start = frame_trace ? OrcaBlackbox::FrameTrace::now() : 0;\n"
         b"#endif\n"),
        (b"    m_canvas->SwapBuffers();\n    m_render_stats.increment_fps_counter();",
         b"#if defined(_WIN32)\n"
         b"    if (frame_trace) {\n"
         b"        const auto submit_start = OrcaBlackbox::FrameTrace::now();\n"
         b"        const bool swapped = m_canvas->SwapBuffers();\n"
         b"        const auto submit_end = OrcaBlackbox::FrameTrace::now();\n"
         b"        frame_trace->record(this, static_cast<unsigned>(m_canvas_type), " + overlay_only + b",\n"
         b"                            swapped, render_start, submit_start, submit_end);\n"
         b"    } else\n"
         b"#endif\n"
         b"    m_canvas->SwapBuffers();\n    m_render_stats.increment_fps_counter();"),
    ]
    for before, after in edits:
        if normalized.count(before) != 1:
            raise ValueError(f"Unexpected GLCanvas3D source near {before[:90]!r}")
        normalized = normalized.replace(before, after)
    header.write_bytes((ROOT / "OrcaFrameTrace.hpp").read_bytes())
    f.write_bytes(normalized.replace(b"\n", newline))
    print(f"Instrumented isolated source {manifest['source_commit']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    apply(parser.parse_args().source)
