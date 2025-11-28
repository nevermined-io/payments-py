"""
X402 + A2A Integration Utilities.

This module provides utilities for managing x402 payment protocol state
within A2A (Agent-to-Agent) messages and tasks.

These utilities bridge the x402 payment protocol with the A2A communication
protocol, enabling payment-protected agent interactions.

Note: PaymentStatus and x402Metadata constants are defined here to match the
A2A x402 specification exactly. They cannot be imported from x402_a2a due to
circular dependency concerns (x402_a2a depends on payments-py).
"""

import logging
from typing import Optional, Union

from a2a.types import Message, Task, TaskState, TaskStatus, TextPart

# NOTE: PaymentStatus and x402Metadata are defined by the A2A x402 specification:
# https://github.com/google-a2a/a2a-x402/blob/main/spec/v0.1/spec.md
#
# These constants are also defined in x402_a2a.types.state, but we cannot import
# from x402_a2a here as it would create a circular dependency (x402_a2a depends
# on payments-py). The values here MUST match the specification exactly.
#
# If these values ever change in the spec, they must be updated here as well.

from enum import Enum


class PaymentStatus(str, Enum):
    """
    Protocol-defined payment states for A2A x402 flow.

    As defined in: https://github.com/google-a2a/a2a-x402/blob/main/spec/v0.1/spec.md
    Section 6: State Management

    These values are part of the A2A x402 specification and must not be changed.
    """

    PAYMENT_REQUIRED = "payment-required"  # Payment requirements sent to client
    PAYMENT_SUBMITTED = "payment-submitted"  # Payment payload received by server
    PAYMENT_VERIFIED = "payment-verified"  # Payment verified by facilitator
    PAYMENT_REJECTED = "payment-rejected"  # Payment requirements rejected
    PAYMENT_COMPLETED = "payment-completed"  # Payment settled successfully
    PAYMENT_FAILED = "payment-failed"  # Payment processing failed


class x402Metadata:
    """
    Spec-defined metadata key constants for A2A x402 protocol.

    As defined in: https://github.com/google-a2a/a2a-x402/blob/main/spec/v0.1/spec.md
    Section 6: State Management

    These keys are part of the A2A x402 specification and must not be changed.
    """

    STATUS_KEY = "x402.payment.status"  # Current payment flow stage
    REQUIRED_KEY = "x402.payment.required"  # x402PaymentRequiredResponse object
    PAYLOAD_KEY = "x402.payment.payload"  # PaymentPayload object
    RECEIPTS_KEY = "x402.payment.receipts"  # Array of SettleResponse objects
    ERROR_KEY = "x402.payment.error"  # Error code on failure


from .types import (
    NvmPaymentRequiredResponse,
    PaymentPayload,
    SettleResponse,
)
from .types_v2 import PaymentPayloadV2
from .types_v2 import PaymentRequiredResponseV2

logger = logging.getLogger(__name__)

# Re-export protocol-defined types for convenience
# These are imported, not defined here
X402Metadata = x402Metadata  # Alias for consistency with naming convention


def _parse_payment_payload(
    payload_data: dict,
) -> Union[PaymentPayload, PaymentPayloadV2]:
    """
    Parse the payment payload using the appropriate Pydantic model.

    Supports both v1 and v2 formats (both use x402Version/x402_version).

    Args:
        payload_data: Raw payment payload dictionary

    Returns:
        Parsed PaymentPayload (v1) or PaymentPayloadV2 (v2)
    """
    # Auto-detect v1 vs v2
    x402_version = payload_data.get("x402Version", payload_data.get("x402_version", 1))

    if x402_version == 2:
        # V2: Parse as PaymentPayloadV2
        return PaymentPayloadV2.model_validate(payload_data)
    else:
        # V1: Parse as PaymentPayload
        return PaymentPayload.model_validate(payload_data)


