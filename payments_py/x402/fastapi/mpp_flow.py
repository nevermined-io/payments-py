"""
The MPP request path for the FastAPI middleware.

Kept whole and separate from the x402 path so that with ``mpp`` unset nothing
here runs and the x402 behaviour is unchanged.

Two things differ from the Express implementation this is ported from
(``nevermined-io/payments`` #417), because the framework differs, not because
the protocol does:

- **No raw-body capture hook.** Express has already parsed the body by the time
  a middleware runs, so the TS side needs ``express.json({verify: captureRawBody})``
  and refuses (500/400) when it was not wired. Starlette hands the middleware the
  raw bytes directly, so ``bind_body`` reads them here and replays them to the
  handler; the two refusal branches have no counterpart and no route can be
  misconfigured into an unbound challenge.
- **No detached-settle branch.** ``BaseHTTPMiddleware`` buffers the handler's
  response before this middleware returns it, so headers are never already on
  the wire when settlement runs: the receipt always attaches, and the delivery
  probe the TS side needs for streamed responses has nothing to probe.
"""

import base64
import inspect
import logging
from typing import Any, Awaitable, Callable, Optional

from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from payments_py.mpp.errors import (
    MppCredentialRejectedError,
    MppError,
    MppSettlementOutcomeUnknown,
    MppSettlementOutcomeUnknownError,
    is_retryable_mpp_code,
)
from payments_py.mpp.mpp_api import (
    IssueMppChallengeParams,
    RedeemMppParams,
    normalize_credits,
)
from payments_py.x402.fastapi.mpp_support import (
    EMPTY_BODY_DIGEST,
    MPP_HEADERS,
    claim_credential,
    compute_body_digest,
    extract_credential,
    is_credential_spent,
    mark_credential_spent,
    mpp_credential_id,
    mpp_resource,
    mpp_verb,
    release_credential,
)
from payments_py.x402.types import PaymentContext

logger = logging.getLogger("payments_py.x402.fastapi.middleware")


async def _maybe_await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


async def _read_and_replay_body(request: Request) -> bytes:
    """Read the raw request body and make it readable again downstream.

    ``BaseHTTPMiddleware`` gives the handler its own ``Request`` built from the
    same ASGI ``receive`` channel, which is single-use — so reading the body here
    would otherwise leave the handler with an empty one. Re-arming ``receive``
    with the bytes just read keeps the handler's view identical to the buyer's.
    """
    body = await request.body()

    async def replay() -> dict:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = replay  # noqa: SLF001 — the documented re-arm
    return body


