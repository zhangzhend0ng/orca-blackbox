#!/bin/bash
# ui_sem.sh — activate Flutter semantics on the CLI web UI and dump the tree.
# Usage: ui_sem.sh [path] [extra_wait_ms]
set -u
PATH_P="${1:-/}"
EXTRA="${2:-4000}"
BASE="http://127.0.0.1:30996/?locale=en-US&dark_mode=1&path=$PATH_P"

agent-browser --cdp 9222 open "$BASE" >/dev/null 2>&1
agent-browser --cdp 9222 wait "flt-semantics-placeholder" >/dev/null 2>&1
cat <<'EOF' | agent-browser --cdp 9222 eval --stdin >/dev/null
(() => { const ph = document.querySelector('flt-semantics-placeholder'); if (ph) ph.click(); })()
EOF
agent-browser --cdp 9222 press Tab >/dev/null 2>&1
agent-browser --cdp 9222 wait "$EXTRA" >/dev/null 2>&1
cat <<'EOF' | agent-browser --cdp 9222 eval --stdin
(() => { const out = []; for (const el of document.querySelectorAll('flt-semantics')) { const t = (el.textContent||'').trim(); if (t && !out.includes(t)) out.push(t.substring(0,70)); } return JSON.stringify(out.slice(0,25)); })()
EOF