class X402A2AUtils:
    """
    Utilities for managing x402 payment state in A2A messages and tasks.

    This class provides methods to:
    - Extract payment status, requirements, and payloads from A2A messages/tasks
    - Create payment-related A2A tasks
    - Manage x402 metadata within the A2A protocol

    Example:
        >>> utils = X402A2AUtils()
        >>>
        >>> # Extract payment requirements from a task
        >>> requirements = utils.get_payment_requirements(task)
        >>>
        >>> # Check payment status
        >>> status = utils.get_payment_status(task)
        >>>
        >>> # Create a payment required task
        >>> payment_task = utils.create_payment_required_task(task, payment_required)
    """

    STATUS_KEY = X402Metadata.STATUS_KEY
    REQUIRED_KEY = X402Metadata.REQUIRED_KEY
    PAYLOAD_KEY = X402Metadata.PAYLOAD_KEY
    RECEIPTS_KEY = X402Metadata.RECEIPTS_KEY
    ERROR_KEY = X402Metadata.ERROR_KEY

    def get_payment_status_from_message(self, message: Message) -> Optional[str]:
        """
        Extract payment status from message metadata.

        Args:
            message: A2A Message object

        Returns:
            Payment status string or None
        """
        if not message or not hasattr(message, "metadata") or not message.metadata:
            return None

        status_value = message.metadata.get(self.STATUS_KEY)
        return status_value if status_value else None

    def get_payment_status_from_task(self, task: Task) -> Optional[str]:
        """
        Extract payment status from task's status message metadata.

        Args:
            task: A2A Task object

        Returns:
            Payment status string or None
        """
        if not task or not hasattr(task, "status") or not task.status:
            return None
        if not hasattr(task.status, "message") or not task.status.message:
            return None

        return self.get_payment_status_from_message(task.status.message)

    def get_payment_status(self, task: Task) -> Optional[str]:
        """
        Extract payment status from task.

        Args:
            task: A2A Task object

        Returns:
            Payment status string or None
        """
        return self.get_payment_status_from_task(task)

    def get_payment_requirements_from_message(
        self, message: Message
    ) -> Optional[Union[NvmPaymentRequiredResponse, PaymentRequiredResponseV2]]:
        """
        Extract payment requirements from message metadata.

        Supports both v1 (NvmPaymentRequiredResponse) and v2 (PaymentRequiredResponseV2).
        Auto-detects version from the data.

        Args:
            message: A2A Message object

        Returns:
            Payment requirements (v1 or v2) or None
        """
        if not message or not hasattr(message, "metadata") or not message.metadata:
            return None

        req_data = message.metadata.get(self.REQUIRED_KEY)
        if req_data:
            try:
                # Detect version from the data
                version = req_data.get("x402Version") or req_data.get("x402_version", 1)

                if version == 2:
                    # V2: Parse as PaymentRequiredResponseV2
                    return PaymentRequiredResponseV2.model_validate(req_data)
                else:
                    # V1: Parse as NvmPaymentRequiredResponse
                    return NvmPaymentRequiredResponse.model_validate(req_data)
            except Exception as e:
                logger.warning(f"Failed to parse payment requirements: {e}")
                return None
        return None

    def get_payment_requirements_from_task(
        self, task: Task
    ) -> Optional[Union[NvmPaymentRequiredResponse, PaymentRequiredResponseV2]]:
        """
        Extract payment requirements from task's status message metadata.

        Supports both v1 and v2 formats.

        Args:
            task: A2A Task object

        Returns:
            Payment requirements (v1 or v2) or None
        """
        if not task or not hasattr(task, "status") or not task.status:
            return None
        if not hasattr(task.status, "message") or not task.status.message:
            return None

        return self.get_payment_requirements_from_message(task.status.message)

    def get_payment_requirements(
        self, task: Task
    ) -> Optional[Union[NvmPaymentRequiredResponse, PaymentRequiredResponseV2]]:
        """
        Extract payment requirements from task.

        Supports both v1 (NvmPaymentRequiredResponse) and v2 (PaymentRequiredResponseV2).
        Auto-detects version and returns the appropriate type.

        Args:
            task: A2A Task object

        Returns:
            Payment requirements (v1 or v2) or None
        """
        return self.get_payment_requirements_from_task(task)

    def get_payment_payload_from_message(
        self, message: Message
    ) -> Optional[PaymentPayload]:
        """
        Extract payment payload from message metadata.

        Args:
            message: A2A Message object

        Returns:
            PaymentPayload or None
        """
        if not message or not hasattr(message, "metadata") or not message.metadata:
            return None

        payload_data = message.metadata.get(self.PAYLOAD_KEY)
        if payload_data:
            try:
                return _parse_payment_payload(payload_data)
            except Exception as e:
                logger.error(f"Failed to parse payment payload: {e}", exc_info=True)
                return None
        return None

    def get_payment_payload_from_task(self, task: Task) -> Optional[PaymentPayload]:
        """
        Extract payment payload from task's status message metadata.

        Args:
            task: A2A Task object

        Returns:
            PaymentPayload or None
        """
        if not task or not hasattr(task, "status") or not task.status:
            return None
        if not hasattr(task.status, "message") or not task.status.message:
            return None

        return self.get_payment_payload_from_message(task.status.message)

    def get_payment_payload(self, task: Task) -> Optional[PaymentPayload]:
        """
        Extract payment payload from task.

        Args:
            task: A2A Task object

        Returns:
            PaymentPayload or None
        """
        return self.get_payment_payload_from_task(task)

    def create_payment_required_task(
        self,
        task: Task,
        payment_required: Union[NvmPaymentRequiredResponse, PaymentRequiredResponseV2],
    ) -> Task:
        """
        Set task to payment required state with proper metadata.

        Args:
            task: A2A Task object
            payment_required: Payment requirements (v1 or v2)

        Returns:
            Updated task with payment required state
        """
        # Set task status to input-required as per A2A spec
        if task.status:
            task.status.state = TaskState.input_required
        else:
            task.status = TaskStatus(state=TaskState.input_required)

        # Ensure task has a status message for metadata
        if not hasattr(task.status, "message") or not task.status.message:
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[
                    TextPart(kind="text", text="Payment is required for this service.")
                ],
                metadata={},
            )

        # Ensure message has metadata
        if (
            not hasattr(task.status.message, "metadata")
            or not task.status.message.metadata
        ):
            task.status.message.metadata = {}

        task.status.message.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_REQUIRED
        task.status.message.metadata[self.REQUIRED_KEY] = payment_required.model_dump(
            by_alias=True
        )
        return task

    def record_payment_verified(self, task: Task) -> Task:
        """
        Record payment verification in task metadata.

        Args:
            task: A2A Task object

        Returns:
            Updated task with payment verified status
        """
        # Ensure task has a status message for metadata
        if not hasattr(task.status, "message") or not task.status.message:
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment verification recorded.")],
                metadata={},
            )

        # Ensure message has metadata
        if (
            not hasattr(task.status.message, "metadata")
            or not task.status.message.metadata
        ):
            task.status.message.metadata = {}

        task.status.message.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_VERIFIED
        return task

    def record_payment_success(
        self, task: Task, settle_response: SettleResponse
    ) -> Task:
        """
        Record successful payment in task metadata.

        Args:
            task: A2A Task object
            settle_response: Settlement response from facilitator

        Returns:
            Updated task with payment completed status
        """
        # Ensure task has a status message for metadata
        if not hasattr(task.status, "message") or not task.status.message:
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment completed successfully.")],
                metadata={},
            )

        # Ensure message has metadata
        if (
            not hasattr(task.status.message, "metadata")
            or not task.status.message.metadata
        ):
            task.status.message.metadata = {}

        task.status.message.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_COMPLETED

        # Store settlement receipt in spec-defined location
        if settle_response:
            task.status.message.metadata[self.RECEIPTS_KEY] = (
                settle_response.model_dump(by_alias=True)
            )

        return task

    def record_payment_failure(
        self, task: Task, error_code: str, error_response: SettleResponse
    ) -> Task:
        """
        Record payment failure in task metadata.

        Args:
            task: A2A Task object
            error_code: Error code
            error_response: Settlement response with error details

        Returns:
            Updated task with payment failed status
        """
        # Ensure task has a status message for metadata
        if not hasattr(task.status, "message") or not task.status.message:
            task.status.message = Message(
                messageId=f"{task.id}-status",
                role="agent",
                parts=[TextPart(kind="text", text="Payment failed.")],
                metadata={},
            )

        # Ensure message has metadata
        if (
            not hasattr(task.status.message, "metadata")
            or not task.status.message.metadata
        ):
            task.status.message.metadata = {}

        task.status.message.metadata[self.STATUS_KEY] = PaymentStatus.PAYMENT_FAILED
        task.status.message.metadata[self.ERROR_KEY] = {
            "code": error_code,
            "reason": (
                error_response.error_reason if error_response else "Unknown error"
            ),
        }

        return task


__all__ = [
    "X402A2AUtils",
    "X402Metadata",  # Alias for x402Metadata
    "x402Metadata",  # Original protocol-defined name
    "PaymentStatus",  # Protocol-defined enum
]