class MppFlow:
    """One MPP request, from challenge to settlement."""

    def __init__(
        self,
        request: Request,
        payments: Any,
        route_config: Any,
        payment_required: Any,
        bind_body: bool,
        options: Any,
    ):
        self.request = request
        self.payments = payments
        self.route_config = route_config
        self.payment_required = payment_required
        self.bind_body = bind_body
        self.options = options
        self.resource = mpp_resource(request)
        self.http_verb = mpp_verb(request)
        self.credits_to_charge: int = 0
        self.body_digest: Optional[str] = None
        self.verification: Any = None

    async def _notify_payment_error(self, error: Exception) -> Optional[Response]:
        """One policy for ``on_payment_error`` on MPP routes: it NOTIFIES, and
        this middleware keeps ownership of the response unless the hook returns
        one outright.

        The x402 branch lets the hook take over on every error. MPP cannot copy
        that wholesale: the protocol only lets a buyer make progress if the 402
        carries a fresh ``WWW-Authenticate`` challenge, so a seller who wired the
        hook for observability would silently strip the one thing the documented
        retry loop needs — and, in the other direction, an unpaid request sent a
        challenge but never notified the hook at all, so adding ``mpp=True`` to a
        working route would quietly stop those events.

        A hook that returns a ``Response`` has answered the request explicitly,
        which is the Python equivalent of the TS hook writing to ``res``, and it
        wins. A throwing hook is logged rather than propagated — it must not turn
        into a buyer-visible 500 on the path whose whole job is to hand back a
        challenge.
        """
        hook = getattr(self.options, "on_payment_error", None)
        if not hook:
            return None
        try:
            return await _maybe_await(hook(error, self.request))
        except Exception as hook_error:  # noqa: BLE001 — a hook bug is not the buyer's
            logger.error("MPP on_payment_error hook failed: %s", hook_error)
            return None

    async def _send_challenge(
        self, message: str, code: Optional[str] = None
    ) -> Response:
        """Mint and return the 402 that carries a fresh challenge.

        ``issue_challenge`` itself can fail (e.g. MPP is turned off on this
        environment: ``BCK.MPP.0002``). This is reached from several places, so a
        failure here must never propagate: unhandled it would skip a configured
        ``on_payment_error`` and hand the buyer a 500 with a traceback on every
        unauthenticated request to the route.
        """
        try:
            issued = self.payments.mpp.issue_challenge(
                IssueMppChallengeParams(
                    plan_id=self.route_config.plan_id,
                    # Normalized here (not left to issue_challenge) so the exact
                    # wire shape is visible to a mocked payments.mpp in tests,
                    # and so a non-integer credits function result is rejected
                    # before a mock could hide the defect by never validating it.
                    credits=normalize_credits(self.credits_to_charge),
                    agent_id=self.route_config.agent_id,
                    resource=self.resource,
                    http_verb=self.http_verb,
                    digest=self.body_digest,
                    description=self.route_config.description,
                )
            )
            challenge = issued["challenge"]
        except Exception as challenge_error:  # noqa: BLE001
            await self._notify_payment_error(challenge_error)
            logger.error("MPP challenge issuance failed: %s", challenge_error)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": (
                        "Unable to issue an MPP payment challenge. Please try "
                        "again later."
                    ),
                },
            )

        payment_required_json = self.payment_required.model_dump_json(by_alias=True)
        payment_required_base64 = base64.b64encode(
            payment_required_json.encode()
        ).decode()

        content = {"error": "Payment Required", "message": message}
        if code:
            # The backend's own BCK.MPP.* code rides along when we have one, so a
            # buyer can tell "this credential was refused" (terminal — paying
            # again with a fresh one is pointless) from "here is a fresh
            # challenge, pay it" (retryable). This echoes a distinction the
            # backend already publishes; it adds no new detail and does not
            # reopen the one-rejection-code forgery-oracle discipline.
            #
            # ``retryable`` is carried alongside the code as an explicit wire
            # signal rather than leaving every buyer to hardcode which codes are
            # exceptions to "code present means terminal".
            content["code"] = code
            content["retryable"] = is_retryable_mpp_code(code)

        return JSONResponse(
            status_code=402,
            content=content,
            headers={
                MPP_HEADERS["CHALLENGE"]: challenge,
                # Advertise x402 on the same 402 so an x402 buyer is unaffected.
                "payment-required": payment_required_base64,
            },
        )

    async def _resolve_credits(self) -> Optional[Response]:
        """Evaluate ``credits`` exactly once, here.

        Credits are sealed into the challenge, so MPP has no equivalent of the
        x402 re-evaluation at settle time; the backend settles the amount the
        challenge carries. A throw in a caller-supplied ``credits`` function (a DB
        lookup, a rate-table fetch) must not escape as a 500 with a traceback and
        no challenge while a configured ``on_payment_error`` never fired.
        """
        credits = self.route_config.credits
        try:
            self.credits_to_charge = (
                credits
                if isinstance(credits, int)
                else await _maybe_await(credits(self.request))
            )
        except Exception as credits_error:  # noqa: BLE001
            taken_over = await self._notify_payment_error(credits_error)
            logger.error("MPP credits evaluation failed: %s", credits_error)
            return taken_over or JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": "Unable to determine the price of this resource.",
                },
            )
        return None

    async def _resolve_body_digest(self) -> None:
        """Bind the challenge to the body's digest on a ``bind_body`` route.

        A request with no body binds the digest of zero bytes rather than nothing
        at all: leaving it unbound would let the buyer mint with an empty request
        and then attach any body they liked to the paid retry — the backend skips
        the comparison when the challenge carries no digest, so "unbound" means
        the BUYER decides whether ``bind_body`` applies.
        """
        if not self.bind_body:
            return
        raw = await _read_and_replay_body(self.request)
        self.body_digest = compute_body_digest(raw) if raw else EMPTY_BODY_DIGEST

    async def run(
        self, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        refusal = await self._resolve_credits()
        if refusal is not None:
            return refusal
        await self._resolve_body_digest()

        credential = extract_credential(self.request)
        if not credential:
            # An ABSENT Authorization header is deliberately NOT routed through
            # on_payment_error, unlike the x402 branch which does notify for a
            # missing token. The two protocols make "unpaid" mean different
            # things: an x402 access token is reusable, so a request arriving
            # without one is an anomaly worth an error event, while in MPP the
            # mint/redeem handshake makes the FIRST request of every payment
            # cycle credential-less by design — notifying there would fire
            # on_payment_error on every successful payment, drowning the
            # rejections and configuration failures the hook exists to surface.
            #
            # A PRESENT Authorization header that yielded no Payment scheme is
            # the opposite case. It means something between the buyer and here
            # rewrote the header — a gateway injecting its own Bearer, a reverse
            # proxy with its own auth — which puts the buyer in a silent infinite
            # loop: mint, pay, present, header rewritten, fresh challenge,
            # repeat. Every iteration costs the seller a real issue_challenge
            # round-trip, the buyer is never served, and the failure is invisible
            # on the only side that can fix it.
            if self.request.headers.get(MPP_HEADERS["CREDENTIAL"]):
                taken_over = await self._notify_payment_error(
                    MppCredentialRejectedError(
                        "An Authorization header was present but carried no MPP "
                        "Payment scheme. An intermediary may be rewriting it; "
                        "the buyer cannot make progress."
                    )
                )
                if taken_over is not None:
                    return taken_over
            return await self._send_challenge(
                "Payment required. Present the challenge credential in Authorization."
            )

        # The identity every guard below keys on. NOT the header bytes: those are
        # buyer-malleable while the backend collapses every variant onto ONE
        # burn, because its own idempotency key is this same decoded id. Keyed on
        # the bytes, single-use and the in-flight guard both cost what a guard
        # costs and guarantee nothing.
        credential_id = mpp_credential_id(credential)
        if not credential_id:
            undecodable = MppCredentialRejectedError("Credential rejected")
            taken_over = await self._notify_payment_error(undecodable)
            logger.error(
                "MPP credential carries no decodable challenge id; refused at the edge"
            )
            return taken_over or await self._send_challenge(
                undecodable.message, undecodable.code
            )

        # Already bought a response. Checked before verify_credential so a replay
        # costs no backend round-trip, and answered with a FRESH challenge rather
        # than a bare error so the buyer can make progress by paying again. The
        # code is BCK.MPP.0003 (non-retryable): a replay is a client-side bug,
        # and a buyer that blindly retried it would loop.
        #
        # This is an optimisation, not the guard: awaits follow before the claim
        # is taken, so the authoritative check is the one at the claim below.
        if is_credential_spent(credential_id):
            return await self._send_challenge(
                "Credential already used. Each credential buys exactly one "
                "response; pay the new challenge.",
                "BCK.MPP.0003",
            )

        try:
            if getattr(self.options, "on_before_verify", None):
                await _maybe_await(
                    self.options.on_before_verify(self.request, self.payment_required)
                )
            self.verification = verification = self.payments.mpp.verify_credential(
                RedeemMppParams(
                    credential=credential,
                    resource=self.resource,
                    http_verb=self.http_verb,
                    body_digest=self.body_digest,
                )
            )
        except Exception as error:  # noqa: BLE001
            taken_over = await self._notify_payment_error(error)
            # Every MPP rejection — expired, replayed, refused — is answered with
            # a fresh challenge, so a buyer can always make progress by paying
            # again. The backend's BCK.MPP.* code rides along so the buyer can
            # tell which kind of rejection this was; it is confined to BCK.MPP.*
            # so an unrelated code (network_error, http_500, a code from another
            # namespace) is never forwarded as if it were one of ours.
            code = (
                error.code
                if isinstance(error, MppError)
                and error.code
                and error.code.startswith("BCK.MPP.")
                else None
            )
            # Log the full detail for the seller's own diagnostics. The buyer
            # only ever sees a fixed generic message plus the coarse code:
            # forwarding the message verbatim would re-widen the anti-oracle
            # discipline, handing back a hint the backend deliberately withheld.
            logger.error("MPP credential verification failed: %s", error)
            return taken_over or await self._send_challenge("Credential rejected", code)

        if not _is_valid(verification):
            # This IS a credential rejection, even though the verify result
            # carries no code of its own. The wire contract is positional: any
            # 402 answering a request that presented a credential must carry a
            # code, or a buyer cannot tell this fresh-but-unmarked challenge
            # apart from "you had not paid yet" and mints a second credential for
            # a rejection that already proved terminal.
            rejection = MppCredentialRejectedError("Credential rejected")
            taken_over = await self._notify_payment_error(rejection)
            logger.error(
                "MPP credential rejected: %s",
                _invalid_reason(verification) or "no invalidReason provided",
            )
            return taken_over or await self._send_challenge(
                rejection.message, rejection.code
            )

        # on_after_verify runs OUTSIDE the verify guard above: a bug in the
        # seller's OWN hook, after the credential has already been proven valid,
        # must never be misreported as a payment rejection (no re-challenge) and
        # must never leak the hook's own exception text into a buyer-visible 402.
        if getattr(self.options, "on_after_verify", None):
            try:
                await _maybe_await(
                    self.options.on_after_verify(self.request, verification)
                )
            except Exception as hook_error:  # noqa: BLE001
                await self._notify_payment_error(hook_error)
                logger.error("MPP on_after_verify hook failed: %s", hook_error)
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "Internal Server Error",
                        "message": (
                            "A server-side hook failed after payment verification."
                        ),
                    },
                )

        # The credential is now verified but not yet settled — exactly the window
        # where an idempotent settle makes concurrent delivery cheap: a second
        # request presenting this SAME credential right now would also pass
        # verify (verify_credential burns nothing) and also get served, while the
        # two settles collapse into a single burn. Refuse it instead.
        #
        # Re-checked here rather than trusting the early check because awaits
        # separate the two, and in that gap a concurrent request holding the same
        # credential can complete, mark itself spent AND release its claim.
        if is_credential_spent(credential_id):
            # A 402 with a fresh challenge, not the 409 below: this credential is
            # finished, so a conflict code would tell the buyer to retry the one
            # thing that can never work again.
            return await self._send_challenge(
                "Credential already used. Each credential buys exactly one "
                "response; pay the new challenge.",
                "BCK.MPP.0003",
            )
        if not claim_credential(credential_id):
            conflict = MppCredentialRejectedError(
                "This credential is already being processed by a concurrent request."
            )
            taken_over = await self._notify_payment_error(conflict)
            return taken_over or JSONResponse(
                status_code=409,
                content={"error": "Conflict", "message": conflict.message},
            )

        try:
            return await self._serve_and_settle(call_next, credential, credential_id)
        finally:
            # Released whatever happened — a successful settle, a failed one, a
            # non-2xx handler response that never reaches settlement, or the
            # handler raising — so a credential can never be left claimed forever.
            release_credential(credential_id)

    async def _serve_and_settle(
        self,
        call_next: Callable[[Request], Awaitable[Response]],
        credential: str,
        credential_id: str,
    ) -> Response:
        payment_context = PaymentContext(
            token=credential,
            payment_required=self.payment_required,
            credits_to_settle=self.credits_to_charge,
            verified=True,
            agent_request_id=_agent_request_id(self.verification),
            mpp={
                "credential": credential,
                "resource": self.resource,
                "http_verb": self.http_verb,
            },
        )
        self.request.state.payment_context = payment_context

        # The handler runs here. An exception propagates to Starlette as a 5xx —
        # the buyer is not charged for a failed run, since settlement is skipped
        # on any non-2xx below.
        response = await call_next(self.request)

        if not 200 <= response.status_code < 300:
            return response

        # Marked spent BEFORE the settle: a credential that reached a delivered
        # 2xx has bought its response, and leaving it unspent until the settle
        # resolves would let a concurrent replay slip through the very window the
        # claim above exists to close.
        mark_credential_spent(credential_id)

        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        served = Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

        try:
            settlement = self.payments.mpp.settle_credential(
                RedeemMppParams(
                    credential=credential,
                    resource=self.resource,
                    http_verb=self.http_verb,
                    body_digest=self.body_digest,
                )
            )
        except MppSettlementOutcomeUnknownError as settle_error:
            # Settlement is the one MPP call that burns: this means OUR OWN
            # deadline fired or the connection died after the request was
            # written, not that the backend rejected anything — the credits may
            # already be burned even though this request never heard back.
            # Logging it as a genuine failure would tell an on-call engineer
            # nothing was charged when it may well have been, and skipping
            # on_after_settle would make a real burn vanish from the seller's own
            # accounting.
            logger.warning(
                "MPP settlement outcome unknown (credits may have been burned): %s",
                settle_error,
            )
            await self._run_after_settle_hook(
                self.credits_to_charge,
                MppSettlementOutcomeUnknown(reason=settle_error.message),
            )
            return served
        except Exception as settle_error:  # noqa: BLE001
            # A DEFINITE failure: the resource has been served and the seller has
            # not been paid — the most expensive thing that can happen to them.
            # on_payment_error is documented as the handler for payment failures,
            # so notify through it; this is the one MPP failure site that runs
            # after the response, so the hook cannot answer the request and is
            # purely a signal.
            payment_context.credits_to_settle = 0
            await self._notify_payment_error(settle_error)
            logger.error("MPP settlement failed: %s", settle_error)
            return served

        receipt = settlement.get("paymentReceipt")
        if settlement.get("success") and receipt:
            served.headers[MPP_HEADERS["RECEIPT"]] = receipt
        elif not settlement.get("success"):
            logger.error(
                "MPP settlement failed: %s",
                settlement.get("errorReason", "no errorReason provided"),
            )
        else:
            logger.warning("MPP settlement succeeded but carried no paymentReceipt")

        payment_context.credits_to_settle = _credits_settled(
            settlement, self.credits_to_charge
        )
        await self._run_after_settle_hook(payment_context.credits_to_settle, settlement)
        return served

    async def _run_after_settle_hook(self, credits: int, settlement: Any) -> None:
        """Run ``on_after_settle``, logging rather than propagating a hook bug.

        The settle has already happened either way, and the worst moment to take
        the request down is the branch where credits may have been burned and the
        seller most needs the record.
        """
        hook = getattr(self.options, "on_after_settle", None)
        if not hook:
            return
        try:
            await _maybe_await(hook(self.request, credits, settlement))
        except Exception as hook_error:  # noqa: BLE001
            logger.error("MPP on_after_settle hook failed: %s", hook_error)


