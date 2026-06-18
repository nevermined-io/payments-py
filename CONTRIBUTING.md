# Contributing to payments-py

Thanks for contributing to the Nevermined Payments Python SDK. This guide covers
conventions that CI enforces; see [`CLAUDE.md`](./CLAUDE.md) for the full
development workflow (Poetry, Black, tests, releases).

## Quick start

```bash
poetry install
poetry run pre-commit install   # runs Black on every commit
poetry run pytest -m "not slow" -v
poetry run black .              # CI fails on unformatted code
```

## Documentation

User-facing SDK docs are hand-written under [`docs/api/`](./docs/api/) as
numbered chapters (`NN-<slug>.md`). On release, `publish-mintlify-docs.yml`
converts them to Mintlify MDX via
[`scripts/convert_to_mintlify.py`](./scripts/convert_to_mintlify.py) and opens a
PR against the docs site (`nevermined-io/docs`), publishing them at
`docs/api-reference/python/<slug>`.

When you change a public API, update the matching chapter in `docs/api/` (see
[`CLAUDE.md`](./CLAUDE.md) for which files map to which APIs) and rebuild with
`poetry run mkdocs build`.

### Link conventions for `docs/api/**`

Because these files are **transformed and republished on the docs site**, a
relative link that resolves fine inside this repo can be **dead on the site** —
the site has no parent directories and no repo source tree. This exact class of
link once broke a docs-site sync PR (`nevermined-io/docs#234`, the v1.15.0
sync of `a2a-module.mdx` → `../../payments_py/x402/README.md`).

In `docs/api/**`, use only:

- ✅ **Chapter links** to other `docs/api/` pages, by filename — `[x402](11-x402.md)`
  or `[x402](./11-x402.md#section)`. The converter rewrites these to the site URL
  (`/docs/api-reference/python/x402-module`). The set of rewritable chapters is
  `LINK_MAPPING` in [`scripts/convert_to_mintlify.py`](./scripts/convert_to_mintlify.py);
  add a chapter there when you add a page.
- ✅ **Site-relative links** to other docs-site pages — `[LangChain](/docs/integrate/add-to-your-agent/langchain)`.
- ✅ **In-page anchors** — `[Credits](#credits-semantics)`.
- ✅ **Absolute GitHub URLs** for anything in the repo (source, tests, READMEs,
  other directories) — `[x402 README](https://github.com/nevermined-io/payments-py/blob/main/payments_py/x402/README.md)`.
- ❌ **Escaping relative links** (`](../…)`) and **links to repo source**
  (`payments_py/…`, paths with a `/` that the converter does not rewrite) — these
  resolve in-repo but 404 on the site. CI rejects them.

### Link checks

Two gates run in CI ([`.github/workflows/docs-link-check.yml`](./.github/workflows/docs-link-check.yml))
on changes to `docs/api/**`, plus a release-time backstop in
`publish-mintlify-docs.yml`. Reproduce them locally:

```bash
# Fast, network-free lint — rejects escaping (../) / unmapped relative links.
# Hard gate. Driven off the converter's LINK_MAPPING, so it never drifts.
python3 scripts/lint_doc_links.py

# Full check — converts the docs, drops them into a clone of the docs site, and
# runs the same `mintlify broken-links` the docs repo uses (internal links only).
# Needs network (clones nevermined-io/docs) + Node/npx.
bash scripts/check_synced_doc_links.sh
```

The lint is the blocking gate (deterministic, never flakes). The staged Mintlify
check is a non-blocking PR backstop and a hard gate in the release pipeline. Only
**internal** links are gated; external-URL liveness is not (it is network-flaky).
