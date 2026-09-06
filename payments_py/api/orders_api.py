"""Orders API — browser-fiat Orders (nvm-monorepo epic #3238).

An Order is a merchant-initiated, off-plan charge for an arbitrary amount (the
Stripe PaymentIntent analog) that the buyer's browser confirms client-side —
no plan, no buyer Nevermined account, no delegation. Wraps
``apps/api/src/orders/`` in nvm-monorepo:

- ``POST /api/v1/orders`` — merchant, server-to-server, authenticated with an
  **organization-scoped** NVM API key. The API reads the merchant organization
  from the key's own org tag, so a personal key is refused with
  ``BCK.ORDER.0003``; :meth:`Payments.set_organization_id` (the
  ``X-Current-Org-Id`` header) does not substitute for an org-scoped key.
- ``GET /api/v1/orders/{id}`` — anonymous; the unguessable id is the sole
  access control, so no API key is sent on that call.

This client is the merchant's: a :class:`Payments` instance is always
constructed with an NVM API key. The buyer never needs one — the buyer's
browser confirms the ``client_secret`` with Stripe.js and can poll the GET
endpoint directly, which is why :meth:`OrdersAPI.get_order` sends no key.
"""

import json
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from payments_py.api.base_payments import BasePaymentsAPI, _stringify_unsafe_ints
from payments_py.api.nvm_api import API_URL_CREATE_ORDER, API_URL_GET_ORDER
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import CreateOrderResult, Order, PaymentOptions


class OrdersAPI(BasePaymentsAPI):
    """Browser-fiat Orders: create a charge, read its buyer-safe view.

    Example::

        payments = Payments.get_instance(PaymentOptions(nvm_api_key=ORG_KEY))
        created = payments.orders.create_order(3437, description="Cart")
        # hand created.client_secret to the browser (Stripe.js confirm) ...
        order = payments.orders.get_order(created.order_id)
        if order.status == "paid":
            fulfil(order)
    """

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "OrdersAPI":
        return cls(options)

    def create_order(
        self,
        amount_minor: int,
        currency: str = "usd",
        *,
        description: Optional[str] = None,
        buyer_ref: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        line_items: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        capture_mode: Optional[str] = None,
        payment_provider: Optional[str] = None,
    ) -> CreateOrderResult:
        """Create an Order and its PaymentIntent (``POST /api/v1/orders``).

        Oriented to merchants: the NVM API key must be scoped to an active
        organization whose Stripe Connect account can receive card payments.

        Args:
            amount_minor: Charge amount in USD cents (at least ``100``,
                i.e. $1.00). The API validates the upper bound
                (``BCK.ORDER.0001``); a deployment may enforce a lower
                per-order cap (``BCK.ORDER.0003``).
            currency: ISO currency, lower-cased. Phase 1 is USD-only.
            description: Human-readable description of the charge (max 1024
                chars).
            buyer_ref: Opaque merchant-supplied buyer reference, e.g. the
                merchant's own order id (max 255 chars).
            idempotency_key: A retried create with the same key returns the
                same Order and ``client_secret`` (max 255 chars).
            line_items: Cart line items, recorded verbatim and opaque to the
                API.
            metadata: Opaque merchant metadata, recorded verbatim.
            capture_mode: Stripe capture mode. Phase 1 supports
                ``"automatic"`` only (the default).
            payment_provider: PSP that settles the Order. Phase 1 implements
                ``"stripe"`` only (the default).

        Returns:
            The new Order id, its status and — while payable — the
            ``client_secret`` the browser confirms against.

        Raises:
            PaymentsError: carrying the backend catalogue code —
                ``BCK.ORDER.0001`` (invalid request), ``BCK.ORDER.0003`` (not
                an active organization / over the per-order cap),
                ``BCK.ORDER.0007`` (idempotency-key conflict),
                ``BCK.ORDER.0010`` (velocity cap, retryable),
                ``BCK.ORDER.0004`` / ``0005`` (Connect account / PaymentIntent
                failure, no money moved). A refusal without a catalogue code
                (e.g. a gateway or throttle response) carries ``http_<status>``
                instead.
        """
        optional = {
            "description": description,
            "buyerRef": buyer_ref,
            "idempotencyKey": idempotency_key,
            "lineItems": line_items,
            "metadata": metadata,
            "captureMode": capture_mode,
            "paymentProvider": payment_provider,
        }
        body = {"amountMinor": amount_minor, "currency": currency}
        body.update({k: v for k, v in optional.items() if v is not None})
        # Serialised here rather than via ``get_backend_http_options(body=...)``:
        # that helper camelCases dict keys RECURSIVELY, which would rewrite the
        # merchant's opaque ``metadata`` / ``line_items`` keys. The wire keys
        # above are already camelCase. The SDK-wide unsafe-int policy still
        # applies: an int above 2**53-1 anywhere in the payload is sent as a
        # decimal string, since the Node backend's JSON parser would otherwise
        # round it.
        options = self.get_backend_http_options("POST")
        url = f"{self.environment.backend}{API_URL_CREATE_ORDER}"
        payload = json.dumps(_stringify_unsafe_ints(body))
        response = requests.post(url, data=payload, **options)
        if not response.ok:
            raise PaymentsError.from_response(response, "Unable to create order")
        return CreateOrderResult.model_validate(response.json())

    def get_order(self, order_id: str) -> Order:
        """Read the buyer-safe view of an Order (``GET /api/v1/orders/{id}``).

        The endpoint is anonymous — the unguessable id is the sole access
        control — so this call sends no API key (the :class:`Payments`
        instance still needs one to be constructed). The response never
        includes the merchant identity or the fee, and carries
        ``client_secret`` only while the Order is payable.

        Args:
            order_id: The unguessable Order id returned by
                :meth:`create_order`.

        Returns:
            The :class:`Order` projection.

        Raises:
            PaymentsError: with code ``BCK.ORDER.0002`` when no Order has this
                id. The read endpoint is rate-limited — all anonymous callers
                behind one IP share a bucket of 60 requests per minute — and a
                throttled call carries no catalogue code, so it surfaces as
                code ``http_429``. That is distinct from the create-side
                velocity cap ``BCK.ORDER.0010``; poll sparingly and back off on
                ``http_429``.
        """
        # Encode the id so a stray ``?``, ``#`` or ``..`` cannot retarget the
        # request (the id is buyer-facing and often arrives from a URL param).
        path = API_URL_GET_ORDER.format(order_id=quote(order_id, safe=""))
        url = f"{self.environment.backend}{path}"
        response = requests.get(url, **self.get_public_http_options("GET"))
        if not response.ok:
            raise PaymentsError.from_response(response, "Unable to get order")
        return Order.model_validate(response.json())
