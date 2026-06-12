#!/bin/bash
# HERMES HQ server launcher (invoked by the AppleScript applet).
#
# Responsibilities:
#   1. activate the project venv
#   2. start the HERMES HQ server as a session leader (its own process group)
#   3. wait for the port, open the dashboard, then EXIT
#
# The applet (app.applescript) is the long-lived foreground process that owns
# the macOS `quit` event; it calls /api/shutdown for a clean stop. This script
# only needs to start the server detached and return. We still make the server
# a session leader so any stray cleanup can reap the whole group reliably.
#
# REPO_DIR and PORT are templated in at build time by build_app.sh.

set -u

REPO_DIR="__REPO_DIR__"
PORT="__PORT__"
HOST="127.0.0.1"
URL="http://${HOST}:${PORT}"
LOG="${HOME}/Library/Logs/HermesHQ.log"

mkdir -p "$(dirname "$LOG")"

notify() {
  /usr/bin/osascript -e "display notification \"$1\" with title \"HERMES HQ\"" >/dev/null 2>&1 || true
}
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG"; }

log "launch requested (repo=$REPO_DIR port=$PORT)"

# --- already running? just open the browser ---
if /usr/bin/curl -s -o /dev/null --max-time 1 "${URL}/api/info"; then
  log "server already up; opening browser"
  /usr/bin/open "$URL"
  notify "Already running — opening dashboard."
  exit 0
fi

cd "$REPO_DIR" || { notify "Repo not found: $REPO_DIR"; log "ERROR repo missing"; exit 1; }

# --- pick the venv python ---
PY=""
for cand in "$REPO_DIR/.venv/bin/python" "$REPO_DIR/venv/bin/python" "$HOME/.hermes/claude-code/venv/bin/python"; do
  if [ -x "$cand" ]; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  notify "No Python venv found. Run setup first."
  log "ERROR no venv python"
  exit 1
fi
log "using python: $PY"

notify "Starting HERMES HQ…"

# --- start the server in its OWN session / process group, fully detached ---
# os.setsid() makes the server a session leader (PID == PGID) so it survives
# this launcher exiting and can be reaped as a group if ever needed. nohup +
# disown detach it from this shell entirely.
nohup "$PY" -c 'import os,sys; os.setsid(); os.execv(sys.executable, [sys.executable, "-m", "hermes_hq", "--host", sys.argv[1], "--port", sys.argv[2]])' "$HOST" "$PORT" >> "$LOG" 2>&1 &
SERVER_PID=$!
disown "$SERVER_PID" 2>/dev/null || true
log "server started pid=$SERVER_PID pgid=$SERVER_PID"

# --- wait for readiness (up to ~30s), then open the dashboard ---
ready=0
for _ in $(seq 1 60); do
  if /usr/bin/curl -s -o /dev/null --max-time 1 "${URL}/api/info"; then ready=1; break; fi
  if ! kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    log "ERROR server exited during startup; see $LOG"
    notify "Server failed to start. See ~/Library/Logs/HermesHQ.log"
    exit 1
  fi
  sleep 0.5
done

if [ "$ready" = "1" ]; then
  log "server ready; opening browser"
  /usr/bin/open "$URL"
  notify "HERMES HQ is live → ${URL}"
else
  log "ERROR server not ready after timeout"
  notify "Server didn't come up in time. See log."
fi

# Return immediately — the applet stays in the foreground and owns lifecycle.
exit 0
