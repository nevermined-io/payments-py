"""Regression tests for `.github/scripts/update-dependabot-branches.sh`.

The workflow that calls it (`.github/workflows/dependabot-update-branches.yml`)
triggers on a push to `main`, so it cannot be exercised before it merges and no
CI run can tell you whether a change to it works. That is not a hypothetical
worry for this particular script: the `payments` copy it was ported from
shipped calling `--method POST` on a PUT endpoint, 404'd on all 21 open PRs,
and reported a green job (nevermined-io/payments#449).

These tests are therefore the only pre-merge cover the selection, ordering,
status handling and cap get. They run the real script with a stubbed `gh` on
PATH, so they fail if any of those behaviours is deleted.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / ".github" / "scripts" / "update-dependabot-branches.sh"

# `gh pr list` is stubbed to print $STUB_PRS_JSON, or to fail like a real
# auth/API error when $STUB_LIST_FAILS is set. `gh api` records the branch of
# every merge call and answers based on the branch name, which is how a test
# chooses the 201/204/409/500 path per PR.
GH_STUB = """#!/usr/bin/env bash
if [ "$1" = "pr" ] && [ "$2" = "list" ]; then
  if [ -n "${STUB_LIST_FAILS:-}" ]; then
    echo "gh: HTTP 401: Bad credentials" >&2
    exit 1
  fi
  printf '%s' "$STUB_PRS_JSON"
  exit 0
fi
if [ "$1" = "api" ]; then
  branch=""
  for a in "$@"; do
    case "$a" in base=*) branch="${a#base=}";; esac
  done
  echo "$branch" >> "$STUB_CALL_LOG"
  case "$branch" in
    *current*)  echo "HTTP/2.0 204 No Content"; exit 0;;
    *conflict*) echo "gh: Merge conflict (HTTP 409)"; exit 1;;
    *boom*)     echo "gh: Internal Server Error (HTTP 500)"; exit 1;;
    *)          echo "HTTP/2.0 201 Created"; exit 0;;
  esac
fi
echo "unexpected gh invocation: $*" >&2
exit 99
"""


def _pr(number, branch, review_decision=""):
    return {
        "number": number,
        "headRefName": branch,
        "reviewDecision": review_decision,
    }


def _run(tmp_path, prs, max_merges=3, list_fails=False, raw_json=None):
    """Run the script with a stubbed `gh`; return (result, merge_call_log).

    `raw_json` replaces the serialised PR list with an arbitrary string, which
    is how the parse-failure cases hand the script a body `jq` cannot read.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(GH_STUB)
    stub.chmod(0o755)

    call_log = tmp_path / "calls.txt"
    call_log.touch()

    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "GH_TOKEN": "stub-token",
        "REPO": "nevermined-io/payments-py",
        "BASE": "main",
        "MAX_MERGES": str(max_merges),
        "STUB_PRS_JSON": json.dumps(prs) if raw_json is None else raw_json,
        "STUB_CALL_LOG": str(call_log),
    }
    if list_fails:
        env["STUB_LIST_FAILS"] = "1"

    result = subprocess.run(
        ["bash", str(SCRIPT)],
        capture_output=True,
        text=True,
        env=env,
    )
    calls = [line for line in call_log.read_text().splitlines() if line]
    return result, calls


pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("jq") is None,
    reason="the sweeper script needs bash and jq",
)


def test_approved_prs_are_served_first(tmp_path):
    """Ordering is load-bearing, not cosmetic.

    A slot spent on an unapproved PR cannot end in a merge, so it cannot
    produce the push to `main` that starts the next wave. The script partitions
    the list itself rather than delegating to `gh --jq` precisely so this test
    can see it: through `--jq` the expression is an argument to the stub and
    the stub's own output would decide the order.
    """
    prs = [
        _pr(1, "dependabot/pip/a"),
        _pr(2, "dependabot/pip/b", "APPROVED"),
        _pr(3, "dependabot/pip/c", "REVIEW_REQUIRED"),
        _pr(4, "dependabot/pip/d", "APPROVED"),
    ]
    result, calls = _run(tmp_path, prs, max_merges=4)

    assert result.returncode == 0, result.stderr
    assert calls == [
        "dependabot/pip/b",
        "dependabot/pip/d",
        "dependabot/pip/a",
        "dependabot/pip/c",
    ]


