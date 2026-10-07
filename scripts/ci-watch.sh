#!/usr/bin/env bash
# Wait for the GitHub "Tests" run of a commit, then report every job and, for each failed
# job, the pytest failures from its log. Exit 0 when the run is green, 1 when it is not.
#
# Usage:
#   scripts/ci-watch.sh              # the run for HEAD
#   scripts/ci-watch.sh <sha>        # the run for another pushed commit
#   scripts/ci-watch.sh --no-wait    # report the run's current state and exit
#
# Run it right after a push (in tmux if your shell caps foreground time) and keep working.
# It reads jobs through `gh api .../runs/<id>/jobs` because `gh run view --json jobs` is
# not available in every gh build, and a monitor polling it stays silent.
set -euo pipefail

WAIT=1
SHA=""
for arg in "$@"; do
    case "$arg" in
        --no-wait) WAIT=0 ;;
        -h|--help) awk 'NR > 1 && /^#/ { sub(/^# ?/, ""); print; next } NR > 1 { exit }' "$0"; exit 0 ;;
        *) SHA="$arg" ;;
    esac
done
SHA="$(git rev-parse "${SHA:-HEAD}")"
POLL="${CI_WATCH_POLL:-30}"
API='repos/{owner}/{repo}/actions'

run_id=""
for _ in $(seq 1 20); do  # a just-pushed commit takes a few seconds to get a run
    run_id="$(gh api "$API/workflows/test.yml/runs?head_sha=$SHA&per_page=1" --jq '.workflow_runs[0].id // empty')"
    [[ -n "$run_id" || $WAIT -eq 0 ]] && break
    sleep 10
done
[[ -n "$run_id" ]] || { echo "no Tests run for ${SHA:0:8} (pushed?)" >&2; exit 2; }
echo "Tests run $run_id for ${SHA:0:8}"

while :; do
    status="$(gh api "$API/runs/$run_id" --jq '.status')"
    [[ "$status" == "completed" || $WAIT -eq 0 ]] && break
    done_jobs="$(gh api "$API/runs/$run_id/jobs?per_page=50" --jq '[.jobs[] | select(.status == "completed")] | length')"
    total_jobs="$(gh api "$API/runs/$run_id/jobs?per_page=50" --jq '.jobs | length')"
    printf '%s  %s/%s jobs done\n' "$(date +%H:%M:%S)" "$done_jobs" "$total_jobs"
    sleep "$POLL"
done

conclusion="$(gh api "$API/runs/$run_id" --jq '.conclusion // .status')"
gh api "$API/runs/$run_id/jobs?per_page=50" \
    --jq '.jobs[] | "\(.conclusion // .status)\t\(.name)\t\(((.completed_at // .started_at) | fromdate) - (.started_at | fromdate))s"' \
    | sort | column -t -s $'\t'

failed_jobs="$(gh api "$API/runs/$run_id/jobs?per_page=50" --jq '.jobs[] | select(.conclusion == "failure") | "\(.id)\t\(.name)"')"
if [[ -n "$failed_jobs" ]]; then
    while IFS=$'\t' read -r job_id name; do
        printf '\n== %s (job %s)\n' "$name" "$job_id"
        # Strip the timestamp column; keep pytest's FAILED/ERROR lines and its summary line.
        gh api "$API/jobs/$job_id/logs" 2>/dev/null | sed -E 's/^[0-9TZ:.-]+ //' \
            | grep -E '^(FAILED|ERROR) |^=+ .*(failed|error).* in [0-9.]+s|^##\[error\]' | sort -u | head -40 || true
    done <<< "$failed_jobs"
fi

printf '\nRun %s: %s  https://github.com/%s/actions/runs/%s\n' "$run_id" "$conclusion" \
    "$(gh repo view --json nameWithOwner --jq .nameWithOwner)" "$run_id"
[[ "$conclusion" == "success" ]]
