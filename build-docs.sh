#!/usr/bin/env bash
lazydocs \
    --output-path="./docs" \
    --overview-file="README.md" \
    --src-base-url="https://github.com/nevermined-io/payments-py/blob/main/" \
    payments_py

mkdocs build