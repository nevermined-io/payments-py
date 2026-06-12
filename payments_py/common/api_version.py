"""Backend API version pinning for the Nevermined Payments SDK.

The Nevermined backend versions its HTTP API independently from this
package, following the monorepo's ``MAJOR.MINOR`` scheme. Every request
the SDK sends declares which backend API version it was built and tested
against via the ``Nevermined-Version`` header, so the backend can keep
serving the pinned contract (or reject the call) instead of silently
changing response shapes under the SDK.

See https://docs.nevermined.app/api-reference/versioning and
nvm-monorepo#1535 / nvm-monorepo#1938.
"""

# The BACKEND API version (monorepo MAJOR.MINOR) this SDK release is built
# and tested against — NOT this package's own version (``pyproject.toml``).
# Bump it only after verifying the SDK against the new backend contract.
# Override per instance via ``PaymentOptions(api_version=...)``.
LOCKED_API_VERSION = "1.1"

# Request header the backend reads to resolve the API contract version.
API_VERSION_HEADER = "Nevermined-Version"
