#!/usr/bin/env bash
# Download the newest "live-data" artifact made on main by the Refresh statuses workflow.
#
#   .github/scripts/download-live-data.sh <folder>
#
# The artifact holds the statuses a refresh read (live/<operator>.json) and its record
# (live/refresh.json). Needs GH_TOKEN and GH_REPO, and "actions: read" permission. Finding
# no artifact is not an error: the folder is left empty and the script succeeds.
set -euo pipefail

dest="$1"
mkdir -p "$dest"

run_id=$(gh api "repos/$GH_REPO/actions/artifacts?name=live-data&per_page=30" \
  --jq '[.artifacts[] | select(.expired == false and .workflow_run.head_branch == "main")][0].workflow_run.id // empty')

if [ -z "$run_id" ]; then
  echo "No earlier statuses found; starting without them."
  exit 0
fi

echo "Using the statuses from workflow run $run_id."
gh run download "$run_id" --name live-data --dir "$dest"
