# MCP Integration

This guide explains how to integrate the Nevermined Payments Python SDK with MCP (Model Context Protocol) servers.

## Overview

MCP (Model Context Protocol) enables AI applications to interact with external tools, resources, and prompts. The Nevermined SDK provides built-in MCP integration to:

- Protect tools, resources, and prompts with paywalls
- Handle OAuth 2.1 authentication
- Manage credit consumption per operation

## MCP Integration API

Access the MCP integration through `payments.mcp`:

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# MCP integration is available as:
mcp = payments.mcp
```

## Simplified API (Recommended)

The simplified API handles server setup automatically:

### Register a Tool

```python
async def hello_handler(args, context=None):
    """Handle the hello tool request."""
    name = args.get("name", "World")
    return {
        "content": [{"type": "text", "text": f"Hello, {name}!"}]
    }

# Register the tool
payments.mcp.register_tool(
    name="hello_world",
    config={
        "description": "Says hello to someone",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name to greet"}
            }
        }
    },
    handler=hello_handler,
    options={"credits": 1}  # Cost: 1 credit per call
)
```

### Register a Resource

```python
async def config_handler(uri, variables, context=None):
    """Handle the configuration resource request."""
    return {
        "contents": [{
            "uri": str(uri),
            "mimeType": "application/json",
            "text": '{"version": "1.0.0", "feature_flags": {"beta": true}}'
        }]
    }

payments.mcp.register_resource(
    uri="data://config",
    config={
        "name": "Configuration",
        "description": "Application configuration",
        "mimeType": "application/json"
    },
    handler=config_handler,
    options={"credits": 2}  # Cost: 2 credits per access
)
```

### Register a Prompt

```python
async def greeting_handler(args, context=None):
    """Handle the greeting prompt request."""
    style = args.get("style", "formal")
    return {
        "messages": [{
            "role": "user",
            "content": {
                "type": "text",
                "text": f"Please greet me in a {style} way."
            }
        }]
    }

payments.mcp.register_prompt(
    name="greeting",
    config={
        "name": "Greeting",
        "description": "Generates a greeting"
    },
    handler=greeting_handler,
    options={"credits": 1}
)
```

### Start the Server

```python
import asyncio

async def main():
    # Register handlers first
    payments.mcp.register_tool("hello", {...}, hello_handler)

    # Start the MCP server
    result = await payments.mcp.start({
        "port": 5001,
        "planId": "your-plan-id",  # required
        "serverName": "my-mcp-server",
        # "agentId": "your-agent-id",  # optional (informational only)
        "version": "1.0.0",
        "description": "My MCP server with Nevermined payments"
    })

    print(f"Server running at: {result['info']['baseUrl']}")
    print(f"Tools: {result['info']['tools']}")

    # Server runs until stopped
    # To stop: await payments.mcp.stop()

asyncio.run(main())
```

## Advanced API

For more control, use the advanced API:

### Configure and Protect Handlers

```python
# Configure shared options (planId required; agentId optional/informational)
payments.mcp.configure({
    "planId": "your-plan-id",
    "serverName": "my-mcp-server"
})

# Wrap a handler with paywall
async def my_handler(args):
    return {"result": "processed"}

protected_handler = payments.mcp.with_paywall(
    handler=my_handler,
    options={
        "kind": "tool",
        "name": "my_tool",
        "credits": 1
    }
)
```

### Attach to Existing Server

```python
from mcp.server import MCPServer

# Create your own MCP server
server = MCPServer()

# Attach payments integration
registrar = payments.mcp.attach(server)

# Register protected handlers
registrar.register_tool(
    name="hello",
    config={"description": "Hello tool"},
    handler=hello_handler,
    options={"credits": 1}
)

registrar.register_resource(
    name="config",
    template="data://{path}",
    config={"name": "Config"},
    handler=config_handler,
    options={"credits": 2}
)
```

## Complete Example

```python
import asyncio
from payments_py import Payments, PaymentOptions

