#!/usr/bin/env bash
# Deploy PrepPilot to the Mac mini.
# Idempotent: safe to re-run for updates. Run from the project root on the MacBook.
# The deploy target lives in deploy/deploy.env (untracked): MINI="user@host"
set -euo pipefail

HERE_EARLY="$(cd "$(dirname "$0")" && pwd)"
[ -f "$HERE_EARLY/deploy.env" ] && source "$HERE_EARLY/deploy.env"
MINI="${MINI:?set MINI in deploy/deploy.env (e.g. MINI=\"user@host\")}"
TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
APP_PORT=8778
SERVE_PORT=10000
REMOTE_DIR="prep-pilot"           # relative to remote $HOME
HERE="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> 1/6  Building frontend locally"
( cd "$HERE/frontend" && npm install --silent && npm run build )

echo "==> 2/6  Syncing project to mini (~/$REMOTE_DIR)"
ssh "$MINI" "mkdir -p ~/$REMOTE_DIR/backend ~/$REMOTE_DIR/frontend/dist"
# Backend code (preserve remote data/ and .env — never overwrite the live DB or secrets).
rsync -az --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude 'data' --exclude '.env' \
  "$HERE/backend/" "$MINI:~/$REMOTE_DIR/backend/"
# Prebuilt frontend.
rsync -az --delete "$HERE/frontend/dist/" "$MINI:~/$REMOTE_DIR/frontend/dist/"

echo "==> 3/6  Ensuring uv is installed on the mini"
ssh "$MINI" 'test -x ~/.local/bin/uv || curl -LsSf https://astral.sh/uv/install.sh | sh'

echo "==> 4/6  Installing Python deps on the mini (uv sync)"
ssh "$MINI" "cd ~/$REMOTE_DIR/backend && ~/.local/bin/uv sync"

echo "==> 5/6  Installing LaunchAgent (auto-start + keep-alive)"
HOME_REMOTE=$(ssh "$MINI" 'echo $HOME')
sed "s#__UV__#$HOME_REMOTE/.local/bin/uv#g; s#__HOME__#$HOME_REMOTE#g" \
  "$HERE/deploy/com.preppilot.server.plist" | \
  ssh "$MINI" "cat > ~/Library/LaunchAgents/com.preppilot.server.plist"
ssh "$MINI" '
  launchctl unload ~/Library/LaunchAgents/com.preppilot.server.plist 2>/dev/null || true
  launchctl load  ~/Library/LaunchAgents/com.preppilot.server.plist
  sleep 4
  curl -sf http://127.0.0.1:'"$APP_PORT"'/api/health && echo " <- app healthy" || echo "app not healthy yet (check ~/Library/Logs/preppilot.log)"
'

echo "==> 6/6  Exposing over Tailscale HTTPS on :$SERVE_PORT (leaves OpenClaw on 443 untouched)"
ssh "$MINI" "$TS serve --bg --https=$SERVE_PORT http://127.0.0.1:$APP_PORT"
ssh "$MINI" "$TS serve status"

DOMAIN=$(ssh "$MINI" "$TS status --json" | python3 -c "import sys,json;print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))")
echo
echo "==> Done. Open:  https://$DOMAIN:$SERVE_PORT"
echo "    First visit will prompt you to set your passcode."
