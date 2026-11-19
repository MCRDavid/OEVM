#!/usr/bin/env bash
# Download one artifact of a workflow run into a folder, trying again if GitHub's
# artifact storage fails for a moment.
#
#   .github/scripts/download-run-artifact.sh <run id> <artifact name> <folder>
#
# GitHub's artifact storage answered "HTTP 503: 503 Egress is over the account limit."
# to a download at 16:30 UTC on 16 and on 19 November 2026, failing a status refresh each
# time, while GitHub's status page showed no incident. So a failed download is tried
# twice more, after 30 and then 60 seconds (DOWNLOAD_RETRY_WAITS, in seconds, for tests).
# Each try goes to a new empty folder, so a half-made download is never mixed with a
# later one. Needs GH_TOKEN and GH_REPO, and "actions: read" permission.
set -euo pipefail

run_id="$1"
name="$2"
dest="$3"
read -r -a waits <<< "${DOWNLOAD_RETRY_WAITS:-30 60}"
mkdir -p "$dest"

attempt=0
while true; do
  attempt=$((attempt + 1))
  try=$(mktemp -d)
  if gh run download "$run_id" --name "$name" --dir "$try"; then
    cp -a "$try/." "$dest/"
    rm -rf "$try"
    exit 0
  fi
  rm -rf "$try"
  if [ "$attempt" -gt "${#waits[@]}" ]; then
    echo "::error::Could not download $name from workflow run $run_id after $attempt tries."
    exit 1
  fi
  wait="${waits[$((attempt - 1))]}"
  echo "::warning::Downloading $name from workflow run $run_id failed; trying again in $wait s."
  sleep "$wait"
done
