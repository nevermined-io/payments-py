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
# Env knobs (all optional):
#   DOCS_REPO       default nevermined-io/docs
#   DOCS_REF        default main
#   MINTLIFY_VERSION default 4.2.629 (pin; the docs repo tracks latest)
#   DOCS_CHECKOUT   pre-cloned docs repo to reuse instead of cloning
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/docs/api"

DOCS_REPO="${DOCS_REPO:-nevermined-io/docs}"
DOCS_REF="${DOCS_REF:-main}"
# Pin Mintlify for reproducibility. The docs repo itself installs floating
# latest (npm i -g mintlify); bump this when that materially changes.
MINTLIFY_VERSION="${MINTLIFY_VERSION:-4.2.629}"

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
# Exits non-zero when it finds broken internal links.
"${MINTLIFY[@]}" broken-links