def _is_valid(verification: Any) -> bool:
    if isinstance(verification, dict):
        return bool(verification.get("isValid"))
    return bool(getattr(verification, "is_valid", False))


def _invalid_reason(verification: Any) -> Optional[str]:
    if isinstance(verification, dict):
        return verification.get("invalidReason")
    return getattr(verification, "invalid_reason", None)


def _agent_request_id(verification: Any) -> Optional[str]:
    if isinstance(verification, dict):
        return verification.get("agentRequestId")
    return getattr(verification, "agent_request_id", None)


def _credits_settled(settlement: Any, credits_to_charge: int) -> int:
    """What actually burned, reported back on the settlement.

    NOT ``credits_to_charge``, which is recomputed on THIS request and can
    diverge from the minting request when ``credits`` is a function. A FAILED
    settle burned nothing, so it reports 0 rather than falling back to the
    charged amount — a seller writing usage or revenue records off this argument
    would otherwise over-report every failed settlement at the full charge.

    ``creditsRedeemed`` is a decimal string precisely because the amount can
    exceed what the charged ``int`` was; an unusable value is treated as "the
    backend did not report an amount" and logged rather than handed on.
    """
    if not settlement.get("success"):
        return 0
    redeemed = settlement.get("creditsRedeemed")
    if redeemed is None:
        # A successful settle that reported no amount at all. Falling back to the
        # charged amount is the best available answer — but it is a GUESS, free
        # to diverge from what the challenge sealed whenever ``credits`` is a
        # function, so the seller's revenue record must not be told it is a
        # measurement.
        logger.warning(
            "MPP settlement reported no creditsRedeemed; reporting the charged "
            "amount instead"
        )
        return credits_to_charge
    try:
        return int(str(redeemed))
    except (TypeError, ValueError):
        logger.warning(
            "MPP settlement reported an unusable creditsRedeemed (%s); reporting "
            "the charged amount instead",
            redeemed,
        )
        return credits_to_charge


__all__ = ["MppFlow"]
