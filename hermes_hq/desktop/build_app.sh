#!/bin/bash
# Build the "HERMES HQ.app" macOS launcher bundle (AppleScript applet).
#
# Usage:
#   ./build_app.sh [--port 8787] [--dest /Applications] [--no-desktop]
#
# Produces "HERMES HQ.app", installs it to --dest (default /Applications),
# and drops a clickable alias on the Desktop unless --no-desktop is given.
#
# The bundle is an osacompiled AppleScript applet (app.applescript) so it runs a
# real Cocoa event loop and receives the `quit` Apple event — letting us shut
# the server down cleanly via /api/shutdown. It starts the server through the
# shell launcher (launcher.sh), which detaches it as a session leader.

set -euo pipefail

PORT="8787"
DEST="/Applications"
MAKE_DESKTOP=1

while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2;;
    --dest) DEST="$2"; shift 2;;
    --no-desktop) MAKE_DESKTOP=0; shift;;
    *) echo "unknown arg: $1"; exit 1;;
  esac
done

# --- resolve paths ---
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"          # .../hermes_hq/desktop
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"                          # repo root
APP_NAME="HERMES HQ"
BUILD_DIR="$SCRIPT_DIR/build"
APP="$BUILD_DIR/${APP_NAME}.app"

echo "▶ repo:  $REPO_DIR"
echo "▶ port:  $PORT"
echo "▶ dest:  $DEST"

# --- pick venv python (for icon generation) ---
PY=""
for cand in "$REPO_DIR/.venv/bin/python" "$REPO_DIR/venv/bin/python"; do
  [ -x "$cand" ] && { PY="$cand"; break; }
done
[ -z "$PY" ] && PY="$(command -v python3)"
echo "▶ python: $PY"

# --- clean & compile the AppleScript applet into the bundle ---
mkdir -p "$BUILD_DIR"
rm -rf "$APP"

# Template REPO_DIR + PORT into the applet source, then osacompile it.
TMP_SCPT="$(mktemp -t hermeshqapp).applescript"
sed -e "s|__REPO_DIR__|${REPO_DIR}|g" -e "s|__PORT__|${PORT}|g" \
  "$SCRIPT_DIR/app.applescript" > "$TMP_SCPT"
echo "▶ compiling applet…"
/usr/bin/osacompile -s -o "$APP" "$TMP_SCPT"
rm -f "$TMP_SCPT"

# --- template the shell launcher used by the applet ---
sed -e "s|__REPO_DIR__|${REPO_DIR}|g" -e "s|__PORT__|${PORT}|g" \
  "$SCRIPT_DIR/launcher.sh" > "$SCRIPT_DIR/launcher.rendered.sh"
chmod +x "$SCRIPT_DIR/launcher.rendered.sh"
# The applet calls launcher.sh directly from the repo; ensure it's executable.
chmod +x "$SCRIPT_DIR/launcher.sh" 2>/dev/null || true

# --- merge our Info.plist keys (name, id, version) into the compiled plist ---
PLIST="$APP/Contents/Info.plist"
/usr/bin/defaults write "$PLIST" CFBundleName "HERMES HQ" 2>/dev/null || true
/usr/bin/defaults write "$PLIST" CFBundleDisplayName "HERMES HQ" 2>/dev/null || true
/usr/bin/defaults write "$PLIST" CFBundleIdentifier "ai.hermes.hq.launcher" 2>/dev/null || true
/usr/bin/defaults write "$PLIST" CFBundleShortVersionString "0.2.0" 2>/dev/null || true
/usr/bin/defaults write "$PLIST" CFBundleVersion "0.2.0" 2>/dev/null || true
/usr/bin/defaults write "$PLIST" LSMinimumSystemVersion "11.0" 2>/dev/null || true
/usr/bin/defaults write "$PLIST" NSHighResolutionCapable -bool true 2>/dev/null || true
# Keep the app visible (not a background-only agent) so quit/Cmd-Q reach it.
/usr/bin/defaults write "$PLIST" LSUIElement -bool false 2>/dev/null || true

# --- icon: PNG -> iconset -> icns (replaces osacompile's default droplet) ---
echo "▶ generating icon…"
TMP_PNG="$(mktemp -t hermeshq).png"
"$PY" "$SCRIPT_DIR/make_icon.py" "$TMP_PNG" >/dev/null
ICONSET="$(mktemp -d)/hermeshq.iconset"
mkdir -p "$ICONSET"
for sz in 16 32 64 128 256 512; do
  sips -z "$sz" "$sz" "$TMP_PNG" --out "$ICONSET/icon_${sz}x${sz}.png" >/dev/null
  dbl=$((sz * 2))
  sips -z "$dbl" "$dbl" "$TMP_PNG" --out "$ICONSET/icon_${sz}x${sz}@2x.png" >/dev/null
done
sips -z 1024 1024 "$TMP_PNG" --out "$ICONSET/icon_512x512@2x.png" >/dev/null
iconutil -c icns "$ICONSET" -o "$APP/Contents/Resources/applet.icns"
/usr/bin/defaults write "$PLIST" CFBundleIconFile "applet" 2>/dev/null || true
rm -f "$TMP_PNG"

echo "▶ bundle built: $APP"

# --- install ---
echo "▶ installing to $DEST …"
rm -rf "${DEST}/${APP_NAME}.app"
if cp -R "$APP" "$DEST/" 2>/dev/null; then
  INSTALLED="${DEST}/${APP_NAME}.app"
else
  echo "  (no permission for $DEST — falling back to ~/Applications)"
  mkdir -p "$HOME/Applications"
  rm -rf "$HOME/Applications/${APP_NAME}.app"
  cp -R "$APP" "$HOME/Applications/"
  INSTALLED="$HOME/Applications/${APP_NAME}.app"
fi
# refresh Launch Services + icon cache
/usr/bin/touch "$INSTALLED"
# register the bundle so the first double-click works reliably (avoids -600)
LSREG="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
[ -x "$LSREG" ] && "$LSREG" -f "$INSTALLED" >/dev/null 2>&1 || true
echo "✅ installed: $INSTALLED"

# --- desktop alias ---
if [ "$MAKE_DESKTOP" = "1" ]; then
  DESKTOP="$HOME/Desktop"
  /usr/bin/osascript >/dev/null 2>&1 <<OSA || ln -sfn "$INSTALLED" "$DESKTOP/${APP_NAME}.app"
tell application "Finder"
  make alias file to (POSIX file "$INSTALLED") at (POSIX file "$DESKTOP")
  set name of result to "${APP_NAME}.app"
end tell
OSA
  echo "✅ desktop launcher: $DESKTOP/${APP_NAME}.app"
fi

echo
echo "Done. Double-click \"${APP_NAME}\" on your Desktop (or in $DEST) to start."
echo "Logs: ~/Library/Logs/HermesHQ.log"
