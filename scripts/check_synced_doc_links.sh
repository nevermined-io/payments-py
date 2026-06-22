#!/usr/bin/env bash
#
# check_synced_doc_links.sh — replicate the docs-site sync, then run the real
# Mintlify link checker against the staged site.
#
# Why staged against the real site, not in-repo: the release pipeline
# (publish-mintlify-docs.yml) converts docs/api/NN-*.md into
# docs/api-reference/python/<slug>.mdx via scripts/convert_to_mintlify.py and
# opens a PR against nevermined-io/docs. A plain mkdocs build here would PASS and
# miss site-only breakage, because relative links resolve differently once the
# files live under api-reference/python/ on the site (this broke
# nevermined-io/docs#234, the v1.15.0 sync).
#
# Unlike the TypeScript sibling (payments#401), the Python pages legitimately
# link to OTHER docs-site sections via site-relative paths (e.g.
# /docs/integrate/add-to-your-agent/langchain). Those resolve only against the
# *whole* site, so a self-contained mini-site of just the 13 python pages would
# false-positive on the clean tree. We therefore clone the real (public)
# nevermined-io/docs, drop the freshly-converted pages into
# docs/api-reference/python/, and run `mintlify broken-links` on the whole site.
#
# Hard-gates INTERNAL links only: `mintlify broken-links` checks internal links
# by default and only pings external URLs with --check-external (NOT passed —
# external liveness is network-flaky and must not block a release).
#
# Scoped to OUR breakage: the whole site may carry pre-existing broken links we
# don't own. We replace ALL python pages with freshly-converted ones, so any
# broken link whose SOURCE file is under docs/api-reference/python/ is breakage
# introduced by these staged pages. We parse the checker output and fail ONLY on
# python-sourced broken links — pre-existing breakage elsewhere on the site does
# not fail this gate. (See the scoped-parse step at the end of this script.)
#
# Env knobs (all optional):
#   DOCS_REPO       default nevermined-io/docs_mintlify
#   DOCS_REF        default main
#   MINTLIFY_VERSION default 4.2.629 (pin; the docs repo tracks latest)
#   DOCS_CHECKOUT   pre-cloned docs repo to reuse instead of cloning
#   SCOPE_PREFIX    site path whose broken links we own (default the python tree)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/docs/api"

# Canonical docs-site repo. Matches the publish-mintlify-docs.yml convention
# (it checks out nevermined-io/docs_mintlify); GitHub redirects the alias to the
# current name, so cloning works either way.
DOCS_REPO="${DOCS_REPO:-nevermined-io/docs_mintlify}"
DOCS_REF="${DOCS_REF:-main}"
# Pin Mintlify for reproducibility. The docs repo itself installs floating
# latest (npm i -g mintlify); bump this when that materially changes.
MINTLIFY_VERSION="${MINTLIFY_VERSION:-4.2.629}"
# Broken links whose source file starts with this site path are ours to fix.
SCOPE_PREFIX="${SCOPE_PREFIX:-docs/api-reference/python/}"

if [ ! -d "$SOURCE_DIR" ]; then
  echo "Error: source docs not found at $SOURCE_DIR" >&2
  exit 1
fi

WORK_DIR="$(mktemp -d)"
cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

# 1. Convert docs/api/*.md -> *.mdx with the SAME transform the release bot uses.
STAGED_MDX="$WORK_DIR/converted"
mkdir -p "$STAGED_MDX"
echo "Converting docs/api/** with scripts/convert_to_mintlify.py …"
python3 "$SCRIPT_DIR/convert_to_mintlify.py" \
  --source "$SOURCE_DIR" --target "$STAGED_MDX" --verbose

# 2. Obtain the docs site (clone the public repo, or reuse a provided checkout).
if [ -n "${DOCS_CHECKOUT:-}" ]; then
  echo "Reusing docs checkout at $DOCS_CHECKOUT"
  DOCS_DIR="$WORK_DIR/docs-site"
  cp -r "$DOCS_CHECKOUT" "$DOCS_DIR"
else
  DOCS_DIR="$WORK_DIR/docs-site"
  echo "Cloning $DOCS_REPO@$DOCS_REF (shallow) …"
  git clone --depth 1 --branch "$DOCS_REF" \
    "https://github.com/$DOCS_REPO.git" "$DOCS_DIR"
fi

# Fail closed if the Mintlify project config is missing: `mintlify broken-links`
# silently no-ops to exit 0 when run with no docs.json/mint.json at its root, so
# without this assertion a docs-site layout change would make the gate pass
# vacuously (symmetric to the api-reference/python guard below).
if [ ! -f "$DOCS_DIR/docs.json" ] && [ ! -f "$DOCS_DIR/mint.json" ]; then
  echo "Error: no docs.json/mint.json at $DOCS_DIR — docs-site layout changed?" >&2
  exit 1
fi

