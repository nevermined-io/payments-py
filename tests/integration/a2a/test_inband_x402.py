"""Integration tests for the in-band x402 v2 A2A payment transport.

Exercises the full HTTP -> middleware -> handler -> settle path of the
standards-compliant in-band flow defined by the Coinbase x402 v2 A2A transport
spec (https://github.com/coinbase/x402/blob/main/specs/transports-v2/a2a.md):

1. A payment-gated ``message/send`` with no header and no payload returns an
   ``input-required`` task carrying ``x402.payment.required``.
2. A ``message/send`` carrying ``x402.payment.payload`` verifies, executes,
   settles, and the resulting task carries ``x402.payment.status =
   payment-completed`` + ``x402.payment.receipts``. (Real clients correlate the
   payload to the prior payment-required task via ``message.taskId``; the
   server-side verify/execute/settle behaviour under test is identical.)
3. A settlement failure yields ``payment-failed`` + ``x402.payment.error`` and
   does NOT deliver the agent's content.

The deprecated ``payment-signature`` header path is covered separately in
``test_complete_message_send_flow.py`` (regression).
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from a2a.types import Artifact, TaskArtifactUpdateEvent

from payments_py.a2a.server import PaymentsA2AServer

# Reuse the battle-tested mocks/executor from the existing flow test.
from tests.integration.a2a.test_complete_message_send_flow import (
    DummyExecutor,
    MockPaymentsService,
    mock_decode_token,
)


class _ArtifactDummyExecutor(DummyExecutor):
    """DummyExecutor that ALSO emits the paid result as an artifact.

    The x402 A2A spec's own example delivers paid content as an artifact, so this
    lets the settlement-failure test prove suppression covers artifacts and not
    only the status message.
    """

    async def execute(self, context, event_queue):  # noqa: ANN001, D401
        task_id = getattr(context, "task_id", None)
        context_id = getattr(context, "context_id", None) or "test-ctx"
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=task_id or "t",
                context_id=context_id,
                artifact=Artifact(
                    artifact_id="paid-artifact",
                    parts=[{"kind": "text", "text": "PAID_SECRET_RESULT"}],
                ),
            )
        )
        await super().execute(context, event_queue)


AGENT_CARD = {
    "capabilities": {
        "extensions": [
            {
                "uri": "urn:nevermined:payment",
                "params": {
                    "agentId": "test-agent-inband",
                    "credits": 10,
                    "planId": "test-plan",
                    "paymentType": "credits",
                },
            }
        ]
    },
}


def _payment_payload() -> dict:
    """A v2 PaymentPayload object as it travels in x402.payment.payload."""
    return {
        "x402Version": 2,
        "accepted": {
            "scheme": "nvm:erc4337",
            "network": "eip155:84532",
            "planId": "test-plan",
            "extra": {"version": "1"},
        },
        "payload": {
            "signature": "0x123",
            "authorization": {"from": "0xTestSubscriber"},
        },
    }


def _make_client(payments, executor) -> TestClient:
    result = PaymentsA2AServer.start(
        payments_service=payments,  # type: ignore[arg-type]
        agent_card=AGENT_CARD,
        executor=executor,
        port=0,
        base_path="/rpc",
        expose_default_routes=True,
    )
    return TestClient(result.app)


# ---------------------------------------------------------------------------
# 1. First contact -> input-required payment-required task
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_inband_first_contact_returns_payment_required_task():
    mock_payments = MockPaymentsService()
    client = _make_client(mock_payments, DummyExecutor())

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-first",
                "contextId": "ctx-first",
                "role": "user",
                "parts": [{"kind": "text", "text": "do the thing"}],
            }
        },
    }
    response = client.post("/rpc", json=payload)

    assert response.status_code == 200
    task = response.json()["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] == "input-required"
    meta = task["status"]["message"]["metadata"]
    assert meta["x402.payment.status"] == "payment-required"
    pr = meta["x402.payment.required"]
    assert pr["x402Version"] == 2
    assert pr["accepts"][0]["planId"] == "test-plan"
    assert pr["accepts"][0]["extra"]["agentId"] == "test-agent-inband"
    # Agent must not run and nothing settles before payment.
    assert mock_payments.facilitator.validation_call_count == 0
    assert mock_payments.facilitator.settle_call_count == 0


# ---------------------------------------------------------------------------
# 2. Follow-up payload -> verify + execute + settle + receipts
# ---------------------------------------------------------------------------
@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token", mock_decode_token
)
@pytest.mark.asyncio
async def test_inband_payload_verifies_executes_and_settles():
    mock_payments = MockPaymentsService()
    client = _make_client(mock_payments, DummyExecutor(credits_to_use=3))

    payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-pay",
                "contextId": "ctx-pay",
                "role": "user",
                "parts": [{"kind": "text", "text": "here is my payment"}],
                "metadata": {
                    "x402.payment.status": "payment-submitted",
                    "x402.payment.payload": _payment_payload(),
                },
            }
        },
    }
    response = client.post("/rpc", json=payload)

    assert response.status_code == 200, response.text
    task = response.json()["result"]
    assert task["status"]["state"] == "completed"
    meta = task["status"]["message"]["metadata"]
    # Spec settlement signalling.
    assert meta["x402.payment.status"] == "payment-completed"
    receipts = meta["x402.payment.receipts"]
    assert receipts["success"] is True
    assert receipts["transaction"].startswith("0xtest")
    # The token was carried in-band: verify + settle both ran.
    assert mock_payments.facilitator.validation_call_count == 1
    assert mock_payments.facilitator.settle_call_count == 1
    assert mock_payments.facilitator.last_settle_credits == 3
    # Agent content is still delivered on success.
    assert (
        task["status"]["message"]["parts"][0]["text"]
        == "Request completed successfully!"
    )


# ---------------------------------------------------------------------------
# 3a. Verification failure -> payment-failed, agent never runs
# ---------------------------------------------------------------------------
@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token", mock_decode_token
)
@pytest.mark.asyncio
async def test_inband_verification_failure_returns_payment_failed():
    mock_payments = MockPaymentsService()
    mock_payments.facilitator.should_fail_validation = True
    client = _make_client(mock_payments, DummyExecutor())

    payload = {
        "jsonrpc": "2.0",
        "id": 3,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-badpay",
                "contextId": "ctx-badpay",
                "role": "user",
                "parts": [{"kind": "text", "text": "bad payment"}],
                "metadata": {
                    "x402.payment.status": "payment-submitted",
                    "x402.payment.payload": _payment_payload(),
                },
            }
        },
    }
    response = client.post("/rpc", json=payload)

    assert response.status_code == 200, response.text
    task = response.json()["result"]
    assert task["status"]["state"] == "failed"
    meta = task["status"]["message"]["metadata"]
    assert meta["x402.payment.status"] == "payment-failed"
    assert "x402.payment.error" in meta
    # Verification was attempted, but the agent never ran and nothing settled.
    assert mock_payments.facilitator.validation_call_count == 1
    assert mock_payments.facilitator.settle_call_count == 0
    assert (
        task["status"]["message"]["parts"][0]["text"]
        != "Request completed successfully!"
    )


# ---------------------------------------------------------------------------
# 3b. Settlement failure -> payment-failed, agent content suppressed
# ---------------------------------------------------------------------------
@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token", mock_decode_token
)
@pytest.mark.asyncio
async def test_inband_settlement_failure_suppresses_content():
    mock_payments = MockPaymentsService()
    mock_payments.facilitator.should_fail_settle = True
    # Executor emits the paid result as an artifact too, so suppression is proven
    # against artifacts, not only the status message.
    client = _make_client(mock_payments, _ArtifactDummyExecutor(credits_to_use=4))

    payload = {
        "jsonrpc": "2.0",
        "id": 4,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-settlefail",
                "contextId": "ctx-settlefail",
                "role": "user",
                "parts": [{"kind": "text", "text": "pay then fail settle"}],
                "metadata": {
                    "x402.payment.status": "payment-submitted",
                    "x402.payment.payload": _payment_payload(),
                },
            }
        },
    }
    response = client.post("/rpc", json=payload)

    assert response.status_code == 200, response.text
    task = response.json()["result"]
    # Settlement failed after execution: task is forced failed and the paid
    # content is dropped (never deliver paid content without settlement).
    assert task["status"]["state"] == "failed"
    meta = task["status"]["message"]["metadata"]
    assert meta["x402.payment.status"] == "payment-failed"
    assert "x402.payment.error" in meta
    # Paid content suppressed in artifacts AND anywhere else in the task.
    assert task.get("artifacts") in (None, [])
    assert "PAID_SECRET_RESULT" not in response.text
    # Verify ran (token was valid) and settle was attempted once.
    assert mock_payments.facilitator.validation_call_count == 1
    assert mock_payments.facilitator.settle_call_count == 1


# ---------------------------------------------------------------------------
# 4. Deprecated payment-signature header path still works (regression).
# ---------------------------------------------------------------------------
@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token", mock_decode_token
)
@pytest.mark.asyncio
async def test_legacy_header_path_still_settles_without_inband_metadata():
    """The deprecated ``payment-signature`` header path remains functional.

    It settles credits and returns a ``completed`` task, but does NOT stamp the
    in-band x402 metadata (that is reserved for the standards in-band flow).
    """
    mock_payments = MockPaymentsService()
    client = _make_client(mock_payments, DummyExecutor(credits_to_use=2))

    payload = {
        "jsonrpc": "2.0",
        "id": 5,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-legacy",
                "contextId": "ctx-legacy",
                "role": "user",
                "parts": [{"kind": "text", "text": "legacy header pay"}],
            }
        },
    }
    response = client.post(
        "/rpc", json=payload, headers={"payment-signature": "LEGACY_TOKEN"}
    )

    assert response.status_code == 200, response.text
    task = response.json()["result"]
    assert task["status"]["state"] == "completed"
    # Legacy path: credits settled, agent content delivered, no in-band metadata.
    assert mock_payments.facilitator.validation_call_count == 1
    assert mock_payments.facilitator.settle_call_count == 1
    assert mock_payments.facilitator.last_settle_credits == 2
    assert (
        task["status"]["message"]["parts"][0]["text"]
        == "Request completed successfully!"
    )
    meta = task["status"]["message"].get("metadata") or {}
    assert "x402.payment.status" not in meta
    assert "x402.payment.receipts" not in meta
