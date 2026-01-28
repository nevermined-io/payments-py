#!/usr/bin/env bash
set -e

echo "Building documentation with mkdocs..."

# Build the documentation
mkdocs build

echo "Documentation built successfully in ./site/"
