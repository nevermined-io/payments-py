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

### Always Format and Build After Changes

**IMPORTANT:** After making ANY code changes (including new files and test files), always run:

```bash
poetry run black .              # Format all code (REQUIRED)
poetry build                    # Build must succeed
```

Both commands must succeed before considering the changes complete.

To verify formatting without making changes (CI check):

```bash
poetry run black --check .      # Check formatting only
```

### Code Changes Require Test Updates

When modifying code in `payments_py/`, always update the corresponding tests:

- `tests/unit/` - Unit tests
- `tests/integration/` - Integration tests
- `tests/e2e/` - End-to-end tests (marked with `@pytest.mark.slow`)

## Code Formatting

This project uses **Black** for code formatting with the following settings (from `pyproject.toml`):

- Line length: 88
- Target Python version: 3.10+

**CRITICAL:** Always run `poetry run black .` after writing or modifying any Python files (including tests). The CI will fail if code is not formatted.

```bash
poetry run black .           # Format all files (run after every change)
poetry run black --check .   # Check formatting without changes (CI uses this)
```

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

1. **Lint** (`.github/workflows/lint.yml`) - Black formatting check
2. **Unit & Integration** (`.github/workflows/test.yaml`) - Fast tests
3. **E2E** - Slow tests (runs after unit/integration pass)

## Project Structure

```
payments_py/       # Source code
  x402/            # X402 payment protocol types and APIs
  api/             # API client implementations
  common/          # Shared types and utilities
tests/
  unit/            # Unit tests
  integration/     # Integration tests
  e2e/             # End-to-end tests (@pytest.mark.slow)
  conftest.py      # Shared fixtures
```

## Key APIs

- `Payments` - Main entry point for the SDK
- `payments.facilitator` - X402 verify/settle permissions
- `payments.x402` - X402 access token generation
- `payments.plans` - Plan management
- `payments.agents` - Agent management
