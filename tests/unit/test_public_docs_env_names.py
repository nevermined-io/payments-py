"""The guides synced to nevermined.ai/docs name only the public environments.

``docs/api/**/*.md`` is converted by ``publish-mintlify-docs.yml`` into the docs
site's ``api-reference/python/`` pages. The SDK still accepts the internal
``staging_sandbox`` / ``staging_live`` environments (and their
``sandbox-staging:`` / ``live-staging:`` key prefixes) for Nevermined's own
development, but the docs site says only ``sandbox`` and ``live``
(nevermined-io/nvm-monorepo#5182). The docs site cannot fix a generated page,
so this repo guards its source.

Out of scope: the mkdocs API reference (``docs/reference/``, published by
``docs.yml``) renders ``payments_py/environments.py`` itself, which keeps the
staging environments on purpose.
"""

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs" / "api"
FORBIDDEN = re.compile(
    r"staging_(sandbox|live)|(sandbox|live)-staging:|nevermined\.dev", re.I
)


def _leaks(text: str) -> list[str]:
    return [m.group(0) for m in FORBIDDEN.finditer(text)]


def test_pattern_catches_each_internal_name():
    planted = "`staging_sandbox` `STAGING_LIVE` `sandbox-staging:` `live-staging:` embed.nevermined.dev"
    assert len(_leaks(planted)) == 5
    assert _leaks("`sandbox` `live` sandbox: live: nevermined.app staging") == []


def test_synced_docs_name_only_public_environments():
    pages = sorted(DOCS.rglob("*.md"))
    assert pages, f"no synced docs found under {DOCS}"
    leaks = {
        str(p.relative_to(DOCS)): found
        for p in pages
        if (found := _leaks(p.read_text(encoding="utf-8")))
    }
    assert leaks == {}, f"internal environment names in public docs: {leaks}"
