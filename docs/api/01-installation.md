# Installation

This guide covers how to install the Nevermined Payments Python SDK.

## Overview

The Nevermined Payments Python SDK (`payments-py`) is a Python library that provides tools for integrating AI agent monetization and access control into your applications. It supports:

- Payment plans (credits-based and time-based)
- AI agent registration and management
- X402 payment protocol
- MCP (Model Context Protocol) integration
- A2A (Agent-to-Agent) protocol support

## Prerequisites

Before installing the SDK, ensure you have:

- **Python 3.10 or higher** - The SDK requires Python 3.10+
- **pip or Poetry** - Package manager for installation
- **Nevermined API Key** - Obtain from the [Nevermined App](https://nevermined.app)

## Installation Steps

### Using pip

```bash
pip install payments-py
```

### Using Poetry

```bash
poetry add payments-py
```

### With Optional Dependencies

For FastAPI/x402 middleware support:

```bash
# Using pip
pip install payments-py[fastapi]

# Using Poetry
poetry add payments-py -E fastapi
```

## Verify Installation

After installation, verify the SDK is working:

```python
from payments_py import Payments, PaymentOptions

# Check version
import payments_py
print(f"payments-py installed successfully")
```

## Environment Setup

Create a `.env` file or set environment variables:

```bash
# Required
NVM_API_KEY=nvm:your-api-key-here

# Optional (for custom environments)
NVM_BACKEND_URL=https://api.sandbox.nevermined.app
NVM_PROXY_URL=https://proxy.sandbox.nevermined.app
```

## Next Steps

Once installed, proceed to [Initializing the Library](02-initializing-the-library.md) to configure the SDK.
