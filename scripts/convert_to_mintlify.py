#!/usr/bin/env python3
"""
Convert Markdown documentation to Mintlify MDX format.

This script transforms .md files from the payments-py docs/api directory
into Mintlify-compatible .mdx files with proper frontmatter and components.
"""

import os
import re
import argparse
from pathlib import Path
from typing import Optional

# Mapping of source files to target names and metadata
FILE_MAPPING = {
    "01-installation.md": {
        "target": "installation.mdx",
        "icon": "download",
        "description": "Install and configure the payments-py Python SDK",
    },
    "02-initializing-the-library.md": {
        "target": "payments-class.mdx",
        "icon": "code",
        "description": "Initialize and configure the Payments class for Python",
    },
    "03-payment-plans.md": {
        "target": "plans-module.mdx",
        "icon": "credit-card",
        "description": "Create and manage payment plans with the Python SDK",
    },
    "04-agents.md": {
        "target": "agents-module.mdx",
        "icon": "robot",
        "description": "Register and manage AI agents with the Python SDK",
    },
    "05-publishing-static-resources.md": {
        "target": "resources-module.mdx",
        "icon": "file",
        "description": "Publish and manage static resources with access control",
    },
    "06-payments-and-balance.md": {
        "target": "balance-module.mdx",
        "icon": "wallet",
        "description": "Order plans and manage credit balances",
    },
    "07-querying-an-agent.md": {
        "target": "requests-module.mdx",
        "icon": "paper-plane",
        "description": "Query agents and process requests with the Python SDK",
    },
    "08-validation-of-requests.md": {
        "target": "validation-module.mdx",
        "icon": "shield-check",
        "description": "Validate incoming requests and access tokens",
    },
    "09-mcp-integration.md": {
        "target": "mcp-module.mdx",
        "icon": "plug",
        "description": "Build MCP servers with integrated payments",
    },
    "10-a2a-integration.md": {
        "target": "a2a-module.mdx",
        "icon": "arrows-left-right",
        "description": "Implement Agent-to-Agent protocol with payments",
    },
    "11-x402.md": {
        "target": "x402-module.mdx",
        "icon": "lock",
        "description": "Use x402 protocol for payment verification and settlement",
    },
}

# Link mapping for internal references
LINK_MAPPING = {
    "01-installation.md": "/docs/api-reference/python/installation",
    "02-initializing-the-library.md": "/docs/api-reference/python/payments-class",
    "03-payment-plans.md": "/docs/api-reference/python/plans-module",
    "04-agents.md": "/docs/api-reference/python/agents-module",
    "05-publishing-static-resources.md": "/docs/api-reference/python/resources-module",
    "06-payments-and-balance.md": "/docs/api-reference/python/balance-module",
    "07-querying-an-agent.md": "/docs/api-reference/python/requests-module",
    "08-validation-of-requests.md": "/docs/api-reference/python/validation-module",
    "09-mcp-integration.md": "/docs/api-reference/python/mcp-module",
    "10-a2a-integration.md": "/docs/api-reference/python/a2a-module",
    "11-x402.md": "/docs/api-reference/python/x402-module",
}


