#!/usr/bin/env bash
# Deploy a committed PrepPilot revision to an isolated development environment.
set -euo pipefail

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"
[ -f "$DEPLOY_DIR/deploy.env" ] && source "$DEPLOY_DIR/deploy.env"
MINI="${MINI:?set MINI in deploy/deploy.env (e.g. MINI=\"user@host\")}"
TS="/Applications/Tailscale.app/Contents/MacOS/Tailscale"
APP_PORT=8779
SERVE_PORT=10004
REMOTE_DIR="prep-pilot-dev"
HERE="$(cd "$DEPLOY_DIR/.." && pwd)"
BRANCH="$(git -C "$HERE" branch --show-current)"
SHA="$(git -C "$HERE" rev-parse --short=12 HEAD)"

if ! git -C "$HERE" diff --quiet || ! git -C "$HERE" diff --cached --quiet; then
  echo "Dev deploy blocked: commit tracked changes first." >&2
  exit 1
fi
UNTRACKED_PAYLOAD="$(git -C "$HERE" ls-files --others --exclude-standard -- backend frontend deploy)"
if [ -n "$UNTRACKED_PAYLOAD" ]; then
  echo "Dev deploy blocked: untracked backend/frontend/deploy source would enter the deployment payload." >&2
  exit 1
fi
if [ "$BRANCH" != "main" ] && [ "${PREPPILOT_DEV_ALLOW_BRANCH:-0}" != "1" ]; then
  echo "Dev deploy blocked: $BRANCH is not main. Set PREPPILOT_DEV_ALLOW_BRANCH=1 for a branch preview." >&2
  exit 1
fi
if [ "$BRANCH" = "main" ]; then
  git -C "$HERE" fetch origin main --quiet
  if [ "$(git -C "$HERE" rev-parse HEAD)" != "$(git -C "$HERE" rev-parse origin/main)" ]; then
    echo "Dev deploy blocked: local main must match origin/main." >&2
    exit 1
  fi
fi

echo "==> 0/6  Attesting preserved isolated development storage"
ssh "$MINI" '
  set -e
  test -f ~/prep-pilot-dev/backend/.env
  python3 - --backend "$HOME/prep-pilot-dev/backend" --env-file "$HOME/prep-pilot-dev/backend/.env"
' < "$HERE/deploy/check-dev-storage.py" || {
  echo "Dev deploy blocked: preserved development storage isolation attestation failed." >&2
  exit 1
}

echo "==> 1/6  Building dev revision $SHA ($BRANCH)"
( cd "$HERE/frontend" && npm install --silent && npm run build )

echo "==> 2/6  Syncing isolated code to mini (~/$REMOTE_DIR)"
ssh "$MINI" "mkdir -p ~/$REMOTE_DIR/backend ~/$REMOTE_DIR/frontend/dist"
rsync -az --delete \
  --exclude '.venv' --exclude '__pycache__' --exclude 'data' --exclude '.env' \
  "$HERE/backend/" "$MINI:~/$REMOTE_DIR/backend/"
rsync -az --delete "$HERE/frontend/dist/" "$MINI:~/$REMOTE_DIR/frontend/dist/"

echo "==> 3/6  Ensuring uv is installed on the mini"
ssh "$MINI" 'test -x ~/.local/bin/uv || curl -LsSf https://astral.sh/uv/install.sh | sh'

echo "==> 4/6  Installing dev dependencies"
ssh "$MINI" "cd ~/$REMOTE_DIR/backend && ~/.local/bin/uv sync"

echo "==> 5/6  Installing isolated dev LaunchAgent"
HOME_REMOTE=$(ssh "$MINI" 'echo $HOME')
sed "s#__UV__#$HOME_REMOTE/.local/bin/uv#g; s#__HOME__#$HOME_REMOTE#g; s#__RELEASE__#$SHA#g" \
  "$HERE/deploy/com.preppilot.dev.plist" | \
  ssh "$MINI" "cat > ~/Library/LaunchAgents/com.preppilot.dev.plist"
ssh "$MINI" '
  launchctl unload ~/Library/LaunchAgents/com.preppilot.dev.plist 2>/dev/null || true
  launchctl load ~/Library/LaunchAgents/com.preppilot.dev.plist
  sleep 4
  HEALTH=$(curl -sf http://127.0.0.1:'"$APP_PORT"'/api/health) || {
    echo "dev not healthy (check ~/Library/Logs/preppilot-dev.log)" >&2
    exit 1
  }
  printf "%s" "$HEALTH" | python3 -c "import json,sys; d=json.load(sys.stdin); assert d.get(\"environment\") == \"development\" and d.get(\"scheduler_enabled\") is False and d.get(\"dev_database_isolated\") is True and d.get(\"dev_book_storage_isolated\") is True" || {
    echo "dev isolation health attestation failed" >&2
    exit 1
  }
  echo "isolated dev health attestations passed"
'

echo "==> 6/6  Exposing dev over Tailscale HTTPS :$SERVE_PORT"
ssh "$MINI" "$TS serve --bg --https=$SERVE_PORT http://127.0.0.1:$APP_PORT"
DOMAIN=$(ssh "$MINI" "$TS status --json" | python3 -c "import sys,json;print(json.load(sys.stdin)['Self']['DNSName'].rstrip('.'))")

echo
echo "==> Dev ready: https://$DOMAIN:$SERVE_PORT"
echo "    Revision: $SHA ($BRANCH)"
echo "    Data, cookies, scheduler, process, logs, and database are isolated from production."
