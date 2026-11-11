#!/usr/bin/env bash
# Sync both GitHub (origin) and GitLab (gitlab) remotes for the current branch
# Usage: ./scripts/sync_gitlab.sh [branch]
# If no branch is supplied, the current checked‑out branch is used.

set -euo pipefail

BRANCH=${1:-$(git rev-parse --abbrev-ref HEAD)}

echo "Synchronising branch '$BRANCH' to both remotes..."

git push origin "$BRANCH"
git push gitlab "$BRANCH"

echo "✅ Done. Both origin and gitlab now have branch '$BRANCH'."