def extract_title(content: str) -> str:
    """Extract the title from the first H1 heading."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return "Documentation"


def convert_admonitions(content: str) -> str:
    """Convert MkDocs admonitions to Mintlify components."""
    # Pattern for MkDocs admonitions: !!! type "title" or !!! type
    patterns = [
        # !!! warning "Title"
        (
            r'!!!\s+warning\s+"([^"]+)"\n((?:\s{4}.+\n?)+)',
            lambda m: f'<Warning title="{m.group(1)}">\n{dedent_content(m.group(2))}</Warning>\n',
        ),
        # !!! warning (no title)
        (
            r"!!!\s+warning\n((?:\s{4}.+\n?)+)",
            lambda m: f"<Warning>\n{dedent_content(m.group(1))}</Warning>\n",
        ),
        # !!! note "Title"
        (
            r'!!!\s+note\s+"([^"]+)"\n((?:\s{4}.+\n?)+)',
            lambda m: f'<Note title="{m.group(1)}">\n{dedent_content(m.group(2))}</Note>\n',
        ),
        # !!! note (no title)
        (
            r"!!!\s+note\n((?:\s{4}.+\n?)+)",
            lambda m: f"<Note>\n{dedent_content(m.group(1))}</Note>\n",
        ),
        # !!! tip "Title"
        (
            r'!!!\s+tip\s+"([^"]+)"\n((?:\s{4}.+\n?)+)',
            lambda m: f'<Tip title="{m.group(1)}">\n{dedent_content(m.group(2))}</Tip>\n',
        ),
        # !!! tip (no title)
        (
            r"!!!\s+tip\n((?:\s{4}.+\n?)+)",
            lambda m: f"<Tip>\n{dedent_content(m.group(1))}</Tip>\n",
        ),
        # !!! info "Title"
        (
            r'!!!\s+info\s+"([^"]+)"\n((?:\s{4}.+\n?)+)',
            lambda m: f'<Info title="{m.group(1)}">\n{dedent_content(m.group(2))}</Info>\n',
        ),
        # !!! info (no title)
        (
            r"!!!\s+info\n((?:\s{4}.+\n?)+)",
            lambda m: f"<Info>\n{dedent_content(m.group(1))}</Info>\n",
        ),
    ]

    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)

    return content


def dedent_content(content: str) -> str:
    """Remove 4-space indentation from admonition content."""
    lines = content.split("\n")
    dedented = []
    for line in lines:
        if line.startswith("    "):
            dedented.append(line[4:])
        else:
            dedented.append(line)
    return "\n".join(dedented)


def convert_internal_links(content: str) -> str:
    """Convert internal markdown links to Mintlify format."""
    for source, target in LINK_MAPPING.items():
        # Match [text](filename.md) or [text](../path/filename.md)
        pattern = rf"\[([^\]]+)\]\([^)]*{re.escape(source)}\)"
        replacement = rf"[\1]({target})"
        content = re.sub(pattern, replacement, content)

    return content


def convert_next_steps_to_cards(content: str) -> str:
    """Convert 'Next Steps' sections with links to CardGroup components."""
    # Pattern to find Next Steps section with bullet points
    next_steps_pattern = r"##\s+Next\s+Steps\n\n((?:-\s+\[.+?\]\(.+?\).*?\n)+)"

    def replace_next_steps(match):
        links_text = match.group(1)
        # Extract individual links
        link_pattern = r"-\s+\[([^\]]+)\]\(([^)]+)\)(?:\s+-\s+(.+))?"
        links = re.findall(link_pattern, links_text)

        if not links:
            return match.group(0)

        cards = []
        for title, href, description in links:
            desc = description if description else title
            cards.append(
                f'  <Card title="{title}" icon="arrow-right" href="{href}">\n'
                f"    {desc}\n"
                f"  </Card>"
            )

        return (
            "## Next Steps\n\n"
            "<CardGroup cols={2}>\n" + "\n".join(cards) + "\n</CardGroup>\n"
        )

    content = re.sub(next_steps_pattern, replace_next_steps, content)
    return content


def remove_first_heading(content: str) -> str:
    """Remove the first H1 heading (it's in the frontmatter now)."""
    return re.sub(r"^#\s+.+\n+", "", content, count=1)


def add_frontmatter(content: str, title: str, description: str, icon: str) -> str:
    """Add Mintlify frontmatter to the content."""
    frontmatter = f'''---
title: "{title}"
description: "{description}"
icon: "{icon}"
---

'''
    return frontmatter + content


def convert_file(
    source_path: Path, target_path: Path, metadata: dict, verbose: bool = False
) -> bool:
    """Convert a single markdown file to Mintlify MDX format."""
    try:
        with open(source_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Extract title before removing it
        title = extract_title(content)

        # Apply transformations
        content = remove_first_heading(content)
        content = convert_admonitions(content)
        content = convert_internal_links(content)
        content = convert_next_steps_to_cards(content)

        # Add frontmatter
        content = add_frontmatter(
            content,
            title=title,
            description=metadata["description"],
            icon=metadata["icon"],
        )

        # Write output
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        if verbose:
            print(f"  ✓ {source_path.name} -> {target_path.name}")

        return True

    except Exception as e:
        print(f"  ✗ Error converting {source_path.name}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Convert Markdown documentation to Mintlify MDX format"
    )
    parser.add_argument(
        "--source",
        "-s",
        type=Path,
        default=Path("docs/api"),
        help="Source directory containing .md files",
    )
    parser.add_argument(
        "--target",
        "-t",
        type=Path,
        default=Path("output/mintlify"),
        help="Target directory for .mdx files",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print detailed progress"
    )

    args = parser.parse_args()

    source_dir = args.source
    target_dir = args.target

    if not source_dir.exists():
        print(f"Error: Source directory '{source_dir}' does not exist")
        return 1

    print(f"Converting documentation from {source_dir} to {target_dir}")
    print()

    success_count = 0
    error_count = 0

    for source_name, metadata in FILE_MAPPING.items():
        source_path = source_dir / source_name
        target_path = target_dir / metadata["target"]

        if not source_path.exists():
            print(f"  ⚠ Skipping {source_name} (not found)")
            continue

        if convert_file(source_path, target_path, metadata, args.verbose):
            success_count += 1
        else:
            error_count += 1

    print()
    print(f"Conversion complete: {success_count} files converted, {error_count} errors")

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    exit(main())