# Initialize payments
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# Define handlers
async def analyze_code(args, context=None):
    """Analyze code for issues."""
    code = args.get("code", "")
    language = args.get("language", "python")

    # Your analysis logic here
    issues = analyze(code, language)

    return {
        "content": [{
            "type": "text",
            "text": f"Found {len(issues)} issues in {language} code."
        }]
    }

async def get_docs(uri, variables, context=None):
    """Return documentation."""
    topic = variables.get("topic", "general")

    return {
        "contents": [{
            "uri": str(uri),
            "mimeType": "text/markdown",
            "text": f"# Documentation for {topic}\n\nContent here..."
        }]
    }

async def code_review_prompt(args, context=None):
    """Generate code review prompt."""
    return {
        "messages": [{
            "role": "user",
            "content": {
                "type": "text",
                "text": "Please review the following code for best practices..."
            }
        }]
    }

# Register handlers
payments.mcp.register_tool(
    "analyze_code",
    {
        "description": "Analyzes code for potential issues",
        "inputSchema": {
            "type": "object",
            "properties": {
                "code": {"type": "string"},
                "language": {"type": "string", "default": "python"}
            },
            "required": ["code"]
        }
    },
    analyze_code,
    {"credits": 5}  # 5 credits per analysis
)

payments.mcp.register_resource(
    "docs://{topic}",
    {
        "name": "Documentation",
        "description": "Technical documentation",
        "mimeType": "text/markdown"
    },
    get_docs,
    {"credits": 1}
)

payments.mcp.register_prompt(
    "code_review",
    {
        "name": "Code Review",
        "description": "Generates a code review prompt"
    },
    code_review_prompt,
    {"credits": 2}
)

# Start server
async def main():
    result = await payments.mcp.start({
        "port": 5001,
        "planId": "plan-123",
        "serverName": "code-assistant-mcp",
        "version": "1.0.0"
    })

    print(f"MCP Server running at {result['info']['baseUrl']}")
    print(f"Tools: {result['info']['tools']}")
    print(f"Resources: {result['info']['resources']}")
    print(f"Prompts: {result['info']['prompts']}")

    # Keep running
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        await payments.mcp.stop()

