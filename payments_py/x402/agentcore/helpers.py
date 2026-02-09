"""
Helper functions for AgentCore x402 Integration.
"""

import base64
import json
from typing import Any, Optional

from payments_py.x402.types import X402PaymentRequired, SettleResponse

from .types import (
    InterceptorOutput,
    MCPRequestBody,
)
from .constants import X402_HEADERS, INTERCEPTOR_OUTPUT_VERSION


def encode_header(data: dict) -> str:
    """Encode a dict as base64 JSON for x402 headers."""
    return base64.b64encode(json.dumps(data).encode()).decode()


def decode_header(header_value: str) -> dict:
    """Decode a base64 JSON x402 header."""
    try:
        return json.loads(base64.b64decode(header_value).decode())
    except Exception:
        return {}


def extract_token(headers: dict[str, str], token_headers: list[str]) -> Optional[str]:
    """
    Extract x402 access token from request headers.

    Checks multiple header name variants (case-insensitive).
    """
    # Normalize header keys to lowercase for comparison
    normalized = {k.lower(): v for k, v in headers.items()}

    for header_name in token_headers:
        value = normalized.get(header_name.lower())
        if value:
            return value

    return None


def extract_tool_name(body: MCPRequestBody) -> Optional[str]:
    """
    Extract the tool name from MCP request body.

    Handles the AgentCore format: "TargetName___tool_name"
    """
    if body.method != "tools/call" or not body.params:
        return None

    name = body.params.name

    # AgentCore prefixes tool names with target: "Target1___getPatient"
    if "___" in name:
        return name.split("___")[-1]

    return name


def extract_credits_to_charge(
    response_body: dict[str, Any],
    response_headers: Optional[dict[str, str]] = None,
    default: int = 1,
) -> int:
    """
    Extract credits to charge from MCP response.

    Searches in order of priority:
    1. result._meta.creditsToCharge (MCP standard)
    2. X-Credits-To-Charge header
    3. result.content[].text JSON with creditsToCharge
    4. body.creditsToCharge (direct)
    5. Default value

    Compatible with MCP, OpenAPI, Lambda raw targets.
    """
    response_headers = response_headers or {}
    result = response_body.get("result", {})

    if isinstance(result, dict):
        # 1. Try _meta (MCP standard)
        meta = result.get("_meta", {})
        if isinstance(meta, dict) and "creditsToCharge" in meta:
            return int(meta["creditsToCharge"])

    # 2. Try HTTP header
    header_value = response_headers.get(
        "X-Credits-To-Charge"
    ) or response_headers.get("x-credits-to-charge")
    if header_value:
        return int(header_value)

    # 3. Try content text (OpenAPI/Lambda raw wrapped by Gateway)
    if isinstance(result, dict):
        content = result.get("content", [])
        if content and isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    try:
                        text_content = json.loads(item.get("text", "{}"))
                        if isinstance(text_content, dict) and "creditsToCharge" in text_content:
                            return int(text_content["creditsToCharge"])
                    except (json.JSONDecodeError, TypeError):
                        pass

    # 4. Try direct body
    if "creditsToCharge" in response_body:
        return int(response_body["creditsToCharge"])

    # 5. Default
    return default


def build_402_response(
    payment_required: X402PaymentRequired,
    rpc_id: str = "1",
    message: str = "Payment required to access this resource",
) -> InterceptorOutput:
    """
    Build a 402 Payment Required response in MCP format.

    AgentCore Gateway requires:
    - HTTP 200 status (not 402)
    - isError: true in result
    - payment-required header (x402 standard)
    """
    payment_required_b64 = encode_header(payment_required.model_dump(by_alias=True))

    error_body = {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "result": {
            "isError": True,
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {"error": "Payment required", "code": 402, "message": message}
                    ),
                }
            ],
        },
    }

    return InterceptorOutput(
        interceptor_output_version=INTERCEPTOR_OUTPUT_VERSION,
        mcp={
            "transformedGatewayResponse": {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    X402_HEADERS["PAYMENT_REQUIRED"]: payment_required_b64,
                },
                "body": error_body,
            }
        },
    )


def build_success_response(
    headers: dict[str, str],
    body: dict[str, Any],
    settlement: SettleResponse,
    status_code: int = 200,
) -> InterceptorOutput:
    """
    Build a success response with payment-response header and _meta transaction data.
    """
    payment_response = {
        "success": settlement.success,
        "transactionHash": settlement.transaction,
        "network": settlement.network,
        "creditsRedeemed": settlement.credits_redeemed,
        "remainingBalance": settlement.remaining_balance,
    }

    new_headers = {
        **headers,
        X402_HEADERS["PAYMENT_RESPONSE"]: encode_header(payment_response),
    }

    # Add transaction data to _meta in the response body
    new_body = body.copy()
    if "result" in new_body and isinstance(new_body["result"], dict):
        result = new_body["result"].copy()
        meta = result.get("_meta", {})
        if isinstance(meta, dict):
            meta = meta.copy()
        else:
            meta = {}
        meta["x402"] = {
            "success": settlement.success,
            "transaction": settlement.transaction,
            "network": settlement.network,
            "creditsRedeemed": settlement.credits_redeemed,
            "remainingBalance": settlement.remaining_balance,
        }
        result["_meta"] = meta
        new_body["result"] = result

    return InterceptorOutput(
        interceptor_output_version=INTERCEPTOR_OUTPUT_VERSION,
        mcp={
            "transformedGatewayResponse": {
                "statusCode": status_code,
                "headers": new_headers,
                "body": new_body,
            }
        },
    )


def forward_request(
    headers: dict[str, str], body: dict[str, Any]
) -> InterceptorOutput:
    """Forward request without modification."""
    return InterceptorOutput(
        interceptor_output_version=INTERCEPTOR_OUTPUT_VERSION,
        mcp={
            "transformedGatewayRequest": {
                "headers": {"Content-Type": "application/json"},
                "body": body,
            }
        },
    )


def forward_response(
    headers: dict[str, str], body: dict[str, Any], status_code: int = 200
) -> InterceptorOutput:
    """Forward response without modification."""
    return InterceptorOutput(
        interceptor_output_version=INTERCEPTOR_OUTPUT_VERSION,
        mcp={
            "transformedGatewayResponse": {
                "statusCode": status_code,
                "headers": headers,
                "body": body,
            }
        },
    )