TARGET_DIR="$DOCS_DIR/docs/api-reference/python"
if [ ! -d "$TARGET_DIR" ]; then
  echo "Error: $DOCS_REPO has no docs/api-reference/python — site layout changed?" >&2
  exit 1
fi

# 3. Replace the python pages with the freshly-converted ones (mirror the bot:
#    rm old *.mdx, copy new). Other sections stay so site-relative links resolve.
rm -f "$TARGET_DIR"/*.mdx
cp "$STAGED_MDX"/*.mdx "$TARGET_DIR/"
echo "Staged $(find "$TARGET_DIR" -name '*.mdx' | wc -l) python page(s) into the site."

# 4. Resolve a runnable, pinned mintlify. CI uses the globally-installed CLI when
#    it already matches the pin; otherwise fall back to a pinned npx invocation.
if command -v mintlify >/dev/null 2>&1 \
   && [ "$(mintlify --version 2>/dev/null)" = "$MINTLIFY_VERSION" ]; then
  MINTLIFY=(mintlify)
else
  MINTLIFY=(npx --yes "mintlify@$MINTLIFY_VERSION")
fi

echo "Running mintlify@$MINTLIFY_VERSION broken-links (internal links only) on the staged site …"
echo ""
cd "$DOCS_DIR"

# Capture the full report (strip ANSI/spinner CRs), then scope to our pages.
# Do not let mintlify's own non-zero exit abort the script — we decide pass/fail
# from the SCOPED parse, since pre-existing site breakage must not fail us.
REPORT="$WORK_DIR/broken-links.txt"
set +e
"${MINTLIFY[@]}" broken-links 2>&1 | sed 's/\x1b\[[0-9;]*[A-Za-z]//g' | tr -d '\r' > "$REPORT"
# The pipe's exit status is tr's (always 0), so grab mintlify's REAL exit code
# from PIPESTATUS — used below to fail closed if mintlify crashed without
# producing a parseable report.
mintlify_rc="${PIPESTATUS[0]}"
set -e

cat "$REPORT"
echo ""

# Parse the report and fail ONLY on broken links sourced from our staged pages.
# Output shape (one source block per file with broken links):
#   docs/api-reference/python/a2a-module.mdx
#    ⎿  ../../payments_py/x402/README.md
SCOPE_PREFIX="$SCOPE_PREFIX" MINTLIFY_RC="$mintlify_rc" python3 - "$REPORT" <<'PY'
import os, re, sys

prefix = os.environ["SCOPE_PREFIX"]
source_re = re.compile(r"^(\S+\.mdx)\s*$")
broken_re = re.compile(r"^\s*⎿\s+(.+?)\s*$")
# Header the checker prints, e.g. "found 2 broken links in 2 files".
header_re = re.compile(r"found\s+(\d+)\s+broken\s+links?\b")

reported = None  # broken-link count from the checker's own summary line
total = 0  # broken links our parser attributed to ANY source file
scoped, current = [], None
with open(sys.argv[1], encoding="utf-8") as fh:
    for line in fh:
        line = line.rstrip("\n")
        h = header_re.search(line)
        if h:
            reported = int(h.group(1))
            continue
        m = source_re.match(line)
        if m:
            current = m.group(1)
            continue
        b = broken_re.match(line)
        if b and current:
            total += 1
            if current.startswith(prefix):
                scoped.append((current, b.group(1)))

# Fail-closed guard: a non-zero mintlify exit with no broken-links header means
# mintlify did not actually run (npx install failure, exec error, OOM) rather
# than "ran and found links". Without this, an empty report → reported=None →
# total==0 → the script would print "✓ no broken links" and exit 0 (fail-OPEN).
# This is the sibling of the missing-docs.json / empty-dir / format-drift guards.
rc = int(os.environ["MINTLIFY_RC"])
if rc != 0 and reported is None:
    print(
        f"✗ mintlify broken-links produced no parseable report (exit {rc}) — "
        "it likely failed to run. Failing closed.",
        file=sys.stderr,
    )
    sys.exit(2)

# False-green guard: the checker reported broken links but our parser attributed
# none to any source — the output format drifted (e.g. a mintlify bump changed
# the glyph/layout). Fail loudly rather than pass silently on an unparsed report.
if reported and reported > 0 and total == 0:
    print(
        "✗ mintlify reported broken links but this script parsed none — the "
        "broken-links output format has likely changed. Update the parser in "
        "scripts/check_synced_doc_links.sh (the source/⎿ line patterns).",
        file=sys.stderr,
    )
    sys.exit(2)

if scoped:
    print(f"✗ {len(scoped)} broken internal link(s) introduced by the staged "
          f"pages ({prefix}):")
    for src, target in scoped:
        print(f"  {src} -> {target}")
    print("\nThese links resolve in-repo but are dead on the docs site. Use a "
          "chapter link the converter rewrites, a site-relative /docs/... path, "
          "or an absolute https://github.com/... URL. See CONTRIBUTING.md.")
    sys.exit(1)

print(f"✓ No broken internal links sourced from the staged pages ({prefix}).")
PY
