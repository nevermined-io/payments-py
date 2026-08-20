"""Regression tests for the MkDocs->Mintlify converter's internal-link rewriting.

The converter (``scripts/convert_to_mintlify.py``) rewrites payments-py's relative
``NN-name.md`` cross-links to absolute docs-site paths. A deep link carrying an
``#anchor`` fragment (e.g. ``09-mcp-integration.md#mcp-oauth-and-x402-discovery``)
must keep its anchor through the rewrite -- otherwise the relative ``.md`` path
leaks into the generated docs site and the Mintlify link-rot check fails (the
relative file does not exist there). See nevermined-io/docs#208.
"""

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "convert_to_mintlify.py"
_spec = importlib.util.spec_from_file_location("convert_to_mintlify", _SCRIPT)
assert _spec is not None and _spec.loader is not None
convert = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(convert)


def test_unanchored_internal_link_is_rewritten():
    md = "- [MCP Integration](09-mcp-integration.md) - x402 with MCP servers"
    out = convert.convert_internal_links(md)
    assert "(/api-reference/python/mcp-module)" in out
    assert "09-mcp-integration.md" not in out


def test_anchored_internal_link_keeps_its_fragment():
    md = "[MCP OAuth and x402 Discovery](09-mcp-integration.md#mcp-oauth-and-x402-discovery)"
    out = convert.convert_internal_links(md)
    assert "(/api-reference/python/mcp-module#mcp-oauth-and-x402-discovery)" in out
    assert "09-mcp-integration.md" not in out


def test_relative_path_prefix_with_anchor_is_rewritten():
    md = "see [rel](../api/09-mcp-integration.md#mcp-oauth-and-x402-discovery) here"
    out = convert.convert_internal_links(md)
    assert "(/api-reference/python/mcp-module#mcp-oauth-and-x402-discovery)" in out


def test_next_steps_anchored_link_becomes_card_with_docs_site_href():
    # End-to-end through the real pipeline order: links are rewritten first, then
    # the Next Steps section is turned into Cards. The anchored deep link must end
    # up as an absolute docs-site href, never the relative .md form.
    md = (
        "## Next Steps\n\n"
        "- [MCP Integration](09-mcp-integration.md) - x402 with MCP servers\n"
        "- [MCP OAuth and x402 Discovery](09-mcp-integration.md#mcp-oauth-and-x402-discovery)"
        " - Experimental MCP payment discovery metadata\n"
    )
    out = convert.convert_next_steps_to_cards(convert.convert_internal_links(md))
    assert 'href="/api-reference/python/mcp-module#mcp-oauth-and-x402-discovery"' in out
    assert "09-mcp-integration.md" not in out


def test_danger_admonition_becomes_a_warning_callout():
    """A `!!! danger` block must convert like every other admonition.

    Without a `danger` case the literal `!!! danger "..."` line survives into the
    .mdx and its 4-space-indented body renders as a CODE BLOCK — invisible to
    `mkdocs build` and only visible after publish, which is the same class of
    defect PR #202 fixed retroactively for chapter 13. Mintlify has no <Danger>,
    so <Warning> (its strongest callout) is the target.
    """
    md = '!!! danger "Both guards are process-local"\n    They live in memory.\n'
    out = convert.convert_admonitions(md)
    assert '<Warning title="Both guards are process-local">' in out
    assert "They live in memory." in out
    assert "!!! danger" not in out


def test_untitled_danger_admonition_converts_too():
    md = "!!! danger\n    The burn may already have committed.\n"
    out = convert.convert_admonitions(md)
    assert "<Warning>" in out
    assert "!!! danger" not in out