def test_already_current_branch_does_not_consume_a_merge_slot(tmp_path):
    """A 204 means the branch was already current, so nothing was spent.

    Counting it against `MAX_MERGES` would shrink each wave for no reason,
    and the cap exists to bound concurrent staging E2E runs — of which a 204
    starts none.
    """
    prs = [
        _pr(1, "dependabot/pip/current-a"),
        _pr(2, "dependabot/pip/current-b"),
        _pr(3, "dependabot/pip/c"),
    ]
    result, calls = _run(tmp_path, prs, max_merges=1)

    assert result.returncode == 0, result.stderr
    assert calls == [
        "dependabot/pip/current-a",
        "dependabot/pip/current-b",
        "dependabot/pip/c",
    ]
    assert "PR #1 is already current." in result.stdout
    assert "Merged into 1 branch(es); 0 conflicted." in result.stdout


def test_conflict_warns_and_the_sweep_continues(tmp_path):
    """One conflicted branch must not strand the ones behind it.

    A merge cannot resolve a poetry.lock conflict, so the PR needs a person —
    but the rest of the queue is still servable, and Dependabot PRs go
    conflicting routinely when a sibling lockfile bump lands first.
    """
    prs = [
        _pr(1, "dependabot/pip/conflict-a"),
        _pr(2, "dependabot/pip/b"),
    ]
    result, calls = _run(tmp_path, prs, max_merges=3)

    assert result.returncode == 0, result.stderr
    assert calls == ["dependabot/pip/conflict-a", "dependabot/pip/b"]
    assert "::warning title=Dependabot PR conflicted::PR #1" in result.stdout
    assert "Merged into 1 branch(es); 1 conflicted." in result.stdout


def test_merge_cap_stops_the_wave(tmp_path):
    """`MAX_MERGES` bounds concurrent staging E2E runs, so it must hold."""
    prs = [_pr(n, f"dependabot/pip/{n}") for n in range(1, 7)]
    result, calls = _run(tmp_path, prs, max_merges=2)

    assert result.returncode == 0, result.stderr
    assert calls == ["dependabot/pip/1", "dependabot/pip/2"]
    assert "Reached MAX_MERGES=2" in result.stdout
    assert "Merged into 2 branch(es); 0 conflicted." in result.stdout


def test_unexpected_api_error_fails_the_job(tmp_path):
    """Anything that is not 201/204/409 is unclassified and must be loud."""
    result, calls = _run(tmp_path, [_pr(1, "dependabot/pip/boom")], max_merges=3)

    assert result.returncode == 1
    assert calls == ["dependabot/pip/boom"]
    assert "::error title=Branch merge failed::PR #1" in result.stdout


def test_empty_pr_list_is_a_clean_no_op(tmp_path):
    result, calls = _run(tmp_path, [], max_merges=3)

    assert result.returncode == 0, result.stderr
    assert calls == []
    assert "No open Dependabot PRs found." in result.stdout


def test_list_failure_fails_the_job(tmp_path):
    """A failed enumeration must not read as an empty one.

    Before review this was a bare `prs=$(gh pr list ...)` with no `set -e`: the
    substitution yielded "" on a 401 and the job printed "No open Dependabot
    PRs found." and exited 0 — green, having swept nothing. Same shape as the
    `--method POST` bug the script's header documents, which is why it is
    guarded rather than left as a style note.
    """
    result, calls = _run(tmp_path, [], max_merges=3, list_fails=True)

    assert result.returncode == 1
    assert calls == []
    assert "::error title=Could not list Dependabot PRs" in result.stdout
    assert "No open Dependabot PRs found." not in result.stdout


def test_malformed_json_fails_the_job(tmp_path):
    """A body `jq` cannot parse must not read as an empty queue.

    `gh pr list` exiting 0 is not on its own evidence that it returned a PR
    list. Without this guard a truncated body makes `jq` exit 5, `prs` come out
    empty, and the job print "No open Dependabot PRs found." and exit 0 — the
    same silent green as the `gh pr list` failure next door, reached by a
    different route, and not covered by that test because the stub always emits
    well-formed JSON.
    """
    result, calls = _run(tmp_path, [], raw_json='[{"number": 1, "headRefName"')

    assert result.returncode == 1
    assert calls == []
    assert "::error title=Could not parse the PR list" in result.stdout
    assert "No open Dependabot PRs found." not in result.stdout


def test_empty_response_body_fails_the_job(tmp_path):
    """`--json` always yields at least `[]`, so an empty body is a malfunction.

    It needs its own guard because `jq` does not distinguish it from an empty
    array: measured, `printf '' | jq -r '.[]'` exits 0 and prints nothing, so
    the parse guard above cannot catch this one.
    """
    result, calls = _run(tmp_path, [], raw_json="")

    assert result.returncode == 1
    assert calls == []
    assert "::error title=Empty response from gh pr list" in result.stdout
    assert "No open Dependabot PRs found." not in result.stdout
