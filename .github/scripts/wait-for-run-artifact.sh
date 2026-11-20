#!/usr/bin/env bash
# Wait until GitHub lists an artifact of a workflow run, so a step that looks it up can
# find it.
#   .github/scripts/wait-for-run-artifact.sh <run id> <artifact name>
# On 19 and 20 November 2026 GitHub Pages' deploy step found no "github-pages" artifact
# less than a second after the package step had stored it, failing the deploy. So after
# a failed deploy this asks GitHub's API for the run's artifacts until the named one is
# listed: at once, then after each wait in ARTIFACT_LIST_WAITS (in seconds, for tests;
# about 5 minutes in all). Needs GH_TOKEN and GH_REPO, and "actions: read" permission.
set -euo pipefail

run_id="$1"
name="$2"
read -r -a waits <<< "${ARTIFACT_LIST_WAITS:-15 15 30 30 60 60 90}"

attempt=0
while true; do
  attempt=$((attempt + 1))
  listed=$(gh api "repos/$GH_REPO/actions/runs/$run_id/artifacts?per_page=100" \
    --jq "[.artifacts[] | select(.name == \"$name\" and .expired == false)] | length" || echo 0)
  if [ "${listed:-0}" -gt 0 ]; then
    echo "GitHub lists $name for workflow run $run_id (try $attempt)."
    exit 0
  fi
  if [ "$attempt" -gt "${#waits[@]}" ]; then
    echo "::error::GitHub still does not list $name for workflow run $run_id after $attempt tries."
    exit 1
  fi
  wait="${waits[$((attempt - 1))]}"
  echo "GitHub does not list $name for workflow run $run_id yet; asking again in $wait s."
  sleep "$wait"
done
