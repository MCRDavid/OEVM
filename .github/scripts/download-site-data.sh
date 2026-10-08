#!/usr/bin/env bash
# Download the newest "site-data" artifact made on main by the Fetch daily workflow.
#
#   .github/scripts/download-site-data.sh <folder> [--required]
#
# The artifact holds the published map files (data/) and feed health page (status/).
# Needs GH_TOKEN and GH_REPO, and "actions: read" permission. With --required, finding
# no artifact is an error; without it, the folder is left empty and the script succeeds.
set -euo pipefail

dest="$1"
required="${2:-}"
mkdir -p "$dest"

run_id=$(gh api "repos/$GH_REPO/actions/artifacts?name=site-data&per_page=30" \
  --jq '[.artifacts[] | select(.expired == false and .workflow_run.head_branch == "main")][0].workflow_run.id // empty')

if [ -z "$run_id" ]; then
  if [ "$required" = "--required" ]; then
    echo "::error::No map files have been published yet. Run the Fetch daily workflow first."
    exit 1
  fi
  echo "No earlier site data found; starting without it."
  exit 0
fi

echo "Using the site data from workflow run $run_id."
gh run download "$run_id" --name site-data --dir "$dest"
