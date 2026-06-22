#!/usr/bin/env python3
"""Cheap, deterministic, network-free escaping-link lint for docs/api/**.

The release pipeline (`publish-mintlify-docs.yml`) converts every
``docs/api/NN-*.md`` into ``docs/api-reference/python/<slug>.mdx`` on the docs
site via ``scripts/convert_to_mintlify.py``. A link that resolves fine *inside
this repo* — e.g. ``](../../payments_py/x402/README.md)`` — is dead once synced,
because the site has no parent dirs and no repo source. This bit the docs site
once (nevermined-io/docs#234, the v1.15.0 sync of a2a-module.mdx).

This lint rejects exactly that class of relative link, while allowing every
link the converter knows how to rewrite. The set of "convertible" links is read
straight from ``convert_to_mintlify.LINK_MAPPING`` so the lint can never drift
from the transform it is guarding: add a chapter to ``LINK_MAPPING`` and the
lint accepts a relative link to it automatically.

A markdown link in ``docs/api/**`` is FLAGGED when its destination is a
relative path (not an anchor, a site-relative ``/docs/...`` path, or an absolute
URL) that the converter will NOT rewrite — i.e. it escapes the synced tree
(contains a ``/``, including any ``../``) or its basename is not one of the
chapter files in ``LINK_MAPPING``.

It intentionally ALLOWS:
  - convertible chapter links: ``](11-x402.md)``, ``](./11-x402.md#anchor)``
    (basename in LINK_MAPPING, no path separator) — rewritten to the site URL.
  - site-relative paths: ``](/docs/integrate/...)`` — resolve on the site.
  - in-page anchors: ``](#section)``.
  - absolute URLs: ``](https://...)``, ``](mailto:...)``.

Runs in milliseconds, never hits the network, never flakes — the first and
always-on hard gate. Exit code 1 if any violation is found, else 0.
"""

import re
import sys
from pathlib import Path

# Import the converter's link map so this lint stays in lockstep with the
# transform. ``scripts/`` is not a package, so add it to sys.path explicitly.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from convert_to_mintlify import LINK_MAPPING  # noqa: E402

# Chapter files the converter rewrites to clean site URLs (e.g. "11-x402.md").
CONVERTIBLE_BASENAMES = set(LINK_MAPPING.keys())

# Inline markdown link: [text](destination). Captures the raw destination,
# which may carry an optional "title" we discard.
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Reference-style link definition: `[label]: destination "optional title"` at
# line start. The escaping target lives on the definition line (the `[text][ref]`
# usage only names the label), so scanning definitions catches that target.
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+(\S+)")

# HTML anchor: <a href="destination"> (single or double quoted).
HTML_HREF_RE = re.compile(r"""<a\s[^>]*\bhref\s*=\s*["']([^"']+)["']""", re.IGNORECASE)

# Fenced code blocks open/close with ``` or ~~~ (optionally indented). Links
# inside fences are code samples, not navigation — skip them.
FENCE_RE = re.compile(r"^\s*(```|~~~)")

# Destinations that are NOT repo-relative and therefore always fine.
NON_RELATIVE_PREFIXES = ("/", "#", "http://", "https://", "mailto:", "tel:")


def is_violation(destination: str) -> bool:
    """Return True if a link destination would be dead on the docs site."""
    # Drop an optional link title: [x](path "Title") -> "path".
    parts = destination.strip().split()
    if not parts:  # whitespace-only destination — not a real link, ignore.
        return False
    target = parts[0]

    if target.startswith(NON_RELATIVE_PREFIXES):
        return False

    # Normalise: strip a single leading "./" and any "#anchor" fragment.
    if target.startswith("./"):
        target = target[2:]
    target = target.split("#", 1)[0]

    if not target:  # was a bare "#anchor" — same-page link, fine.
        return False

    basename = target.rsplit("/", 1)[-1]

    # Safe iff it stays in the synced tree (no path separator) AND names a
    # chapter the converter rewrites. Everything else escapes or is unmapped.
    return "/" in target or basename not in CONVERTIBLE_BASENAMES


def check_file(path: Path) -> list[tuple[int, str]]:
    """Return [(line_number, destination), ...] for each violating link.

    Scans inline links ``[t](dest)``, reference-style definitions
    ``[ref]: dest``, and HTML ``<a href="dest">`` — skipping fenced code.
    """
    violations: list[tuple[int, str]] = []
    in_fence = False
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        destinations = [m.group(1) for m in LINK_RE.finditer(line)]
        destinations += [m.group(1) for m in HTML_HREF_RE.finditer(line)]
        ref_def = REF_DEF_RE.match(line)
        if ref_def:
            destinations.append(ref_def.group(1))
        for destination in destinations:
            if is_violation(destination):
                violations.append((lineno, destination.strip().split()[0]))
    return violations


def main() -> int:
    docs_dir = Path(__file__).resolve().parent.parent / "docs" / "api"
    if not docs_dir.is_dir():
        print(f"Error: docs directory not found at {docs_dir}", file=sys.stderr)
        return 1

    md_files = sorted(docs_dir.glob("*.md"))
    if not md_files:
        # Fail closed: an empty docs/api/ means the layout moved or the glob is
        # wrong — never report "clean" on zero inspected files.
        print(f"Error: no markdown files found in {docs_dir}", file=sys.stderr)
        return 1

    total = 0
    for md_file in md_files:
        for lineno, destination in check_file(md_file):
            rel = md_file.relative_to(docs_dir.parent.parent)
            print(
                f"  ✗ {rel}:{lineno} — escaping/unmapped relative link: {destination}"
            )
            total += 1

    if total:
        print()
        print(f"✗ Found {total} escaping/unmapped relative link(s) in docs/api/**.")
        print()
        print(
            "Synced docs (docs/api/**) are converted to the docs site under\n"
            "  docs/api-reference/python/. A relative link that escapes that tree\n"
            "  (../…) or points at repo source resolves in-repo but is dead on the\n"
            "  site (this broke nevermined-io/docs#234). Use a chapter link the\n"
            "  converter rewrites (e.g. 11-x402.md — see LINK_MAPPING in\n"
            "  scripts/convert_to_mintlify.py), a site-relative path (/docs/…), or\n"
            "  an absolute https://github.com/… URL instead. See CONTRIBUTING.md."
        )
        return 1

    print("✓ docs/api/** has no escaping or unmapped relative links.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