asyncio.run(main())
```

## Server Configuration

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `port` | `int` | Yes | Server port |
| `planId` | `str` | Yes | Nevermined plan ID the server charges against |
| `serverName` | `str` | Yes | Human-readable name |
| `agentId` | `str` | No | Nevermined agent DID (informational; the facilitator resolves access from the plan + token) |
| `baseUrl` | `str` | No | Base URL (default: localhost) |
| `version` | `str` | No | Server version |
| `description` | `str` | No | Server description |

## Handler Options

| Option | Type | Description |
|--------|------|-------------|
| `credits` | `int` or `callable` | Credits to consume per call |
| `planId` | `str` | Optional override for the plan ID (otherwise inferred from token) |
| `maxAmount` | `int` | Max credits to verify during authentication (default: `1`) |
| `onRedeemError` | `str` | `"ignore"` (default) or `"propagate"` to raise on redemption failure |

## In-band x402 signaling (`_meta`)

The MCP transport follows the [x402 v2 MCP transport specification](https://github.com/coinbase/x402/blob/main/specs/transports-v2/mcp.md): payments are signalled **in band** through the MCP tool-call machinery, not via HTTP status codes or headers.

**Request — payment payload.** The client sends the x402 `PaymentPayload` as plain JSON in the tool-call request params under `_meta["x402/payment"]`:

```json
{
  "method": "tools/call",
  "params": {
    "name": "premium_tool",
    "arguments": { "...": "..." },
    "_meta": { "x402/payment": { "x402Version": 2, "accepted": { "...": "..." }, "payload": { "...": "..." } } }
  }
}
```

For backward compatibility the server still falls back to reading the access token from the `Authorization: Bearer` header when `_meta["x402/payment"]` is absent, but that path is deprecated under the x402 v2 MCP transport.

**Response — settlement receipt.** On a successful paid call the SDK injects the settlement receipt under the spec key `_meta["x402/payment-response"]`, alongside Nevermined-specific observability under the namespaced `_meta["nevermined/credits"]` key (not part of the x402 spec):

```python
{
    "content": [{"type": "text", "text": "result"}],
    "_meta": {
        "x402/payment-response": {
            "success": True,
            "transaction": "0xabc...",
            "network": "eip155:84532",
            "payer": "0x123..."
        },
        "nevermined/credits": {
            "success": True,
            "txHash": "0xabc...",
            "creditsRedeemed": "5",
            "planId": "plan-123",
            "subscriberAddress": "0x123..."
        }
    }
}
```

**Payment required.** When the caller has not paid (or cannot be authorized), the tool returns an **error tool result** carrying the `PaymentRequired` object in both `structuredContent` (the object) and `content[0].text` (its JSON-stringified copy):

```python
{
    "isError": True,
    "structuredContent": {
        "x402Version": 2,
        "error": "payment required",
        "resource": { "url": "mcp://my-server/tools/premium_tool", "...": "..." },
        "accepts": [ { "scheme": "nvm:erc4337", "planId": "plan-123", "...": "..." } ]
    },
    "content": [{"type": "text", "text": "{\"x402Version\": 2, ...}"}]
}
```

**Settlement failure after execution.** If settlement fails *after* the tool has already executed, the server returns the same payment-required error result and **suppresses the tool's content** — a paid result is never delivered without payment landing.

> **Note on `onRedeemError`.** Under the in-band MCP transport, content is *always* suppressed when post-execution settlement fails — even with the default `onRedeemError: "ignore"` — because the x402 v2 spec forbids delivering a paid result without settlement. `onRedeemError` no longer controls whether content is returned; it now only affects the *kind* of error surfaced: `"ignore"` yields the in-band payment-required error result, while `"propagate"` raises a JSON-RPC misconfiguration error instead.

| `nevermined/credits` field | Type | Description |
|----------------------------|------|-------------|
| `success` | `bool` | Whether credit redemption succeeded |
| `txHash` | `str` or `None` | Blockchain transaction hash (only on success) |
| `creditsRedeemed` | `str` | Number of credits burned (`"0"` on failure) |
| `planId` | `str` | Plan used for the operation |
| `subscriberAddress` | `str` | Subscriber's wallet address |
| `errorReason` | `str` | Error message (only on failure) |

## Endpoints

The MCP server exposes:

- `/.well-known/oauth-authorization-server` - OAuth 2.1 discovery
- `/.well-known/oauth-protected-resource` - Resource metadata
- `/.well-known/oauth-protected-resource/mcp` - MCP-specific protected resource metadata
- `/register` - Client registration
- `/mcp` - MCP protocol endpoint (POST/GET/DELETE)
- `/health` - Health check

## OAuth `401` vs. payment-required

OAuth and x402 payment-required live at **different layers**, so they never collide:

| Layer | Signal | Meaning |
|-------|--------|---------|
| HTTP transport | `401 Unauthorized` + `WWW-Authenticate: Bearer` (OAuth 2.1) | The request is not authenticated; follow OAuth discovery to obtain a token. |
| MCP tool call | tool result with `isError: true` + `PaymentRequired` in `structuredContent` | The caller is authenticated but has not paid for this tool. |

Because payment-required is signalled **in band** as a tool result (not as an HTTP `402`), there is no clash with the OAuth `401` challenge and no need to special-case the `/mcp` status code. The `/mcp` endpoint keeps the standard OAuth `401` behavior; payment is negotiated entirely through the tool-call `_meta` / tool-result mechanism described above.

x402 discovery is therefore **implicit on the first tool call**: a client that has not paid receives the `PaymentRequired` object (with its `accepts` array) in the error tool result and pays on the next call. There is no `/.well-known/x402-payment` endpoint.

## Next Steps

- [A2A Integration](10-a2a-integration.md) - Agent-to-Agent protocol
- [x402 Protocol](11-x402.md) - Payment protocol details
