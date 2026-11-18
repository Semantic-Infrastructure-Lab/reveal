# Sourced by release.sh and pre-release-check.sh; tested by tests/test_release_checks_back2683.py.
#
# ci_runs and ci_verdict: whether GitHub's Tests passed for a sha (BACK-2683).
# release_test_python: the interpreter of their local test runs (BACK-2684).
#
# Two environment traps made the 0.135.0 preflight report 11 failures on a tree GitHub had passed:
# an exported PYTHONPATH put another project's tests/conftest.py ahead of reveal's, and the
# python3 on PATH lacked the dev extras (hatchling and editables for the BACK-2575 build oracle).
# The suite runs as ci-local.sh runs it: PYTHONPATH unset, on ci-local's 3.12 venv, which installs
# the dev extras. REVEAL_TEST_PYTHON names another interpreter; python3 is the last resort.

# Print the interpreter for the release test run, or fail naming what is missing.
release_test_python() {
    local py="${REVEAL_TEST_PYTHON:-${REVEAL_CI_VENV_ROOT:-$HOME/.cache/reveal-ci}/py3.12/bin/python}"
    [ -x "$py" ] || py="$(command -v python3)"
    if ! "$py" -c 'import pytest, pytest_cov, xdist, hatchling, editables' 2>/dev/null; then
        echo "release tests need reveal's dev extras in $py: run scripts/ci-local.sh once," \
             "set REVEAL_TEST_PYTHON, or $py -m pip install -e '.[dev]'" >&2
        return 1
    fi
    echo "$py"
}

# List a commit's Tests runs as ci_verdict reads them. One sha usually has several: its ci/** branch
# run, then the master fast-forward's (BACK-2590), and a superseded push leaves a cancelled one.
ci_runs() {
    gh run list --workflow test.yml --commit "$1" -L 100 --json databaseId,headBranch,status,conclusion \
        --jq '.[] | "\(.databaseId) \(.headBranch) \(.status) \(.conclusion)"'
}

# Judge a commit's Tests runs, one "ID BRANCH STATUS CONCLUSION" line each (BACK-2683). The newest
# run alone can still be queued while an older one on the same sha passed, so every run counts. Prints
# "failed RUNS" if any completed run failed, else "green RUN" for a completed success, else
# "pending RUNS" while runs are still going, else "none". A cancelled or skipped run (a superseded
# push) is neither green nor red.
ci_verdict() {
    local id branch status conclusion green="" failed="" pending=""
    while read -r id branch status conclusion; do
        [ -n "$id" ] || continue
        if [ "$status" != "completed" ]; then
            pending+="${pending:+, }$id ($branch, $status)"
            continue
        fi
        case "$conclusion" in
            success) green="${green:-$id ($branch)}" ;;
            cancelled|skipped|neutral) ;;
            *) failed+="${failed:+, }$id ($branch, $conclusion)" ;;
        esac
    done
    if [ -n "$failed" ]; then echo "failed $failed"
    elif [ -n "$green" ]; then echo "green $green"
    elif [ -n "$pending" ]; then echo "pending $pending"
    else echo "none"
    fi
}

unset PYTHONPATH
