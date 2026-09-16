#!/usr/bin/env bash
#
# Merges $BASE into the open Dependabot branches so their CI re-runs against the
# branch they will actually land on. Called by
# .github/workflows/dependabot-update-branches.yml; see that file's header for
# why this repository runs it and what it does NOT guarantee.
#
# It lives in a file rather than inline in the workflow so it can be tested:
# `tests/unit/test_dependabot_sweeper.py` drives it with a stubbed `gh` on
# PATH. The workflow cannot be exercised pre-merge (its trigger is a push to
# `main`), so that suite is the only pre-merge check on this logic.
#
# Environment:
#   GH_TOKEN    token `gh` authenticates with
#   REPO        owner/name
#   BASE        branch to merge FROM, i.e. the default branch
#   MAX_MERGES  cap on merges performed per run
#
# Requires `gh` and `jq`, both preinstalled on ubuntu-latest runners.

set -uo pipefail

# Deliberately NOT `set -e`. The merge loop distinguishes three outcomes per PR
# — merged, already current, conflicted — from a fourth that must fail the job,
# and it does so by inspecting exit status itself. Under `set -e` the first
# conflict would end the run instead.

: "${GH_TOKEN:?GH_TOKEN is required}"
: "${REPO:?REPO is required}"
: "${BASE:?BASE is required}"
: "${MAX_MERGES:?MAX_MERGES is required}"

err_file=$(mktemp)
trap 'rm -f "$err_file"' EXIT

# History, so the next reader does not redo it:
#
# - This shipped on `payments` calling `--method POST` on
#   /pulls/{n}/update-branch, which is a PUT endpoint. Every call 404'd and a
#   trailing `|| echo "skipped"` printed that as a benign line under a green
#   job, so no branch was ever updated (run 34743328585, 2026-09-13: all 21
#   open PRs 404; output quoted in nevermined-io/payments#449).
# - Commenting `@dependabot rebase` would be the better mechanism — Dependabot
#   regenerates the lockfile conflicts a merge cannot — but it refuses commands
#   from GitHub App identities ("Sorry, only users with push access can use
#   that command", dependabot/dependabot-core#9147, open). This job runs as the
#   release bot, so its comment would be ignored while `gh pr comment` still
#   exits 0.
# - `PUT /pulls/{n}/update-branch` works, but answers 202: the merge is queued,
#   so confirming it meant polling `compare/{base}...{head}`, and that compare
#   races a moving `main` — a push landing inside the window makes a branch
#   that *was* updated read as still behind.
#
# `POST /repos/{owner}/{repo}/merges` avoids all three. It is synchronous,
# App-enabled, and takes `commit_message`, which matters: "Dependabot will stop
# rebasing a pull request once extra commits have been pushed to it", unless the
# message carries `[dependabot skip]` (or `[skip dependabot]`,
# `[dependabot-skip]`, `[skip-dependabot]`). So the marker is meant to keep
# Dependabot's own rebase — the thing that regenerates a conflicted lockfile —
# alive on branches this job has touched. Two limits on that claim:
#
# - It does not lift the other cutoff in the same docs section: "If a pull
#   request has not been merged for 30 days, Dependabot will stop rebasing the
#   pull request."
# - Whether Dependabot honours it on an App-authored commit is documented
#   nowhere, and no run of this job can tell you: a run only shows the commit
#   landing with the marker in its message. It is observable only when
#   Dependabot next tries to rebase such a branch, which nothing here watches.
#   If it turns out to be ignored, the loss is silent — touched PRs strand at
#   their first conflict and the warning below becomes the steady state rather
#   than the exception.
#
# Measured against the real API on `payments` on 2026-09-14:
#   201 Created  — #356, commit 8dbd041 carrying the marker verbatim
#   204 No Content — same call repeated, branch already current
#   409 Merge conflict — #39, which is DIRTY
echo "Looking for open Dependabot PRs..."

# The failure of this call must fail the job. Before review it was a bare
# `prs=$(gh pr list ...)`: `gh` writes its error to stderr and exits non-zero,
# the command substitution yields the empty string, and with no `set -e` the
# next branch printed "No open Dependabot PRs found." and exited 0 — a green
# job reporting a successful sweep of nothing. That is the same shape as the
# `--method POST` bug above, which is what made it worth a guard rather than a
# style note. `test_list_failure_fails_the_job` holds it.
if ! prs_json=$(gh pr list \
  --repo "$REPO" \
  --state open \
  --search "author:app/dependabot sort:updated-asc" \
  --limit 100 \
  --json number,headRefName,reviewDecision 2>"$err_file"); then
  echo "::error title=Could not list Dependabot PRs::gh pr list failed: $(cat "$err_file")"
  exit 1
fi

# Approved first, least-recently-updated within each half. A slot spent on a PR
# nobody has approved buys nothing: it cannot merge, so it cannot produce the
# push that starts the next wave. Serving the approved ones first means every
# wave that has one ends in a merge.
#
# Applied here rather than passed to `gh --jq` so that a test can exercise it:
# through `--jq` the ordering is an argument to the stub and the stub's own
# output decides the order, so deleting the expression would not fail anything.
if ! prs=$(printf '%s' "$prs_json" | jq -r '
      [.[] | select(.reviewDecision == "APPROVED")]
      + [.[] | select(.reviewDecision != "APPROVED")]
      | .[] | "\(.number) \(.headRefName)"' 2>"$err_file"); then
  echo "::error title=Could not parse the PR list::jq failed: $(cat "$err_file")"
  exit 1
fi

if [ -z "$prs" ]; then
  echo "No open Dependabot PRs found."
  exit 0
fi

# Least-recently-updated first, which is what makes the queue drain. A fixed
# order — by number, by creation date — feeds run N+1 the same head of the list
# as run N and never reaches the tail. A merge bumps that PR's updatedAt and
# sends it to the back: round-robin.
merged=0
conflicted=0
while read -r pr branch; do
  if [ -z "$pr" ]; then
    continue
  fi

  if [ "$merged" -ge "$MAX_MERGES" ]; then
    echo "Reached MAX_MERGES=$MAX_MERGES; the rest wait for the next run."
    break
  fi

  # -i so the 204 (already current) is distinguishable from the 201.
  if out=$(gh api -i \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    "/repos/$REPO/merges" \
    -f base="$branch" \
    -f head="$BASE" \
    -f commit_message="Merge $BASE into $branch to satisfy strict status checks [dependabot skip]" 2>&1); then
    case "$out" in
      *"HTTP/2.0 204"*|*"HTTP/1.1 204"*)
        echo "PR #$pr is already current."
        continue;;
    esac
    echo "PR #$pr updated."
    merged=$((merged + 1))
    continue
  fi

  case "$out" in
    *"Merge conflict"*)
      # A merge cannot resolve a poetry.lock conflict. The marker on this job's
      # earlier commits keeps Dependabot's own rebase available, but a conflict
      # it has already given up on needs a person.
      echo "::warning title=Dependabot PR conflicted::PR #$pr ($branch) — comment '@dependabot recreate' from a user account"
      conflicted=$((conflicted + 1))
      continue;;
  esac

  echo "::error title=Branch merge failed::PR #$pr ($branch): $out"
  exit 1
done <<EOF
$prs
EOF

echo "Merged into $merged branch(es); $conflicted conflicted."
