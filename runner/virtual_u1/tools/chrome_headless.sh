#!/bin/bash
# chrome_headless.sh — start the automation Chrome for the CLI web UI.
#
# headless=new keeps Flutter's frame pump alive (a headed window that gets
# occluded stops rendering and drops its semantics tree) and the semantics
# tree forms on the first frame. Own profile, so the user's Chrome is never
# touched. Stays up after the script exits; test_l2.py --ui attaches to it.
#
# Usage: chrome_headless.sh [port=9224]
set -u
PORT="${1:-9224}"
PROFILE="$LOCALAPPDATA\\Temp\\orca-hl-profile"
CHROME="/c/Program Files/Google/Chrome/Application/chrome.exe"

if curl -s -m 2 "http://127.0.0.1:$PORT/json/version" >/dev/null; then
  echo "already listening on $PORT"
  exit 0
fi
# Chrome outlives this script: keep its stdio off ours, or a caller that
# pipes the script's output (`... | tail`, `$(...)`) waits forever for EOF.
"$CHROME" --headless=new --remote-debugging-port="$PORT" --user-data-dir="$PROFILE" \
  --window-size=1600,1000 --no-first-run --no-default-browser-check \
  --disable-backgrounding-occluded-windows --disable-features=CalculateNativeWinOcclusion \
  about:blank >/dev/null 2>&1 </dev/null &
for _ in $(seq 1 20); do
  if curl -s -m 2 "http://127.0.0.1:$PORT/json/version" >/dev/null; then
    echo "headless chrome listening on $PORT (profile $PROFILE)"
    exit 0
  fi
  sleep 1
done
echo "chrome did not open port $PORT"
exit 1
