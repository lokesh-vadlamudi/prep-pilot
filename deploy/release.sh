#!/usr/bin/env bash
# Tag the current origin/main revision and deploy that exact tag to production.
set -euo pipefail

TAG="${1:-}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"

if ! [[ "$TAG" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Usage: $0 vMAJOR.MINOR.PATCH" >&2
  exit 1
fi
if [ "$(git -C "$HERE" branch --show-current)" != "main" ]; then
  echo "Release blocked: switch to main first." >&2
  exit 1
fi
if ! git -C "$HERE" diff --quiet || ! git -C "$HERE" diff --cached --quiet; then
  echo "Release blocked: tracked files must be clean." >&2
  exit 1
fi

git -C "$HERE" fetch origin main --tags --quiet
if [ "$(git -C "$HERE" rev-parse HEAD)" != "$(git -C "$HERE" rev-parse origin/main)" ]; then
  echo "Release blocked: local main must match origin/main." >&2
  exit 1
fi
if git -C "$HERE" rev-parse "$TAG" >/dev/null 2>&1; then
  echo "Release blocked: tag $TAG already exists." >&2
  exit 1
fi

git -C "$HERE" tag -a "$TAG" -m "PrepPilot $TAG"
git -C "$HERE" push origin "$TAG"
RELEASE_TAG="$TAG" bash "$HERE/deploy/deploy.sh"
