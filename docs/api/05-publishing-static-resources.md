# Publishing Static Resources

This guide explains how to publish static resources (files, datasets) using the Nevermined Payments Python SDK.

## Overview

Static resources are files or datasets that users can access through payment plans. Unlike AI agents that process requests, static resources are downloadable content such as:

- Documents (PDFs, reports)
- Datasets (CSV, JSON files)
- Media files (images, videos)
- Software packages

## Register Static Resource Agents

Static resources are registered as a special type of agent with file endpoints:

```python
from payments_py.common.types import AgentMetadata, AgentAPIAttributes

# Resource metadata
resource_metadata = AgentMetadata(
    name="Premium Dataset Collection",
    description="A curated collection of ML training datasets",
    tags=["dataset", "machine-learning", "premium"]
)

# Static file endpoints
resource_api = AgentAPIAttributes(
    endpoints=[
        {"GET": "https://storage.example.com/datasets/training-data.csv"},
        {"GET": "https://storage.example.com/datasets/validation-data.csv"},
        {"GET": "https://storage.example.com/datasets/test-data.csv"}
    ],
    agent_definition_url="https://storage.example.com/datasets/manifest.json"
)

# Register with a payment plan
result = payments.agents.register_agent(
    agent_metadata=resource_metadata,
    agent_api=resource_api,
    payment_plans=[plan_id]
)
print(f"Resource ID: {result['agentId']}")
```

## Using Wildcards for Multiple Files

When you have multiple files that follow a pattern, you can use wildcard URLs:

```python
# Single wildcard for dynamic file names
resource_api = AgentAPIAttributes(
    endpoints=[
        # Matches: /files/report-001.pdf, /files/report-2024.pdf, etc.
        {"GET": "https://storage.example.com/files/report-*.pdf"},

        # Matches: /data/dataset_v1.csv, /data/dataset_v2.csv, etc.
        {"GET": "https://storage.example.com/data/dataset_*.csv"}
    ],
    agent_definition_url="https://storage.example.com/manifest.json"
)
```

### Wildcard Patterns

| Pattern | Matches |
|---------|---------|
| `*.pdf` | Any PDF file |
| `report-*.pdf` | report-001.pdf, report-2024.pdf |
| `data/*.csv` | All CSV files in data folder |
| `v*/data.json` | v1/data.json, v2/data.json |

## Complete Example: Dataset Publishing

```python
from payments_py import Payments, PaymentOptions
from payments_py.common.types import AgentMetadata, AgentAPIAttributes, PlanMetadata
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config

# Initialize
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

ERC20_TOKEN = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
builder_address = payments.account_address

# 1. Create a plan for the dataset
plan_result = payments.plans.register_credits_plan(
    plan_metadata=PlanMetadata(
        name="Dataset Access Plan",
        description="Access to premium ML datasets"
    ),
    price_config=get_erc20_price_config(100, ERC20_TOKEN, builder_address),
    credits_config=get_fixed_credits_config(10)  # 10 downloads
)
plan_id = plan_result['planId']

# 2. Register the dataset resource
dataset_result = payments.agents.register_agent(
    agent_metadata=AgentMetadata(
        name="ML Training Datasets",
        description="High-quality labeled datasets for machine learning",
        tags=["dataset", "ml", "training", "labeled"]
    ),
    agent_api=AgentAPIAttributes(
        endpoints=[
            {"GET": "https://storage.example.com/datasets/images/*.zip"},
            {"GET": "https://storage.example.com/datasets/text/*.jsonl"},
            {"GET": "https://storage.example.com/datasets/audio/*.tar.gz"}
        ],
        agent_definition_url="https://storage.example.com/datasets/catalog.json"
    ),
    payment_plans=[plan_id]
)
print(f"Dataset Resource ID: {dataset_result['agentId']}")
```

## Example: Document Repository

```python
# Publishing a document repository
doc_result = payments.agents.register_agent(
    agent_metadata=AgentMetadata(
        name="Research Papers Collection",
        description="Exclusive research papers and technical reports",
        tags=["research", "papers", "technical"]
    ),
    agent_api=AgentAPIAttributes(
        endpoints=[
            # Specific documents
            {"GET": "https://docs.example.com/papers/whitepaper-2024.pdf"},
            {"GET": "https://docs.example.com/papers/research-findings.pdf"},

            # Wildcard for quarterly reports
            {"GET": "https://docs.example.com/reports/q*-report.pdf"},

            # All supplementary materials
            {"GET": "https://docs.example.com/supplementary/*.zip"}
        ],
        agent_definition_url="https://docs.example.com/index.json"
    ),
    payment_plans=[plan_id]
)
```

## Example: Software Distribution

```python
# Publishing software packages
software_result = payments.agents.register_agent(
    agent_metadata=AgentMetadata(
        name="Premium Software Tools",
        description="Professional development tools and utilities",
        tags=["software", "tools", "professional"]
    ),
    agent_api=AgentAPIAttributes(
        endpoints=[
            # Version-specific downloads
            {"GET": "https://releases.example.com/tool/v*/tool-*.zip"},

            # Platform-specific binaries
            {"GET": "https://releases.example.com/tool/latest/tool-linux-*.tar.gz"},
            {"GET": "https://releases.example.com/tool/latest/tool-macos-*.dmg"},
            {"GET": "https://releases.example.com/tool/latest/tool-windows-*.exe"},

            # Documentation
            {"GET": "https://releases.example.com/tool/docs/*.pdf"}
        ],
        agent_definition_url="https://releases.example.com/tool/manifest.json"
    ),
    payment_plans=[plan_id]
)
```

## Accessing Static Resources

Subscribers can access static resources using the x402 access token:

```python
# As a subscriber, get access token
access_result = payments.x402.get_x402_access_token(
    plan_id=plan_id,
    agent_id=resource_id
)
access_token = access_result['accessToken']

# Download a file
import requests

response = requests.get(
    "https://storage.example.com/datasets/training-data.csv",
    headers={"Authorization": f"Bearer {access_token}"}
)

if response.status_code == 200:
    with open("training-data.csv", "wb") as f:
        f.write(response.content)
    print("File downloaded successfully")
```

## Best Practices

1. **Use descriptive metadata**: Include clear names, descriptions, and tags for discoverability

2. **Organize files logically**: Use consistent URL patterns that work well with wildcards

3. **Version your resources**: Include version numbers in URLs for easy updates

4. **Provide a manifest**: Create a JSON manifest at the `agent_definition_url` listing all available files

5. **Set appropriate credits**: Consider the value and size of files when setting credit costs

## Next Steps

- [Payments and Balance](06-payments-and-balance.md) - Order plans and check balances
- [Querying an Agent](07-querying-an-agent.md) - Access resources with tokens
