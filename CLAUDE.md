# CLAUDE.md

Project-specific instructions for Claude Code when working with the Nevermined Payments Python SDK.

## Package Manager

This project uses **Poetry**. Common commands:

```bash
poetry install              # Install dependencies
poetry install --with test  # Install with test dependencies
poetry build                # Build the package
poetry run pytest           # Run tests
poetry run black .          # Format code
```

## Development Workflow

### Always Format Before Committing

**CRITICAL:** Code must be black-formatted before commit. The CI lint job will fail otherwise. This applies to ALL Python files — source, tests, and scripts.

The repo ships a [`pre-commit`](https://pre-commit.com) config (`.pre-commit-config.yaml`) that runs black automatically on every `git commit`. Enable it once per clone:

```bash
poetry install
poetry run pre-commit install
```

After that, `git commit` runs black on staged files; if any file would be reformatted the commit aborts so you re-stage and commit the formatted code. Verify without staging:

```bash
poetry run pre-commit run --all-files
```

To format manually (matches what the hook does):

```bash
poetry run black .
poetry run black --check .      # same check CI's pre-commit hook runs; no changes
```

If you skip `pre-commit install`, CI still catches unformatted code via `pre-commit run --all-files`, but the round-trip is wasteful — install it once.

### Update Documentation When Changing Public APIs

When modifying public interfaces (function signatures, options, types, response fields) in `payments_py/`, update the corresponding documentation in `docs/api/` to reflect the changes. These are **hand-written guides** — not auto-generated. Code examples in these files will break at runtime if they reference removed parameters, so they must be updated alongside the source code.

Key docs to update when changing x402/token/delegation APIs:
- `docs/api/07-querying-an-agent.md` — token generation examples and parameter tables
- `docs/api/11-x402.md` — scheme examples, delegation config, DelegationAPI usage

After updating, rebuild the documentation site to verify:

```bash
poetry run mkdocs build          # Must succeed without errors
```

The `docs/reference/` files are auto-generated from docstrings via mkdocstrings, so keep docstrings up to date in the source code. The `docs.yml` CI workflow deploys docs via `mike` on push to main and on version tags.

### Code Changes Require Test Updates

When modifying code in `payments_py/`, always update the corresponding tests:

- `tests/unit/` - Unit tests
- `tests/integration/` - Integration tests
- `tests/e2e/` - End-to-end tests (marked with `@pytest.mark.slow`)

## Code Style

### Imports

- **All imports must be at the top of the file** - Do not use inline imports inside functions unless absolutely necessary (e.g., to avoid circular dependencies)
- **Remove unused imports** - Do not leave imports that are not used in the file
- **Order imports**: standard library, third-party, local imports — by hand; Black does not reorder imports and no import sorter runs in pre-commit or CI

### Formatting

This project uses **Black** for code formatting with the following settings (from `pyproject.toml`):

- Line length: 88
- Target Python version: 3.10+

Format every Python file you touch (source, tests, scripts) — see "Always Format Before Committing" above for the commands and the CI gate (`pre-commit run --all-files`).

## Testing

This project uses **pytest** for testing.

```bash
# Run all tests except slow (E2E) tests
poetry run pytest -m "not slow" -v -s

# Run only E2E tests
poetry run pytest -m "slow" -v -s

# Run specific test file
poetry run pytest tests/unit/test_example.py -v

# Run with coverage
poetry run pytest --cov=payments_py --cov-report=term-missing
```

### Never hand-roll a settle/verify test double

Tests that stub `facilitator.verify_permissions` / `settle_permissions` must
build the **real** model via `tests/x402_responses.py`, never an attribute bag:

```python
from tests.x402_responses import make_settle_response, make_verify_response

facilitator.settle_permissions = lambda **k: make_settle_response(transaction="0xabc")
```

A hand-rolled class only ever carries the fields production code read the day it
was written, so it drifts from the model, and adding a field to `SettleResponse`
turns unrelated tests red with `AttributeError`. Building the model means every
field exists, populated by the model's own defaults, so a new field is inert in
tests that do not care about it.

Do **not** "fix" that by making production code use `getattr(result, "f", None)`
— that bends the SDK around its fixtures and hides the drift.

The factories validate keyword **names** themselves, for both the overrides and
their own defaults, and the check is **not** redundant with Pydantic:

- **Unknown name** — both models use Pydantic's default `extra="ignore"`, so
  constructing them directly *silently drops* a typo'd or since-removed field.
  The model does no enforcing; `_reject_unknown` does.
- **camelCase alias** — this one is **not** dropped. `populate_by_name=True`
  means `SettleResponse(creditsRedeemed="5")` is accepted and sets
  `credits_redeemed`. It is rejected because of the defaults/overrides dict
  merge: two spellings of one field survive as two keys, and Pydantic resolves
  the alias in preference to the field name *whatever the dict order* — so a
  mixed-spelling merge silently discards one of them, in the direction where the
  override is the loser.

`tests/unit/test_x402_response_doubles.py` fails if a hand-rolled bag reappears,
and carries its own positive control so it cannot silently stop detecting. Its
sweep parses `ast.ClassDef` only, so `dict` / `Mock` / `SimpleNamespace` stubs
are **outside** what it can see — those are on review to catch.

### Test Markers

- No marker: Unit and integration tests (fast)
- `@pytest.mark.slow`: E2E tests (require API keys)

### E2E Tests and Staging

E2E tests run directly against the **staging environment**. When making changes:

1. Ensure E2E tests pass after code changes: `poetry run pytest -m "slow" -v -s`
2. If E2E tests fail after backend API changes (in `nvm-monorepo`), the staging environment may need to be redeployed with those changes before the SDK E2E tests will pass
3. E2E test failures due to pending backend deployments are expected - coordinate with the team to deploy backend changes to staging first

## CI Workflow

The CI pipeline runs:

1. **Lint** (`.github/workflows/lint.yml`) - `poetry check --lock`, then `pre-commit run --all-files` (black)
2. **Unit & Integration** (`.github/workflows/test.yaml`) - Fast tests on Python 3.10, the declared floor
3. **Deep Agents compatibility** (`test.yaml`, job `deepagents_compat`) - `tests/unit/x402/test_deepagents_compat.py`
   on Python 3.11, installed with pip outside the poetry lock (deepagents needs >=3.11). Under the local
   poetry run on 3.10 that test is skipped (`pytest.importorskip`), so after changing `payments_py/x402/langchain/`
   reproduce the job in a 3.11 venv:
   `pip install -e ".[langchain,langsmith]" deepagents pytest pytest-timeout pytest-asyncio && pytest tests/unit/x402/test_deepagents_compat.py`
4. **E2E** - Slow tests (runs after unit/integration pass)

`TEST_SUBSCRIBER_API_KEY` / `TEST_BUILDER_API_KEY` live in **two separate
secret stores** — Actions and Dependabot — and which one a run reads depends on
the actor that triggered it. Before rotating either, read
**"Rotating the CI keys"** in `tests/e2e/README.md`; getting it wrong breaks
Dependabot PRs only, which is a hard failure to diagnose from the symptom.

Dependabot PRs that are patch or minor are auto-approved and queued by
`.github/workflows/dependabot-auto-merge.yml` (#283). Majors stop for a human.

`.github/workflows/dependabot-update-branches.yml` is the companion sweeper,
ported from `nevermined-io/payments`. On every push to `main` (plus a Monday
09:00 UTC fallback and `workflow_dispatch`) it merges `main` into up to
`MAX_MERGES` open Dependabot branches via `POST /repos/{owner}/{repo}/merges`,
so their required checks re-run against the `main` they will land on rather
than the one Dependabot branched from.

`main` sets `strict: true` (aligned with `payments` in #287), so this is
**load-bearing, not a convenience**: a Dependabot branch that has fallen behind
cannot merge until something merges `main` into it, and unattended that
something is this workflow. If it breaks, the queue stalls silently — nothing
merges, no check goes red, the PRs just sit.

The sweep enforces nothing on its own: without `strict`, `dependabot-auto-merge.yml`
arms a PR the moment it opens, and one green on its original head merges before
any push wakes the sweep. Before describing this workflow as enforcing anything,
re-check that `strict` is still set —
`gh api repos/nevermined-io/payments-py/branches/main/protection`.

`MAX_MERGES` bounds how fast the queue drains, not whether a PR can slip
through unswept; overflow waits for a later wave, and a merge is itself a push
to `main` that starts one. This repo also sets `allow_update_branch: true`
(`payments` does not), which only surfaces GitHub's manual "Update branch"
button — it performs no update and replaces nothing here.

Conflicts are reported as a job warning and need `@dependabot recreate` from a
*user* account; the App identity cannot issue Dependabot commands.
`.github/dependabot.yml` pins its weekly run to Monday 08:00 Europe/Madrid so
the cron fallback has a known run to clear.

The logic lives in `.github/scripts/update-dependabot-branches.sh`, not inline
in the workflow, because the workflow triggers on a push to `main` and so
cannot be exercised before it merges. `tests/unit/test_dependabot_sweeper.py`
runs that script against a stubbed `gh` and is the only pre-merge cover the
ordering, status handling and cap get — treat it as required when touching
either file. The failure it exists to catch is a job that reports green while
updating nothing (for example, calling a GitHub endpoint with the wrong HTTP method).

## Release Process

**Do NOT bump the version in `pyproject.toml` by hand in a feature PR.** The release is fully automated through three workflows:

1. **`prepare-release.yml`** — manual trigger via Actions UI (`workflow_dispatch`). Takes a `version` input (e.g. `1.8.0`), bumps `pyproject.toml`, opens a PR from a `release/<version>` branch.
2. **`finalize-release.yml`** — fires when the `release/*` PR is merged. Creates the `v<version>` git tag.
3. **`release-python.yml`** — fires on `v*.*` tag push. Builds and publishes to PyPI.

In addition, **`publish-mintlify-docs.yml`** fires on the same tag, runs `scripts/convert_to_mintlify.py` over `docs/api/`, and opens a PR in `nevermined-io/docs_mintlify` updating `docs/api-reference/python/*.mdx`.

Feature PRs ship code, tests, and source docs (`docs/api/*.md`). The version stays where it is — the human releasing decides what number to use and runs the workflow.

## Project Structure

```
payments_py/       # Source code
  x402/            # X402 payment protocol types and APIs
    strands/       # Strands agent decorator (@requires_payment)
    fastapi/       # FastAPI middleware (PaymentMiddleware)
    langchain/     # LangChain tool decorator
    agentcore/     # AgentCore Gateway Lambda interceptor
    extensions/    # x402 extensions
  a2a/             # A2A server/client integration
  mcp/             # MCP integration
  mpp/             # Machine Payments Protocol (MPP)
  langsmith/       # LangSmith verify/settle spans ([langsmith] extra)
  api/             # API client implementations
  common/          # Shared types and utilities
tests/
  unit/            # Unit tests (x402/, a2a/, mcp_tests/, mpp/, langsmith/ subdirs)
  integration/     # Integration tests
  e2e/             # End-to-end tests (@pytest.mark.slow)
  conftest.py      # Shared fixtures
  x402_responses.py  # Settle/verify model factories for test doubles
```

## Key APIs

- `Payments` - Main entry point for the SDK
- `payments.facilitator` - X402 verify/settle permissions
- `payments.x402` - X402 access token generation
- `payments.plans` - Plan management
- `payments.agents` - Agent management

## API Version Pinning

Every HTTP call to the Nevermined backend carries a `Nevermined-Version`
header: both option builders (`get_backend_http_options()` /
`get_public_http_options()` in `payments_py/api/base_payments.py`) inject
it, and the read-only GETs that historically bypassed the builders
(`get_plan`, `get_plan_balance`, `get_agents_associated_to_plan`,
`get_agent`, `get_agent_plans`, `get_deployment_info`) are routed through
`get_public_http_options("GET")` so the invariant holds everywhere
(wire-level tests in `TestBareEndpointVersionPin`). New endpoint code MUST
use one of the two builders — never hand-build headers. Constants live in
`payments_py/common/api_version.py`:

- `LOCKED_API_VERSION` (`"1.1"`) — the **backend API version** (nvm-monorepo
  `MAJOR.MINOR`) this SDK release is built and tested against. It is **not**
  the package version in `pyproject.toml`; the two move independently. See
  https://nevermined.ai/docs/development-guide/api-versioning and
  nvm-monorepo#1535 / nvm-monorepo#1938.
- `API_VERSION_HEADER` (`"Nevermined-Version"`) — the request header name.

**Bump procedure:** when the backend ships a new API version, run the full
test suite (unit + integration + E2E against a backend already serving the
new version), fix any contract drift, then update — in the same PR:

1. `LOCKED_API_VERSION` in `payments_py/common/api_version.py`
2. the pinned value in `tests/unit/test_base_payments_http.py`
   (`test_header_name_and_locked_version_constants`)
3. the prose `"1.1"` occurrences in this section and in
   `docs/api/02-initializing-the-library.md` (the `api_version="1.1"`
   example) — they are documentation, not constants, and drift silently

Never bump it speculatively — the constant is a tested-compatibility claim.

**Override path:** users can target a different backend contract per
instance via `PaymentOptions(api_version="x.y")`; `BasePaymentsAPI`
resolves `options.api_version or LOCKED_API_VERSION` into
`self.api_version`, and `Payments._build_options()` propagates it to
lazily-built sub-APIs. Note `PaymentOptions.version` is a different,
legacy field (SDK version reported to the backend) — do not reuse it for
API version pinning.

## Framework Integrations

- **FastAPI**: `payments_py.x402.fastapi` — `PaymentMiddleware` (install with `pip install payments-py[fastapi]`)
- **Strands Agent**: `payments_py.x402.strands` — `@requires_payment` decorator (install with `pip install payments-py[strands]`)
  - Must use `@tool(context=True)` for Strands to inject `tool_context`
  - Token via `agent(prompt, invocation_state={"payment_token": token})`
  - Client extraction: `extract_payment_required(agent.messages)`
