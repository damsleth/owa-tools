#!/bin/bash
# Restart the default Chromium browser with remote debugging enabled.
# Detects the default browser, quits it gracefully, relaunches with --remote-debugging-port.

PORT="${1:-9222}"

# Detect default browser from macOS launch services
BUNDLE_ID=$(plutil -convert json -o - ~/Library/Preferences/com.apple.LaunchServices/com.apple.launchservices.secure.plist 2>/dev/null \
  | python3 -c "import json,sys; handlers=json.load(sys.stdin).get('LSHandlers',[]); print(next((h['LSHandlerRoleAll'] for h in handlers if h.get('LSHandlerURLScheme')=='https'),''))" 2>/dev/null)

if [ -z "$BUNDLE_ID" ]; then
  echo "ERROR: Could not detect default browser" >&2
  exit 1
fi

# Map bundle ID to app name and binary
case "$BUNDLE_ID" in
  com.vivaldi.vivaldi)
    APP_NAME="Vivaldi"
    BINARY="/Applications/Vivaldi.app/Contents/MacOS/Vivaldi"
    KEYCHAIN_SERVICE="Vivaldi Safe Storage"
    ;;
  com.google.chrome|com.google.chrome.canary)
    APP_NAME="Google Chrome"
    BINARY="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    KEYCHAIN_SERVICE="Chrome Safe Storage"
    ;;
  com.microsoft.edgemac)
    APP_NAME="Microsoft Edge"
    BINARY="/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
    KEYCHAIN_SERVICE="Microsoft Edge Safe Storage"
    ;;
  com.brave.browser)
    APP_NAME="Brave Browser"
    BINARY="/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
    KEYCHAIN_SERVICE="Brave Safe Storage"
    ;;
  company.thebrowser.browser)
    APP_NAME="Arc"
    BINARY="/Applications/Arc.app/Contents/MacOS/Arc"
    KEYCHAIN_SERVICE="Arc Safe Storage"
    ;;
  *)
    echo "ERROR: Default browser ($BUNDLE_ID) is not a known Chromium browser" >&2
    echo "Supported: Vivaldi, Chrome, Edge, Brave, Arc" >&2
    exit 1
    ;;
esac

if [ ! -f "$BINARY" ]; then
  echo "ERROR: $APP_NAME binary not found at $BINARY" >&2
  exit 1
fi

# Check if already listening on the debug port
if curl -s "http://127.0.0.1:$PORT/json/version" >/dev/null 2>&1; then
  echo "$APP_NAME already has remote debugging on port $PORT" >&2
  exit 0
fi

echo "Restarting $APP_NAME with remote debugging on port $PORT..." >&2
osascript -e "tell application \"$APP_NAME\" to quit" 2>/dev/null
sleep 2

open -a "$APP_NAME" --args --remote-debugging-port="$PORT"
echo "Done. $APP_NAME is now debuggable on port $PORT." >&2
