"""
Constants for AgentCore x402 Integration.
"""

# x402 HTTP Transport header names (v2 spec)
# @see https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md
X402_HEADERS = {
    # Client sends payment token in this header
    "PAYMENT_SIGNATURE": "payment-signature",
    # Server sends PaymentRequired in this header (base64-encoded)
    "PAYMENT_REQUIRED": "payment-required",
    # Server sends settlement receipt in this header (base64-encoded)
    "PAYMENT_RESPONSE": "payment-response",
    # Internal: passes agent_request_id from REQUEST to RESPONSE phase
    "AGENT_REQUEST_ID": "x-nvm-agent-request-id",
}

# MCP JSON-RPC 2.0 methods
MCP_METHODS = {
    "TOOLS_CALL": "tools/call",
    "TOOLS_LIST": "tools/list",
    "RESOURCES_LIST": "resources/list",
    "RESOURCES_READ": "resources/read",
    "PROMPTS_LIST": "prompts/list",
    "PROMPTS_GET": "prompts/get",
}

# Default billable methods
DEFAULT_BILLABLE_METHODS = [MCP_METHODS["TOOLS_CALL"]]

# Interceptor output version
INTERCEPTOR_OUTPUT_VERSION = "1.0"
